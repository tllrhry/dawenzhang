"""Maintenance operations for the published green-finance condition index."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion
from app.services.national_economy_catalog_chunks import embed_texts
from app.services.scenario_registry import GREEN_FINANCE_SCENARIO


@dataclass(frozen=True)
class GreenFinanceConditionIndexReport:
    mapping_version_id: int
    mapping_version: int
    total_rows: int
    criteria_rows: int
    embedding_rows: int

    @property
    def complete(self) -> bool:
        return (
            self.total_rows > 0
            and self.criteria_rows == self.total_rows
            and self.embedding_rows == self.total_rows
        )


def latest_green_finance_mapping_version(
    session: Session,
) -> FiveArticlesMappingVersion:
    version = session.scalar(
        select(FiveArticlesMappingVersion)
        .where(
            FiveArticlesMappingVersion.scenario_id == GREEN_FINANCE_SCENARIO,
            FiveArticlesMappingVersion.status == "published",
        )
        .order_by(
            FiveArticlesMappingVersion.version.desc(),
            FiveArticlesMappingVersion.created_at.desc(),
            FiveArticlesMappingVersion.id.desc(),
        )
        .limit(1)
    )
    if version is None:
        raise RuntimeError("published green-finance mapping version not found")
    return version


def inspect_green_finance_condition_index(
    session: Session,
    *,
    mapping_version: FiveArticlesMappingVersion | None = None,
) -> GreenFinanceConditionIndexReport:
    version = mapping_version or latest_green_finance_mapping_version(session)
    total_rows, criteria_rows, embedding_rows = session.execute(
        select(
            func.count(FiveArticlesMappingRow.id),
            func.count(FiveArticlesMappingRow.condition_criteria),
            func.count(FiveArticlesMappingRow.condition_embedding),
        ).where(
            FiveArticlesMappingRow.mapping_version_id == version.id,
            FiveArticlesMappingRow.scenario_id == GREEN_FINANCE_SCENARIO,
        )
    ).one()
    return GreenFinanceConditionIndexReport(
        mapping_version_id=version.id,
        mapping_version=version.version,
        total_rows=int(total_rows),
        criteria_rows=int(criteria_rows),
        embedding_rows=int(embedding_rows),
    )


def rebuild_green_finance_condition_embeddings(
    session: Session,
    settings: Settings,
) -> GreenFinanceConditionIndexReport:
    """Atomically overwrite every vector in the latest published mapping."""
    version = latest_green_finance_mapping_version(session)
    rows = tuple(
        session.scalars(
            select(FiveArticlesMappingRow)
            .where(
                FiveArticlesMappingRow.mapping_version_id == version.id,
                FiveArticlesMappingRow.scenario_id == GREEN_FINANCE_SCENARIO,
            )
            .order_by(FiveArticlesMappingRow.source_row, FiveArticlesMappingRow.id)
        ).all()
    )
    if not rows:
        raise RuntimeError("latest green-finance mapping contains no rows")
    criteria = tuple((row.condition_criteria or "").strip() for row in rows)
    missing_rows = [row.source_row for row, text in zip(rows, criteria) if not text]
    if missing_rows:
        raise RuntimeError(
            "green-finance mapping contains empty condition criteria at source rows: "
            + ",".join(str(row) for row in missing_rows[:20])
        )

    # Generate the full replacement before mutating ORM rows. A cloud failure
    # leaves the currently published index untouched.
    embeddings = tuple(embed_texts(criteria, settings))
    if len(embeddings) != len(rows):
        raise RuntimeError("condition embedding response count does not match mapping rows")
    for row, embedding in zip(rows, embeddings):
        row.condition_embedding = list(embedding)

    report = dict(version.validation_report)
    report.update(
        {
            "condition_embedding_model": settings.siliconflow_embedding_model,
            "condition_embedding_dimension": settings.embedding_dimension,
            "condition_embedding_row_count": len(rows),
        }
    )
    version.validation_report = report
    session.flush()
    return inspect_green_finance_condition_index(session, mapping_version=version)
