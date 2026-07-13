import assert from 'node:assert/strict'
import test from 'node:test'

import {
  NATIONAL_ECONOMY_SCENARIO,
  TECHNOLOGY_FINANCE_SCENARIO,
  INCLUSIVE_FINANCE_SCENARIO,
  caseMatchesScenario,
  comingSoonScenarios,
  currentCaseStorageKey,
  scenarioCasesPath,
  scenarioViews,
  templateScenarioId,
} from '../src/scenarios.ts'

test('国民经济、科技金融与普惠金融均有可执行入口', () => {
  assert.equal(scenarioViews[NATIONAL_ECONOMY_SCENARIO].classifyPath, '/classify')
  assert.equal(scenarioViews[TECHNOLOGY_FINANCE_SCENARIO].classifyPath, '/scenarios/technology_finance/classify')
  assert.equal(templateScenarioId(TECHNOLOGY_FINANCE_SCENARIO), TECHNOLOGY_FINANCE_SCENARIO)
  assert.equal(scenarioViews[INCLUSIVE_FINANCE_SCENARIO].classifyPath, '/scenarios/inclusive_finance/classify')
  assert.equal(templateScenarioId(INCLUSIVE_FINANCE_SCENARIO), INCLUSIVE_FINANCE_SCENARIO)
})

test('其余专题与涉农只登记为暂未开放且不产生执行入口', () => {
  assert.deepEqual(comingSoonScenarios.map(({ id }) => id), [
    'agriculture_related',
    'green_finance',
    'pension_finance',
    'digital_finance',
  ])
  assert.ok(comingSoonScenarios.every(({ id }) => !(id in scenarioViews)))
})

test('API 路径和 session key 完整携带场景，错配场景不通过', () => {
  assert.equal(scenarioCasesPath(NATIONAL_ECONOMY_SCENARIO), '/national-economy/cases')
  assert.equal(scenarioCasesPath(TECHNOLOGY_FINANCE_SCENARIO), '/scenarios/technology_finance/cases')
  assert.equal(scenarioCasesPath(INCLUSIVE_FINANCE_SCENARIO), '/scenarios/inclusive_finance/cases')
  assert.notEqual(currentCaseStorageKey(NATIONAL_ECONOMY_SCENARIO), currentCaseStorageKey(TECHNOLOGY_FINANCE_SCENARIO))
  assert.notEqual(currentCaseStorageKey(TECHNOLOGY_FINANCE_SCENARIO), currentCaseStorageKey(INCLUSIVE_FINANCE_SCENARIO))
  assert.equal(caseMatchesScenario(TECHNOLOGY_FINANCE_SCENARIO, 'technology_finance'), true)
  assert.equal(caseMatchesScenario(TECHNOLOGY_FINANCE_SCENARIO, 'national_economy_classification'), false)
  assert.equal(caseMatchesScenario(INCLUSIVE_FINANCE_SCENARIO, 'inclusive_finance'), true)
})
