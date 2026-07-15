from dataclasses import dataclass
import re
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion
from app.services.technology_finance_mapping_sync import (
    TECHNOLOGY_FINANCE_SCENARIO_ID,
)


MappingLookupStatus = Literal["mapping_hit", "not_applicable", "needs_review"]
MappingMatchMethod = Literal["neic_code", "condition_fallback"]
FOUR_DIGIT_CODE_PATTERN = re.compile(r"^\d{4}$")
MAJOR_CATEGORY_CODE_PATTERN = re.compile(r"^[A-Za-z]?(\d{2})$")
INDUSTRY_CODE_PATTERN = re.compile(r"^[A-Za-z]?(\d{2,4})$")
MIDDLE_CATEGORY_CODE_PATTERN = re.compile(r"^[A-Za-z]?(\d{3})$")


@dataclass(frozen=True)
class FiveArticlesMappingLabel:
    mapping_version_id: int
    scenario_id: str
    neic_code: str
    code_level: int
    neic_name: str
    subject: str
    tier1: str
    tier2: str | None
    tier3: str | None
    tier4: str | None
    source_row: int
    match_method: MappingMatchMethod = "neic_code"

    @property
    def taxonomy_path(self) -> tuple[str, ...]:
        return tuple(
            tier
            for tier in (self.tier1, self.tier2, self.tier3, self.tier4)
            if tier is not None
        )

    @property
    def deduplication_key(self) -> tuple[object, ...]:
        return (
            self.subject,
            self.tier1,
            self.tier2,
            self.tier3,
            self.tier4,
            self.neic_code,
        )


@dataclass(frozen=True)
class FiveArticlesMappingLookupResult:
    status: MappingLookupStatus
    mapping_version_id: int | None
    mapping_version: int | None
    enterprise_labels: tuple[FiveArticlesMappingLabel, ...]
    loan_direction_labels: tuple[FiveArticlesMappingLabel, ...]
    detail: str


def lookup_five_articles_mapping(
    session: Session,
    *,
    enterprise_four_digit_code: str,
    enterprise_major_category_code: str,
    loan_direction_four_digit_code: str,
    loan_direction_major_category_code: str,
    scenario_id: str,
) -> FiveArticlesMappingLookupResult:
    """Compatibility wrapper for the original four-digit lookup contract."""
    return lookup_five_articles_hierarchy_mapping(
        session,
        enterprise_industry_code=enterprise_four_digit_code,
        enterprise_major_category_code=enterprise_major_category_code,
        enterprise_middle_category_code=None,
        loan_direction_industry_code=loan_direction_four_digit_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
        loan_direction_middle_category_code=None,
        scenario_id=scenario_id,
    )


def lookup_five_articles_hierarchy_mapping(
    session: Session,
    *,
    enterprise_industry_code: str,
    enterprise_major_category_code: str,
    enterprise_middle_category_code: str | None,
    loan_direction_industry_code: str,
    loan_direction_major_category_code: str,
    loan_direction_middle_category_code: str | None,
    scenario_id: str,
) -> FiveArticlesMappingLookupResult:
    """Look up one scenario's labels at the highest mapped Stage A granularity."""
    versions = tuple(
        session.scalars(
            select(FiveArticlesMappingVersion)
            .where(
                FiveArticlesMappingVersion.scenario_id == scenario_id,
                FiveArticlesMappingVersion.status == "published",
            )
            .order_by(
                FiveArticlesMappingVersion.version.desc(),
                FiveArticlesMappingVersion.created_at.desc(),
                FiveArticlesMappingVersion.id.desc(),
            )
            .limit(2)
        ).all()
    )
    if not versions:
        return _review_result(detail="published_mapping_version_not_found")

    version = versions[0]
    if len(versions) > 1 and versions[1].version == version.version:
        return _review_result(
            version=version,
            detail=f"duplicate_published_mapping_version:{version.version}",
        )

    version_issue = _validate_published_version(session, version, scenario_id)
    if version_issue is not None:
        return _review_result(version=version, detail=version_issue)

    normalized_codes = _normalize_lookup_codes(
        enterprise_industry_code=enterprise_industry_code,
        enterprise_major_category_code=enterprise_major_category_code,
        enterprise_middle_category_code=enterprise_middle_category_code,
        loan_direction_industry_code=loan_direction_industry_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
        loan_direction_middle_category_code=loan_direction_middle_category_code,
    )
    if isinstance(normalized_codes, str):
        return _review_result(version=version, detail=normalized_codes)

    enterprise_rows = _query_preferred_rows(
        session,
        version_id=version.id,
        scenario_id=scenario_id,
        codes=normalized_codes[0],
    )
    loan_direction_rows = _query_preferred_rows(
        session,
        version_id=version.id,
        scenario_id=scenario_id,
        codes=normalized_codes[1],
    )

    enterprise_issue = _validate_query_rows(enterprise_rows)
    loan_direction_issue = _validate_query_rows(loan_direction_rows)
    if enterprise_issue is not None or loan_direction_issue is not None:
        issue = enterprise_issue or loan_direction_issue
        return _review_result(version=version, detail=issue or "mapping_query_conflict")

    enterprise_labels = tuple(_row_to_label(row) for row in enterprise_rows)
    loan_direction_labels = tuple(_row_to_label(row) for row in loan_direction_rows)
    if not loan_direction_labels:
        return FiveArticlesMappingLookupResult(
            status="not_applicable",
            mapping_version_id=version.id,
            mapping_version=version.version,
            enterprise_labels=enterprise_labels,
            loan_direction_labels=(),
            detail="loan_direction_has_no_explicit_mapping",
        )

    return FiveArticlesMappingLookupResult(
        status="mapping_hit",
        mapping_version_id=version.id,
        mapping_version=version.version,
        enterprise_labels=enterprise_labels,
        loan_direction_labels=loan_direction_labels,
        detail="loan_direction_mapping_hit",
    )


def _review_result(
    *,
    detail: str,
    version: FiveArticlesMappingVersion | None = None,
) -> FiveArticlesMappingLookupResult:
    return FiveArticlesMappingLookupResult(
        status="needs_review",
        mapping_version_id=version.id if version is not None else None,
        mapping_version=version.version if version is not None else None,
        enterprise_labels=(),
        loan_direction_labels=(),
        detail=detail,
    )


def _validate_published_version(
    session: Session,
    version: FiveArticlesMappingVersion,
    scenario_id: str,
) -> str | None:
    report = version.validation_report
    if not isinstance(report, dict) or report.get("valid") is not True:
        return "published_mapping_validation_report_invalid"
    if report.get("scenario_id") != scenario_id:
        return "published_mapping_scenario_conflict"
    if report.get("errors") != []:
        return "published_mapping_code_name_conflict"

    actual_row_count = session.scalar(
        select(func.count(FiveArticlesMappingRow.id)).where(
            FiveArticlesMappingRow.mapping_version_id == version.id
        )
    )
    scenario_row_count = session.scalar(
        select(func.count(FiveArticlesMappingRow.id)).where(
            FiveArticlesMappingRow.mapping_version_id == version.id,
            FiveArticlesMappingRow.scenario_id == scenario_id,
        )
    )
    expected_row_count = report.get("published_row_count")
    if (
        type(expected_row_count) is not int
        or expected_row_count <= 0
        or actual_row_count != expected_row_count
        or scenario_row_count != actual_row_count
    ):
        return "published_mapping_row_count_conflict"
    return None


def _normalize_lookup_codes(
    *,
    enterprise_industry_code: str,
    enterprise_major_category_code: str,
    enterprise_middle_category_code: str | None,
    loan_direction_industry_code: str,
    loan_direction_major_category_code: str,
    loan_direction_middle_category_code: str | None,
) -> tuple[tuple[tuple[int, str], ...], tuple[tuple[int, str], ...]] | str:
    enterprise_codes = _normalize_side_codes(
        side="enterprise",
        industry_code=enterprise_industry_code,
        major_category_code=enterprise_major_category_code,
        middle_category_code=enterprise_middle_category_code,
    )
    if isinstance(enterprise_codes, str):
        return enterprise_codes
    loan_direction_codes = _normalize_side_codes(
        side="loan_direction",
        industry_code=loan_direction_industry_code,
        major_category_code=loan_direction_major_category_code,
        middle_category_code=loan_direction_middle_category_code,
    )
    if isinstance(loan_direction_codes, str):
        return loan_direction_codes
    return enterprise_codes, loan_direction_codes


def _normalize_side_codes(
    *,
    side: str,
    industry_code: str,
    major_category_code: str,
    middle_category_code: str | None,
) -> tuple[tuple[int, str], ...] | str:
    industry_match = INDUSTRY_CODE_PATTERN.fullmatch(str(industry_code).strip())
    if industry_match is None:
        return f"invalid_stage_a_code:{side}_industry_code"
    major_match = MAJOR_CATEGORY_CODE_PATTERN.fullmatch(str(major_category_code).strip())
    if major_match is None:
        return f"invalid_stage_a_code:{side}_major_category_code"

    actual_code = industry_match.group(1)
    major_code = major_match.group(1)
    if len(actual_code) == 2:
        return ((2, actual_code),)
    if len(actual_code) == 3:
        return ((3, actual_code), (2, major_code))

    if middle_category_code is None:
        return ((4, actual_code), (2, major_code))
    middle_match = MIDDLE_CATEGORY_CODE_PATTERN.fullmatch(
        str(middle_category_code).strip()
    )
    if middle_match is None:
        return f"invalid_stage_a_code:{side}_middle_category_code"
    return ((4, actual_code), (3, middle_match.group(1)), (2, major_code))


def _query_preferred_rows(
    session: Session,
    *,
    version_id: int,
    scenario_id: str,
    codes: tuple[tuple[int, str], ...],
) -> tuple[FiveArticlesMappingRow, ...]:
    for code_level, code in codes:
        rows = tuple(
            session.scalars(
                select(FiveArticlesMappingRow)
                .where(
                    FiveArticlesMappingRow.mapping_version_id == version_id,
                    FiveArticlesMappingRow.scenario_id == scenario_id,
                    FiveArticlesMappingRow.code_level == code_level,
                    FiveArticlesMappingRow.neic_code == code,
                )
                .order_by(FiveArticlesMappingRow.source_row, FiveArticlesMappingRow.id)
            ).all()
        )
        if rows:
            return rows
    return ()


def _validate_query_rows(rows: tuple[FiveArticlesMappingRow, ...]) -> str | None:
    deduplication_keys: set[tuple[object, ...]] = set()
    code_names: dict[tuple[int, str], str] = {}
    source_rows: set[int] = set()
    for row in rows:
        label = _row_to_label(row)
        row_issue = _row_integrity_issue(label)
        if row_issue is not None:
            return row_issue
        if label.deduplication_key in deduplication_keys:
            return "mapping_query_duplicate_taxonomy_code"
        deduplication_keys.add(label.deduplication_key)

        code_key = (label.code_level, label.neic_code)
        existing_name = code_names.setdefault(code_key, label.neic_name)
        if existing_name != label.neic_name:
            return "mapping_query_code_name_conflict"
        if label.source_row in source_rows:
            return "mapping_query_duplicate_source_row"
        source_rows.add(label.source_row)
    return None


def _row_integrity_issue(label: FiveArticlesMappingLabel) -> str | None:
    if (
        not label.neic_name.strip()
        or not label.subject.strip()
        or not label.tier1.strip()
        or label.source_row < 2
    ):
        return "mapping_query_incomplete_row"
    optional_tiers = (label.tier2, label.tier3, label.tier4)
    found_empty_tier = False
    for tier in optional_tiers:
        if tier is None:
            found_empty_tier = True
        elif not tier.strip() or found_empty_tier:
            return "mapping_query_incomplete_taxonomy_path"
    return None


def _prefer_most_specific_labels(
    rows: tuple[FiveArticlesMappingRow, ...],
) -> tuple[FiveArticlesMappingLabel, ...]:
    labels = tuple(_row_to_label(row) for row in rows)
    four_digit_by_subject: dict[str, tuple[FiveArticlesMappingLabel, ...]] = {}
    for label in labels:
        if label.code_level != 4:
            continue
        four_digit_by_subject[label.subject] = (
            *four_digit_by_subject.get(label.subject, ()),
            label,
        )

    filtered = [
        label
        for label in labels
        if not (
            label.code_level == 2
            and any(
                _is_path_prefix(label.taxonomy_path, specific.taxonomy_path)
                for specific in four_digit_by_subject.get(label.subject, ())
            )
        )
    ]
    return tuple(
        sorted(
            filtered,
            key=lambda label: (
                label.subject,
                label.tier1,
                label.tier2 or "",
                label.tier3 or "",
                label.tier4 or "",
                -label.code_level,
                label.neic_code,
                label.source_row,
            ),
        )
    )


def _is_path_prefix(prefix: tuple[str, ...], path: tuple[str, ...]) -> bool:
    return len(prefix) <= len(path) and path[: len(prefix)] == prefix


def _row_to_label(row: FiveArticlesMappingRow) -> FiveArticlesMappingLabel:
    return FiveArticlesMappingLabel(
        mapping_version_id=row.mapping_version_id,
        scenario_id=row.scenario_id,
        neic_code=row.neic_code,
        code_level=row.code_level,
        neic_name=row.neic_name,
        subject=row.subject,
        tier1=row.tier1,
        tier2=row.tier2,
        tier3=row.tier3,
        tier4=row.tier4,
        source_row=row.source_row,
    )


# Compatibility aliases keep the completed technology-finance workflow import-stable
# while new callers use the scenario-generic names above.
TechnologyFinanceMappingLabel = FiveArticlesMappingLabel
TechnologyFinanceMappingLookupResult = FiveArticlesMappingLookupResult


def lookup_technology_finance_mapping(
    session: Session,
    *,
    enterprise_four_digit_code: str,
    enterprise_major_category_code: str,
    loan_direction_four_digit_code: str,
    loan_direction_major_category_code: str,
    scenario_id: str = TECHNOLOGY_FINANCE_SCENARIO_ID,
) -> FiveArticlesMappingLookupResult:
    return lookup_five_articles_mapping(
        session,
        enterprise_four_digit_code=enterprise_four_digit_code,
        enterprise_major_category_code=enterprise_major_category_code,
        loan_direction_four_digit_code=loan_direction_four_digit_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
        scenario_id=scenario_id,
    )
