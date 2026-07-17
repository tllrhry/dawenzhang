import json
from collections.abc import Mapping, Sequence

from app.services.five_articles_policies import get_five_articles_policy
from app.services.five_articles_stage_b_evidence import (
    MAX_EVIDENCE_EXCERPT_LENGTH,
    build_business_sources,
    serialize_label,
    text,
)
from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


def build_stage_b_request_payload(
    input_payload: Mapping[str, object],
    stage_a_snapshot: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    model: str,
    profile: ScenarioRegistration,
    *,
    same_code: bool,
) -> dict[str, object]:
    policy = get_five_articles_policy(profile.id)
    field_payload = [
        {"field_key": field.key, "field_label": field.label, "value": value}
        for field in profile.field_schema
        if (value := text(input_payload.get(field.key)))
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
            for source in build_business_sources(
                input_payload, stage_a_snapshot, profile
            ).values()
        ],
        "enterprise_labels": [serialize_label(label) for label in enterprise_labels],
        "loan_direction_labels": [
            serialize_label(label) for label in loan_direction_labels
        ],
        "same_four_digit_code": same_code,
        "max_excerpt_length": MAX_EVIDENCE_EXCERPT_LENGTH,
    }
    is_single_label = len(loan_direction_labels) == 1
    missing_enterprise_instruction = policy.missing_enterprise_instruction()
    consistency_instruction = (
        (
            "企业四位码与投向四位码相同，一致性由服务端确定为 consistent；"
            "根对象只能返回 label_basis，不得返回 consistency。"
            if is_single_label
            else "企业四位码与投向四位码相同，一致性由服务端确定为 consistent；"
            "根对象只能返回 label_bases，不得返回 consistency。"
        )
        if same_code
        else (
            "两码不同，根对象必须返回 "
            + ("label_basis" if is_single_label else "label_bases")
            + " 和 consistency。consistency 只能包含 "
            "status、basis，不得返回任何 evidence_refs。status 只能是 consistent、"
            "inconsistent 或 "
            "needs_review：企业和投向标签存在交集且资金服务企业现有主营或科技活动才可"
            "为 consistent；标签无交集或资金明确流向无关独立活动可为 inconsistent；"
            + missing_enterprise_instruction
            + "用途笼统、证据冲突或业务证据不足必须为 needs_review。不得仅凭两码"
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
            "按输入候选的原始顺序输出 label_bases 数组；数组条目数量必须与候选数量一致。"
            "不得新增、删除、重排或替换任何候选；标签固定字段不由模型返回。"
        )
        output_instruction = (
            "每个 label_bases 条目只能包含 matching_basis 和 business_evidence_refs。"
            "每个条目的 matching_basis 都是对应候选的中文匹配依据，且 business_evidence_refs 至少一条；"
        )
        evidence_instruction = (
            "business_evidence_refs 必须全部是 business 证据；对应候选的 mapping 证据由服务端组装。"
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
                    "不得把数组直接作为最外层值，不得包含 JSON 以外的任何文字。"
                    "多标签同码时最外层形态必须是 {\"label_bases\":[...]}。"
                    "输入中的 enterprise_labels 和 "
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
                    "必须输出 needs_review。"
                    + consistency_instruction
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_input, ensure_ascii=False),
            },
        ],
    }

