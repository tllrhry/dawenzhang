import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  AGRICULTURE_RELATED_SCENARIO,
  DIGITAL_FINANCE_SCENARIO,
  GREEN_FINANCE_SCENARIO,
  NATIONAL_ECONOMY_SCENARIO,
  PENSION_FINANCE_SCENARIO,
  TECHNOLOGY_FINANCE_SCENARIO,
  INCLUSIVE_FINANCE_SCENARIO,
  caseMatchesScenario,
  currentCaseStorageKey,
  fiveArticlesScenarioIds,
  isFiveArticlesScenario,
  scenarioCasesPath,
  scenarioViews,
  templateScenarioId,
} from '../src/scenarios.ts'

test('国民经济与五个五篇子场景均有独立可执行入口', () => {
  assert.equal(scenarioViews[NATIONAL_ECONOMY_SCENARIO].classifyPath, '/classify')
  assert.deepEqual(fiveArticlesScenarioIds, [TECHNOLOGY_FINANCE_SCENARIO, GREEN_FINANCE_SCENARIO, INCLUSIVE_FINANCE_SCENARIO, PENSION_FINANCE_SCENARIO, DIGITAL_FINANCE_SCENARIO])
  for (const scenarioId of fiveArticlesScenarioIds) {
    assert.equal(scenarioViews[scenarioId].classifyPath, `/scenarios/${scenarioId}/classify`)
    assert.equal(scenarioViews[scenarioId].historyPath, `/scenarios/${scenarioId}/history`)
    assert.equal(templateScenarioId(scenarioId), scenarioId)
    assert.equal(isFiveArticlesScenario(scenarioId), true)
  }
  assert.equal(isFiveArticlesScenario(NATIONAL_ECONOMY_SCENARIO), false)
})

test('涉农场景是正式可用入口且不再属于暂未开放场景', () => {
  assert.equal(scenarioViews[AGRICULTURE_RELATED_SCENARIO].classifyPath, '/scenarios/agriculture_related/classify')
  assert.equal(scenarioViews[AGRICULTURE_RELATED_SCENARIO].historyPath, '/scenarios/agriculture_related/history')
  assert.equal(templateScenarioId(AGRICULTURE_RELATED_SCENARIO), AGRICULTURE_RELATED_SCENARIO)
  assert.equal(isFiveArticlesScenario(AGRICULTURE_RELATED_SCENARIO), false)
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

test('数字金融前台展示业务结论与辅助证据但不展示决策策略版本', () => {
  const resultCardsSource = readFileSync(new URL('../src/components/FinanceResultCards.tsx', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.match(resultCardsSource, /数字金融判定依据/)
  assert.match(resultCardsSource, /数字投向类别/)
  assert.doesNotMatch(resultCardsSource, /决策策略版本|policyVersion/)
  assert.doesNotMatch(appSource, /策略 \$\{policyVersion/)
})

test('绿色金融前台按行展示目录、匹配方式、辅助证据和环保违法状态', () => {
  const resultCardsSource = readFileSync(new URL('../src/components/FinanceResultCards.tsx', import.meta.url), 'utf8')

  assert.match(resultCardsSource, /绿色金融判定依据/)
  assert.match(resultCardsSource, /绿色目录命中/)
  assert.match(resultCardsSource, /条件匹配方式/)
  assert.match(resultCardsSource, /重大环保违法失信/)
  assert.match(resultCardsSource, /green-evidence-row/)
})

test('科技金融前台逐行展示投向、分类型名单、研发指标和知识产权预警', () => {
  const resultCardsSource = readFileSync(new URL('../src/components/FinanceResultCards.tsx', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.match(resultCardsSource, /科技金融判定依据/)
  assert.match(resultCardsSource, /是否属于科技金融/)
  assert.match(resultCardsSource, /贷款实际投向/)
  assert.match(resultCardsSource, /technology_registry/)
  assert.match(resultCardsSource, /registry_type === 'high_tech'/)
  assert.match(resultCardsSource, /高新技术企业名单/)
  assert.match(resultCardsSource, /专精特新企业名单/)
  assert.doesNotMatch(resultCardsSource, /classificationText|hasNamedRegistryHit/)
  assert.match(resultCardsSource, /研发人员占比/)
  assert.match(resultCardsSource, /研发投入占营收/)
  assert.match(resultCardsSource, /专利或软著/)
  assert.match(resultCardsSource, /green-evidence-row/)
  assert.match(appSource, /technologyHistorySummary/)
})

test('普惠金融前台参考养老结果按行展示划型、额度来源、主体条件和最终依据', () => {
  const resultCardsSource = readFileSync(new URL('../src/components/FinanceResultCards.tsx', import.meta.url), 'utf8')
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')

  assert.match(resultCardsSource, /普惠金融判定依据/)
  assert.match(resultCardsSource, /计算企业规模/)
  assert.match(resultCardsSource, /填写企业规模/)
  assert.match(resultCardsSource, /审批意见批复额度/)
  assert.match(resultCardsSource, /额度一致性/)
  assert.match(resultCardsSource, /主体条件/)
  assert.match(resultCardsSource, /最终判定依据/)
  assert.match(resultCardsSource, /inclusive-evidence-row/)
  assert.match(appSource, /inclusiveCreditSummary/)
  assert.match(appSource, /inclusiveBorrowerBasis/)
})

test('Stage A 优先突出实际贷款投向并明确展示企业行业信息', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const stylesSource = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8')

  assert.ok(appSource.indexOf('conclusion-result-card') < appSource.indexOf('input-result-card'))
  assert.match(appSource, /实际贷款投向结论/)
  assert.match(appSource, /actual-loan-conclusion/)
  assert.match(appSource, /企业行业代码/)
  assert.match(appSource, /企业行业名称/)
  assert.match(stylesSource, /\.actual-loan-conclusion \.final-decision/)
})

test('首页提供两类企业名单的单 PDF 导入入口并立即关闭弹窗提示成功', () => {
  const appSource = readFileSync(new URL('../src/App.tsx', import.meta.url), 'utf8')
  const apiSource = readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8')

  assert.match(appSource, /企业名单维护/)
  assert.match(appSource, /导入企业名单/)
  assert.match(appSource, /accept: '\.pdf,application\/pdf'/)
  assert.match(appSource, /value="high_tech"/)
  assert.match(appSource, /value="specialized_innovation"/)
  assert.match(appSource, /setRegistryModalOpen\(false\)[\s\S]*setRegistryUploadSuccess\(true\)/)
  assert.match(appSource, /message="上传成功"/)
  assert.doesNotMatch(appSource, /await uploadEnterpriseRegistry/)
  assert.match(apiSource, /\/technology-finance\/enterprise-registries/)
  assert.match(apiSource, /body\.append\('registry_type', registryType\)/)
})
