import json
import re
from collections.abc import Mapping, Sequence

from app.services.five_articles_policies import get_five_articles_policy
from app.services.five_articles_stage_b_evidence import (
    MAX_EVIDENCE_EXCERPT_LENGTH,
    EvidenceSource as _EvidenceSource,
    build_business_sources as _build_business_sources,
    business_evidence_ref as _business_evidence_ref,
    serialize_label as _serialize_label,
    text as _text,
)
from app.services.five_articles_stage_b_types import (
    StageAResult,
    TechnologyFinanceConsistencyStatus,
    TechnologyFinanceStageBError,
    TechnologyFinanceStageBResult,
)
from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


_FOUR_DIGIT_CODE_PATTERN = re.compile(r"^\d{4}$")
_CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_ROOT_FIELDS_WITH_CONSISTENCY = frozenset({"labels", "consistency"})
_ROOT_FIELDS_SAME_CODE = frozenset({"labels"})
_BASIS_ROOT_FIELDS_WITH_CONSISTENCY = frozenset({"label_basis", "consistency"})
_BASIS_ROOT_FIELDS_SAME_CODE = frozenset({"label_basis"})
_MULTI_BASIS_ROOT_FIELDS_WITH_CONSISTENCY = frozenset(
    {"label_bases", "consistency"}
)
_MULTI_BASIS_ROOT_FIELDS_SAME_CODE = frozenset({"label_bases"})
_LABEL_BASIS_FIELDS = frozenset({"matching_basis", "business_evidence_refs"})
_COMPACT_LABEL_FIELDS = frozenset({"matching_basis", "evidence_refs"})
_LABEL_FIELDS = frozenset(
    {
        "mapping_version_id",
        "source_row",
        "NEIC_Code",
        "NEIC_Name",
        "subject",
        "taxonomy_path",
        "matching_basis",
        "evidence_refs",
    }
)
_MAPPING_EVIDENCE_FIELDS = frozenset(
    {
        "type",
        "mapping_version_id",
        "source_row",
        "NEIC_Code",
        "NEIC_Name",
        "taxonomy_path",
    }
)
_BUSINESS_EVIDENCE_FIELDS = frozenset(
    {"type", "field_key", "field_label", "excerpt"}
)
_LABEL_EVIDENCE_FIELDS = frozenset(
    {
        "type",
        "side",
        "mapping_version_id",
        "source_row",
        "NEIC_Code",
        "NEIC_Name",
        "taxonomy_path",
    }
)
_CONSISTENCY_FIELDS = frozenset({"status", "basis"})
_SERVER_OWNED_CONSISTENCY_FIELDS = frozenset(
    {"status", "basis", "business_evidence_refs"}
)
_LEGACY_CONSISTENCY_FIELDS = frozenset({"status", "basis", "evidence_refs"})
_CONSISTENCY_STATUSES = frozenset(
    {"consistent", "inconsistent", "needs_review"}
)

def _validate_stage_b_model_response(
    response_payload: object,
    stage_a_snapshot: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    business_sources: Mapping[str, _EvidenceSource],
    profile: ScenarioRegistration,
    *,
    same_code: bool,
) -> TechnologyFinanceStageBResult:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise TechnologyFinanceStageBError(
            "DeepSeek response is missing choices[0].message.content"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise TechnologyFinanceStageBError(
            "DeepSeek Stage B response content must be non-empty"
        )
    try:
        model_output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TechnologyFinanceStageBError(
            "DeepSeek Stage B response content is not valid JSON"
        ) from exc
    if (
        same_code
        and len(loan_direction_labels) > 1
        and isinstance(model_output, list)
    ):
        # DeepSeek occasionally obeys every deterministic label/evidence
        # constraint but returns the requested labels array as the JSON root.
        # Same-code decisions do not require a model-owned consistency object,
        # so restoring the omitted server-declared wrapper is lossless. The
        # existing strict label-set and evidence validation still runs below.
        wrapper = (
            "label_bases"
            if all(
                isinstance(item, dict) and "business_evidence_refs" in item
                for item in model_output
            )
            else "labels"
        )
        model_output = {wrapper: model_output}
    if not isinstance(model_output, dict):
        raise TechnologyFinanceStageBError(
            "DeepSeek Stage B model output must be a JSON object"
        )
    if "label_basis" in model_output:
        _require_exact_fields(
            model_output,
            (
                _BASIS_ROOT_FIELDS_SAME_CODE
                if same_code
                else _BASIS_ROOT_FIELDS_WITH_CONSISTENCY
            ),
            "root",
        )
        labels = _validate_single_label_basis(
            model_output.get("label_basis"),
            loan_direction_labels,
            business_sources,
        )
    elif "label_bases" in model_output:
        _require_exact_fields(
            model_output,
            (
                _MULTI_BASIS_ROOT_FIELDS_SAME_CODE
                if same_code
                else _MULTI_BASIS_ROOT_FIELDS_WITH_CONSISTENCY
            ),
            "root",
        )
        labels = _validate_multi_label_bases(
            model_output.get("label_bases"),
            loan_direction_labels,
            business_sources,
        )
    else:
        # Tolerate the legacy cloud response shape during rollout. Fixed label
        # fields are still normalized from the server-owned selected label.
        _require_exact_fields(
            model_output,
            _ROOT_FIELDS_SAME_CODE if same_code else _ROOT_FIELDS_WITH_CONSISTENCY,
            "root",
        )
        labels = _validate_label_outputs(
            model_output.get("labels"),
            loan_direction_labels,
            business_sources,
        )

    if same_code:
        code = str(stage_a_snapshot["enterprise_neic_code"])
        enterprise_name = str(stage_a_snapshot["enterprise_neic_name"])
        loan_name = str(stage_a_snapshot["loan_neic_name"])
        return TechnologyFinanceStageBResult(
            labels=labels,
            consistency_status="consistent",
            consistency_basis=(
                f"企业四位码与贷款投向四位码均为{code}，对应企业行业{enterprise_name}"
                f"和投向行业{loan_name}，确定为一致。"
            ),
            consistency_evidence_refs=(
                _stage_a_evidence_ref(
                    "stage_a.industry_code", "Stage A 企业四位码", code
                ),
                _stage_a_evidence_ref(
                    "stage_a.loan_industry_code", "Stage A 贷款投向四位码", code
                ),
            ),
            model_output=model_output,
        )

    status, basis, refs = _validate_consistency_output(
        model_output.get("consistency"),
        enterprise_labels,
        loan_direction_labels,
        business_sources,
        profile,
    )
    return TechnologyFinanceStageBResult(
        labels=labels,
        consistency_status=status,
        consistency_basis=basis,
        consistency_evidence_refs=refs,
        model_output=model_output,
    )


def _validate_label_outputs(
    raw_labels: object,
    expected_labels: Sequence[FiveArticlesMappingLabel],
    business_sources: Mapping[str, _EvidenceSource],
) -> tuple[dict[str, object], ...]:
    if not isinstance(raw_labels, list):
        raise TechnologyFinanceStageBError("model output labels must be an array")
    expected_by_key = {_label_key_from_label(label): label for label in expected_labels}
    if len(expected_by_key) != 1 and len(raw_labels) != len(expected_by_key):
        raise TechnologyFinanceStageBError("model output changed deterministic label count")

    validated_by_key: dict[tuple[object, ...], dict[str, object]] = {}
    for index, raw_label in enumerate(raw_labels):
        if not isinstance(raw_label, dict):
            raise TechnologyFinanceStageBError(
                f"labels[{index}] must be a JSON object"
            )
        echoed_match_method = raw_label.get("match_method")
        fields_without_match_method = {
            field: value for field, value in raw_label.items() if field != "match_method"
        }
        is_compact = frozenset(fields_without_match_method) == _COMPACT_LABEL_FIELDS
        if is_compact:
            if len(raw_labels) != len(expected_labels):
                raise TechnologyFinanceStageBError(
                    "model output changed deterministic label count"
                )
            expected = expected_labels[index]
            key = _label_key_from_label(expected)
        else:
            _require_exact_fields(
                fields_without_match_method, _LABEL_FIELDS, f"labels[{index}]"
            )
            key = _label_key_from_output(raw_label, f"labels[{index}]")
            expected = expected_by_key.get(key)
        if expected is None:
            if len(expected_by_key) == 1:
                continue
            raise TechnologyFinanceStageBError(
                f"labels[{index}] altered or invented a deterministic label"
            )
        if key in validated_by_key:
            if len(expected_by_key) == 1:
                continue
            raise TechnologyFinanceStageBError(
                f"labels[{index}] duplicated a deterministic label"
            )
        if "match_method" in raw_label and echoed_match_method != expected.match_method:
            raise TechnologyFinanceStageBError(
                f"labels[{index}].match_method differs from the deterministic label"
            )
        basis = _required_chinese_text(raw_label, "matching_basis", f"labels[{index}]")
        evidence_refs = _validate_label_evidence_refs(
            raw_label.get("evidence_refs"),
            expected,
            business_sources,
            branch=f"labels[{index}]",
        )
        validated_by_key[key] = {
            **_serialize_label(expected),
            "matching_basis": basis,
            "evidence_refs": list(evidence_refs),
        }

    if not validated_by_key and len(expected_by_key) == 1:
        raise TechnologyFinanceStageBError(
            "model output altered or invented the selected deterministic label"
        )
    if set(validated_by_key) != set(expected_by_key):
        raise TechnologyFinanceStageBError(
            "model output label set differs from deterministic labels"
        )
    return tuple(
        validated_by_key[_label_key_from_label(label)] for label in expected_labels
    )


def _validate_multi_label_bases(
    raw_bases: object,
    expected_labels: Sequence[FiveArticlesMappingLabel],
    business_sources: Mapping[str, _EvidenceSource],
) -> tuple[dict[str, object], ...]:
    if len(expected_labels) < 2:
        raise TechnologyFinanceStageBError(
            "Stage B multi-label bases require at least two server-owned labels"
        )
    if not isinstance(raw_bases, list):
        raise TechnologyFinanceStageBError("label_bases must be an array")
    if len(raw_bases) != len(expected_labels):
        raise TechnologyFinanceStageBError(
            "model output changed deterministic label count"
        )

    validated: list[dict[str, object]] = []
    for index, (raw_basis, expected_label) in enumerate(
        zip(raw_bases, expected_labels, strict=True)
    ):
        if not isinstance(raw_basis, dict):
            raise TechnologyFinanceStageBError(
                f"label_bases[{index}] must be a JSON object"
            )
        _require_exact_fields(
            raw_basis, _LABEL_BASIS_FIELDS, f"label_bases[{index}]"
        )
        validated.append(
            _validate_single_label_basis(
                raw_basis,
                (expected_label,),
                business_sources,
            )[0]
        )
    return tuple(validated)


def _validate_single_label_basis(
    raw_basis: object,
    expected_labels: Sequence[FiveArticlesMappingLabel],
    business_sources: Mapping[str, _EvidenceSource],
) -> tuple[dict[str, object], ...]:
    if len(expected_labels) != 1:
        raise TechnologyFinanceStageBError(
            "Stage B label basis requires exactly one server-selected label"
        )
    if not isinstance(raw_basis, dict):
        raise TechnologyFinanceStageBError("label_basis must be a JSON object")
    _require_exact_fields(raw_basis, _LABEL_BASIS_FIELDS, "label_basis")
    basis = _required_chinese_text(raw_basis, "matching_basis", "label_basis")
    raw_business_refs = _required_array(
        raw_basis.get("business_evidence_refs"),
        "label_basis.business_evidence_refs",
    )
    if not raw_business_refs:
        raise TechnologyFinanceStageBError(
            "label_basis requires at least one business evidence ref"
        )
    business_refs: list[dict[str, object]] = []
    validation_errors: list[TechnologyFinanceStageBError] = []
    for index, raw_ref in enumerate(raw_business_refs):
        branch = f"label_basis.business_evidence_refs[{index}]"
        try:
            if not isinstance(raw_ref, dict):
                raise TechnologyFinanceStageBError(f"{branch} must be an object")
            _require_exact_fields(raw_ref, _BUSINESS_EVIDENCE_FIELDS, branch)
            if raw_ref.get("type") != "business":
                raise TechnologyFinanceStageBError(f"{branch}.type must be business")
            business_refs.append(
                _validate_business_ref(raw_ref, business_sources, branch)
            )
        except TechnologyFinanceStageBError as exc:
            validation_errors.append(exc)
    if not business_refs:
        raise validation_errors[0]

    selected_label = expected_labels[0]
    return (
        {
            **_serialize_label(selected_label),
            "matching_basis": basis,
            "evidence_refs": [
                _mapping_evidence_ref(selected_label),
                *business_refs,
            ],
        },
    )


def _validate_label_evidence_refs(
    raw_refs: object,
    expected_label: FiveArticlesMappingLabel,
    business_sources: Mapping[str, _EvidenceSource],
    *,
    branch: str,
) -> tuple[dict[str, object], ...]:
    refs = _required_array(raw_refs, f"{branch}.evidence_refs")
    business_refs: list[dict[str, object]] = []
    for index, raw_ref in enumerate(refs):
        ref_branch = f"{branch}.evidence_refs[{index}]"
        if not isinstance(raw_ref, dict):
            raise TechnologyFinanceStageBError(f"{ref_branch} must be an object")
        ref_type = raw_ref.get("type")
        if ref_type == "mapping":
            echoed_match_method = raw_ref.get("match_method")
            fields_without_match_method = {
                field: value for field, value in raw_ref.items() if field != "match_method"
            }
            _require_exact_fields(
                fields_without_match_method, _MAPPING_EVIDENCE_FIELDS, ref_branch
            )
            if _mapping_ref_key(raw_ref, ref_branch) != _mapping_key(expected_label):
                raise TechnologyFinanceStageBError(
                    f"{ref_branch} does not match the label mapping source"
                )
            if "match_method" in raw_ref and echoed_match_method != expected_label.match_method:
                raise TechnologyFinanceStageBError(
                    f"{ref_branch}.match_method differs from the deterministic label"
                )
        elif ref_type == "business":
            _require_exact_fields(raw_ref, _BUSINESS_EVIDENCE_FIELDS, ref_branch)
            business_refs.append(_validate_business_ref(raw_ref, business_sources, ref_branch))
        else:
            raise TechnologyFinanceStageBError(
                f"{ref_branch}.type must be mapping or business"
            )
    if not business_refs:
        raise TechnologyFinanceStageBError(
            f"{branch} requires at least one business evidence ref"
        )
    return (_mapping_evidence_ref(expected_label), *business_refs)


def _validate_consistency_output(
    raw_consistency: object,
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    business_sources: Mapping[str, _EvidenceSource],
    profile: ScenarioRegistration,
) -> tuple[
    TechnologyFinanceConsistencyStatus,
    str,
    tuple[dict[str, object], ...],
]:
    policy = get_five_articles_policy(profile.id)
    if not isinstance(raw_consistency, dict):
        raise TechnologyFinanceStageBError("model output consistency must be an object")
    actual_fields = frozenset(raw_consistency)
    if actual_fields not in {
        _CONSISTENCY_FIELDS,
        _SERVER_OWNED_CONSISTENCY_FIELDS,
        _LEGACY_CONSISTENCY_FIELDS,
    }:
        _require_exact_fields(raw_consistency, _CONSISTENCY_FIELDS, "consistency")
    raw_status = raw_consistency.get("status")
    if raw_status not in _CONSISTENCY_STATUSES:
        raise TechnologyFinanceStageBError(
            "consistency.status must be consistent, inconsistent, or needs_review"
        )
    status: TechnologyFinanceConsistencyStatus = raw_status
    basis = _required_chinese_text(raw_consistency, "basis", "consistency")
    business_evidence_is_insufficient = (
        "loan_purpose" not in business_sources
        or "stage_a.loan_matching_basis" not in business_sources
    )
    evidence_is_insufficient = business_evidence_is_insufficient or (
        not enterprise_labels
        and policy.enterprise_labels_required_for_consistency()
    )
    if evidence_is_insufficient and status != "needs_review":
        raise TechnologyFinanceStageBError(
            "insufficient consistency evidence must result in needs_review"
        )
    policy_override = policy.override_missing_enterprise_consistency(
        profile,
        business_evidence_is_insufficient=business_evidence_is_insufficient,
        enterprise_labels=enterprise_labels,
        status=status,
        basis=basis,
    )
    if policy_override is not None:
        status, basis = policy_override
    elif enterprise_labels and not _labels_intersect(
        enterprise_labels, loan_direction_labels
    ):
        status = "inconsistent"
        basis = (
            "企业侧与贷款投向侧科技金融标签不存在主题或层级交集，判定为不一致。"
        )
    validated_refs = [
        *(
            _consistency_label_ref(label, "enterprise")
            for label in enterprise_labels
        ),
        *(
            _consistency_label_ref(label, "loan_direction")
            for label in loan_direction_labels
        ),
        *(
            _business_evidence_ref(business_sources[field_key])
            for field_key in ("loan_purpose", "stage_a.loan_matching_basis")
            if field_key in business_sources
        ),
    ]
    return status, basis, tuple(validated_refs)


def _validate_deterministic_labels(
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    stage_a_snapshot: Mapping[str, object],
    profile: ScenarioRegistration,
) -> None:
    if not loan_direction_labels:
        raise TechnologyFinanceStageBError(
            "Stage B constrained decision requires loan-direction mapping labels"
        )
    all_labels = (*enterprise_labels, *loan_direction_labels)
    mapping_version_ids = {label.mapping_version_id for label in all_labels}
    if len(mapping_version_ids) != 1 or next(iter(mapping_version_ids)) <= 0:
        raise TechnologyFinanceStageBError(
            "all deterministic labels must use one positive mapping_version_id"
        )
    scenario_ids = {label.scenario_id for label in all_labels}
    if (
        len(scenario_ids) != 1
        or not next(iter(scenario_ids)).strip()
    ):
        raise TechnologyFinanceStageBError(
            "all deterministic labels must use one non-empty scenario_id"
        )
    if scenario_ids != {profile.id}:
        raise TechnologyFinanceStageBError(
            f"deterministic labels must belong to scenario {profile.id}"
        )
    for side, labels in (
        ("enterprise", enterprise_labels),
        ("loan_direction", loan_direction_labels),
    ):
        keys = [_label_key_from_label(label) for label in labels]
        if len(keys) != len(set(keys)):
            raise TechnologyFinanceStageBError(
                f"{side} deterministic labels contain duplicates"
            )
    if _has_same_neic_code_match(
        stage_a_snapshot, enterprise_labels, loan_direction_labels
    ) and {
        _label_key_from_label(label) for label in enterprise_labels
    } != {_label_key_from_label(label) for label in loan_direction_labels}:
        raise TechnologyFinanceStageBError(
            "same-code enterprise and loan deterministic label sets must be identical"
        )


def _has_same_neic_code_match(
    stage_a_snapshot: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
) -> bool:
    """Only pure NEIC lookup can use the same-code consistency shortcut.

    Condition fallbacks are independently selected from side-specific evidence,
    so equal Stage A codes do not establish equal labels or consistency.
    """
    return (
        stage_a_snapshot["enterprise_neic_code"]
        == stage_a_snapshot["loan_neic_code"]
        and all(
            label.match_method == "neic_code"
            for label in (*enterprise_labels, *loan_direction_labels)
        )
    )


def _serialize_stage_a_result(stage_a_result: StageAResult) -> dict[str, object]:
    enterprise_code = _required_stage_a_text(
        stage_a_result.industry_code, "industry_code"
    )
    loan_code = _required_stage_a_text(
        stage_a_result.loan_industry_code, "loan_industry_code"
    )
    if (
        _FOUR_DIGIT_CODE_PATTERN.fullmatch(enterprise_code) is None
        or _FOUR_DIGIT_CODE_PATTERN.fullmatch(loan_code) is None
    ):
        raise TechnologyFinanceStageBError(
            "Stage A enterprise and loan codes must be four digits"
        )
    result_id = stage_a_result.id
    if type(result_id) is not int or result_id <= 0:
        raise TechnologyFinanceStageBError("Stage A result id must be positive")
    return {
        "stage_a_result_id": result_id,
        "enterprise_neic_code": enterprise_code,
        "enterprise_major_category_code": _text(
            stage_a_result.industry_major_code
        ),
        "enterprise_neic_name": _required_stage_a_text(
            stage_a_result.industry_name, "industry_name"
        ),
        "enterprise_matching_basis": _text(stage_a_result.rationale),
        "loan_neic_code": loan_code,
        "loan_major_category_code": _text(
            stage_a_result.loan_industry_major_code
        ),
        "loan_neic_name": _required_stage_a_text(
            stage_a_result.loan_industry_name, "loan_industry_name"
        ),
        "loan_matching_basis": _text(stage_a_result.loan_matching_basis),
    }


def _validate_business_ref(
    raw_ref: Mapping[str, object],
    business_sources: Mapping[str, _EvidenceSource],
    branch: str,
) -> dict[str, object]:
    field_key = raw_ref.get("field_key")
    if not isinstance(field_key, str) or field_key not in business_sources:
        raise TechnologyFinanceStageBError(
            f"{branch} references a business field absent from the input"
        )
    source = business_sources[field_key]
    if raw_ref.get("field_label") != source.field_label:
        raise TechnologyFinanceStageBError(f"{branch} has a false field label")
    excerpt = raw_ref.get("excerpt")
    if not isinstance(excerpt, str) or not excerpt.strip():
        raise TechnologyFinanceStageBError(f"{branch}.excerpt must be non-empty")
    excerpt = excerpt.strip()
    if _strip_whitespace(excerpt) not in _strip_whitespace(source.value):
        raise TechnologyFinanceStageBError(
            f"{branch}.excerpt is not present in the input source text"
        )
    if len(excerpt) > MAX_EVIDENCE_EXCERPT_LENGTH:
        excerpt = excerpt[:MAX_EVIDENCE_EXCERPT_LENGTH].rstrip()
    return {
        "type": "business",
        "field_key": source.field_key,
        "field_label": source.field_label,
        "excerpt": excerpt,
    }


def _mapping_evidence_ref(
    label: FiveArticlesMappingLabel,
) -> dict[str, object]:
    return {
        "type": "mapping",
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "taxonomy_path": list(label.taxonomy_path),
    }


def _consistency_label_ref(
    label: FiveArticlesMappingLabel, side: str
) -> dict[str, object]:
    return {
        "type": "label",
        "side": side,
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "taxonomy_path": list(label.taxonomy_path),
    }


def _label_key_from_label(
    label: FiveArticlesMappingLabel,
) -> tuple[object, ...]:
    return (
        label.mapping_version_id,
        label.source_row,
        label.neic_code,
        label.neic_name,
        label.subject,
        label.taxonomy_path,
    )


def _label_key_from_output(
    payload: Mapping[str, object], branch: str
) -> tuple[object, ...]:
    taxonomy_path = payload.get("taxonomy_path")
    if (
        not isinstance(taxonomy_path, list)
        or not taxonomy_path
        or any(not isinstance(tier, str) or not tier.strip() for tier in taxonomy_path)
    ):
        raise TechnologyFinanceStageBError(
            f"{branch}.taxonomy_path must be a non-empty string array"
        )
    return (
        payload.get("mapping_version_id"),
        payload.get("source_row"),
        payload.get("NEIC_Code"),
        payload.get("NEIC_Name"),
        payload.get("subject"),
        tuple(taxonomy_path),
    )


def _mapping_key(label: FiveArticlesMappingLabel) -> tuple[object, ...]:
    return (
        label.mapping_version_id,
        label.source_row,
        label.neic_code,
        label.neic_name,
        label.taxonomy_path,
    )


def _mapping_ref_key(
    payload: Mapping[str, object], branch: str
) -> tuple[object, ...]:
    taxonomy_path = payload.get("taxonomy_path")
    if not isinstance(taxonomy_path, list) or any(
        not isinstance(tier, str) or not tier.strip() for tier in taxonomy_path
    ):
        raise TechnologyFinanceStageBError(
            f"{branch}.taxonomy_path must be a string array"
        )
    return (
        payload.get("mapping_version_id"),
        payload.get("source_row"),
        payload.get("NEIC_Code"),
        payload.get("NEIC_Name"),
        tuple(taxonomy_path),
    )


def _labels_intersect(
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
) -> bool:
    enterprise_taxonomies = {
        (label.subject, label.taxonomy_path) for label in enterprise_labels
    }
    return any(
        (label.subject, label.taxonomy_path) in enterprise_taxonomies
        for label in loan_direction_labels
    )


def _stage_a_evidence_ref(
    field_key: str, field_label: str, excerpt: str
) -> dict[str, object]:
    return {
        "type": "stage_a",
        "field_key": field_key,
        "field_label": field_label,
        "excerpt": excerpt,
    }


def _required_stage_a_text(value: object, field: str) -> str:
    text = _text(value)
    if not text:
        raise TechnologyFinanceStageBError(f"Stage A {field} must be non-empty")
    return text


def _required_chinese_text(
    payload: Mapping[str, object], field: str, branch: str
) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise TechnologyFinanceStageBError(
            f"{branch}.{field} must be non-empty text"
        )
    value = value.strip()
    if _CHINESE_PATTERN.search(value) is None:
        raise TechnologyFinanceStageBError(f"{branch}.{field} must contain Chinese")
    return value


def _required_array(value: object, branch: str) -> list[object]:
    if not isinstance(value, list):
        raise TechnologyFinanceStageBError(f"{branch} must be an array")
    return value


def _require_exact_fields(
    payload: Mapping[str, object], expected: frozenset[str], branch: str
) -> None:
    actual = set(payload)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise TechnologyFinanceStageBError(
            f"{branch} fields differ: missing={missing}, unexpected={unexpected}"
        )


def _strip_whitespace(value: str) -> str:
    return _WHITESPACE_PATTERN.sub("", value)


validate_stage_b_model_response = _validate_stage_b_model_response
validate_deterministic_labels = _validate_deterministic_labels
has_same_neic_code_match = _has_same_neic_code_match
serialize_stage_a_result = _serialize_stage_a_result

