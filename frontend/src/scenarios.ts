export const NATIONAL_ECONOMY_SCENARIO = 'national_economy_classification'
export const TECHNOLOGY_FINANCE_SCENARIO = 'technology_finance'
export const GREEN_FINANCE_SCENARIO = 'green_finance'
export const INCLUSIVE_FINANCE_SCENARIO = 'inclusive_finance'
export const PENSION_FINANCE_SCENARIO = 'pension_finance'
export const DIGITAL_FINANCE_SCENARIO = 'digital_finance'
export const AGRICULTURE_RELATED_SCENARIO = 'agriculture_related'

export type FiveArticlesScenarioId = typeof TECHNOLOGY_FINANCE_SCENARIO | typeof GREEN_FINANCE_SCENARIO | typeof INCLUSIVE_FINANCE_SCENARIO | typeof PENSION_FINANCE_SCENARIO | typeof DIGITAL_FINANCE_SCENARIO
export type ScenarioId = typeof NATIONAL_ECONOMY_SCENARIO | FiveArticlesScenarioId | typeof AGRICULTURE_RELATED_SCENARIO

export interface ScenarioView { id: ScenarioId; name: string; description: string; templateName: string; classifyPath: string; historyPath: string }

export const fiveArticlesScenarioIds: readonly FiveArticlesScenarioId[] = [TECHNOLOGY_FINANCE_SCENARIO, GREEN_FINANCE_SCENARIO, INCLUSIVE_FINANCE_SCENARIO, PENSION_FINANCE_SCENARIO, DIGITAL_FINANCE_SCENARIO]

export const scenarioViews: Record<ScenarioId, ScenarioView> = {
  [NATIONAL_ECONOMY_SCENARIO]: { id: NATIONAL_ECONOMY_SCENARIO, name: '国民经济行业分类', description: '依据企业经营信息，辅助判定 GB/T 4754-2017 四级行业分类。', templateName: '国民经济类别模板', classifyPath: '/classify', historyPath: '/history' },
  [TECHNOLOGY_FINANCE_SCENARIO]: { id: TECHNOLOGY_FINANCE_SCENARIO, name: '科技金融', description: '先完成国民经济分类，再生成可追溯的科技金融标签判定。', templateName: '科技金融分类模板', classifyPath: '/scenarios/technology_finance/classify', historyPath: '/scenarios/technology_finance/history' },
  [GREEN_FINANCE_SCENARIO]: { id: GREEN_FINANCE_SCENARIO, name: '绿色金融', description: '先完成国民经济分类，再生成可追溯的绿色金融标签判定。', templateName: '绿色金融分类模板', classifyPath: '/scenarios/green_finance/classify', historyPath: '/scenarios/green_finance/history' },
  [INCLUSIVE_FINANCE_SCENARIO]: { id: INCLUSIVE_FINANCE_SCENARIO, name: '普惠金融', description: '复用国民经济行业分类，按企业划型、经营性与授信额度进行确定性普惠判定。', templateName: '普惠金融判定模板', classifyPath: '/scenarios/inclusive_finance/classify', historyPath: '/scenarios/inclusive_finance/history' },
  [PENSION_FINANCE_SCENARIO]: { id: PENSION_FINANCE_SCENARIO, name: '养老金融', description: '先完成国民经济分类，再生成可追溯的养老金融标签判定。', templateName: '养老金融分类模板', classifyPath: '/scenarios/pension_finance/classify', historyPath: '/scenarios/pension_finance/history' },
  [DIGITAL_FINANCE_SCENARIO]: { id: DIGITAL_FINANCE_SCENARIO, name: '数字金融', description: '先完成国民经济分类，再生成可追溯的数字金融标签判定。', templateName: '数字金融分类模板', classifyPath: '/scenarios/digital_finance/classify', historyPath: '/scenarios/digital_finance/history' },
  [AGRICULTURE_RELATED_SCENARIO]: { id: AGRICULTURE_RELATED_SCENARIO, name: '涉农分类', description: '复用国民经济行业分类，按全口径涉农贷款四类标准进行完整判定。', templateName: '涉农类别判定模板', classifyPath: '/scenarios/agriculture_related/classify', historyPath: '/scenarios/agriculture_related/history' },
}

export function isFiveArticlesScenario(scenarioId: ScenarioId): scenarioId is FiveArticlesScenarioId { return fiveArticlesScenarioIds.includes(scenarioId as FiveArticlesScenarioId) }
export function scenarioCasesPath(scenarioId: ScenarioId): string { return scenarioId === NATIONAL_ECONOMY_SCENARIO ? '/national-economy/cases' : `/scenarios/${scenarioId}/cases` }
export function templateScenarioId(scenarioId: ScenarioId): string { return scenarioId === NATIONAL_ECONOMY_SCENARIO ? 'national-economy' : scenarioId }
export function currentCaseStorageKey(scenarioId: ScenarioId): string { return `classification-current-case-id:${scenarioId}` }
export function caseMatchesScenario(scenarioId: ScenarioId, caseScenario: string): boolean { return scenarioId === caseScenario }
