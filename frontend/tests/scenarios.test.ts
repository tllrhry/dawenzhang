import assert from 'node:assert/strict'
import test from 'node:test'

import {
  DIGITAL_FINANCE_SCENARIO,
  GREEN_FINANCE_SCENARIO,
  NATIONAL_ECONOMY_SCENARIO,
  PENSION_FINANCE_SCENARIO,
  TECHNOLOGY_FINANCE_SCENARIO,
  caseMatchesScenario,
  comingSoonScenarios,
  currentCaseStorageKey,
  fiveArticlesScenarioIds,
  isFiveArticlesScenario,
  scenarioCasesPath,
  scenarioViews,
  templateScenarioId,
} from '../src/scenarios.ts'

test('国民经济与四个五篇子场景均有独立可执行入口', () => {
  assert.equal(scenarioViews[NATIONAL_ECONOMY_SCENARIO].classifyPath, '/classify')
  assert.deepEqual(fiveArticlesScenarioIds, [TECHNOLOGY_FINANCE_SCENARIO, GREEN_FINANCE_SCENARIO, PENSION_FINANCE_SCENARIO, DIGITAL_FINANCE_SCENARIO])
  for (const scenarioId of fiveArticlesScenarioIds) {
    assert.equal(scenarioViews[scenarioId].classifyPath, `/scenarios/${scenarioId}/classify`)
    assert.equal(scenarioViews[scenarioId].historyPath, `/scenarios/${scenarioId}/history`)
    assert.equal(templateScenarioId(scenarioId), scenarioId)
    assert.equal(isFiveArticlesScenario(scenarioId), true)
  }
  assert.equal(isFiveArticlesScenario(NATIONAL_ECONOMY_SCENARIO), false)
})

test('普惠与涉农只登记为暂未开放且不产生执行入口', () => {
  assert.deepEqual(comingSoonScenarios.map(({ id }) => id), [
    'agriculture_related',
    'inclusive_finance',
  ])
  assert.ok(comingSoonScenarios.every(({ id }) => !(id in scenarioViews)))
})

test('API 路径和 session key 完整携带场景，切换和错配均不复用案例', () => {
  assert.equal(scenarioCasesPath(NATIONAL_ECONOMY_SCENARIO), '/national-economy/cases')
  const sessionKeys = new Set(fiveArticlesScenarioIds.map(currentCaseStorageKey))
  assert.equal(sessionKeys.size, fiveArticlesScenarioIds.length)
  for (const scenarioId of fiveArticlesScenarioIds) {
    assert.equal(scenarioCasesPath(scenarioId), `/scenarios/${scenarioId}/cases`)
    assert.equal(caseMatchesScenario(scenarioId, scenarioId), true)
    assert.equal(caseMatchesScenario(scenarioId, NATIONAL_ECONOMY_SCENARIO), false)
  }
  assert.equal(caseMatchesScenario(GREEN_FINANCE_SCENARIO, DIGITAL_FINANCE_SCENARIO), false)
  assert.notEqual(currentCaseStorageKey(NATIONAL_ECONOMY_SCENARIO), currentCaseStorageKey(TECHNOLOGY_FINANCE_SCENARIO))
})
