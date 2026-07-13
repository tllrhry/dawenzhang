"""Enforce five-articles result scenario integrity."""

from typing import Sequence, Union

from alembic import op


revision: str = "0009_five_articles_integrity"
down_revision: Union[str, Sequence[str], None] = "0008_five_articles_results"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_five_articles_result_scenario_integrity()
        RETURNS trigger AS $$
        DECLARE
            case_scenario text;
            stage_a_case_id bigint;
            mapping_scenario text;
        BEGIN
            SELECT scenario INTO case_scenario
            FROM national_economy_classification_cases WHERE id = NEW.case_id;
            IF case_scenario IS NULL OR NEW.scenario_id <> case_scenario THEN
                RAISE EXCEPTION 'five_articles_results scenario must match case scenario';
            END IF;

            SELECT case_id INTO stage_a_case_id
            FROM national_economy_classification_results WHERE id = NEW.stage_a_result_id;
            IF stage_a_case_id IS NULL OR stage_a_case_id <> NEW.case_id THEN
                RAISE EXCEPTION 'five_articles_results Stage A must belong to case';
            END IF;

            IF NEW.mapping_version_id IS NOT NULL THEN
                SELECT scenario_id INTO mapping_scenario
                FROM five_articles_mapping_versions WHERE id = NEW.mapping_version_id;
                IF mapping_scenario IS NULL OR mapping_scenario <> NEW.scenario_id THEN
                    RAISE EXCEPTION 'five_articles_results mapping version must match scenario';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_five_articles_results_scenario_integrity
        BEFORE INSERT OR UPDATE ON five_articles_results
        FOR EACH ROW EXECUTE FUNCTION enforce_five_articles_result_scenario_integrity();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_five_articles_results_scenario_integrity ON five_articles_results"
    )
    op.execute("DROP FUNCTION enforce_five_articles_result_scenario_integrity()")
