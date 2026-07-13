from dataclasses import dataclass
import re
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion
from app.services.technology_finance_mapping_sync import (
    TECHNOLOGY_FINANCE_SCENARIO_ID,
)


MappingLookupStatus = Literal["mapping_hit", "not_applicable", "needs_review"]
FOUR_DIGIT_CODE_PATTERN = re.compile(r"^\d{4}$")
MAJOR_CATEGORY_CODE_PATTERN = re.compile(r"^[A-Za-z]?(\d{2})$")


@dataclass(frozen=True)
class TechnologyFinanceMappingLabel:
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
class TechnologyFinanceMappingLookupResult:
    status: MappingLookupStatus
    mapping_version_id: int | None
    mapping_version: int | None
    enterprise_labels: tuple[TechnologyFinanceMappingLabel, ...]
    loan_direction_labels: tuple[TechnologyFinanceMappingLabel, ...]
    detail: str


def lookup_technology_finance_mapping(
    session: Session,
    *,
    enterprise_four_digit_code: str,
    enterprise_major_category_code: str,
    loan_direction_four_digit_code: str,
    loan_direction_major_category_code: str,
    scenario_id: str = TECHNOLOGY_FINANCE_SCENARIO_ID,
) -> TechnologyFinanceMappingLookupResult:
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
        enterprise_four_digit_code=enterprise_four_digit_code,
        enterprise_major_category_code=enterprise_major_category_code,
        loan_direction_four_digit_code=loan_direction_four_digit_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
    )
    if isinstance(normalized_codes, str):
        return _review_result(version=version, detail=normalized_codes)

    enterprise_rows = _query_explicit_rows(
        session,
        version_id=version.id,
        scenario_id=scenario_id,
        four_digit_code=normalized_codes[0],
        two_digit_code=normalized_codes[1],
    )
    loan_direction_rows = _query_explicit_rows(
        session,
        version_id=version.id,
        scenario_id=scenario_id,
        four_digit_code=normalized_codes[2],
        two_digit_code=normalized_codes[3],
    )

    enterprise_issue = _validate_query_rows(enterprise_rows)
    loan_direction_issue = _validate_query_rows(loan_direction_rows)
    if enterprise_issue is not None or loan_direction_issue is not None:
        issue = enterprise_issue or loan_direction_issue
        return _review_result(version=version, detail=issue or "mapping_query_conflict")

    enterprise_labels = _prefer_most_specific_labels(enterprise_rows)
    loan_direction_labels = _prefer_most_specific_labels(loan_direction_rows)
    if not loan_direction_labels:
        return TechnologyFinanceMappingLookupResult(
            status="not_applicable",
            mapping_version_id=version.id,
            mapping_version=version.version,
            enterprise_labels=enterprise_labels,
            loan_direction_labels=(),
            detail="loan_direction_has_no_explicit_mapping",
        )

    return TechnologyFinanceMappingLookupResult(
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
) -> TechnologyFinanceMappingLookupResult:
    return TechnologyFinanceMappingLookupResult(
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
    enterprise_four_digit_code: str,
    enterprise_major_category_code: str,
    loan_direction_four_digit_code: str,
    loan_direction_major_category_code: str,
) -> tuple[str, str, str, str] | str:
    values = (
        ("enterprise_four_digit_code", enterprise_four_digit_code, "four"),
        ("enterprise_major_category_code", enterprise_major_category_code, "major"),
        ("loan_direction_four_digit_code", loan_direction_four_digit_code, "four"),
        (
            "loan_direction_major_category_code",
            loan_direction_major_category_code,
            "major",
        ),
    )
    normalized: list[str] = []
    for field, raw_value, code_type in values:
        value = str(raw_value).strip()
        if code_type == "four":
            if FOUR_DIGIT_CODE_PATTERN.fullmatch(value) is None:
                return f"invalid_stage_a_code:{field}"
            normalized.append(value)
            continue
        match = MAJOR_CATEGORY_CODE_PATTERN.fullmatch(value)
        if match is None:
            return f"invalid_stage_a_code:{field}"
        normalized.append(match.group(1))
    return normalized[0], normalized[1], normalized[2], normalized[3]


def _query_explicit_rows(
    session: Session,
    *,
    version_id: int,
    scenario_id: str,
    four_digit_code: str,
    two_digit_code: str,
) -> tuple[FiveArticlesMappingRow, ...]:
    return tuple(
        session.scalars(
            select(FiveArticlesMappingRow)
            .where(
                FiveArticlesMappingRow.mapping_version_id == version_id,
                FiveArticlesMappingRow.scenario_id == scenario_id,
                or_(
                    and_(
                        FiveArticlesMappingRow.code_level == 4,
                        FiveArticlesMappingRow.neic_code == four_digit_code,
                    ),
                    and_(
                        FiveArticlesMappingRow.code_level == 2,
                        FiveArticlesMappingRow.neic_code == two_digit_code,
                    ),
                ),
            )
            .order_by(FiveArticlesMappingRow.source_row, FiveArticlesMappingRow.id)
        ).all()
    )


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


def _row_integrity_issue(label: TechnologyFinanceMappingLabel) -> str | None:
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
) -> tuple[TechnologyFinanceMappingLabel, ...]:
    labels = tuple(_row_to_label(row) for row in rows)
    four_digit_by_subject: dict[str, tuple[TechnologyFinanceMappingLabel, ...]] = {}
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


def _row_to_label(row: FiveArticlesMappingRow) -> TechnologyFinanceMappingLabel:
    return TechnologyFinanceMappingLabel(
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
