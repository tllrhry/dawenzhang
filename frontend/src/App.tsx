import { useEffect, useState } from 'react'
import {
  Alert,
  Button,
  Card,
  ConfigProvider,
  Descriptions,
  Divider,
  Input,
  Progress,
  Steps,
  Tag,
  Timeline,
  Upload,
} from 'antd'
import type { UploadProps } from 'antd'
import {
  ArrowRightOutlined,
  AuditOutlined,
  BankOutlined,
  CheckCircleFilled,
  CloudUploadOutlined,
  DownloadOutlined,
  FileTextOutlined,
  HistoryOutlined,
  InfoCircleOutlined,
  QuestionCircleOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { BrowserRouter, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import {
  ApiError,
  AGRICULTURE_RELATED_SCENARIO,
  NATIONAL_ECONOMY_SCENARIO,
  TECHNOLOGY_FINANCE_SCENARIO,
  classifyCase,
  createCase,
  exportUrl,
  getCase,
  getHistory,
  submitObjection,
  templateUrl,
} from './api'
import type {
  AgricultureRelatedResult,
  AgricultureRelatedWorkflowResult,
  ClassificationCase,
  ClassificationHistoryItem,
  ClassificationOutcome,
  ClassificationResult,
  EvidenceReference,
  FiveArticlesResult,
  InclusiveFinanceResult,
  InclusiveFinanceWorkflowResult,
  ScenarioId,
  TechnologyFinanceWorkflowResult,
} from './api'
import { caseMatchesScenario, currentCaseStorageKey, fiveArticlesScenarioIds, INCLUSIVE_FINANCE_SCENARIO, isFiveArticlesScenario, scenarioViews } from './scenarios'

function isTechnologyFinanceWorkflow(result: ClassificationOutcome): result is TechnologyFinanceWorkflowResult | InclusiveFinanceWorkflowResult | AgricultureRelatedWorkflowResult {
  return 'stage_a' in result
}

function isFiveArticlesResult(result: ClassificationHistoryItem): result is FiveArticlesResult {
  return 'stage_a_result_id' in result && 'labels' in result
}

function isInclusiveFinanceResult(result: ClassificationHistoryItem): result is InclusiveFinanceResult {
  return 'stage_a_result_id' in result && 'borrower_type' in result
}

function isAgricultureRelatedResult(result: ClassificationHistoryItem): result is AgricultureRelatedResult {
  return 'stage_a_result_id' in result && 'matched_categories' in result && 'is_agriculture_related' in result
}

function isStageBScenario(scenarioId: ScenarioId): boolean {
  return isFiveArticlesScenario(scenarioId) || scenarioId === AGRICULTURE_RELATED_SCENARIO
}

const stageBStatusLabels: Record<Exclude<FiveArticlesResult['status'], 'not_applicable'>, string> = {
  completed: '判定已完成',
  needs_review: '待人工复核',
  classification_failed: '判定失败',
}

function stageBStatusLabel(scenarioId: ScenarioId, status: FiveArticlesResult['status']): string { return status === 'not_applicable' ? `不属于${scenarioViews[scenarioId].name}` : stageBStatusLabels[status] }
function stageBEmptyDescription(scenarioId: ScenarioId, result: FiveArticlesResult): string {
  const scenarioName = scenarioViews[scenarioId].name
  return result.error_detail || result.consistency_basis || (result.status === 'not_applicable' ? `有效${scenarioName}映射中未命中该贷款投向，因此不属于${scenarioName}。` : `当前没有可展示的正式${scenarioName}标签。`)
}

const consistencyLabels: Record<NonNullable<FiveArticlesResult['consistency_status']>, string> = {
  consistent: '一致',
  inconsistent: '不一致',
  needs_review: '待人工复核',
  not_applicable: '不适用',
}

function statusColor(status: FiveArticlesResult['status']): string {
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

const flowSteps = [
  ['选择分类', '选择业务分类入口'],
  ['下载模板', '下载标准模板文件'],
  ['上传案例', '上传企业信息或案例'],
  ['AI 判定', '智能判定分类结果'],
  ['结果确认', '查看并确认判定结果'],
  ['结果复核', '如有异议发起复核'],
  ['历史导出', '导出历史判定记录'],
]
const ipIntensiveIndustrySubjects = new Set(['知识产权（专利）密集型产业', '知识产权(专利)密集型产业'])

type ClassificationStage = 'upload' | 'processing' | 'result'

function Brand() {
  return (
    <NavLink to="/" className="brand" aria-label="行业智能判定平台首页">
      <span className="brand-mark"><BankOutlined /></span>
      <span>
        <strong>行业智能判定平台</strong>
        <small>基于企业经营信息的国民经济行业分类智能识别</small>
      </span>
    </NavLink>
  )
}

function AppHeader() {
  return (
    <header className="site-header">
      <Brand />
      <nav className="main-nav" aria-label="主导航">
        <NavLink end to="/">首页</NavLink>
        <NavLink to="/help">使用说明</NavLink>
        <NavLink to="/history">历史记录</NavLink>
        <NavLink to="/help">帮助中心</NavLink>
      </nav>
      <button className="user-menu" type="button" aria-label="管理员账户">
        <span className="user-avatar"><UserOutlined /></span>
        <span>管理员</span><span className="caret">▾</span>
      </button>
    </header>
  )
}

function AppFooter() {
  return (
    <footer className="site-footer">
      <span>© 2026 行业智能判定平台</span><i />
      <span>仅供内部使用</span><i />
      <span>建议使用 Chrome、Edge 等现代浏览器访问</span><i />
      <span className="safe-note"><SafetyCertificateOutlined /> 数据安全保护中</span>
    </footer>
  )
}

function HomePage() {
  const navigate = useNavigate()
  return (
    <>
      <section className="hero-section">
        <div className="hero-skyline" />
        <p className="hero-kicker">INTELLIGENT CLASSIFICATION</p>
        <h1>请选择分类入口</h1>
      </section>

      <main className="home-content">
        <section className="scenario-grid" aria-label="业务分类入口">
          <Card className="scenario-card scenario-card-active" bordered={false}>
            <div className="scene-icon scene-icon-active"><AuditOutlined /></div>
            <div className="scene-body">
              <h2>国民经济行业分类</h2>
              <p>基于企业经营信息，智能识别唯一四级行业代码与名称。</p>
              <Button type="primary" size="large" block icon={<ArrowRightOutlined />} iconPosition="end" onClick={() => navigate(scenarioViews[NATIONAL_ECONOMY_SCENARIO].classifyPath)}>
                进入分类
              </Button>
            </div>
            <Divider />
            <button className="learn-link" type="button" onClick={() => navigate('/help')}><InfoCircleOutlined /> 了解更多 <ArrowRightOutlined /></button>
          </Card>

          <Card className="scenario-card scenario-card-active" bordered={false}>
            <div className="scene-icon scene-icon-active"><AuditOutlined /></div>
            <div className="scene-body">
              <h2>涉农分类</h2><p>{scenarioViews[AGRICULTURE_RELATED_SCENARIO].description}</p>
              <Button type="primary" size="large" block icon={<ArrowRightOutlined />} iconPosition="end" onClick={() => navigate(scenarioViews[AGRICULTURE_RELATED_SCENARIO].classifyPath)}>进入分类</Button>
            </div>
            <Divider />
            <button className="learn-link" type="button" onClick={() => navigate('/help')}><InfoCircleOutlined /> 了解更多 <ArrowRightOutlined /></button>
          </Card>
          <FiveArticlesScenario />
        </section>

        <Alert className="workflow-alert" showIcon icon={<InfoCircleOutlined />} message="请选择业务分类入口，进入后按流程完成模板下载、案例上传与智能判定，获取分类结果。" />

        <section className="flow-card">
          <div className="section-title"><b>流程概览</b><span /> 支持结果复核与再次 AI 判定</div>
          <div className="process-flow">
            {flowSteps.map(([title, description], index) => (
              <div className="process-step" key={title}>
                <span className={`process-number ${index === 6 ? 'is-last' : ''}`}>{index + 1}</span>
                <strong>{title}</strong><small>{description}</small>
              </div>
            ))}
          </div>
          <div className="review-loop">复核后再次 AI 判定</div>
        </section>
      </main>
    </>
  )
}

function FiveArticlesScenario() {
  const navigate = useNavigate()
  return (
    <Card className="scenario-card scenario-card-active" bordered={false}>
      <div className="scene-icon scene-icon-active"><BankOutlined /></div>
      <div className="scene-body">
        <h2>五篇大文章分类</h2>
        <p>涵盖科技、绿色、普惠、养老、数字金融；普惠金融采用独立的确定性判定规则。</p>
        {fiveArticlesScenarioIds.map((scenarioId) => <Button key={scenarioId} type="primary" size="middle" block icon={<ArrowRightOutlined />} iconPosition="end" onClick={() => navigate(scenarioViews[scenarioId].classifyPath)}>进入{scenarioViews[scenarioId].name}</Button>)}
      </div>
      <Divider />
      <span className="learn-link is-muted"><InfoCircleOutlined /> 查看专题使用说明 <ArrowRightOutlined /></span>
    </Card>
  )
}

function ClassifyPage({ scenarioId }: { scenarioId: ScenarioId }) {
  const [stage, setStage] = useState<ClassificationStage>('upload')
  const [selectedFile, setSelectedFile] = useState<File>()
  const [caseData, setCaseData] = useState<ClassificationCase>()
  const [result, setResult] = useState<ClassificationResult>()
  const [stageBResult, setStageBResult] = useState<FiveArticlesResult | InclusiveFinanceResult | AgricultureRelatedResult | null>()
  const [errorMessage, setErrorMessage] = useState<string>()
  const [isSubmittingReview, setIsSubmittingReview] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [reviewText, setReviewText] = useState('')
  const navigate = useNavigate()
  const scenarioView = scenarioViews[scenarioId]
  const storageKey = currentCaseStorageKey(scenarioId)

  useEffect(() => {
    const caseId = window.sessionStorage.getItem(storageKey)
    if (!caseId) return
    Promise.all([
      getCase(scenarioId, caseId),
      isStageBScenario(scenarioId) ? getHistory(scenarioId, caseId) : Promise.resolve([]),
    ]).then(([loadedCase, history]) => {
      setCaseData(loadedCase)
      if (loadedCase.current_result) {
        setResult(loadedCase.current_result)
        const latestStageB = history.filter((item) => isFiveArticlesResult(item) || isInclusiveFinanceResult(item) || isAgricultureRelatedResult(item)).at(-1) || null
        setStageBResult(latestStageB)
        setStage('result')
      }
    }).catch(() => window.sessionStorage.removeItem(storageKey))
  }, [scenarioId, storageKey])

  const uploadProps: UploadProps = {
    accept: '.docx',
    maxCount: 1,
    beforeUpload: (file) => {
      setSelectedFile(file)
      setErrorMessage(undefined)
      return false
    },
    onRemove: () => setSelectedFile(undefined),
    showUploadList: false,
  }

  const formatError = (error: unknown) => {
    if (!(error instanceof ApiError)) return '请求失败，请稍后重试。'
    if (error.status === 502) return '分类服务暂时不可用，请稍后重试。'
    if (typeof error.detail === 'object' && error.detail) {
      const details = [
        error.detail.missing?.length ? `缺失字段：${error.detail.missing.join('、')}` : '',
        error.detail.duplicate?.length ? `重复字段：${error.detail.duplicate.join('、')}` : '',
        error.detail.unrecognized?.length ? `无法识别：${error.detail.unrecognized.join('、')}` : '',
      ].filter(Boolean)
      return [error.message, ...details].join('；')
    }
    return error.message
  }

  const applyOutcome = (outcome: ClassificationOutcome) => {
    if (isTechnologyFinanceWorkflow(outcome)) {
      setResult(outcome.stage_a)
      setStageBResult(outcome.stage_b)
    } else {
      setResult(outcome)
      setStageBResult(undefined)
    }
  }

  const runClassification = async (caseId: string) => {
    setStage('processing')
    setErrorMessage(undefined)
    try {
      const classification = await classifyCase(scenarioId, caseId)
      const refreshedCase = await getCase(scenarioId, caseId)
      applyOutcome(classification)
      setCaseData(refreshedCase)
      setStage('result')
    } catch (error) {
      setErrorMessage(formatError(error))
      setStage('upload')
    }
  }

  const startClassification = async () => {
    if (!selectedFile) return
    setErrorMessage(undefined)
    try {
      const createdCase = await createCase(scenarioId, selectedFile)
      if (!caseMatchesScenario(scenarioId, createdCase.scenario)) throw new ApiError(404, '案例与当前场景不匹配')
      window.sessionStorage.setItem(storageKey, createdCase.id)
      setCaseData(await getCase(scenarioId, createdCase.id))
      await runClassification(createdCase.id)
    } catch (error) {
      setErrorMessage(formatError(error))
      setStage('upload')
    }
  }

  const retryClassification = async () => {
    if (caseData) await runClassification(caseData.id)
  }

  const backToClassification = () => {
    window.sessionStorage.removeItem(storageKey)
    setSelectedFile(undefined)
    setCaseData(undefined)
    setResult(undefined)
    setStageBResult(undefined)
    setErrorMessage(undefined)
    setReviewText('')
    setShowReview(false)
    setStage('upload')
    window.requestAnimationFrame(() => window.scrollTo({ top: 0, behavior: 'smooth' }))
  }

  const reclassify = async () => {
    if (!caseData || !reviewText.trim()) return
    setIsSubmittingReview(true)
    setErrorMessage(undefined)
    try {
      const classification = await submitObjection(scenarioId, caseData.id, reviewText.trim())
      applyOutcome(classification)
      setCaseData(await getCase(scenarioId, caseData.id))
      setReviewText('')
      setShowReview(false)
    } catch (error) {
      setErrorMessage(formatError(error))
    } finally {
      setIsSubmittingReview(false)
    }
  }

  const downloadTemplate = () => {
    window.location.assign(templateUrl(scenarioId))
  }

  return (
    <main className="page-content workspace-page">
      <div className="page-breadcrumb"><button onClick={() => navigate('/')} type="button">首页</button><span>/</span> {scenarioView.name}</div>
      <div className="workspace-heading">
        <span className="workspace-icon"><AuditOutlined /></span>
        <div><h1>{scenarioView.name}</h1><p>{scenarioView.description}</p></div>
      </div>
      <Steps className="workspace-steps" current={stage === 'upload' ? 1 : stage === 'processing' ? 3 : 4} size="small" items={flowSteps.map(([title]) => ({ title }))} />

      {stage === 'upload' && (
        <section className="workspace-grid">
          <Card className="upload-card" bordered={false} title="上传企业分类案例" extra={<Tag color="blue">单企业 · Word 模板</Tag>}>
            <div className="template-panel">
              <div><FileTextOutlined /><span><b>{scenarioView.templateName}</b><small>请使用标准模板填写企业信息后上传</small></span></div>
              <Button icon={<DownloadOutlined />} onClick={downloadTemplate}>下载模板</Button>
            </div>
            {errorMessage && <Alert type="error" showIcon message={errorMessage} />}
            <Upload.Dragger {...uploadProps} className={selectedFile ? 'has-file' : ''}>
              <p className="ant-upload-drag-icon"><CloudUploadOutlined /></p>
              <p className="ant-upload-text">拖拽 Word 文件到此处，或点击选择文件</p>
              <p className="ant-upload-hint">仅支持已填写的 .docx 标准模板，每次仅上传一个企业案例</p>
            </Upload.Dragger>
            {selectedFile && <div className="selected-file"><CheckCircleFilled /><span>{selectedFile.name}</span><button type="button" onClick={() => setSelectedFile(undefined)}>移除</button></div>}
            <Button type="primary" size="large" disabled={!selectedFile} onClick={() => void startClassification()} icon={<ArrowRightOutlined />} iconPosition="end">开始智能判定</Button>
          </Card>
          <AsideGuide scenarioId={scenarioId} />
        </section>
      )}

      {stage === 'processing' && <ProcessingPanel scenarioId={scenarioId} fileName={caseData?.original_filename || selectedFile?.name} />}
      {stage === 'result' && result && caseData && <ResultPanel scenarioId={scenarioId} caseData={caseData} result={result} stageBResult={stageBResult} errorMessage={errorMessage} showReview={showReview} setShowReview={setShowReview} reviewText={reviewText} setReviewText={setReviewText} isSubmittingReview={isSubmittingReview} onBackToClassification={backToClassification} onReclassify={() => void reclassify()} onRetry={() => void retryClassification()} />}
    </main>
  )
}

function AsideGuide({ scenarioId }: { scenarioId: ScenarioId }) {
  const isFiveArticles = isStageBScenario(scenarioId)
  return <Card className="aside-guide" bordered={false} title={<><QuestionCircleOutlined /> 填写说明</>}>
    <p>{isFiveArticles ? `模板包含国民经济分类所需 13 项字段，以及${scenarioViews[scenarioId].name}判定所需的附加字段。` : '模板包含企业名称、主营业务、核心产品/服务、经营范围和贷款用途等 13 项字段。'}</p>
    <ol><li>请勿修改模板中的字段标签。</li><li>主营业务和核心产品越具体，判定依据越充分。</li><li>空白字段会保留，并可能触发证据层逐级降级。</li></ol>
    <Button type="link" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>查看完整使用说明 <ArrowRightOutlined /></Button>
  </Card>
}

function ProcessingPanel({ scenarioId, fileName }: { scenarioId: ScenarioId; fileName?: string }) {
  const isFiveArticles = isStageBScenario(scenarioId)
  return <section className="processing-panel">
    <div className="processing-orbit"><AuditOutlined /></div>
    <h2>正在进行智能分类</h2><p>{fileName || '企业分类案例'} 已通过格式校验，{isFiveArticles ? `系统正依次执行国民经济分类与${scenarioViews[scenarioId].name}判定。` : '系统正检索行业目录并进行智能判定。'}</p>
    <Progress percent={78} status="active" showInfo={false} strokeColor={{ from: '#0e63f4', to: '#74a9ff' }} />
    <div className="processing-list"><span><CheckCircleFilled /> 企业信息已解析</span><span><CheckCircleFilled /> 行业候选已召回</span><span className="is-processing">● 正在生成判定结论</span></div>
    <small>分类过程通常需要 1–3 分钟，请勿重复提交。</small>
  </section>
}

function ResultPanel({ scenarioId, caseData, result, stageBResult, errorMessage, showReview, setShowReview, reviewText, setReviewText, isSubmittingReview, onBackToClassification, onReclassify, onRetry }: {
  scenarioId: ScenarioId; caseData: ClassificationCase; result: ClassificationResult; stageBResult?: FiveArticlesResult | InclusiveFinanceResult | AgricultureRelatedResult | null; errorMessage?: string; showReview: boolean; setShowReview: (value: boolean) => void; reviewText: string; setReviewText: (value: string) => void; isSubmittingReview: boolean; onBackToClassification: () => void; onReclassify: () => void; onRetry: () => void
}) {
  const navigate = useNavigate()
  const scenarioView = scenarioViews[scenarioId]
  const isFiveArticles = isStageBScenario(scenarioId)
  const needsReview = result.status === 'needs_review'
  const stageAFailed = result.status === 'classification_failed'
  const stageAStatusLabel = stageAFailed ? '判定失败' : needsReview ? '待人工复核' : '已完成'
  const loanConsistencyLabel = result.loan_matches_enterprise === null
    ? '待人工复核'
    : result.loan_matches_enterprise ? '与企业主营一致' : '与企业主营不一致'
  const toggleReview = () => {
    const shouldShow = !showReview
    setShowReview(shouldShow)
    if (shouldShow) {
      window.requestAnimationFrame(() => document.getElementById('classification-review')?.scrollIntoView({ behavior: 'smooth', block: 'center' }))
    }
  }
  return <section className="result-layout">
    {errorMessage && <Alert className="result-error" type="error" showIcon message={errorMessage} action={<Button size="small" onClick={onRetry}>重试分类</Button>} />}
    <Card className="result-card input-result-card" bordered={false} title="Word 企业信息">
      <Descriptions className="result-details source-details" column={1} size="small">
        <Descriptions.Item label="原始文件名">{caseData.original_filename || '--'}</Descriptions.Item>
        {caseData.input_fields.map((field) => <Descriptions.Item key={field.field} label={field.label}>{field.value || '--'}</Descriptions.Item>)}
      </Descriptions>
    </Card>
    <Card className="result-card conclusion-result-card" bordered={false} title={isFiveArticles ? 'Stage A · 国民经济行业分类' : 'AI 判定结论'}>
      <div className={`result-status ${stageAFailed ? 'is-failed' : needsReview ? 'is-review' : ''}`}><span><CheckCircleFilled /></span><div><p>Stage A {stageAStatusLabel}</p><h2>{result.industry_name || stageAStatusLabel}</h2><small>GB/T 4754-2017 · 四级行业分类结果 · 版本 {result.version}</small></div></div>
      <Descriptions className="result-details" column={1} size="small">
        <Descriptions.Item label="行业代码">{result.industry_display_code || '--'}</Descriptions.Item>
        <Descriptions.Item label="行业名称">{result.industry_name || '--'}</Descriptions.Item>
        <Descriptions.Item label="案例状态"><Tag color={stageAFailed ? 'error' : needsReview ? 'warning' : 'success'}>{stageAStatusLabel}</Tag></Descriptions.Item>
        <Descriptions.Item label="匹配依据">{result.matching_basis || '--'}</Descriptions.Item>
      </Descriptions>
      <Divider className="loan-direction-divider" orientation="left" plain>贷款投向结论</Divider>
      <Descriptions className="result-details loan-direction-details" column={1} size="small">
        <Descriptions.Item label="贷款投向代码">{result.loan_industry_display_code || '--'}</Descriptions.Item>
        <Descriptions.Item label="贷款投向名称">{result.loan_industry_name || '--'}</Descriptions.Item>
        <Descriptions.Item label="贷款投向是否一致"><Tag color={result.loan_matches_enterprise === true ? 'success' : 'warning'}>{loanConsistencyLabel}</Tag></Descriptions.Item>
        <Descriptions.Item label="贷款投向匹配依据">{result.loan_matching_basis || '--'}</Descriptions.Item>
        {result.objection?.description && <Descriptions.Item label="关联异议">{result.objection.description}</Descriptions.Item>}
      </Descriptions>
      <div className="result-actions"><Button onClick={onBackToClassification}>返回{scenarioView.name}</Button><Button icon={<DownloadOutlined />} onClick={() => window.location.assign(exportUrl(scenarioId, caseData.id))}>导出 Excel</Button><Button icon={<HistoryOutlined />} onClick={() => navigate(scenarioView.historyPath)}>查看判定历史</Button><Button type="primary" onClick={toggleReview}>提出异议并复核</Button></div>
    </Card>
    {isFiveArticles && scenarioId !== INCLUSIVE_FINANCE_SCENARIO && scenarioId !== AGRICULTURE_RELATED_SCENARIO && <Card className="result-card technology-result-card" bordered={false} title={`Stage B · ${scenarioView.name}判定`}>
      {stageBResult && isFiveArticlesResult(stageBResult) ? <>
        <div className="technology-status-row">
          <div><span>判定状态</span><Tag color={statusColor(stageBResult.status)}>{stageBStatusLabel(scenarioId, stageBResult.status)}</Tag></div>
          <small>{scenarioView.name}版本 {stageBResult.version} · Stage A 结果 #{stageBResult.stage_a_result_id}{stageBResult.mapping_version_id ? ` · 映射版本 ${stageBResult.mapping_version_id}` : ''}</small>
        </div>
        {stageBResult.labels.length > 0 ? <div className="technology-label-list">
          {stageBResult.labels.map((label, index) => {
            return <section className="technology-label" key={`${label.subject}-${label.source_row}-${index}`}>
              <div className="technology-label-heading"><Tag color="blue">{label.subject}</Tag><strong>{label.NEIC_Code} · {label.NEIC_Name}</strong></div>
              <Descriptions column={{ xs: 1, sm: 2 }} size="small">
                {label.taxonomy_path.map((tier, tierIndex) => <Descriptions.Item key={`tier-${tierIndex}`} label={['第一层名称', '第二层名称', '第三层名称', '第四层名称'][tierIndex]}>{tier}</Descriptions.Item>)}
                <Descriptions.Item label="映射来源">版本 {label.mapping_version_id} · 源行 {label.source_row}</Descriptions.Item>
                <Descriptions.Item label="匹配依据" span={2}>{label.matching_basis || '--'}</Descriptions.Item>
                {scenarioId === TECHNOLOGY_FINANCE_SCENARIO && ipIntensiveIndustrySubjects.has(label.subject) && label.ip_intensive_industry_status && <><Descriptions.Item label="知识产权条件"><Tag color={label.ip_intensive_industry_status === 'satisfied' ? 'success' : 'error'}>{label.ip_intensive_industry_status === 'satisfied' ? '满足' : '不满足'}</Tag></Descriptions.Item><Descriptions.Item label="知识产权条件依据" span={2}>{label.ip_intensive_industry_basis || '--'}</Descriptions.Item></>}
              </Descriptions>
              <div className="evidence-summary"><b>映射与业务证据</b>{label.evidence_refs.map((reference, evidenceIndex) => <span key={`${reference.type || 'evidence'}-${evidenceIndex}`}>{evidenceSummary(reference)}</span>)}</div>
            </section>
          })}
        </div> : <Alert className="technology-empty-state" type={stageBResult.status === 'classification_failed' ? 'error' : stageBResult.status === 'needs_review' ? 'warning' : 'info'} showIcon message={stageBStatusLabel(scenarioId, stageBResult.status)} description={stageBEmptyDescription(scenarioId, stageBResult)} />}
        <Divider />
        <section className="consistency-panel">
          <h3>贷款对应的五篇大文章类别与企业类别是否一致</h3>
          <Tag color={consistencyColor(stageBResult.consistency_status)}>{stageBResult.consistency_status ? consistencyLabels[stageBResult.consistency_status] : '待人工复核'}</Tag>
          <p>{stageBResult.consistency_basis || stageBResult.error_detail || '暂无一致性说明。'}</p>
          {stageBResult.consistency_evidence_refs.length > 0 && <div className="evidence-summary"><b>一致性证据</b>{stageBResult.consistency_evidence_refs.map((reference, index) => <span key={`consistency-${index}`}>{evidenceSummary(reference)}</span>)}</div>}
        </section>
      </> : <Alert className="technology-empty-state" type={stageAFailed ? 'error' : 'warning'} showIcon message="Stage B 未执行" description={`Stage A 当前为“${stageAStatusLabel}”，只有 Stage A 完成后才会进入${scenarioView.name}判定。`} />}
    </Card>}
    {scenarioId === AGRICULTURE_RELATED_SCENARIO && <AgricultureResultCard stageBResult={stageBResult} stageAFailed={stageAFailed} stageAStatusLabel={stageAStatusLabel} scenarioViewName={scenarioView.name} />}
    {scenarioId === INCLUSIVE_FINANCE_SCENARIO && <Card className="result-card technology-result-card" bordered={false} title="Stage B · 普惠金融判定">
      {stageBResult && isInclusiveFinanceResult(stageBResult) ? <Descriptions column={1} size="small">
        <Descriptions.Item label="判定状态"><Tag color={statusColor(stageBResult.status)}>{stageBResult.status === 'not_applicable' ? '不属于普惠金融' : stageBStatusLabels[stageBResult.status]}</Tag></Descriptions.Item>
        <Descriptions.Item label="借款主体类型">{stageBResult.borrower_type || '--'}</Descriptions.Item>
        <Descriptions.Item label="计算划型">{stageBResult.computed_size || '--'}{stageBResult.size_consistent === false ? '（与填报不一致）' : ''}</Descriptions.Item>
        <Descriptions.Item label="是否经营性贷款">{stageBResult.is_operating_loan === null ? '待人工复核' : stageBResult.is_operating_loan ? '是' : '否'}</Descriptions.Item>
        <Descriptions.Item label="授信金额">{stageBResult.credit_amount_wan ?? '--'} 万元</Descriptions.Item>
        <Descriptions.Item label="是否属于普惠">{stageBResult.qualifies === null ? '待人工复核' : stageBResult.qualifies ? '是' : '否'}</Descriptions.Item>
        <Descriptions.Item label="普惠子类别">{stageBResult.inclusive_category || '--'}</Descriptions.Item>
        <Descriptions.Item label="判定依据">{stageBResult.basis || stageBResult.error_detail || '--'}</Descriptions.Item>
      </Descriptions> : <Alert type="warning" showIcon message="Stage B 未执行" description="Stage A 完成后才会执行普惠金融判定。" />}
    </Card>}
    {showReview && <Card id="classification-review" className="review-card" bordered={false} title="补充异议信息，发起再次判定">
      <p>新的说明会与原始企业资料一同重新检索和判定，原有结论会保留在历史版本中。</p>
      <Input.TextArea value={reviewText} onChange={(event) => setReviewText(event.target.value)} placeholder="例如：企业实际主要收入来自……，请结合以下情况重新判定" autoSize={{ minRows: 4, maxRows: 6 }} />
      <div><Button onClick={() => setShowReview(false)}>取消</Button><Button type="primary" loading={isSubmittingReview} disabled={!reviewText.trim() || isSubmittingReview} onClick={onReclassify}>提交异议并重新判定</Button></div>
    </Card>}
    <Card className="evidence-card" bordered={false} title="判定过程与候选证据">
      <Timeline items={[
        { color: 'green', children: <><b>企业信息解析完成</b><small>已识别 {caseData.input_fields.length} 项模板字段</small></> },
        { color: 'green', children: <><b>行业候选召回与重排</b><small>保留 {result.candidate_snapshot.length} 个候选证据快照</small></> },
        { color: needsReview ? 'orange' : 'blue', children: <><b>{needsReview ? '等待人工复核' : '生成最终结论'}</b><small>{result.objection?.description ? `本版本已纳入异议：${result.objection.description}` : '仅依据企业输入与命中行业目录片段'}</small></> },
      ]} />
    </Card>
  </section>
}

function AgricultureResultCard({ stageBResult, stageAFailed, stageAStatusLabel, scenarioViewName }: {
  stageBResult?: FiveArticlesResult | InclusiveFinanceResult | AgricultureRelatedResult | null
  stageAFailed: boolean
  stageAStatusLabel: string
  scenarioViewName: string
}) {
  const result = stageBResult && isAgricultureRelatedResult(stageBResult) ? stageBResult : null
  if (!result) return <Card className="result-card technology-result-card" bordered={false} title={`Stage B · ${scenarioViewName}判定`}><Alert type={stageAFailed ? 'error' : 'warning'} showIcon message="Stage B 未执行" description={`Stage A 当前为“${stageAStatusLabel}”，只有 Stage A 完成后才会进入${scenarioViewName}判定。`} /></Card>

  const matched = result.matched_categories.filter((category) => category.result === 'matched')
  const details = result.matched_categories.filter((category) => category.result !== 'matched')
  const statusDescription = result.status === 'classification_failed'
    ? result.error_detail || '涉农判定过程中发生异常，请重试或联系管理员。'
    : result.status === 'needs_review'
      ? result.basis || '存在待人工复核的类别，暂不能形成确定的整体结论。'
      : result.status === 'not_applicable'
        ? result.basis || '四类涉农贷款口径均未命中，明确不属于涉农贷款。'
        : result.basis || '已完成涉农四类判定。'

  return <Card className="result-card technology-result-card" bordered={false} title={`Stage B · ${scenarioViewName}判定`}>
    <div className="technology-status-row"><div><span>判定状态</span><Tag color={statusColor(result.status)}>{result.status === 'completed' ? '判定已完成' : result.status === 'not_applicable' ? '明确不属于涉农贷款' : result.status === 'needs_review' ? '待人工复核' : '判定失败'}</Tag></div><small>涉农版本 {result.version} · Stage A 结果 #{result.stage_a_result_id}</small></div>
    <Descriptions column={1} size="small">
      <Descriptions.Item label="是否涉农"><Tag color={result.is_agriculture_related === true ? 'success' : result.is_agriculture_related === false ? 'default' : 'warning'}>{result.is_agriculture_related === true ? '是' : result.is_agriculture_related === false ? '否' : '待人工复核'}</Tag></Descriptions.Item>
      <Descriptions.Item label="匹配依据">{statusDescription}</Descriptions.Item>
    </Descriptions>
    {matched.length > 0 ? <section className="technology-label-list"><h3>命中类别</h3>{matched.map((category) => <section className="technology-label" key={category.category}><div className="technology-label-heading"><Tag color="blue">类别 {category.category}</Tag><strong>{category.category_name}</strong></div><Descriptions column={1} size="small"><Descriptions.Item label="判定方式">{category.method === 'stage_a' ? 'Stage A' : category.method === 'ai' ? 'AI 兜底' : '规则'}</Descriptions.Item><Descriptions.Item label="匹配依据">{category.basis || '未提供依据'}</Descriptions.Item></Descriptions></section>)}</section> : <Alert type={result.status === 'classification_failed' ? 'error' : result.status === 'needs_review' ? 'warning' : 'info'} showIcon message={result.status === 'not_applicable' ? '明确不属于涉农贷款' : result.status === 'needs_review' ? '涉农结论待人工复核' : '涉农判定失败'} description={statusDescription} />}
    {details.length > 0 && <section className="consistency-panel"><h3>其他类别明细</h3>{details.map((category) => <div className="evidence-summary" key={category.category}><b>{category.category_name}</b><Tag color={category.result === 'needs_review' ? 'warning' : 'default'}>{category.result === 'not_matched' ? '未命中' : category.result === 'not_applicable' ? '不适用' : '待复核'}</Tag><span>{category.basis || '未提供原因'}</span></div>)}</section>}
  </Card>
}

function HistoryPage({ scenarioId }: { scenarioId: ScenarioId }) {
  const navigate = useNavigate()
  const [history, setHistory] = useState<ClassificationHistoryItem[]>([])
  const [caseData, setCaseData] = useState<ClassificationCase>()
  const [errorMessage, setErrorMessage] = useState<string>()
  const scenarioView = scenarioViews[scenarioId]
  const storageKey = currentCaseStorageKey(scenarioId)

  useEffect(() => {
    const caseId = window.sessionStorage.getItem(storageKey)
    if (!caseId) return
    Promise.all([getCase(scenarioId, caseId), getHistory(scenarioId, caseId)])
      .then(([loadedCase, items]) => {
        setCaseData(loadedCase)
        setHistory(items)
      })
      .catch(() => { window.sessionStorage.removeItem(storageKey); setCaseData(undefined); setHistory([]); setErrorMessage('历史版本加载失败，已清除当前场景案例上下文。') })
  }, [scenarioId, storageKey])

  return <main className="page-content history-page">
    <div className="page-breadcrumb"><button onClick={() => navigate('/')} type="button">首页</button><span>/</span> 历史记录</div>
    <section className="history-heading"><div><h1>{scenarioView.name}历史记录</h1><p>查看企业案例的判定结果、复核记录与导出状态。</p></div><Button type="primary" onClick={() => navigate(scenarioView.classifyPath)} icon={<CloudUploadOutlined />}>新建分类</Button></section>
    <Card className="history-card" bordered={false}>
      <div className="history-row history-row-head"><span>企业名称</span><span>行业结论</span><span>匹配依据</span><span>状态</span><span>最近更新时间</span><span>操作</span></div>
      {errorMessage && <div className="history-row empty-row"><Alert type="error" showIcon message={errorMessage} /></div>}
      {history.map((item) => isFiveArticlesResult(item)
        ? <div className="history-row" key={`stage-b-${item.id}`}><b>{caseData?.original_filename || '当前企业案例'}<small>{scenarioView.name}版本 {item.version} · Stage A #{item.stage_a_result_id}</small></b><span className="history-conclusion"><span><strong>{item.loan_neic_code || '--'}</strong> {item.loan_neic_name || '暂无正式标签'}</span><small>{item.labels.length} 个{scenarioView.name}标签{item.consistency_status ? ` · ${consistencyLabels[item.consistency_status]}` : ''}</small></span><span className="history-basis">{stageBEmptyDescription(scenarioId, item)}</span><span><Tag color={statusColor(item.status)}>{stageBStatusLabel(scenarioId, item.status)}</Tag></span><span>{new Date(item.created_at).toLocaleString('zh-CN')}</span><button type="button" onClick={() => navigate(scenarioView.classifyPath)}>查看详情 <ArrowRightOutlined /></button></div>
        : isAgricultureRelatedResult(item)
          ? <div className="history-row" key={`agriculture-${item.id}`}><b>{caseData?.original_filename || '当前企业案例'}<small>涉农版本 {item.version} · Stage A #{item.stage_a_result_id}</small></b><span className="history-conclusion"><strong>{item.is_agriculture_related === true ? '属于涉农贷款' : item.is_agriculture_related === false ? '不属于涉农贷款' : '涉农结论待复核'}</strong><small>{item.matched_categories.filter((category) => category.result === 'matched').map((category) => category.category_name).join('、') || '暂无命中类别'}</small></span><span className="history-basis">{item.basis || item.error_detail || '暂无说明'}</span><span><Tag color={statusColor(item.status)}>{item.status === 'completed' ? '判定已完成' : item.status === 'not_applicable' ? '明确不属于涉农贷款' : item.status === 'needs_review' ? '待人工复核' : '判定失败'}</Tag></span><span>{new Date(item.created_at).toLocaleString('zh-CN')}</span><button type="button" onClick={() => navigate(scenarioView.classifyPath)}>查看详情 <ArrowRightOutlined /></button></div>
        : isInclusiveFinanceResult(item)
          ? <div className="history-row" key={`inclusive-${item.id}`}><b>{caseData?.original_filename || '当前企业案例'}<small>普惠版本 {item.version} · Stage A #{item.stage_a_result_id}</small></b><span className="history-conclusion"><strong>{item.inclusive_category || '未形成普惠子类别'}</strong><small>{item.computed_size || '划型待复核'} · {item.credit_amount_wan ?? '--'} 万元</small></span><span className="history-basis">{item.basis || item.error_detail || '暂无说明'}</span><span><Tag color={statusColor(item.status)}>{item.status === 'not_applicable' ? '不属于普惠金融' : stageBStatusLabels[item.status]}</Tag></span><span>{new Date(item.created_at).toLocaleString('zh-CN')}</span><button type="button" onClick={() => navigate(scenarioView.classifyPath)}>查看详情 <ArrowRightOutlined /></button></div>
          : <div className="history-row" key={item.id}><b>{caseData?.original_filename || '当前企业案例'}<small>版本 {item.version}{item.objection?.description ? ` · 异议：${item.objection.description}` : ''}</small></b><span className="history-conclusion"><span><strong>{item.industry_display_code || '--'}</strong> {item.industry_name || '待人工复核'}</span><small><span>贷款投向 <strong>{item.loan_industry_display_code || '--'}</strong> {item.loan_industry_name || '--'}</span><Tag color={item.loan_matches_enterprise ? 'success' : 'warning'}>{item.loan_matches_enterprise ? '一致' : '不一致'}</Tag></small></span><span className="history-basis">{item.matching_basis || '--'}<small>贷款投向依据：{item.loan_matching_basis || '--'}</small></span><span><Tag color={item.status === 'needs_review' ? 'warning' : 'success'}>{item.status === 'needs_review' ? '待人工复核' : '已完成'}</Tag></span><span>{new Date(item.created_at).toLocaleString('zh-CN')}</span><button type="button" onClick={() => navigate(scenarioView.classifyPath)}>查看详情 <ArrowRightOutlined /></button></div>)}
      {!errorMessage && history.length === 0 && <div className="history-row empty-row"><span>暂无可展示的当前案例版本，请先完成一次分类。</span></div>}
    </Card>
  </main>
}

function HelpPage() {
  return <main className="page-content help-page"><div className="page-breadcrumb"><NavLink to="/">首页</NavLink><span>/</span> 使用说明</div><h1>使用说明</h1><Card bordered={false}><Steps direction="vertical" current={0} items={flowSteps.map(([title, description], index) => ({ title: `${index + 1}. ${title}`, description }))} /></Card></main>
}

function Platform() {
  const availableScenarioIds: readonly ScenarioId[] = [...fiveArticlesScenarioIds, AGRICULTURE_RELATED_SCENARIO]
  return <div className="app-shell"><AppHeader /><Routes><Route path="/" element={<HomePage />} /><Route path="/classify" element={<ClassifyPage scenarioId={NATIONAL_ECONOMY_SCENARIO} />} /><Route path="/history" element={<HistoryPage scenarioId={NATIONAL_ECONOMY_SCENARIO} />} />{availableScenarioIds.flatMap((scenarioId) => [<Route key={`${scenarioId}-classify`} path={scenarioViews[scenarioId].classifyPath} element={<ClassifyPage scenarioId={scenarioId} />} />, <Route key={`${scenarioId}-history`} path={scenarioViews[scenarioId].historyPath} element={<HistoryPage scenarioId={scenarioId} />} />])}<Route path="/help" element={<HelpPage />} /></Routes><AppFooter /></div>
}

function App() {
  return <ConfigProvider theme={{ token: { colorPrimary: '#1264ed', borderRadius: 10, fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' } }}><BrowserRouter><Platform /></BrowserRouter></ConfigProvider>
}

export default App
