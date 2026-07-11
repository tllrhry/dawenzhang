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
  LockOutlined,
  QuestionCircleOutlined,
  SafetyCertificateOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { BrowserRouter, NavLink, Route, Routes, useNavigate } from 'react-router-dom'
import {
  ApiError,
  classifyCase,
  createCase,
  exportUrl,
  getCase,
  getHistory,
  submitObjection,
  templateUrl,
} from './api'
import type { ClassificationCase, ClassificationResult } from './api'

const currentCaseStorageKey = 'national-economy-current-case-id'

const flowSteps = [
  ['选择分类', '选择业务分类入口'],
  ['下载模板', '下载标准模板文件'],
  ['上传案例', '上传企业信息或案例'],
  ['AI 判定', '智能判定分类结果'],
  ['结果确认', '查看并确认判定结果'],
  ['结果复核', '如有异议发起复核'],
  ['历史导出', '导出历史判定记录'],
]

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
        <p>当前仅开放“国民经济行业分类”，涉农分类与“五篇大文章分类”暂未开放。</p>
      </section>

      <main className="home-content">
        <section className="scenario-grid" aria-label="业务分类入口">
          <Card className="scenario-card scenario-card-active" bordered={false}>
            <div className="scene-icon scene-icon-active"><AuditOutlined /></div>
            <div className="scene-body">
              <h2>国民经济行业分类</h2>
              <p>基于企业经营信息，智能识别唯一四级行业代码与名称。</p>
              <Tag className="available-tag" icon={<CheckCircleFilled />}>已开放</Tag>
              <Button type="primary" size="large" block icon={<ArrowRightOutlined />} iconPosition="end" onClick={() => navigate('/classify')}>
                进入分类
              </Button>
            </div>
            <Divider />
            <button className="learn-link" type="button" onClick={() => navigate('/help')}><InfoCircleOutlined /> 了解更多 <ArrowRightOutlined /></button>
          </Card>

          <LockedScenario title="涉农分类" description="面向涉农相关企业或案例的专项分类识别。" />
          <LockedScenario title="五篇大文章分类" description="包含科技金融、绿色金融、养老金融、数字金融等专题分类识别。" tags={['科技金融', '绿色金融', '养老金融', '数字金融']} />
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

function LockedScenario({ title, description, tags = [] }: { title: string; description: string; tags?: string[] }) {
  return (
    <Card className="scenario-card scenario-card-locked" bordered={false}>
      <div className="scene-icon scene-icon-locked"><LockOutlined /></div>
      <div className="scene-body">
        <h2>{title}</h2><p>{description}</p>
        <Tag className="locked-tag" icon={<LockOutlined />}>暂未开放</Tag>
        {tags.length > 0 && <div className="topic-tags">{tags.map((tag) => <span key={tag}>{tag}</span>)}</div>}
      </div>
      <Divider />
      <span className="learn-link is-muted"><InfoCircleOutlined /> 了解更多 <ArrowRightOutlined /></span>
    </Card>
  )
}

function ClassifyPage() {
  const [stage, setStage] = useState<ClassificationStage>('upload')
  const [selectedFile, setSelectedFile] = useState<File>()
  const [caseData, setCaseData] = useState<ClassificationCase>()
  const [result, setResult] = useState<ClassificationResult>()
  const [errorMessage, setErrorMessage] = useState<string>()
  const [isSubmittingReview, setIsSubmittingReview] = useState(false)
  const [showReview, setShowReview] = useState(false)
  const [reviewText, setReviewText] = useState('')
  const navigate = useNavigate()

  useEffect(() => {
    const caseId = window.sessionStorage.getItem(currentCaseStorageKey)
    if (!caseId) return
    getCase(caseId).then((loadedCase) => {
      setCaseData(loadedCase)
      if (loadedCase.current_result) {
        setResult(loadedCase.current_result)
        setStage('result')
      }
    }).catch(() => window.sessionStorage.removeItem(currentCaseStorageKey))
  }, [])

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

  const runClassification = async (caseId: string) => {
    setStage('processing')
    setErrorMessage(undefined)
    try {
      const classification = await classifyCase(caseId)
      const refreshedCase = await getCase(caseId)
      setResult(classification)
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
      const createdCase = await createCase(selectedFile)
      window.sessionStorage.setItem(currentCaseStorageKey, createdCase.id)
      setCaseData(await getCase(createdCase.id))
      await runClassification(createdCase.id)
    } catch (error) {
      setErrorMessage(formatError(error))
      setStage('upload')
    }
  }

  const retryClassification = async () => {
    if (caseData) await runClassification(caseData.id)
  }

  const reclassify = async () => {
    if (!caseData || !reviewText.trim()) return
    setIsSubmittingReview(true)
    setErrorMessage(undefined)
    try {
      const classification = await submitObjection(caseData.id, reviewText.trim())
      setResult(classification)
      setCaseData(await getCase(caseData.id))
      setReviewText('')
      setShowReview(false)
    } catch (error) {
      setErrorMessage(formatError(error))
    } finally {
      setIsSubmittingReview(false)
    }
  }

  const downloadTemplate = () => {
    window.location.assign(templateUrl())
  }

  return (
    <main className="page-content workspace-page">
      <div className="page-breadcrumb"><button onClick={() => navigate('/')} type="button">首页</button><span>/</span> 国民经济行业分类</div>
      <div className="workspace-heading">
        <span className="workspace-icon"><AuditOutlined /></span>
        <div><h1>国民经济行业分类</h1><p>依据企业经营信息，辅助判定 GB/T 4754-2017 四级行业分类。</p></div>
      </div>
      <Steps className="workspace-steps" current={stage === 'upload' ? 1 : stage === 'processing' ? 3 : 4} size="small" items={flowSteps.map(([title]) => ({ title }))} />

      {stage === 'upload' && (
        <section className="workspace-grid">
          <Card className="upload-card" bordered={false} title="上传企业分类案例" extra={<Tag color="blue">单企业 · Word 模板</Tag>}>
            <div className="template-panel">
              <div><FileTextOutlined /><span><b>国民经济类别模板</b><small>请使用标准模板填写企业信息后上传</small></span></div>
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
          <AsideGuide />
        </section>
      )}

      {stage === 'processing' && <ProcessingPanel fileName={caseData?.original_filename || selectedFile?.name} />}
      {stage === 'result' && result && caseData && <ResultPanel caseData={caseData} result={result} errorMessage={errorMessage} showReview={showReview} setShowReview={setShowReview} reviewText={reviewText} setReviewText={setReviewText} isSubmittingReview={isSubmittingReview} onReclassify={() => void reclassify()} onRetry={() => void retryClassification()} />}
    </main>
  )
}

function AsideGuide() {
  return <Card className="aside-guide" bordered={false} title={<><QuestionCircleOutlined /> 填写说明</>}>
    <p>模板包含企业名称、主营业务、核心产品/服务、经营范围和贷款用途等 13 项字段。</p>
    <ol><li>请勿修改模板中的字段标签。</li><li>主营业务和核心产品越具体，判定依据越充分。</li><li>空白字段会保留，并可能触发证据层逐级降级。</li></ol>
    <Button type="link" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>查看完整使用说明 <ArrowRightOutlined /></Button>
  </Card>
}

function ProcessingPanel({ fileName }: { fileName?: string }) {
  return <section className="processing-panel">
    <div className="processing-orbit"><AuditOutlined /></div>
    <h2>正在进行智能分类</h2><p>{fileName || '企业分类案例'} 已通过格式校验，系统正检索行业目录并进行智能判定。</p>
    <Progress percent={78} status="active" showInfo={false} strokeColor={{ from: '#0e63f4', to: '#74a9ff' }} />
    <div className="processing-list"><span><CheckCircleFilled /> 企业信息已解析</span><span><CheckCircleFilled /> 行业候选已召回</span><span className="is-processing">● 正在生成判定结论</span></div>
    <small>分类过程通常需要 1–3 分钟，请勿重复提交。</small>
  </section>
}

function ResultPanel({ caseData, result, errorMessage, showReview, setShowReview, reviewText, setReviewText, isSubmittingReview, onReclassify, onRetry }: {
  caseData: ClassificationCase; result: ClassificationResult; errorMessage?: string; showReview: boolean; setShowReview: (value: boolean) => void; reviewText: string; setReviewText: (value: string) => void; isSubmittingReview: boolean; onReclassify: () => void; onRetry: () => void
}) {
  const navigate = useNavigate()
  const needsReview = result.status === 'needs_review'
  return <section className="result-layout">
    {errorMessage && <Alert className="result-error" type="error" showIcon message={errorMessage} action={<Button size="small" onClick={onRetry}>重试分类</Button>} />}
    <Card className="result-card input-result-card" bordered={false} title="Word 企业信息">
      <Descriptions className="result-details source-details" column={1} size="small">
        <Descriptions.Item label="原始文件名">{caseData.original_filename || '--'}</Descriptions.Item>
        {caseData.input_fields.map((field) => <Descriptions.Item key={field.field} label={field.label}>{field.value || '--'}</Descriptions.Item>)}
      </Descriptions>
    </Card>
    <Card className="result-card conclusion-result-card" bordered={false} title="AI 判定结论">
      <div className="result-status"><span><CheckCircleFilled /></span><div><p>{needsReview ? 'AI 判定需人工复核' : 'AI 判定已完成'}</p><h2>{result.industry_name || '待人工复核'}</h2><small>GB/T 4754-2017 · 四级行业分类结果 · 版本 {result.version}</small></div></div>
      <Descriptions className="result-details" column={1} size="small">
        <Descriptions.Item label="行业代码">{result.industry_code || '--'}</Descriptions.Item>
        <Descriptions.Item label="行业名称">{result.industry_name || '--'}</Descriptions.Item>
        <Descriptions.Item label="案例状态"><Tag color={needsReview ? 'warning' : 'success'}>{needsReview ? '待人工复核' : '已完成'}</Tag></Descriptions.Item>
        <Descriptions.Item label="匹配依据">{result.matching_basis || '--'}</Descriptions.Item>
      </Descriptions>
      <Divider className="loan-direction-divider" orientation="left" plain>贷款投向结论</Divider>
      <Descriptions className="result-details loan-direction-details" column={1} size="small">
        <Descriptions.Item label="贷款投向代码">{result.loan_industry_code || '--'}</Descriptions.Item>
        <Descriptions.Item label="贷款投向名称">{result.loan_industry_name || '--'}</Descriptions.Item>
        <Descriptions.Item label="贷款投向是否一致"><Tag color={result.loan_matches_enterprise ? 'success' : 'warning'}>{result.loan_matches_enterprise ? '与企业主营一致' : '与企业主营不一致'}</Tag></Descriptions.Item>
        <Descriptions.Item label="贷款投向匹配依据">{result.loan_matching_basis || '--'}</Descriptions.Item>
        {result.objection?.description && <Descriptions.Item label="关联异议">{result.objection.description}</Descriptions.Item>}
      </Descriptions>
      <div className="result-actions"><Button icon={<DownloadOutlined />} onClick={() => window.location.assign(exportUrl(caseData.id))}>导出 Excel</Button><Button icon={<HistoryOutlined />} onClick={() => navigate('/history')}>查看判定历史</Button><Button type="primary" onClick={() => setShowReview(!showReview)}>提出异议并复核</Button></div>
    </Card>
    {showReview && <Card className="review-card" bordered={false} title="补充异议信息，发起再次判定">
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

function HistoryPage() {
  const navigate = useNavigate()
  const [history, setHistory] = useState<ClassificationResult[]>([])
  const [caseData, setCaseData] = useState<ClassificationCase>()
  const [errorMessage, setErrorMessage] = useState<string>()

  useEffect(() => {
    const caseId = window.sessionStorage.getItem(currentCaseStorageKey)
    if (!caseId) return
    Promise.all([getCase(caseId), getHistory(caseId)])
      .then(([loadedCase, items]) => {
        setCaseData(loadedCase)
        setHistory(items)
      })
      .catch(() => setErrorMessage('历史版本加载失败，请稍后重试。'))
  }, [])

  return <main className="page-content history-page">
    <div className="page-breadcrumb"><button onClick={() => navigate('/')} type="button">首页</button><span>/</span> 历史记录</div>
    <section className="history-heading"><div><h1>分类历史记录</h1><p>查看企业案例的判定结果、复核记录与导出状态。</p></div><Button type="primary" onClick={() => navigate('/classify')} icon={<CloudUploadOutlined />}>新建分类</Button></section>
    <Card className="history-card" bordered={false}>
      <div className="history-row history-row-head"><span>企业名称</span><span>行业结论</span><span>匹配依据</span><span>状态</span><span>最近更新时间</span><span>操作</span></div>
      {errorMessage && <div className="history-row empty-row"><Alert type="error" showIcon message={errorMessage} /></div>}
      {history.map((item) => <div className="history-row" key={item.id}><b>{caseData?.original_filename || '当前企业案例'}<small>版本 {item.version}{item.objection?.description ? ` · 异议：${item.objection.description}` : ''}</small></b><span className="history-conclusion"><span><strong>{item.industry_code || '--'}</strong> {item.industry_name || '待人工复核'}</span><small><span>贷款投向 <strong>{item.loan_industry_code || '--'}</strong> {item.loan_industry_name || '--'}</span><Tag color={item.loan_matches_enterprise ? 'success' : 'warning'}>{item.loan_matches_enterprise ? '一致' : '不一致'}</Tag></small></span><span className="history-basis">{item.matching_basis || '--'}<small>贷款投向依据：{item.loan_matching_basis || '--'}</small></span><span><Tag color={item.status === 'needs_review' ? 'warning' : 'success'}>{item.status === 'needs_review' ? '待人工复核' : '已完成'}</Tag></span><span>{new Date(item.created_at).toLocaleString('zh-CN')}</span><button type="button" onClick={() => navigate('/classify')}>查看详情 <ArrowRightOutlined /></button></div>)}
      {!errorMessage && history.length === 0 && <div className="history-row empty-row"><span>暂无可展示的当前案例版本，请先完成一次分类。</span></div>}
    </Card>
  </main>
}

function HelpPage() {
  return <main className="page-content help-page"><div className="page-breadcrumb"><NavLink to="/">首页</NavLink><span>/</span> 使用说明</div><h1>使用说明</h1><Card bordered={false}><Steps direction="vertical" current={0} items={flowSteps.map(([title, description], index) => ({ title: `${index + 1}. ${title}`, description }))} /></Card></main>
}

function Platform() {
  return <div className="app-shell"><AppHeader /><Routes><Route path="/" element={<HomePage />} /><Route path="/classify" element={<ClassifyPage />} /><Route path="/history" element={<HistoryPage />} /><Route path="/help" element={<HelpPage />} /></Routes><AppFooter /></div>
}

function App() {
  return <ConfigProvider theme={{ token: { colorPrimary: '#1264ed', borderRadius: 10, fontFamily: 'Inter, PingFang SC, Microsoft YaHei, sans-serif' } }}><BrowserRouter><Platform /></BrowserRouter></ConfigProvider>
}

export default App
