from collections.abc import Mapping
from dataclasses import dataclass

from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


MAX_EVIDENCE_EXCERPT_LENGTH = 160


@dataclass(frozen=True)
class EvidenceSource:
    field_key: str
    field_label: str
    value: str


def build_business_sources(
    input_payload: Mapping[str, object],
    stage_a_snapshot: Mapping[str, object],
    profile: ScenarioRegistration,
) -> dict[str, EvidenceSource]:
    schema_by_key = {field.key: field for field in profile.field_schema}
    sources = {
        field_key: EvidenceSource(
            field_key,
            schema_by_key[field_key].label,
            value,
        )
        for field_key in profile.stage_b_evidence_field_keys
        if field_key in schema_by_key
        if (value := text(input_payload.get(field_key)))
    }
    stage_a_fields = (
        (
            "stage_a.enterprise_matching_basis",
            "Stage A 企业匹配依据",
            stage_a_snapshot["enterprise_matching_basis"],
        ),
        (
            "stage_a.loan_matching_basis",
            "Stage A 贷款投向匹配依据",
            stage_a_snapshot["loan_matching_basis"],
        ),
    )
    for field_key, field_label, raw_value in stage_a_fields:
        if value := text(raw_value):
            sources[field_key] = EvidenceSource(field_key, field_label, value)
    return sources


def business_evidence_ref(source: EvidenceSource) -> dict[str, object]:
    return {
        "type": "business",
        "field_key": source.field_key,
        "field_label": source.field_label,
        "excerpt": source.value[:MAX_EVIDENCE_EXCERPT_LENGTH].rstrip(),
    }


def serialize_label(label: FiveArticlesMappingLabel) -> dict[str, object]:
    return {
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
        "match_method": label.match_method,
    }


def text(value: object) -> str:
    return "" if value is None else str(value).strip()

