from types import SimpleNamespace
from unittest.mock import Mock

from app.core.config import Settings
from app.services import green_finance_batch_reclassification as batch_module
from app.services import green_finance_mapping_maintenance as maintenance_module
from app.services.green_finance_batch_reclassification import (
    GreenFinanceReclassificationCandidate,
    reclassify_stale_green_finance_cases,
)
from app.services.green_finance_mapping_maintenance import (
    rebuild_green_finance_condition_embeddings,
)


def test_embedding_rebuild_replaces_every_vector_before_flush(monkeypatch) -> None:
    session = Mock()
    version = SimpleNamespace(id=72, version=3, validation_report={})
    rows = [
        SimpleNamespace(source_row=2, condition_criteria="节能改造", condition_embedding=None),
        SimpleNamespace(source_row=3, condition_criteria="污染治理", condition_embedding=None),
    ]
    session.scalar.return_value = version
    session.scalars.return_value.all.return_value = rows
    session.execute.return_value.one.return_value = (2, 2, 2)
    monkeypatch.setattr(
        maintenance_module,
        "embed_texts",
        lambda texts, settings: ((0.1, 0.2), (0.3, 0.4)),
    )

    report = rebuild_green_finance_condition_embeddings(
        session,
        Settings(
            _env_file=None,
            siliconflow_embedding_model="embedding-test",
            embedding_dimension=2,
        ),
    )

    assert rows[0].condition_embedding == [0.1, 0.2]
    assert rows[1].condition_embedding == [0.3, 0.4]
    assert version.validation_report["condition_embedding_row_count"] == 2
    assert report.complete
    session.flush.assert_called_once()


def test_batch_reclassification_summarizes_each_case_and_supports_resume(
    monkeypatch,
) -> None:
    candidates = tuple(
        GreenFinanceReclassificationCandidate(
            case=SimpleNamespace(id=case_id),
            stage_a_result=SimpleNamespace(id=case_id + 100),
        )
        for case_id in (10, 20, 30, 40)
    )
    statuses = iter(("completed", "not_applicable", "needs_review", "classification_failed"))
    monkeypatch.setattr(
        batch_module,
        "list_stale_green_finance_cases",
        lambda session, after_case_id, limit: candidates,
    )
    monkeypatch.setattr(
        batch_module,
        "run_five_articles_stage_b",
        lambda *args, **kwargs: SimpleNamespace(
            stage_b_result=SimpleNamespace(status=next(statuses))
        ),
    )

    summary = reclassify_stale_green_finance_cases(
        Mock(), Settings(_env_file=None), after_case_id=5, limit=4
    )

    assert summary.selected == 4
    assert summary.completed == 1
    assert summary.not_applicable == 1
    assert summary.needs_review == 1
    assert summary.classification_failed == 1
    assert summary.last_case_id == 40
