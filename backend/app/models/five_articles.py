from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class FiveArticlesMappingVersion(Base):
    __tablename__ = "five_articles_mapping_versions"
    __table_args__ = (
        UniqueConstraint(
            "scenario_id",
            "source_hash",
            name="uq_five_articles_mapping_versions_scenario_source_hash",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'invalid')",
            name="ck_five_articles_mapping_versions_status",
        ),
        Index(
            "ix_five_articles_mapping_versions_scenario_status",
            "scenario_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_report: Mapped[dict[str, object]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    rows: Mapped[list["FiveArticlesMappingRow"]] = relationship(
        back_populates="mapping_version",
        cascade="all, delete-orphan",
        order_by="FiveArticlesMappingRow.source_row",
    )


class FiveArticlesMappingRow(Base):
    __tablename__ = "five_articles_mapping_rows"
    __table_args__ = (
        CheckConstraint(
            "code_level IN (2, 3, 4)",
            name="ck_five_articles_mapping_rows_code_level",
        ),
        CheckConstraint(
            "char_length(neic_code) = code_level",
            name="ck_five_articles_mapping_rows_code_length",
        ),
        Index(
            "ix_five_articles_mapping_rows_lookup",
            "mapping_version_id",
            "scenario_id",
            "code_level",
            "neic_code",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    mapping_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("five_articles_mapping_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    neic_code: Mapped[str] = mapped_column(String(4), nullable=False)
    code_level: Mapped[int] = mapped_column(Integer, nullable=False)
    neic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    tier1: Mapped[str] = mapped_column(String(255), nullable=False)
    tier2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier3: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier4: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    mapping_version: Mapped[FiveArticlesMappingVersion] = relationship(
        back_populates="rows"
    )


class FiveArticlesResult(Base):
    __tablename__ = "five_articles_results"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "version",
            name="uq_five_articles_results_case_version",
        ),
        CheckConstraint(
            "status IN ('completed', 'not_applicable', 'needs_review', "
            "'classification_failed')",
            name="ck_five_articles_results_status",
        ),
        CheckConstraint(
            "consistency_status IN ('consistent', 'inconsistent', "
            "'needs_review', 'not_applicable')",
            name="ck_five_articles_results_consistency_status",
        ),
        Index(
            "uq_five_articles_results_case_stage_a_completed",
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
    mapping_version_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("five_articles_mapping_versions.id"),
        nullable=True,
    )
    labels: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    loan_neic_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    loan_neic_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enterprise_neic_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    enterprise_neic_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    consistency_status: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    consistency_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    consistency_evidence_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        default=list,
        server_default=text("'[]'::jsonb"),
        nullable=False,
    )
    model_output: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True
    )
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped["NationalEconomyClassificationCase"] = relationship()
    stage_a_result: Mapped["NationalEconomyClassificationResult"] = relationship()
    mapping_version: Mapped[FiveArticlesMappingVersion | None] = relationship()
