from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AgricultureRelatedResult(Base):
    __tablename__ = "agriculture_related_results"
    __table_args__ = (
        UniqueConstraint("case_id", "version", name="uq_agriculture_related_results_case_version"),
        CheckConstraint(
            "status IN ('completed', 'not_applicable', 'needs_review', 'classification_failed')",
            name="ck_agriculture_related_results_status",
        ),
        Index(
            "uq_agriculture_related_results_case_stage_a_completed",
            "case_id",
            "stage_a_result_id",
            unique=True,
            postgresql_where=text("status = 'completed'"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("national_economy_classification_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    stage_a_result_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("national_economy_classification_results.id", ondelete="CASCADE"),
        nullable=False,
    )
    is_agriculture_related: Mapped[bool | None] = mapped_column(Boolean)
    matched_categories: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    basis: Mapped[str | None] = mapped_column(Text)
    evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb"), nullable=False
    )
    model_output: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    error_detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped["NationalEconomyClassificationCase"] = relationship()
    stage_a_result: Mapped["NationalEconomyClassificationResult"] = relationship()
