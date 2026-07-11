const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export type ClassificationStatus = 'completed' | 'needs_review'

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
  industry_name: string | null
  matching_basis: string | null
  loan_industry_code: string | null
  loan_industry_name: string | null
  loan_matching_basis: string | null
  loan_matches_enterprise: boolean
  candidate_snapshot: unknown[]
  objection: ResultObjection | null
  created_at: string
}

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

interface CreatedCase {
  id: string
  scenario: string
  status: string
  original_filename: string
}

interface HistoryResponse {
  items: ClassificationResult[]
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

export function createCase(file: File): Promise<CreatedCase> {
  const body = new FormData()
  body.append('file', file)
  return requestJson<CreatedCase>('/national-economy/cases', { method: 'POST', body })
}

export function getCase(caseId: string): Promise<ClassificationCase> {
  return requestJson<ClassificationCase>(`/national-economy/cases/${caseId}`)
}

export function classifyCase(caseId: string): Promise<ClassificationResult> {
  return requestJson<ClassificationResult>(`/national-economy/cases/${caseId}/classifications`, { method: 'POST' })
}

export function submitObjection(caseId: string, objectionText: string): Promise<ClassificationResult> {
  return requestJson<ClassificationResult>(`/national-economy/cases/${caseId}/objections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ objection_text: objectionText }),
  })
}

export function getHistory(caseId: string): Promise<ClassificationResult[]> {
  return requestJson<HistoryResponse>(`/national-economy/cases/${caseId}/history`).then(({ items }) => items)
}

export function templateUrl(): string {
  return `${apiBaseUrl}/scenarios/national-economy/template`
}

export function exportUrl(caseId: string): string {
  return `${apiBaseUrl}/national-economy/cases/${caseId}/export`
}
