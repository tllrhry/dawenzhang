import { Alert, Card, Descriptions, Divider, Tag } from 'antd'
import { CheckCircleFilled, SafetyCertificateOutlined } from '@ant-design/icons'

import { DIGITAL_FINANCE_SCENARIO, GREEN_FINANCE_SCENARIO, PENSION_FINANCE_SCENARIO, TECHNOLOGY_FINANCE_SCENARIO } from '../api'
import type { EvidenceReference, FiveArticlesResult, InclusiveFinanceResult, ScenarioId } from '../api'
import { scenarioViews } from '../scenarios'


export const stageBStatusLabels: Record<Exclude<FiveArticlesResult['status'], 'not_applicable'>, string> = {
  completed: '判定已完成',
  needs_review: '待人工复核',
  classification_failed: '判定失败',
}

export const consistencyLabels: Record<NonNullable<FiveArticlesResult['consistency_status']>, string> = {
  consistent: '一致',
  inconsistent: '不一致',
  needs_review: '待人工复核',
  not_applicable: '不适用',
}

export function stageBStatusLabel(scenarioId: ScenarioId, status: FiveArticlesResult['status']): string {
  return status === 'not_applicable' ? `不属于${scenarioViews[scenarioId].name}` : stageBStatusLabels[status]
}

export function stageBEmptyDescription(scenarioId: ScenarioId, result: FiveArticlesResult): string {
  const scenarioName = scenarioViews[scenarioId].name
  return result.error_detail || result.consistency_basis || (result.status === 'not_applicable' ? `有效${scenarioName}映射中未命中该贷款投向，因此不属于${scenarioName}。` : `当前没有可展示的正式${scenarioName}标签。`)
}

export function statusColor(status: FiveArticlesResult['status']): string {
  if (status === 'completed') return 'success'
  if (status === 'not_applicable') return 'default'
  if (status === 'classification_failed') return 'error'
  return 'warning'
}

function consistencyColor(status: FiveArticlesResult['consistency_status']): string {
  if (status === 'consistent') return 'success'
  if (status === 'inconsistent') return 'error'
  if (status === 'needs_review') return 'warning'
  return 'default'
}

function evidenceSummary(reference: EvidenceReference): string {
  if (reference.type === 'mapping') {
    const path = reference.taxonomy_path?.filter(Boolean).join(' / ')
    return `映射版本 ${reference.mapping_version_id ?? '--'} · 源行 ${reference.source_row ?? '--'} · ${reference.NEIC_Code || '--'} ${reference.NEIC_Name || ''}${path ? ` · ${path}` : ''}`
  }
  if (reference.type === 'pension_matrix') {
    const normalized = reference.normalized_percent === null || reference.normalized_percent === undefined
      ? '未知'
      : `${reference.normalized_percent}%`
    return `${reference.field_label || '比例字段'}：原始值 ${String(reference.raw_value ?? '--')} · 规范化 ${normalized}`
  }
  if (reference.type === 'pension_qualification') {
    return reference.warning || `${reference.field_label || '养老资质'}：${reference.excerpt || '--'}`
  }
  if (reference.type === 'digital_direction') {
    const path = reference.taxonomy_path?.filter(Boolean).join(' / ')
    return `${reference.digital_category || '数字类别待确认'}${path ? ` · ${path}` : ''}`
  }
  if (reference.type === 'digital_auxiliary') {
    return reference.warning || `${reference.field_label || '数字辅助证据'}：${reference.excerpt || '--'}`
  }
  if (reference.type === 'green_direction') {
    const path = reference.taxonomy_path?.filter(Boolean).join(' / ')
    return `${reference.subject || '绿色目录'}${path ? ` · ${path}` : ''} · ${reference.match_method === 'condition_fallback' ? '条件回退命中' : '行业编码命中'}`
  }
  if (reference.type === 'green_auxiliary' || reference.type === 'green_violation') {
    return reference.warning || `${reference.field_label || '绿色辅助证据'}：${reference.excerpt || '--'}`
  }
  if (reference.type === 'technology_direction') {
    const path = reference.taxonomy_path?.filter(Boolean).join(' / ')
    return reference.mapping_hit
      ? `命中科技金融映射：${reference.NEIC_Code || '--'} ${reference.NEIC_Name || ''}${path ? ` · ${path}` : ''}`
      : '贷款实际投向未命中科技金融映射'
  }
  if (reference.type === 'technology_auxiliary') {
    return reference.warning || `${reference.field_label || '科技辅助证据'}：${reference.excerpt || '--'}`
  }
  return `${reference.field_label || reference.field_key || '业务证据'}：${reference.excerpt || '--'}`
}

function auxiliaryStatusLabel(status: unknown): string {
  if (status === 'satisfied') return '满足'
  if (status === 'unsatisfied') return '未满足'
  return '未知'
}

function technologyAuxiliaryValue(reference: EvidenceReference): string {
  const status = auxiliaryStatusLabel(reference.status)
  if (reference.evidence_role === 'rd_staff_ratio') {
    return reference.normalized_percent === null || reference.normalized_percent === undefined
      ? status
      : `${status} · ${reference.normalized_percent}%（参考阈值 10%）`
  }
  if (reference.evidence_role === 'rd_investment_ratio') {
    const amount = reference.normalized_amount_wan === null || reference.normalized_amount_wan === undefined
      ? '研发投入未知'
      : `研发投入 ${reference.normalized_amount_wan} 万元`
    const ratio = reference.derived_ratio_percent === null || reference.derived_ratio_percent === undefined
      ? '研发投入占营收比例未知'
      : `研发投入占营收 ${reference.derived_ratio_percent}%（参考阈值 3%）`
    return `${status} · ${amount} · ${ratio}`
  }
  return `${status}${reference.excerpt ? ` · ${reference.excerpt}` : ''}`
}

function technologyAuxiliaryLabel(reference: EvidenceReference): string {
  if (reference.evidence_role === 'official_qualification') return '企业核心资质与认证'
  if (reference.evidence_role === 'rd_staff_ratio') return '研发人员占比'
  if (reference.evidence_role === 'rd_investment_ratio') return '研发投入占营收比例'
  if (reference.evidence_role === 'patent_software_copyright') return '专利或软著等'
  return reference.field_label || '科技辅助证据'
}

function technologyDecisionDetails(result: FiveArticlesResult | null) {
  if (!result) return null
  const directionRef = result.consistency_evidence_refs.find((reference) => reference.type === 'technology_direction')
  const auxiliaryRefs = result.consistency_evidence_refs.filter((reference) => reference.type === 'technology_auxiliary')
  const registryRefs = result.consistency_evidence_refs.filter((reference) => reference.type === 'technology_registry')
  if (!directionRef && auxiliaryRefs.length === 0 && registryRefs.length === 0) return null
  return {
    directionRef,
    auxiliaryRefs,
    registryRefs,
    warnings: [...auxiliaryRefs, ...registryRefs]
      .map((reference) => reference.warning)
      .filter((warning): warning is string => Boolean(warning)),
  }
}

function pensionDecisionDetails(result: FiveArticlesResult | null) {
  if (!result) return null
  const matrixRefs = result.consistency_evidence_refs.filter((reference) => reference.type === 'pension_matrix')
  const qualificationRef = result.consistency_evidence_refs.find((reference) => reference.type === 'pension_qualification')
  if (matrixRefs.length === 0) return null
  return {
    matrixRefs,
    qualificationWarning: qualificationRef?.warning,
    qualificationEvidence: qualificationRef?.excerpt,
  }
}

function digitalDecisionDetails(result: FiveArticlesResult | null) {
  if (!result) return null
  const directionRef = result.consistency_evidence_refs.find((reference) => reference.type === 'digital_direction')
  const auxiliaryRefs = result.consistency_evidence_refs.filter((reference) => reference.type === 'digital_auxiliary')
  const category = result.labels.find((label) => label.digital_category)?.digital_category || directionRef?.digital_category
  if (!category && auxiliaryRefs.length === 0) return null
  return {
    category,
    auxiliaryRefs,
    warnings: auxiliaryRefs.map((reference) => reference.warning).filter((warning): warning is string => Boolean(warning)),
  }
}

function greenDecisionDetails(result: FiveArticlesResult | null) {
  if (!result) return null
  const directionRef = result.consistency_evidence_refs.find((reference) => reference.type === 'green_direction')
  const auxiliaryRefs = result.consistency_evidence_refs.filter((reference) => reference.type === 'green_auxiliary')
  const violationRef = result.consistency_evidence_refs.find((reference) => reference.type === 'green_violation')
  if (!directionRef && auxiliaryRefs.length === 0 && !violationRef) return null
  return {
    directionRef,
    auxiliaryRefs,
    violationRef,
    warnings: [...auxiliaryRefs, ...(violationRef ? [violationRef] : [])]
      .map((reference) => reference.warning)
      .filter((warning): warning is string => Boolean(warning)),
  }
}

const ipIntensiveIndustrySubjects = new Set(['知识产权（专利）密集型产业', '知识产权(专利)密集型产业'])

function technologyRegistryHits(result: FiveArticlesResult | null): { specializedInnovation: boolean; highTech: boolean } {
  if (!result) return { specializedInnovation: false, highTech: false }
  const registryRefs = result.consistency_evidence_refs.filter((reference) => reference.type === 'technology_registry')
  return {
    specializedInnovation: registryRefs.some((reference) => reference.registry_type === 'specialized_innovation' && reference.matched === true),
    highTech: registryRefs.some((reference) => reference.registry_type === 'high_tech' && reference.matched === true),
  }
}

export function FiveArticlesResultCard({ scenarioId, result, stageAFailed, stageAStatusLabel }: {
  scenarioId: ScenarioId
  result: FiveArticlesResult | null
  stageAFailed: boolean
  stageAStatusLabel: string
}) {
  const scenarioView = scenarioViews[scenarioId]
  const registryHits = scenarioId === TECHNOLOGY_FINANCE_SCENARIO
    ? technologyRegistryHits(result)
    : { specializedInnovation: false, highTech: false }
  const pensionDetails = scenarioId === PENSION_FINANCE_SCENARIO
    ? pensionDecisionDetails(result)
    : null
  const digitalDetails = scenarioId === DIGITAL_FINANCE_SCENARIO
    ? digitalDecisionDetails(result)
    : null
  const greenDetails = scenarioId === GREEN_FINANCE_SCENARIO
    ? greenDecisionDetails(result)
    : null
  const technologyDetails = scenarioId === TECHNOLOGY_FINANCE_SCENARIO
    ? technologyDecisionDetails(result)
    : null
  const title = <span className="technology-card-title">
    <span>{`Stage B · ${scenarioView.name}判定`}</span>
    {registryHits.specializedInnovation && <Tag color="success" icon={<CheckCircleFilled />}>命中专精特新企业名单</Tag>}
    {registryHits.highTech && <Tag color="processing" icon={<SafetyCertificateOutlined />}>命中高新技术名单</Tag>}
  </span>

  return <Card className="result-card technology-result-card" bordered={false} title={title}>
    {result ? <>
      <div className="technology-status-row">
        <div><span>判定状态</span><Tag className="key-decision-tag" color={statusColor(result.status)}>{stageBStatusLabel(scenarioId, result.status)}</Tag></div>
        <small>{scenarioView.name}版本 {result.version} · Stage A 结果 #{result.stage_a_result_id}{result.mapping_version_id ? ` · 映射版本 ${result.mapping_version_id}` : ''}</small>
      </div>
      {result.labels.length > 0 ? <div className="technology-label-list">
        {result.labels.map((label, index) => <section className="technology-label" key={`${label.subject}-${label.source_row}-${index}`}>
          <div className="technology-label-heading"><Tag color="blue">{label.subject}</Tag><strong>{label.NEIC_Code} · {label.NEIC_Name}</strong></div>
          <Descriptions column={{ xs: 1, sm: 2 }} size="small">
            {label.taxonomy_path.map((tier, tierIndex) => <Descriptions.Item key={`tier-${tierIndex}`} label={['第一层名称', '第二层名称', '第三层名称', '第四层名称'][tierIndex]}>{tier}</Descriptions.Item>)}
            <Descriptions.Item label="映射来源">版本 {label.mapping_version_id} · 源行 {label.source_row}</Descriptions.Item>
            <Descriptions.Item label="匹配依据" span={2}>{label.matching_basis || '--'}</Descriptions.Item>
            {scenarioId === TECHNOLOGY_FINANCE_SCENARIO && ipIntensiveIndustrySubjects.has(label.subject) && label.ip_intensive_industry_status && <><Descriptions.Item label="知识产权条件"><Tag color={label.ip_intensive_industry_status === 'satisfied' ? 'success' : 'error'}>{label.ip_intensive_industry_status === 'satisfied' ? '满足' : '不满足'}</Tag></Descriptions.Item><Descriptions.Item label="知识产权条件依据" span={2}>{label.ip_intensive_industry_basis || '--'}</Descriptions.Item></>}
          </Descriptions>
          <div className="evidence-summary"><b>映射与业务证据</b>{label.evidence_refs.map((reference, evidenceIndex) => <span key={`${reference.type || 'evidence'}-${evidenceIndex}`}>{evidenceSummary(reference)}</span>)}</div>
        </section>)}
      </div> : <Alert className="technology-empty-state" type={result.status === 'classification_failed' ? 'error' : result.status === 'needs_review' ? 'warning' : 'info'} showIcon message={stageBStatusLabel(scenarioId, result.status)} description={stageBEmptyDescription(scenarioId, result)} />}
      {technologyDetails && <>
        <Divider />
        <section className="consistency-panel technology-decision-panel">
          <h3>科技金融判定依据</h3>
          <div className="green-evidence-list">
            <div className="green-evidence-row">
              <span>是否属于科技金融</span>
              <p>{result.status === 'completed' ? '是' : result.status === 'not_applicable' ? '否' : '待人工复核'}</p>
            </div>
            <div className="green-evidence-row">
              <span>贷款实际投向</span>
              <p>{technologyDetails.directionRef ? evidenceSummary(technologyDetails.directionRef) : '未形成投向映射证据'}</p>
            </div>
            {technologyDetails.auxiliaryRefs.map((reference) => <div className="green-evidence-row" key={`${reference.evidence_role}-${reference.field_key}`}>
              <span>{technologyAuxiliaryLabel(reference)}</span>
              <p>{technologyAuxiliaryValue(reference)}</p>
            </div>)}
            {technologyDetails.registryRefs.map((reference) => <div className="green-evidence-row" key={reference.registry_type}>
              <span>{reference.registry_type === 'high_tech' ? '高新技术企业名单' : '专精特新企业名单'}</span>
              <p>{`${auxiliaryStatusLabel(reference.status)} · ${reference.excerpt || '--'}`}</p>
            </div>)}
            <div className="green-evidence-row">
              <span>最终判定依据</span>
              <p>{result.consistency_basis || result.error_detail || '暂无说明'}</p>
            </div>
          </div>
          {technologyDetails.warnings.length > 0
            ? <Alert type="warning" showIcon message="科技辅助证据预警" description={<div className="green-warning-list">{technologyDetails.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>} />
            : <Alert type="success" showIcon message="科技辅助证据完整" description="官方科技资质、研发人员占比、研发投入与知识产权均形成正向辅助佐证。" />}
        </section>
      </>}
      {pensionDetails && <>
        <Divider />
        <section className="consistency-panel pension-decision-panel">
          <h3>养老投向判定依据</h3>
          <div className="pension-matrix-list">
            {pensionDetails.matrixRefs.map((reference) => {
              const hasNormalizedValue = reference.normalized_percent !== null && reference.normalized_percent !== undefined
              const rawValue = String(reference.raw_value ?? '').trim()
              return <div className="pension-matrix-row" key={reference.field_key}>
                <span>{reference.field_label || '比例字段'}</span>
                <div className={hasNormalizedValue ? 'pension-percent-value' : undefined}>
                  {hasNormalizedValue ? `${reference.normalized_percent}%` : rawValue || '未填写'}
                </div>
              </div>
            })}
            <div className="pension-matrix-row">
              <span>主体辅助依据</span>
              <div>{result.consistency_basis || '--'}</div>
            </div>
          </div>
          {pensionDetails.qualificationWarning
            ? <Alert type="warning" showIcon message="养老资质预警" description={`${pensionDetails.qualificationWarning}；该预警不改变投向矩阵结论。`} />
            : <Alert type="success" showIcon message="养老资质辅助佐证" description={pensionDetails.qualificationEvidence || '已提供养老相关资质。'} />}
        </section>
      </>}
      {digitalDetails && <>
        <Divider />
        <section className="consistency-panel digital-decision-panel">
          <h3>数字金融判定依据</h3>
          <div className="digital-category-summary">
            <span>数字投向类别</span>
            <strong>{digitalDetails.category || '待人工确认'}</strong>
          </div>
          <div className="digital-evidence-list">
            {digitalDetails.auxiliaryRefs.map((reference) => <div className="digital-evidence-row" key={`${reference.evidence_role}-${reference.field_key}`}>
              <span>{reference.field_label || '辅助证据'}</span>
              <p>{reference.excerpt || '未提供'}</p>
            </div>)}
          </div>
          {digitalDetails.warnings.length > 0
            ? <Alert type="warning" showIcon message="数字辅助证据预警" description={`${digitalDetails.warnings.join('；')}；该预警不改变已成立的贷款投向结论。`} />
            : <Alert type="success" showIcon message="数字辅助证据完整" description="行业定位、数字核心竞争力与研发知识产权已形成正向辅助佐证。" />}
        </section>
      </>}
      {greenDetails && <>
        <Divider />
        <section className="consistency-panel green-decision-panel">
          <h3>绿色金融判定依据</h3>
          <div className="green-evidence-list">
            <div className="green-evidence-row">
              <span>绿色目录命中</span>
              <p>{greenDetails.directionRef ? `${greenDetails.directionRef.subject || '绿色目录'}${greenDetails.directionRef.taxonomy_path?.length ? ` / ${greenDetails.directionRef.taxonomy_path.join(' / ')}` : ''}` : '未形成目录命中证据'}</p>
            </div>
            <div className="green-evidence-row">
              <span>条件匹配方式</span>
              <p>{greenDetails.directionRef?.match_method === 'condition_fallback' ? '条件回退命中' : '行业编码命中'}</p>
            </div>
            {greenDetails.auxiliaryRefs.map((reference) => <div className="green-evidence-row" key={`${reference.evidence_role}-${reference.field_key}`}>
              <span>{reference.field_label || '辅助证据'}</span>
              <p>{reference.excerpt || '未提供'}</p>
            </div>)}
            <div className="green-evidence-row">
              <span>重大环保违法失信</span>
              <p>{greenDetails.violationRef?.violation_status === 'yes' ? '有' : greenDetails.violationRef?.violation_status === 'no' ? '无' : '未知'}</p>
            </div>
          </div>
          {greenDetails.warnings.length > 0
            ? <Alert type="warning" showIcon message="绿色辅助证据预警" description={<div className="green-warning-list">{greenDetails.warnings.map((warning) => <p key={warning}>{warning}</p>)}</div>} />
            : <Alert type="success" showIcon message="绿色辅助证据完整" description="绿色资质、治理措施、环境效益及环保违法失信信息均已提供。" />}
        </section>
      </>}
      <Divider />
      <section className="consistency-panel">
        <h3>贷款对应的五篇大文章类别与企业类别是否一致</h3>
        <Tag color={consistencyColor(result.consistency_status)}>{result.consistency_status ? consistencyLabels[result.consistency_status] : '待人工复核'}</Tag>
        <p>{result.consistency_basis || result.error_detail || '暂无一致性说明。'}</p>
        {result.consistency_evidence_refs.length > 0 && <div className="evidence-summary"><b>一致性证据</b>{result.consistency_evidence_refs.map((reference, index) => <span key={`consistency-${index}`}>{evidenceSummary(reference)}</span>)}</div>}
      </section>
    </> : <Alert className="technology-empty-state" type={stageAFailed ? 'error' : 'warning'} showIcon message="Stage B 未执行" description={`Stage A 当前为“${stageAStatusLabel}”，只有 Stage A 完成后才会进入${scenarioView.name}判定。`} />}
  </Card>
}

const inclusiveCreditSourceLabels: Record<string, string> = {
  structured_and_approval_consistent: '结构化额度与审批意见一致',
  structured: '仅采用结构化授信额度',
  approval_opinion: '仅采用授信审批意见批复额度',
  approval_opinion_multiple: '审批意见存在多个批复额度',
  conflict: '结构化额度与审批意见冲突',
  missing: '两处均无明确额度',
}

export function inclusiveCreditSummary(result: InclusiveFinanceResult): string {
  const determination = result.determination
  const source = determination?.credit_amount_source || 'missing'
  const adopted = result.credit_amount_wan === null ? '未采用' : `${result.credit_amount_wan} 万元`
  return `${adopted} · ${inclusiveCreditSourceLabels[source] || source}`
}

export function inclusiveBorrowerBasis(result: InclusiveFinanceResult): string {
  return result.determination?.borrower_type_basis || `主体类型：${result.borrower_type || '待人工确认'}`
}

function inclusiveCreditConsistencySummary(result: InclusiveFinanceResult): string {
  const determination = result.determination
  if (determination?.credit_amount_conflict) return '冲突，已转人工复核'
  if (determination?.credit_amount_consistent === true) return '双来源一致'
  if (determination?.credit_amount_source === 'structured' || determination?.credit_amount_source === 'approval_opinion') return '仅有一个明确来源'
  if (determination?.credit_amount_source === 'approval_opinion_multiple') return '存在多个不同批复额度，已转人工复核'
  return '两处均无明确额度，已转人工复核'
}

export function InclusiveFinanceResultCard({ result }: { result: InclusiveFinanceResult | null }) {
  return <Card className="result-card technology-result-card" bordered={false} title="Stage B · 普惠金融判定">
    {result ? <>
      <div className="technology-status-row">
        <div><span>判定状态</span><Tag className="key-decision-tag" color={statusColor(result.status)}>{result.status === 'not_applicable' ? '不属于普惠金融' : stageBStatusLabels[result.status]}</Tag></div>
        <small>普惠版本 {result.version} · Stage A 结果 #{result.stage_a_result_id}</small>
      </div>
      <section className="consistency-panel inclusive-decision-panel">
        <h3>普惠金融判定依据</h3>
        <div className="inclusive-evidence-list">
          <div className="inclusive-evidence-row"><span>是否属于普惠金融</span><p>{result.qualifies === null ? '待人工复核' : result.qualifies ? '是' : '否'}</p></div>
          <div className="inclusive-evidence-row"><span>普惠子类别</span><p>{result.inclusive_category || '未形成普惠子类别'}</p></div>
          <div className="inclusive-evidence-row"><span>借款主体类型</span><p>{result.borrower_type || '待人工确认'}</p></div>
          <div className="inclusive-evidence-row"><span>主体条件</span><p>{inclusiveBorrowerBasis(result)}</p></div>
          <div className="inclusive-evidence-row"><span>计算企业规模</span><p>{result.computed_size || '不适用或待复核'}</p></div>
          <div className="inclusive-evidence-row"><span>填写企业规模</span><p>{result.filled_size || '未填写或不适用'}</p></div>
          <div className="inclusive-evidence-row"><span>规模一致性</span><p>{result.size_consistent === null ? '未判定' : result.size_consistent ? '一致' : '不一致，以计算规模为准'}</p></div>
          <div className="inclusive-evidence-row"><span>是否经营性贷款</span><p>{result.is_operating_loan === null ? '待人工复核' : result.is_operating_loan ? '是' : '否'}</p></div>
          <div className="inclusive-evidence-row"><span>结构化授信额度</span><p>{result.determination?.structured_credit_amount_wan === null || result.determination?.structured_credit_amount_wan === undefined ? '未解析' : `${result.determination.structured_credit_amount_wan} 万元`}{result.determination?.structured_credit_amount_raw ? `（原文：${result.determination.structured_credit_amount_raw}）` : ''}</p></div>
          <div className="inclusive-evidence-row"><span>审批意见批复额度</span><p>{result.determination?.approval_credit_amounts_wan?.length ? `${result.determination.approval_credit_amounts_wan.join('、')} 万元` : '未提取到明确批复额度'}</p></div>
          <div className="inclusive-evidence-row"><span>最终采用额度</span><p>{inclusiveCreditSummary(result)}</p></div>
          <div className="inclusive-evidence-row"><span>额度一致性</span><p>{inclusiveCreditConsistencySummary(result)}</p></div>
          <div className="inclusive-evidence-row"><span>注册地址辅助</span><p>{result.determination?.farmer_registration_address_support || '无地址辅助信息'}</p></div>
          <div className="inclusive-evidence-row"><span>最终判定依据</span><p>{result.basis || result.error_detail || '暂无说明'}</p></div>
        </div>
        {result.anomalies.length > 0 && <Alert type="warning" showIcon message="需关注的判定异常" description={<div className="inclusive-warning-list">{result.anomalies.map((anomaly, index) => <p key={`${anomaly.type || 'anomaly'}-${index}`}>{anomaly.message || anomaly.type || '未知异常'}</p>)}</div>} />}
      </section>
    </> : <Alert type="warning" showIcon message="Stage B 未执行" description="Stage A 完成后才会执行普惠金融判定。" />}
  </Card>
}
