export const NATIONAL_ECONOMY_SCENARIO = 'national_economy_classification'
export const TECHNOLOGY_FINANCE_SCENARIO = 'technology_finance'

export type ScenarioId = typeof NATIONAL_ECONOMY_SCENARIO | typeof TECHNOLOGY_FINANCE_SCENARIO
export type ComingSoonScenarioId = 'agriculture_related' | 'green_finance' | 'inclusive_finance' | 'pension_finance' | 'digital_finance'

export interface ScenarioView {
  id: ScenarioId
  name: string
  description: string
  templateName: string
  classifyPath: string
  historyPath: string
}

export const scenarioViews: Record<ScenarioId, ScenarioView> = {
  [NATIONAL_ECONOMY_SCENARIO]: {
    id: NATIONAL_ECONOMY_SCENARIO,
    name: '国民经济行业分类',
    description: '依据企业经营信息，辅助判定 GB/T 4754-2017 四级行业分类。',
    templateName: '国民经济类别模板',
    classifyPath: '/classify',
    historyPath: '/history',
  },
  [TECHNOLOGY_FINANCE_SCENARIO]: {
    id: TECHNOLOGY_FINANCE_SCENARIO,
    name: '科技金融',
    description: '先完成国民经济行业分类，再生成可追溯的科技金融标签判定。',
    templateName: '科技金融分类模板',
    classifyPath: '/scenarios/technology_finance/classify',
    historyPath: '/scenarios/technology_finance/history',
  },
}

export const comingSoonScenarios: ReadonlyArray<{ id: ComingSoonScenarioId; name: string }> = [
  { id: 'agriculture_related', name: '涉农分类' },
  { id: 'green_finance', name: '绿色金融' },
  { id: 'inclusive_finance', name: '普惠金融' },
  { id: 'pension_finance', name: '养老金融' },
  { id: 'digital_finance', name: '数字金融' },
]

export function scenarioCasesPath(scenarioId: ScenarioId): string {
  return scenarioId === NATIONAL_ECONOMY_SCENARIO
    ? '/national-economy/cases'
    : `/scenarios/${scenarioId}/cases`
}

export function templateScenarioId(scenarioId: ScenarioId): string {
  return scenarioId === NATIONAL_ECONOMY_SCENARIO ? 'national-economy' : scenarioId
}

export function currentCaseStorageKey(scenarioId: ScenarioId): string {
  return `classification-current-case-id:${scenarioId}`
}

export function caseMatchesScenario(scenarioId: ScenarioId, caseScenario: string): boolean {
  return scenarioId === caseScenario
}
