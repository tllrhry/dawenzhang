from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import get_settings
from app.models.base import Base


settings = get_settings()


class NationalEconomyCatalogVersion(Base):
    __tablename__ = "national_economy_catalog_versions"
    __table_args__ = (
        UniqueConstraint(
            "source_hash",
            "embedding_model",
            "embedding_dimension",
            name="uq_national_economy_catalog_version_identity",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    chunks: Mapped[list["NationalEconomyIndustryChunk"]] = relationship(
        back_populates="catalog_version", cascade="all, delete-orphan"
    )


class NationalEconomyIndustryChunk(Base):
    __tablename__ = "national_economy_industry_chunks"
    __table_args__ = (
        UniqueConstraint(
            "catalog_version_id",
            "industry_code",
            "source_row",
            "chunk_type",
            "text",
            name="uq_national_economy_industry_chunk_source",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    catalog_version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("national_economy_catalog_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    industry_code: Mapped[str] = mapped_column(String(4), nullable=False, index=True)
    industry_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_type: Mapped[str] = mapped_column(String(32), nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        Vector(settings.embedding_dimension), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    catalog_version: Mapped[NationalEconomyCatalogVersion] = relationship(
        back_populates="chunks"
    )


class NationalEconomyClassificationCase(Base):
    __tablename__ = "national_economy_classification_cases"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    scenario: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    result_versions: Mapped[list["NationalEconomyClassificationResult"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="NationalEconomyClassificationResult.version",
    )


class NationalEconomyClassificationResult(Base):
    __tablename__ = "national_economy_classification_results"
    __table_args__ = (
        UniqueConstraint(
            "case_id",
            "version",
            name="uq_national_economy_classification_result_case_version",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    case_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("national_economy_classification_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    industry_code: Mapped[str | None] = mapped_column(String(4), nullable=True)
    industry_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidate_snapshot: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB, nullable=False
    )
    objection: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    model_output: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    case: Mapped[NationalEconomyClassificationCase] = relationship(
        back_populates="result_versions"
    )
