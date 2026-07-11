from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
