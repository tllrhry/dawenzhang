from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class TechnologyFinanceIpRegistryVersion(Base):
    __tablename__ = "technology_finance_ip_registry_versions"
    __table_args__ = (
        UniqueConstraint("version", name="uq_technology_finance_ip_registry_versions_version"),
        CheckConstraint(
            "status IN ('published')",
            name="ck_technology_finance_ip_registry_versions_status",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    entries: Mapped[list["TechnologyFinanceIpRegistryEntry"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="TechnologyFinanceIpRegistryEntry.source_row",
    )


class TechnologyFinanceIpRegistryEntry(Base):
    __tablename__ = "technology_finance_ip_registry_entries"
    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "enterprise_name",
            name="uq_technology_finance_ip_registry_entries_version_name",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    version_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_finance_ip_registry_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    enterprise_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_row: Mapped[int] = mapped_column(Integer, nullable=False)

    version: Mapped[TechnologyFinanceIpRegistryVersion] = relationship(back_populates="entries")
