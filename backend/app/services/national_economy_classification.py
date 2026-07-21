import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import Settings
from app.services.national_economy_decision_policy import (
    EvidenceLayer,
    EvidenceLevel,
    LoanDirectionRoute,
)
from app.services.national_economy_retrieval import EvidenceSnapshot, display_chunk_type


ClassificationStatus = Literal["completed", "needs_review"]
LoanSpecificity = Literal["generic", "specific"]
_ENTERPRISE_SUCCESS_OUTPUT_FIELDS = frozenset(
    {"no_match", "industry_code", "industry_name", "matching_basis"}
)
_ENTERPRISE_NO_MATCH_OUTPUT_FIELDS = frozenset({"no_match", "reason"})
_LOAN_INHERITED_OUTPUT_FIELDS = frozenset(
    {"route", "matching_basis", "specificity"}
)
_LOAN_CLASSIFIED_SUCCESS_OUTPUT_FIELDS = frozenset(
    {
        "route",
        "no_match",
        "industry_code",
        "industry_name",
        "matching_basis",
        "specificity",
    }
)
_LOAN_CLASSIFIED_NO_MATCH_OUTPUT_FIELDS = frozenset(
    {"route", "no_match", "reason", "specificity"}
)
_DUAL_OUTPUT_FIELDS = frozenset({"enterprise", "loan_direction"})
_MAX_MODEL_VALIDATION_ATTEMPTS = 3


class NationalEconomyClassificationError(RuntimeError):
    """Raised when DeepSeek cannot produce a valid constrained classification."""


@dataclass(frozen=True)
class ConstrainedClassificationResult:
    status: ClassificationStatus
    industry_code: str | None
    industry_name: str | None
    confidence: float | None
    matching_basis: str
    summary: str | None
    candidate_snapshot: tuple[dict[str, object], ...]
    objection: dict[str, object] | None
    model_output: dict[str, object]
    industry_major_code: str | None = None
    industry_category_name: str | None = None
    industry_middle_code: str | None = None
    industry_middle_name: str | None = None
    loan_industry_code: str | None = None
    loan_industry_major_code: str | None = None
    loan_industry_category_name: str | None = None
    loan_industry_middle_code: str | None = None
    loan_industry_middle_name: str | None = None
    loan_industry_name: str | None = None
    loan_matching_basis: str | None = None
    loan_specificity: LoanSpecificity | None = None
    loan_matches_enterprise: bool | None = None


def classify_national_economy(
    evidence_layers: Sequence[EvidenceLayer],
    candidates: Sequence[EvidenceSnapshot],
    settings: Settings,
    objection: Mapping[str, object] | None = None,
    client: httpx.Client | None = None,
    loan_direction_candidates: Sequence[EvidenceSnapshot] = (),
) -> ConstrainedClassificationResult:
    if not candidates:
        raise ValueError("at least one industry candidate is required")
    if not settings.deepseek_api_key:
        raise NationalEconomyClassificationError(
            "DEEPSEEK_API_KEY is required for classification"
        )

    candidate_snapshot = tuple(_serialize_candidate(candidate) for candidate in candidates)
    loan_direction_candidate_snapshot = tuple(
        _serialize_candidate(candidate) for candidate in loan_direction_candidates
    )
    request_payload = _build_request_payload(
        evidence_layers,
        candidate_snapshot,
        loan_direction_candidate_snapshot,
        settings.deepseek_model,
        objection,
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
        for attempt in range(_MAX_MODEL_VALIDATION_ATTEMPTS):
            try:
                response = http_client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json=request_payload,
                )
                response.raise_for_status()
            except httpx.TransportError:
                if attempt == _MAX_MODEL_VALIDATION_ATTEMPTS - 1:
                    raise
                continue
            response_payload = response.json()
            try:
                return _validate_model_response(
                    response_payload,
                    candidates,
                    loan_direction_candidates,
                    candidate_snapshot,
                    objection,
                )
            except NationalEconomyClassificationError as exc:
                if attempt == _MAX_MODEL_VALIDATION_ATTEMPTS - 1:
                    raise
                messages = list(request_payload["messages"])
                try:
                    previous_content = response_payload["choices"][0]["message"][
                        "content"
                    ]
                except (TypeError, KeyError, IndexError):
                    previous_content = None
                if isinstance(previous_content, str) and previous_content.strip():
                    messages.append(
                        {"role": "assistant", "content": previous_content}
                    )
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上次 JSON 未通过服务端契约校验："
                            f"{exc}。请重新检查全部业务证据与两组候选并返回完整 JSON。"
                            "不得放宽候选约束，不得沿用矛盾结论。尤其当贷款投向选择 "
                            "use_enterprise_conclusion 时，先依据主导主营重新逐项检查企业候选，"
                            "若存在语义或结构上覆盖主导主营的企业候选，必须选出该候选并保持"
                            "继承路由，不得仅为消除格式矛盾而改成独立分类。只有全部企业候选"
                            "确实不匹配时，贷款投向才不得选择继承路由。"
                        ),
                    }
                )
                request_payload = {**request_payload, "messages": messages}
        raise AssertionError("unreachable model validation loop")
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise NationalEconomyClassificationError(
            f"DeepSeek classification failed: {exc}"
        ) from exc
    finally:
        if owns_client:
            http_client.close()


def _build_request_payload(
    evidence_layers: Sequence[EvidenceLayer],
    candidate_snapshot: Sequence[dict[str, object]],
    loan_direction_candidate_snapshot: Sequence[dict[str, object]],
    model: str,
    objection: Mapping[str, object] | None,
) -> dict[str, object]:
    ordered_layers = tuple(sorted(evidence_layers, key=lambda layer: layer.level))
    dominant_main_business = next(
        (
            fact.indicated_business.strip()
            for layer in ordered_layers
            if layer.level is EvidenceLevel.MAIN_BUSINESS_REVENUE
            for fact in layer.usable_facts
            if fact.field_label == "主营业务及营收占比（主导主营）"
        ),
        None,
    )
    prompt_input: dict[str, object] = {
        "dominant_main_business": dominant_main_business,
        "ordered_evidence": [
            _serialize_evidence_layer(layer) for layer in ordered_layers
        ],
        "enterprise_candidates": list(candidate_snapshot),
        "loan_direction_candidates": list(loan_direction_candidate_snapshot),
    }
    if objection is not None:
        prompt_input["objection"] = dict(objection)
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 GB/T 4754-2017 国民经济行业分类器。只能依据企业输入、"
                    "异议（如有）和两组给定候选的定义/命中片段作答，不得使用或声称使用"
                    "候选外目录、企业清单、涉农规则或其他标签。企业证据已按 priority=1"
                    "到 4 排序：主营业务及营收、贸易合同及产业链、贷款用途、营业执照"
                    "经营范围。必须采用最高可用层；低层冲突不得推翻高层，只有高层不可用"
                    "才可降级。异议已并入 ordered_evidence 的既有层，不是第五级。"
                    "当 dominant_main_business 非空时，表示原文存在单项占比不低于50%的"
                    "唯一主导主营：企业结论必须落在该主导主营对应的四级行业，绝对不得因"
                    "核心产品/服务中的其他条目或更低占比业务线改判；该锁定只约束企业结论。"
                    "此时只有 dominant_main_business 才是本次比较中的主营；低于50%的其他"
                    "业务线即使已登记、已有收入或属于经营范围，也不得称为主营，不得据此将"
                    "其贷款投向回落为企业结论。"
                    "当 dominant_main_business 为空时，不存在主导主营锁定，企业结论继续按"
                    "上述四级证据优先级综合判定，既有行为不变。"
                    "企业结论与贷款投向结论都必须以各自候选携带的完整目录定义、包括和"
                    "不包括逐条校验：所选行业必须有业务证据命中其包括中的至少一条，且"
                    "业务证据不得命中其不包括；业务证据与候选定义相斥，或命中候选不包括"
                    "时，必须排除该候选，不得仅因候选重排靠前而选中。matching_basis 必须"
                    "明确指出业务证据命中了所选行业包括中的哪一条。语义匹配不要求业务原文"
                    "与目录逐字重复；目录中的概括项、其他项或未列明项可以覆盖语义明确的同类"
                    "经营活动。只有全部企业候选都与主导主营定义相斥、命中不包括项或属于不同"
                    "经营活动时，企业结论才可返回 no_match，不得仅因业务名称比目录更细而"
                    "拒绝最匹配候选。门类级结构性判别原则"
                    "数量有限，不得逐项业务枚举关键词：批发与零售按客户对象区分，面向经营"
                    "单位、经销商或集团等客户的销售属于批发，面向最终消费者的销售属于零售。"
                    "购买软件产品、软件著作权、源代码、算法模型或成套技术包，资金流向软件"
                    "研发提供方的，属于购买软件产品与技术，归入软件开发相关行业；知识产权"
                    "服务仅指知识产权代理、登记、鉴定、评估、检索及交易中介等专门服务活动，"
                    "不得仅因交易标的为著作权转让就把软件技术购买归入知识产权服务。"
                    "判定贷款真实投向时必须融合三类证据：贷款用途详细描述是主信号，"
                    "贸易合同核心交易品类用于揭示并校正资金真实流向，授信审批意见是"
                    "资金用途的刚性约束。固定仲裁优先顺序为贷款用途详细描述高于贸易合同"
                    "核心交易品类，贸易合同核心交易品类高于授信审批意见。贷款用途明确且"
                    "符合实际流向时作为首要依据；贷款用途笼统或与能够证明实际资金流向的"
                    "贸易合同不符时，必须由贸易合同校正真实投向；贸易合同与授信审批意见"
                    "冲突时必须以贸易合同揭示的资金真实流向为准。不得采用逐级降级只取"
                    "最高可用层的布尔机制，不得因某一类证据可用就丢弃其余证据，必须综合"
                    "三类证据得出真实投向。该融合只决定贷款投向，不得改变企业结论。"
                    "必须先区分交易对象、项目终端用途与借款人实际开展的经营活动。购买原材料、"
                    "库存商品、生产设备等直接进入主导主营产品/服务生产、销售或交付的投入品，"
                    "真实投向仍是该主导主营，不得改判为投入品所属行业。借款人以自身"
                    "主导主营能力为客户交付项目时，客户所属行业、项目服务对象或项目终端用途"
                    "也不得改变借款人实际开展的经营活动。借款人自身使用资金开展另一项"
                    "生产、销售、运营或投资活动时，真实投向为该项经营活动对应的行业；"
                    "购置车辆、设备、物资用于自身开展该活动的，归入该活动本身，不得归入"
                    "所购设备或物资的制造行业。将资金支付给其他行业购买员工培训、软件"
                    "技术等独立服务或无形资产、购买行为本身即资金最终用途且不构成主导"
                    "主营产品/服务生产交付投入时，同样属于不同经营活动，真实投向为资金"
                    "收款方所提供产品或服务对应的行业；贷款用途明确声明不用于主营业务"
                    "投入时，不得返回 route=use_enterprise_conclusion。"
                    "贷款投向必须按以下决策树判定：一、贷款用途为空或仅为经营周转、"
                    "流动资金、经营使用等笼统表述，且贸易合同未揭示具体非主营经营领域、"
                    "授信审批意见也未限定具体经营领域时，返回 specificity=generic、"
                    "route=use_enterprise_conclusion，由服务端继承企业结论；二、融合三类"
                    "证据得出的具体用途服务于 dominant_main_business 所指主导主营，包括"
                    "为主导主营采购投入品、备货、设备，或以主导主营能力交付不同客户/终端"
                    "用途的项目时，返回 specificity=specific、route=use_enterprise_conclusion，"
                    "只说明用途如何服务于主导主营，不返回贷款行业代码和名称；三、具体用途"
                    "属于低占比业务线或其他经营活动时，无论是否已登记在营业执照经营范围内，"
                    "都返回 specificity=specific、route=classify_actual_direction，并依据"
                    "融合后的真实资金流向和 loan_direction_candidates 的完整目录定义独立分类；"
                    "不得因为该活动是已登记业务、已有少量收入或使用相似原材料而回落企业结论。"
                    "营业执照经营范围只用于说明企业现有经营边界，不得作为否定真实贷款投向或"
                    "拒绝选择候选的门槛。四、只有给定候选均无法覆盖真实投向时，贷款投向才"
                    "返回 no_match=true 及非空 reason；reason 必须说明候选定义为何不匹配或"
                    "业务证据为何不足，不得仅以不属于主营或不在营业执照经营范围内为由返回"
                    "无匹配，也不得臆造代码或名称。matching_basis 与 reason 的内容必须全中文，"
                    "不得出现任何英文词元，包括英文单词、字母缩写或英文片段类型标签。依据"
                    "必须直接用业务语言陈述结论与支撑事实，引用主营、营收占比、贸易、贷款"
                    "用途等具体内容以及"
                    "命中的目录片段；不得写采用了哪个优先级、字段或证据层，也不得描述内部"
                    "降级和字段调度过程。贷款投向 matching_basis 必须明确指明真实投向依据"
                    "贷款用途、贸易合同核心交易品类、授信审批意见中的哪一类或哪几类证据"
                    "判定，并写明真实投向命中的业务事实及对应四级代码；真实投向不属于主营或"
                    "不在营业执照经营范围内时，应如实说明资金流向与企业现有经营边界不同，但"
                    "仍须按实际资金用途完成分类。企业代码/名称只能从 enterprise_candidates"
                    "的同一记录选择。贷款投向 route=use_enterprise_conclusion 时只能返回"
                    "route、specificity 和 matching_basis，行业代码/名称由服务端继承企业"
                    "结论；route=classify_actual_direction 时，成功代码/名称只能从 "
                    "loan_direction_candidates 的同一记录选择。必须仅返回 JSON，根对象只能"
                    "包含 enterprise 和 loan_direction。企业成功结论返回 no_match=false、"
                    "industry_code、industry_name、matching_basis；企业无匹配返回"
                    "no_match=true 和非空 reason。独立分类的贷款成功结论返回 route、"
                    "no_match=false、industry_code、industry_name、matching_basis、specificity；"
                    "独立分类无匹配返回 route、no_match=true、非空 reason、specificity。"
                    "不得返回置信度、AI 总结或 matched；"
                    "一致性由服务端复算。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_input, ensure_ascii=False),
            },
        ],
    }


def _serialize_candidate(candidate: EvidenceSnapshot) -> dict[str, object]:
    return {
        "category_name": candidate.category_name,
        "major_category_code": candidate.major_category_code,
        "major_category_name": candidate.major_category_name,
        "middle_category_code": candidate.middle_category_code,
        "middle_category_name": candidate.middle_category_name,
        "industry_code": candidate.industry_code,
        "industry_name": candidate.industry_name,
        "complete_catalog_fragments": [
            {
                "chunk_type": display_chunk_type(hit.chunk_type),
                "text": hit.text,
                "source_row": hit.source_row,
            }
            for hit in candidate.hits
        ],
        "evidence_traces": [
            {
                "priority": int(trace.level),
                "level": trace.level.name,
                "facts": [
                    {
                        "field_label": fact.field_label,
                        "raw_text": fact.raw_text,
                        "source": fact.source,
                    }
                    for fact in trace.facts
                ],
                "matched_catalog_fragments": [
                    {
                        "chunk_type": display_chunk_type(hit.chunk_type),
                        "text": hit.text,
                        "source_row": hit.source_row,
                    }
                    for hit in trace.hits
                ],
            }
            for trace in candidate.evidence_traces
        ],
        "vector_score": candidate.vector_score,
        "rerank_score": candidate.rerank_score,
    }


def _serialize_evidence_layer(layer: EvidenceLayer) -> dict[str, object]:
    return {
        "priority": int(layer.level),
        "level": layer.level.name,
        "available": layer.is_available,
        "unavailable_reason": layer.unavailable_reason,
        "facts": [
            {
                "field_label": fact.field_label,
                "raw_text": fact.raw_text,
                "source": fact.source,
            }
            for fact in layer.facts
        ],
    }


def _validate_model_response(
    response_payload: object,
    candidates: Sequence[EvidenceSnapshot],
    loan_direction_candidates: Sequence[EvidenceSnapshot],
    candidate_snapshot: tuple[dict[str, object], ...],
    objection: Mapping[str, object] | None,
) -> ConstrainedClassificationResult:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise NationalEconomyClassificationError(
            "DeepSeek response is missing choices[0].message.content"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise NationalEconomyClassificationError("DeepSeek response content must be non-empty")
    try:
        model_output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise NationalEconomyClassificationError(
            "DeepSeek response content is not valid JSON"
        ) from exc
    if not isinstance(model_output, dict):
        raise NationalEconomyClassificationError("DeepSeek model output must be a JSON object")
    _require_exact_output_fields(model_output, _DUAL_OUTPUT_FIELDS, branch="dual")
    enterprise_output = _required_object(model_output, "enterprise")
    loan_output = _required_object(model_output, "loan_direction")
    enterprise_no_match = _required_boolean(enterprise_output, "no_match", "enterprise")
    loan_route = _required_loan_route(loan_output)
    loan_specificity = _required_specificity(loan_output)
    objection_snapshot = dict(objection) if objection is not None else None

    enterprise_code: str | None = None
    enterprise_name: str | None = None
    enterprise_candidate: EvidenceSnapshot | None = None
    if enterprise_no_match:
        _require_exact_output_fields(
            enterprise_output,
            _ENTERPRISE_NO_MATCH_OUTPUT_FIELDS,
            branch="enterprise no_match",
        )
        enterprise_basis = _required_text(enterprise_output, "reason")
    else:
        _require_exact_output_fields(
            enterprise_output,
            _ENTERPRISE_SUCCESS_OUTPUT_FIELDS,
            branch="enterprise successful",
        )
        enterprise_code = _required_text(enterprise_output, "industry_code")
        enterprise_name = _required_text(enterprise_output, "industry_name")
        enterprise_basis = _required_text(enterprise_output, "matching_basis")
        enterprise_candidate = _require_candidate_pair(
            enterprise_code,
            enterprise_name,
            candidates,
            branch="enterprise",
        )

    loan_code: str | None = None
    loan_name: str | None = None
    loan_candidate: EvidenceSnapshot | None = None
    if loan_route is LoanDirectionRoute.USE_ENTERPRISE_CONCLUSION:
        _require_exact_output_fields(
            loan_output,
            _LOAN_INHERITED_OUTPUT_FIELDS,
            branch="loan_direction inherited",
        )
        if enterprise_code is None or enterprise_candidate is None:
            raise NationalEconomyClassificationError(
                "loan_direction cannot inherit an unsuccessful enterprise conclusion"
            )
        loan_no_match = False
        loan_code = enterprise_code
        loan_name = enterprise_name
        loan_candidate = enterprise_candidate
        loan_basis = _required_text(loan_output, "matching_basis")
    else:
        if loan_specificity != "specific":
            raise NationalEconomyClassificationError(
                "classify_actual_direction requires specificity=specific"
            )
        loan_no_match = _required_boolean(
            loan_output, "no_match", "loan_direction"
        )
        if loan_no_match:
            _require_exact_output_fields(
                loan_output,
                _LOAN_CLASSIFIED_NO_MATCH_OUTPUT_FIELDS,
                branch="loan_direction no_match",
            )
            loan_basis = _required_text(loan_output, "reason")
        else:
            _require_exact_output_fields(
                loan_output,
                _LOAN_CLASSIFIED_SUCCESS_OUTPUT_FIELDS,
                branch="loan_direction successful",
            )
            loan_code = _required_text(loan_output, "industry_code")
            loan_name = _required_text(loan_output, "industry_name")
            loan_basis = _required_text(loan_output, "matching_basis")
            loan_candidate = _require_candidate_pair(
                loan_code,
                loan_name,
                loan_direction_candidates,
                branch="loan_direction",
            )

    enterprise_major_code = (
        enterprise_candidate.major_category_code
        if enterprise_candidate is not None
        else None
    )
    loan_major_code = (
        loan_candidate.major_category_code if loan_candidate is not None else None
    )
    if loan_route is LoanDirectionRoute.USE_ENTERPRISE_CONCLUSION:
        loan_major_code = enterprise_major_code
    enterprise_middle_code = (
        enterprise_candidate.middle_category_code
        if enterprise_candidate is not None and len(enterprise_code or "") == 4
        else None
    )
    enterprise_middle_name = (
        enterprise_candidate.middle_category_name if enterprise_middle_code else None
    )
    loan_middle_code = (
        loan_candidate.middle_category_code
        if loan_candidate is not None and len(loan_code or "") == 4
        else None
    )
    loan_middle_name = loan_candidate.middle_category_name if loan_middle_code else None
    enterprise_category_name = enterprise_candidate.category_name if enterprise_candidate else None
    loan_category_name = loan_candidate.category_name if loan_candidate else None
    if loan_route is LoanDirectionRoute.USE_ENTERPRISE_CONCLUSION:
        loan_middle_code = enterprise_middle_code
        loan_middle_name = enterprise_middle_name
        loan_category_name = enterprise_category_name

    loan_matches_enterprise = (
        loan_code == enterprise_code
        if loan_code is not None and enterprise_code is not None
        else None
    )
    return ConstrainedClassificationResult(
        status=(
            "needs_review" if enterprise_no_match or loan_no_match else "completed"
        ),
        industry_code=enterprise_code,
        industry_name=enterprise_name,
        confidence=None,
        matching_basis=enterprise_basis,
        summary=None,
        candidate_snapshot=candidate_snapshot,
        objection=objection_snapshot,
        model_output=model_output,
        industry_major_code=enterprise_major_code,
        industry_category_name=enterprise_category_name,
        industry_middle_code=enterprise_middle_code,
        industry_middle_name=enterprise_middle_name,
        loan_industry_code=loan_code,
        loan_industry_major_code=loan_major_code,
        loan_industry_category_name=loan_category_name,
        loan_industry_middle_code=loan_middle_code,
        loan_industry_middle_name=loan_middle_name,
        loan_industry_name=loan_name,
        loan_matching_basis=loan_basis,
        loan_specificity=loan_specificity,
        loan_matches_enterprise=loan_matches_enterprise,
    )


def _required_object(
    payload: Mapping[str, object], field: str
) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise NationalEconomyClassificationError(
            f"model output {field} must be a JSON object"
        )
    return value


def _required_boolean(
    payload: Mapping[str, object], field: str, branch: str
) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise NationalEconomyClassificationError(
            f"{branch} model output {field} must be a boolean"
        )
    return value


def _required_specificity(
    loan_output: Mapping[str, object],
) -> LoanSpecificity:
    value = loan_output.get("specificity")
    if value not in {"generic", "specific"}:
        raise NationalEconomyClassificationError(
            "loan_direction specificity must be generic or specific"
        )
    return value


def _required_loan_route(
    loan_output: Mapping[str, object],
) -> LoanDirectionRoute:
    value = loan_output.get("route")
    if value not in {
        LoanDirectionRoute.USE_ENTERPRISE_CONCLUSION.value,
        LoanDirectionRoute.CLASSIFY_ACTUAL_DIRECTION.value,
    }:
        raise NationalEconomyClassificationError(
            "loan_direction route must be use_enterprise_conclusion or "
            "classify_actual_direction"
        )
    return LoanDirectionRoute(value)


def _require_candidate_pair(
    industry_code: str,
    industry_name: str,
    candidates: Sequence[EvidenceSnapshot],
    *,
    branch: str,
) -> EvidenceSnapshot:
    matched_candidate = next(
        (
            candidate
            for candidate in candidates
            if (candidate.industry_code, candidate.industry_name)
            == (industry_code, industry_name)
        ),
        None,
    )
    if matched_candidate is None:
        raise NationalEconomyClassificationError(
            f"{branch} industry_code and industry_name must exactly match the same candidate"
        )
    return matched_candidate


def _require_exact_output_fields(
    payload: Mapping[str, object],
    expected_fields: frozenset[str],
    *,
    branch: str,
) -> None:
    actual_fields = set(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        unexpected = sorted(actual_fields - expected_fields)
        raise NationalEconomyClassificationError(
            f"{branch} model output fields do not match contract; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NationalEconomyClassificationError(f"model output {field} must be non-empty")
    return value.strip()
