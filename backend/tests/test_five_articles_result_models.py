from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from app.db.session import get_engine, get_sessionmaker
from app.models import (
    FiveArticlesMappingVersion,
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)


ROOT_DIR = Path(__file__).resolve().parents[2]


def _case_and_stage_a(
    scenario_id: str,
) -> tuple[NationalEconomyClassificationCase, NationalEconomyClassificationResult]:
    case = NationalEconomyClassificationCase(
        scenario=scenario_id,
        input_payload={"enterprise_name": "五篇结果模型测试企业"},
        original_filename="technology-finance.docx",
        status="completed",
    )
    stage_a = NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        industry_code="2710",
        industry_name="化学药品原料药制造",
        loan_industry_code="2720",
        loan_industry_name="化学药品制剂制造",
        candidate_snapshot=[],
        model_output={"stage": "a"},
    )
    return case, stage_a


def _mapping_version(scenario_id: str) -> FiveArticlesMappingVersion:
    return FiveArticlesMappingVersion(
        scenario_id=scenario_id,
        version=1,
        source_hash=uuid4().hex * 2,
        status="published",
        validation_report={"valid": True},
    )


def _result(
    *,
    case_id: int,
    stage_a_result_id: int,
    scenario_id: str,
    version: int,
    status: str,
    mapping_version_id: int | None,
    consistency_status: str | None,
) -> FiveArticlesResult:
    labels = []
    if status == "completed":
        labels = [
            {
                "taxonomy": {
                    "subject": "高技术产业（制造业）",
                    "tier1": "医药制造业",
                    "tier2": "化学药品制造",
                    "tier3": None,
                    "tier4": None,
                },
                "code": "2720",
                "name": "化学药品制剂制造",
                "source_row": 12,
                "matching_basis": "贷款投向命中科技金融映射。",
                "evidence_refs": [
                    {"type": "mapping", "source_row": 12},
                    {
                        "type": "business",
                        "field_key": "loan_purpose",
                        "excerpt": "用于化学药品制剂项目建设",
                    },
                ],
            }
        ]

    return FiveArticlesResult(
        case_id=case_id,
        scenario_id=scenario_id,
        version=version,
        status=status,
        stage_a_result_id=stage_a_result_id,
        mapping_version_id=mapping_version_id,
        labels=labels,
        loan_neic_code="2720",
        loan_neic_name="化学药品制剂制造",
        enterprise_neic_code="2710",
        enterprise_neic_name="化学药品原料药制造",
        consistency_status=consistency_status,
        consistency_basis=(
            "模型服务失败，未形成一致性结论。"
            if consistency_status is None
            else "贷款用途与企业科技活动的关系已按证据判断。"
        ),
        consistency_evidence_refs=(
            []
            if consistency_status is None
            else [{"field_key": "loan_purpose", "excerpt": "用于项目建设"}]
        ),
        model_output={"status": status} if status == "completed" else None,
        error_detail=(
            "DeepSeek request timed out"
            if status == "classification_failed"
            else None
        ),
    )


def _cleanup(
    session: object,
    case_id: int | None,
    mapping_version_id: int | None,
) -> None:
    session.rollback()
    if case_id is not None:
        persisted_case = session.get(NationalEconomyClassificationCase, case_id)
        if persisted_case is not None:
            session.delete(persisted_case)
            session.commit()
    if mapping_version_id is not None:
        persisted_mapping = session.get(
            FiveArticlesMappingVersion, mapping_version_id
        )
        if persisted_mapping is not None:
            session.delete(persisted_mapping)
            session.commit()
    session.close()


def test_result_model_metadata_contains_design_fields_constraints_and_fks() -> None:
    columns = FiveArticlesResult.__table__.columns
    assert {
        "id",
        "case_id",
        "scenario_id",
        "version",
        "status",
        "stage_a_result_id",
        "mapping_version_id",
        "labels",
        "loan_neic_code",
        "loan_neic_name",
        "enterprise_neic_code",
        "enterprise_neic_name",
        "consistency_status",
        "consistency_basis",
        "consistency_evidence_refs",
        "model_output",
        "error_detail",
        "created_at",
    } == set(columns.keys())
    for column_name in ("labels", "consistency_evidence_refs", "model_output"):
        assert isinstance(columns[column_name].type, JSONB)
    assert columns["mapping_version_id"].nullable

    foreign_keys = {
        column_name: next(iter(columns[column_name].foreign_keys))
        for column_name in ("case_id", "stage_a_result_id", "mapping_version_id")
    }
    assert foreign_keys["case_id"].target_fullname == (
        "national_economy_classification_cases.id"
    )
    assert foreign_keys["stage_a_result_id"].target_fullname == (
        "national_economy_classification_results.id"
    )
    assert foreign_keys["mapping_version_id"].target_fullname == (
        "five_articles_mapping_versions.id"
    )

    constraint_names = {
        constraint.name for constraint in FiveArticlesResult.__table__.constraints
    }
    assert "uq_five_articles_results_case_version" in constraint_names
    assert "ck_five_articles_results_status" in constraint_names
    assert "ck_five_articles_results_consistency_status" in constraint_names
    completed_index = next(
        index
        for index in FiveArticlesResult.__table__.indexes
        if index.name == "uq_five_articles_results_case_stage_a_completed"
    )
    assert completed_index.unique
    assert str(completed_index.dialect_options["postgresql"]["where"]) == (
        "status = 'completed'"
    )


def test_migration_creates_result_table_constraints_indexes_and_fks() -> None:
    inspector = inspect(get_engine())
    assert "five_articles_results" in inspector.get_table_names()

    columns = {
        column["name"]: column
        for column in inspector.get_columns("five_articles_results")
    }
    assert str(columns["labels"]["type"]) == "JSONB"
    assert str(columns["consistency_evidence_refs"]["type"]) == "JSONB"
    assert str(columns["model_output"]["type"]) == "JSONB"
    assert columns["mapping_version_id"]["nullable"]

    unique_constraints = inspector.get_unique_constraints("five_articles_results")
    assert any(
        constraint["name"] == "uq_five_articles_results_case_version"
        and constraint["column_names"] == ["case_id", "version"]
        for constraint in unique_constraints
    )
    check_names = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("five_articles_results")
    }
    assert "ck_five_articles_results_status" in check_names
    assert "ck_five_articles_results_consistency_status" in check_names

    completed_index = next(
        index
        for index in inspector.get_indexes("five_articles_results")
        if index["name"] == "uq_five_articles_results_case_stage_a_completed"
    )
    assert completed_index["unique"]
    assert completed_index["column_names"] == ["case_id", "stage_a_result_id"]
    assert "completed" in str(
        completed_index.get("dialect_options", {}).get("postgresql_where", "")
    )

    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys("five_articles_results")
    }
    assert foreign_keys[("case_id",)]["referred_table"] == (
        "national_economy_classification_cases"
    )
    assert foreign_keys[("stage_a_result_id",)]["referred_table"] == (
        "national_economy_classification_results"
    )
    assert foreign_keys[("mapping_version_id",)]["referred_table"] == (
        "five_articles_mapping_versions"
    )


def test_result_statuses_round_trip_and_later_failure_preserves_history() -> None:
    session = get_sessionmaker()()
    scenario_id = f"technology_finance_{uuid4().hex}"
    case, stage_a = _case_and_stage_a(scenario_id)
    mapping_version = _mapping_version(scenario_id)
    case_id: int | None = None
    mapping_version_id: int | None = None

    try:
        session.add_all([case, mapping_version])
        session.commit()
        case_id = case.id
        mapping_version_id = mapping_version.id

        results = [
            _result(
                case_id=case.id,
                stage_a_result_id=stage_a.id,
                scenario_id=scenario_id,
                version=1,
                status="completed",
                mapping_version_id=mapping_version.id,
                consistency_status="consistent",
            ),
            _result(
                case_id=case.id,
                stage_a_result_id=stage_a.id,
                scenario_id=scenario_id,
                version=2,
                status="not_applicable",
                mapping_version_id=mapping_version.id,
                consistency_status="not_applicable",
            ),
            _result(
                case_id=case.id,
                stage_a_result_id=stage_a.id,
                scenario_id=scenario_id,
                version=3,
                status="needs_review",
                mapping_version_id=None,
                consistency_status="needs_review",
            ),
            _result(
                case_id=case.id,
                stage_a_result_id=stage_a.id,
                scenario_id=scenario_id,
                version=4,
                status="classification_failed",
                mapping_version_id=mapping_version.id,
                consistency_status=None,
            ),
        ]
        session.add_all(results)
        session.commit()
        session.expire_all()

        loaded = (
            session.query(FiveArticlesResult)
            .filter(FiveArticlesResult.case_id == case.id)
            .order_by(FiveArticlesResult.version)
            .all()
        )
        assert [result.status for result in loaded] == [
            "completed",
            "not_applicable",
            "needs_review",
            "classification_failed",
        ]
        assert loaded[0].labels[0]["source_row"] == 12
        assert loaded[1].labels == []
        assert loaded[2].mapping_version_id is None
        assert loaded[3].error_detail == "DeepSeek request timed out"
        assert loaded[0].stage_a_result_id == loaded[3].stage_a_result_id
    finally:
        _cleanup(session, case_id, mapping_version_id)


def test_database_enforces_status_version_and_completed_stage_a_idempotency() -> None:
    session = get_sessionmaker()()
    scenario_id = f"technology_finance_{uuid4().hex}"
    case, stage_a = _case_and_stage_a(scenario_id)
    mapping_version = _mapping_version(scenario_id)
    case_id: int | None = None
    mapping_version_id: int | None = None

    try:
        session.add_all([case, mapping_version])
        session.commit()
        case_id = case.id
        mapping_version_id = mapping_version.id

        completed = _result(
            case_id=case.id,
            stage_a_result_id=stage_a.id,
            scenario_id=scenario_id,
            version=1,
            status="completed",
            mapping_version_id=mapping_version.id,
            consistency_status="consistent",
        )
        session.add(completed)
        session.commit()

        session.add(
            _result(
                case_id=case.id,
                stage_a_result_id=stage_a.id,
                scenario_id=scenario_id,
                version=2,
                status="completed",
                mapping_version_id=mapping_version.id,
                consistency_status="consistent",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        failed_retry = _result(
            case_id=case.id,
            stage_a_result_id=stage_a.id,
            scenario_id=scenario_id,
            version=2,
            status="classification_failed",
            mapping_version_id=mapping_version.id,
            consistency_status=None,
        )
        session.add(failed_retry)
        session.commit()

        session.add(
            _result(
                case_id=case.id,
                stage_a_result_id=stage_a.id,
                scenario_id=scenario_id,
                version=2,
                status="not_applicable",
                mapping_version_id=mapping_version.id,
                consistency_status="not_applicable",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        invalid_status = _result(
            case_id=case.id,
            stage_a_result_id=stage_a.id,
            scenario_id=scenario_id,
            version=3,
            status="failed",
            mapping_version_id=mapping_version.id,
            consistency_status=None,
        )
        session.add(invalid_status)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        invalid_consistency = _result(
            case_id=case.id,
            stage_a_result_id=stage_a.id,
            scenario_id=scenario_id,
            version=3,
            status="needs_review",
            mapping_version_id=mapping_version.id,
            consistency_status="unknown",
        )
        session.add(invalid_consistency)
        with pytest.raises(IntegrityError):
            session.commit()
    finally:
        _cleanup(session, case_id, mapping_version_id)


def test_result_migration_downgrade_and_upgrade_round_trip() -> None:
    config = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
    try:
        command.downgrade(config, "0007_five_articles_mapping")
        assert "five_articles_results" not in inspect(get_engine()).get_table_names()
    finally:
        command.upgrade(config, "head")

    assert "five_articles_results" in inspect(get_engine()).get_table_names()
