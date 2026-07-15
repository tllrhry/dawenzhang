import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from app.core.config import Settings
from app.services.scenario_registry import (
    ScenarioRegistration,
    TECHNOLOGY_FINANCE_REGISTRATION,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
)


TechnologyFinanceConsistencyStatus = Literal[
    "consistent", "inconsistent", "needs_review"
]
MAX_EVIDENCE_EXCERPT_LENGTH = 160
_FOUR_DIGIT_CODE_PATTERN = re.compile(r"^\d{4}$")
_CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")
_WHITESPACE_PATTERN = re.compile(r"\s+")
_ROOT_FIELDS_WITH_CONSISTENCY = frozenset({"labels", "consistency"})
_ROOT_FIELDS_SAME_CODE = frozenset({"labels"})
_BASIS_ROOT_FIELDS_WITH_CONSISTENCY = frozenset({"label_basis", "consistency"})
_BASIS_ROOT_FIELDS_SAME_CODE = frozenset({"label_basis"})
_LABEL_BASIS_FIELDS = frozenset({"matching_basis", "business_evidence_refs"})
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


class StageAResult(Protocol):
    id: int
    industry_code: str | None
    industry_major_code: str | None
    industry_name: str | None
    rationale: str | None
    loan_industry_code: str | None
    loan_industry_major_code: str | None
    loan_industry_name: str | None
    loan_matching_basis: str | None


class TechnologyFinanceStageBError(RuntimeError):
    """Raised when Stage B cannot produce a grounded constrained decision."""


@dataclass(frozen=True)
class TechnologyFinanceStageBResult:
    labels: tuple[dict[str, object], ...]
    consistency_status: TechnologyFinanceConsistencyStatus
    consistency_basis: str
    consistency_evidence_refs: tuple[dict[str, object], ...]
    model_output: dict[str, object]


@dataclass(frozen=True)
class _EvidenceSource:
    field_key: str
    field_label: str
    value: str


def classify_technology_finance_stage_b(
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    settings: Settings,
    client: httpx.Client | None = None,
) -> TechnologyFinanceStageBResult:
    """Compatibility wrapper for the technology-finance Stage B profile."""
    return classify_five_articles_stage_b(
        TECHNOLOGY_FINANCE_REGISTRATION,
        input_payload,
        stage_a_result,
        enterprise_labels,
        loan_direction_labels,
        settings,
        client=client,
    )


def classify_five_articles_stage_b(
    profile: ScenarioRegistration,
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    settings: Settings,
    client: httpx.Client | None = None,
) -> TechnologyFinanceStageBResult:
    """Generate a grounded Stage B decision using one scenario profile only."""
    if not profile.is_executable_profile:
        raise TechnologyFinanceStageBError(f"场景 {profile.id} 不具备 Stage B 配置")
    enterprise_snapshot = tuple(enterprise_labels)
    loan_snapshot = tuple(loan_direction_labels)
    stage_a_snapshot = _serialize_stage_a_result(stage_a_result)
    _validate_deterministic_labels(
        enterprise_snapshot,
        loan_snapshot,
        stage_a_snapshot,
        profile,
    )
    business_sources = _build_business_sources(input_payload, stage_a_snapshot, profile)
    same_code = _has_same_neic_code_match(
        stage_a_snapshot, enterprise_snapshot, loan_snapshot
    )
    request_payload = _build_stage_b_request_payload(
        input_payload,
        stage_a_snapshot,
        enterprise_snapshot,
        loan_snapshot,
        settings.deepseek_model,
        profile,
        same_code=same_code,
    )

    if not settings.deepseek_api_key:
        raise TechnologyFinanceStageBError(
            f"DEEPSEEK_API_KEY is required for {profile.name} Stage B"
        )

    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.deepseek_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.deepseek_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        for attempt in range(3):
            try:
                response = http_client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json=request_payload,
                )
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))
        response.raise_for_status()
        return _validate_stage_b_model_response(
            response.json(),
            stage_a_snapshot,
            enterprise_snapshot,
            loan_snapshot,
            business_sources,
            same_code=same_code,
        )
    except TechnologyFinanceStageBError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise TechnologyFinanceStageBError(
            f"DeepSeek {profile.name} Stage B failed: {exc}"
        ) from exc
    finally:
        if owns_client:
            http_client.close()


def _build_stage_b_request_payload(
    input_payload: Mapping[str, object],
    stage_a_snapshot: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    model: str,
    profile: ScenarioRegistration,
    *,
    same_code: bool,
) -> dict[str, object]:
    field_payload = [
        {"field_key": field.key, "field_label": field.label, "value": value}
        for field in profile.field_schema
        if (value := _text(input_payload.get(field.key)))
    ]
    prompt_input = {
        "template_fields": field_payload,
        "stage_a_result": dict(stage_a_snapshot),
        "business_evidence_sources": [
            {
                "field_key": source.field_key,
                "field_label": source.field_label,
                "value": source.value,
            }
            for source in _build_business_sources(
                input_payload, stage_a_snapshot, profile
            ).values()
        ],
        "enterprise_labels": [_serialize_label(label) for label in enterprise_labels],
        "loan_direction_labels": [
            _serialize_label(label) for label in loan_direction_labels
        ],
        "same_four_digit_code": same_code,
        "max_excerpt_length": MAX_EVIDENCE_EXCERPT_LENGTH,
    }
    is_single_label = len(loan_direction_labels) == 1
    consistency_instruction = (
        (
            "企业四位码与投向四位码相同，一致性由服务端确定为 consistent；"
            "根对象只能返回 label_basis，不得返回 consistency。"
            if is_single_label
            else "企业四位码与投向四位码相同，一致性由服务端确定为 consistent；"
            "根对象只能返回 labels，不得返回 consistency。"
        )
        if same_code
        else (
            "两码不同，根对象必须返回 label_basis 和 consistency。consistency 只能包含 "
            "status、basis，不得返回任何 evidence_refs。status 只能是 consistent、"
            "inconsistent 或 "
            "needs_review：企业和投向标签存在交集且资金服务企业现有主营或科技活动才可"
            "为 consistent；标签无交集或资金明确流向无关独立活动可为 inconsistent；"
            "企业侧未命中、用途笼统、证据冲突或不足必须为 needs_review。不得仅凭两码"
            "不同判 inconsistent，也不得仅凭研发、专利或资质判 consistent。"
        )
    )
    if is_single_label:
        label_instruction = (
            "loan_direction_labels 已由服务端收窄为唯一最匹配标签。你不得输出 labels "
            "数组，也不得复制标签字段；不得新增、删除、改写或替换标签。"
            "你只能输出一个 label_basis 对象，"
        )
        output_instruction = (
            "且只能包含 matching_basis 和 business_evidence_refs。"
            "matching_basis 是唯一标签的中文匹配依据；"
            "business_evidence_refs 至少一条，每条只能包含 "
            "type、field_key、field_label、excerpt，type 必须为 business。"
        )
        evidence_instruction = ""
    else:
        label_instruction = (
            "loan_direction_labels 包含多个相互独立、互不排斥的主题候选。你必须为每个候选分别生成中文匹配依据，"
            "输出 labels 数组；数组条目数量必须与候选数量一致，候选集合必须完全一致。"
            "不得新增、删除、改写或替换任何候选；每个条目必须对应一个原始候选并保留其固定字段。"
        )
        output_instruction = (
            "每个 labels 条目除候选固定字段外只能包含 matching_basis 和 evidence_refs。"
            "每个条目的 matching_basis 都是对应候选的中文匹配依据，且 evidence_refs 至少一条；"
        )
        evidence_instruction = (
            "evidence_refs 必须至少包含一条 business 证据；对应候选的 mapping 证据由服务端组装。"
            "每条 business 证据只能包含 type、field_key、field_label、excerpt，type 必须为 business。"
        )
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"你是{profile.name} Stage B 受限判定器。你必须只输出一个合法的 JSON 对象，"
                    "不得包含 JSON 以外的任何文字。输入中的 enterprise_labels 和 "
                    "loan_direction_labels 均来自已发布 Excel 映射，是不可更改的事实。"
                    + label_instruction
                    + output_instruction
                    + evidence_instruction
                    + "字段必须属于当前场景证据白名单且来自输入，"
                    "label 必须匹配，excerpt 必须是对应 value 的原文子串且不超过输入规定"
                    f"长度。业务证据优先级依次为：{'、'.join(profile.stage_b_evidence_field_keys)}；"
                    "Stage A 贷款投向依据可作为补充。不得捏造"
                    "字段或摘录。标签固定字段和 mapping 证据由服务端组装。"
                    "matching_basis、consistency.basis 必须是非空中文。"
                    "consistency 不得输出 label 引用或复制标签固定字段；企业与投向标签证据"
                    "由服务端从确定性标签组装。consistent、inconsistent 或 needs_review 的"
                    "正式一致性证据由服务端根据 business_evidence_sources 组装；证据不足时"
                    "必须输出 needs_review。" + consistency_instruction
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_input, ensure_ascii=False),
            },
        ],
    }


def _validate_stage_b_model_response(
    response_payload: object,
    stage_a_snapshot: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    business_sources: Mapping[str, _EvidenceSource],
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
        _require_exact_fields(fields_without_match_method, _LABEL_FIELDS, f"labels[{index}]")
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
) -> tuple[
    TechnologyFinanceConsistencyStatus,
    str,
    tuple[dict[str, object], ...],
]:
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
    evidence_is_insufficient = (
        not enterprise_labels
        or "loan_purpose" not in business_sources
        or "stage_a.loan_matching_basis" not in business_sources
    )
    if evidence_is_insufficient and status != "needs_review":
        raise TechnologyFinanceStageBError(
            "insufficient consistency evidence must result in needs_review"
        )
    if enterprise_labels and not _labels_intersect(
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


def _build_business_sources(
    input_payload: Mapping[str, object],
    stage_a_snapshot: Mapping[str, object],
    profile: ScenarioRegistration,
) -> dict[str, _EvidenceSource]:
    schema_by_key = {field.key: field for field in profile.field_schema}
    sources = {
        field_key: _EvidenceSource(field_key, schema_by_key[field_key].label, value)
        for field_key in profile.stage_b_evidence_field_keys
        if field_key in schema_by_key
        if (value := _text(input_payload.get(field_key)))
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
        if value := _text(raw_value):
            sources[field_key] = _EvidenceSource(field_key, field_label, value)
    return sources


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


def _business_evidence_ref(source: _EvidenceSource) -> dict[str, object]:
    return {
        "type": "business",
        "field_key": source.field_key,
        "field_label": source.field_label,
        "excerpt": source.value[:MAX_EVIDENCE_EXCERPT_LENGTH].rstrip(),
    }


def _serialize_label(label: FiveArticlesMappingLabel) -> dict[str, object]:
    return {
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
        "match_method": label.match_method,
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


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _strip_whitespace(value: str) -> str:
    return _WHITESPACE_PATTERN.sub("", value)
