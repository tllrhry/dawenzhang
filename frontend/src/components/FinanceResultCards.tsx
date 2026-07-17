import { Alert, Card, Descriptions, Divider, Tag } from 'antd'
import { CheckCircleFilled, SafetyCertificateOutlined } from '@ant-design/icons'

import { TECHNOLOGY_FINANCE_SCENARIO } from '../api'
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
  return `${reference.field_label || reference.field_key || '业务证据'}：${reference.excerpt || '--'}`
}

const ipIntensiveIndustrySubjects = new Set(['知识产权（专利）密集型产业', '知识产权(专利)密集型产业'])

function technologyRegistryHits(result: FiveArticlesResult | null): { specializedInnovation: boolean; highTech: boolean } {
  if (!result) return { specializedInnovation: false, highTech: false }

  const hasNamedRegistryHit = (keyword: string) => result.labels.some((label) => {
    const classificationText = [label.subject, ...label.taxonomy_path].join('')
    if (classificationText.includes(keyword)) return true

    return [label.matching_basis, label.ip_intensive_industry_basis, ...label.evidence_refs.map((reference) => reference.excerpt)]
      .filter((value): value is string => Boolean(value))
      .some((value) => value.includes(keyword) && /(命中|匹配到)/.test(value) && !/(未命中|未能匹配到)/.test(value))
  })

  return {
    specializedInnovation: hasNamedRegistryHit('专精特新'),
    highTech: result.labels.some((label) => label.ip_intensive_industry_status === 'satisfied') || hasNamedRegistryHit('高新技术'),
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

export function InclusiveFinanceResultCard({ result }: { result: InclusiveFinanceResult | null }) {
  return <Card className="result-card technology-result-card" bordered={false} title="Stage B · 普惠金融判定">
    {result ? <Descriptions column={1} size="small">
      <Descriptions.Item label="判定状态"><Tag className="key-decision-tag" color={statusColor(result.status)}>{result.status === 'not_applicable' ? '不属于普惠金融' : stageBStatusLabels[result.status]}</Tag></Descriptions.Item>
      <Descriptions.Item label="借款主体类型">{result.borrower_type || '--'}</Descriptions.Item>
      <Descriptions.Item label="计算划型">{result.computed_size || '--'}{result.size_consistent === false ? '（与填报不一致）' : ''}</Descriptions.Item>
      <Descriptions.Item label="是否经营性贷款">{result.is_operating_loan === null ? '待人工复核' : result.is_operating_loan ? '是' : '否'}</Descriptions.Item>
      <Descriptions.Item label="授信金额">{result.credit_amount_wan ?? '--'} 万元</Descriptions.Item>
      <Descriptions.Item label="是否属于普惠">{result.qualifies === null ? '待人工复核' : result.qualifies ? '是' : '否'}</Descriptions.Item>
      <Descriptions.Item label="普惠子类别">{result.inclusive_category || '--'}</Descriptions.Item>
      <Descriptions.Item label="判定依据">{result.basis || result.error_detail || '--'}</Descriptions.Item>
    </Descriptions> : <Alert type="warning" showIcon message="Stage B 未执行" description="Stage A 完成后才会执行普惠金融判定。" />}
  </Card>
}

