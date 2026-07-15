import {
  caseMatchesScenario,
  scenarioCasesPath,
  templateScenarioId,
} from './scenarios'
import type { ScenarioId } from './scenarios'

export { AGRICULTURE_RELATED_SCENARIO, DIGITAL_FINANCE_SCENARIO, GREEN_FINANCE_SCENARIO, INCLUSIVE_FINANCE_SCENARIO, NATIONAL_ECONOMY_SCENARIO, PENSION_FINANCE_SCENARIO, TECHNOLOGY_FINANCE_SCENARIO } from './scenarios'
export type { ScenarioId } from './scenarios'

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export type ClassificationStatus = 'completed' | 'needs_review' | 'classification_failed'
export type FiveArticlesStatus = ClassificationStatus | 'not_applicable'
export type ConsistencyStatus = 'consistent' | 'inconsistent' | 'needs_review' | 'not_applicable'

export interface InputField {
  field: string
  label: string
  value: string
}

export interface ResultObjection {
  description?: string
}

export interface ClassificationResult {
  id: string
  version: number
  status: ClassificationStatus
  industry_code: string | null
  industry_display_code: string | null
  industry_name: string | null
  matching_basis: string | null
  loan_industry_code: string | null
  loan_industry_display_code: string | null
  loan_industry_name: string | null
  loan_matching_basis: string | null
  loan_matches_enterprise: boolean | null
  candidate_snapshot: unknown[]
  objection: ResultObjection | null
  created_at: string
}

export interface EvidenceReference {
  type?: 'mapping' | 'business' | 'stage_a' | string
  mapping_version_id?: number
  source_row?: number
  NEIC_Code?: string
  NEIC_Name?: string
  taxonomy_path?: string[]
  field_key?: string
  field_label?: string
  excerpt?: string
}

export interface TechnologyFinanceLabel {
  mapping_version_id: number
  subject: string
  taxonomy_path: string[]
  NEIC_Code: string
  NEIC_Name: string
  source_row: number
  matching_basis: string
  evidence_refs: EvidenceReference[]
  ip_intensive_industry_status?: 'satisfied' | 'unsatisfied'
  ip_intensive_industry_basis?: string
}

export interface FiveArticlesResult {
  id: string
  version: number
  status: FiveArticlesStatus
  stage_a_result_id: string
  mapping_version_id: number | null
  labels: TechnologyFinanceLabel[]
  loan_neic_code: string | null
  loan_neic_name: string | null
  enterprise_neic_code: string | null
  enterprise_neic_name: string | null
  consistency_status: ConsistencyStatus | null
  consistency_basis: string | null
  consistency_evidence_refs: EvidenceReference[]
  error_detail: string | null
  created_at: string
}

export interface TechnologyFinanceWorkflowResult {
  stage_a: ClassificationResult
  stage_b: FiveArticlesResult | null
}

export interface InclusiveFinanceResult {
  id: string
  version: number
  status: FiveArticlesStatus
  stage_a_result_id: string
  borrower_type: string | null
  computed_size: string | null
  filled_size: string | null
  size_consistent: boolean | null
  is_operating_loan: boolean | null
  credit_amount_wan: number | null
  qualifies: boolean | null
  inclusive_category: string | null
  basis: string | null
  evidence_refs: EvidenceReference[]
  anomalies: Array<{ type?: string; message?: string }>
  determination: Record<string, unknown> | null
  error_detail: string | null
  created_at: string
}

export interface InclusiveFinanceWorkflowResult {
  stage_a: ClassificationResult
  stage_b: InclusiveFinanceResult | null
}

export type AgricultureRelatedStatus = FiveArticlesStatus

export interface AgricultureRelatedCategory {
  category: number
  category_name: string
  result: 'matched' | 'not_matched' | 'not_applicable' | 'needs_review'
  basis: string
  method: string
  evidence_refs: EvidenceReference[]
  model_output?: Record<string, unknown> | null
}

export interface AgricultureRelatedResult {
  id: string
  version: number
  status: AgricultureRelatedStatus
  stage_a_result_id: string
  is_agriculture_related: boolean | null
  matched_categories: AgricultureRelatedCategory[]
  basis: string | null
  evidence_refs: EvidenceReference[]
  model_output: Record<string, unknown> | null
  error_detail: string | null
  created_at: string
}

export interface AgricultureRelatedWorkflowResult {
  stage_a: ClassificationResult
  stage_b: AgricultureRelatedResult | null
}

export type ClassificationOutcome = ClassificationResult | TechnologyFinanceWorkflowResult | InclusiveFinanceWorkflowResult | AgricultureRelatedWorkflowResult
export type ClassificationHistoryItem = ClassificationResult | FiveArticlesResult | InclusiveFinanceResult | AgricultureRelatedResult

export interface ClassificationCase {
  id: string
  scenario: string
  status: string
  original_filename: string
  input_fields: InputField[]
  current_result: ClassificationResult | null
  created_at: string
  updated_at: string
}

export interface CreatedCase {
  id: string
  scenario: string
  status: string
  original_filename: string
}

interface HistoryResponse<T> {
  items: T[]
}

interface ValidationDetail {
  message?: string
  missing?: string[]
  duplicate?: string[]
  unrecognized?: string[]
  error?: string
}

interface ErrorResponse {
  detail?: string | ValidationDetail
}

export class ApiError extends Error {
  status: number
  detail?: string | ValidationDetail

  constructor(status: number, message: string, detail?: string | ValidationDetail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, init)
  if (!response.ok) {
    let payload: ErrorResponse | undefined
    try {
      payload = await response.json() as ErrorResponse
    } catch {
      payload = undefined
    }
    const detail = payload?.detail
    const message = typeof detail === 'string' ? detail : detail?.message || `请求失败（${response.status}）`
    throw new ApiError(response.status, message, detail)
  }
  return response.json() as Promise<T>
}

export function createCase(scenarioId: ScenarioId, file: File): Promise<CreatedCase> {
  const body = new FormData()
  body.append('file', file)
  return requestJson<CreatedCase>(scenarioCasesPath(scenarioId), { method: 'POST', body })
}

export function getCase(scenarioId: ScenarioId, caseId: string): Promise<ClassificationCase> {
  return requestJson<ClassificationCase>(`${scenarioCasesPath(scenarioId)}/${caseId}`).then((caseData) => {
    if (!caseMatchesScenario(scenarioId, caseData.scenario)) {
      throw new ApiError(404, '案例与当前场景不匹配')
    }
    return caseData
  })
}

export function classifyCase(scenarioId: ScenarioId, caseId: string): Promise<ClassificationOutcome> {
  return requestJson<ClassificationOutcome>(`${scenarioCasesPath(scenarioId)}/${caseId}/classifications`, { method: 'POST' })
}

export function submitObjection(scenarioId: ScenarioId, caseId: string, objectionText: string): Promise<ClassificationOutcome> {
  return requestJson<ClassificationOutcome>(`${scenarioCasesPath(scenarioId)}/${caseId}/objections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ objection_text: objectionText }),
  })
}

export function getHistory(scenarioId: ScenarioId, caseId: string): Promise<ClassificationHistoryItem[]> {
  return requestJson<HistoryResponse<ClassificationHistoryItem>>(`${scenarioCasesPath(scenarioId)}/${caseId}/history`).then(({ items }) => items)
}

export function templateUrl(scenarioId: ScenarioId): string {
  return `${apiBaseUrl}/scenarios/${templateScenarioId(scenarioId)}/template`
}

export function exportUrl(scenarioId: ScenarioId, caseId: string): string {
  return `${apiBaseUrl}${scenarioCasesPath(scenarioId)}/${caseId}/export`
}
