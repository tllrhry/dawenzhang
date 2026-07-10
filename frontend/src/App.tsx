import { useEffect, useState } from 'react'

const defaultApiBaseUrl = 'http://127.0.0.1:8000/api/v1'
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl).replace(/\/$/, '')

type HealthState = 'checking' | 'ok' | 'error'

function App() {
  const [healthState, setHealthState] = useState<HealthState>('checking')
  const [healthMessage, setHealthMessage] = useState('正在检查后端连接…')

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const response = await fetch(`${apiBaseUrl}/health`)
        if (!response.ok) throw new Error(`HTTP ${response.status}`)
        const data = await response.json() as { status?: string }
        if (data.status !== 'ok') throw new Error('后端依赖未就绪')
        setHealthState('ok')
        setHealthMessage('后端、MySQL 和 Redis 已连接')
      } catch (error) {
        setHealthState('error')
        setHealthMessage(`后端暂不可用：${error instanceof Error ? error.message : '未知错误'}`)
      }
    }
    void checkHealth()
  }, [])

  return (
    <main className="page-shell">
      <section className="hero-card">
        <p className="eyebrow">DAWENZHANG · MVP FOUNDATION</p>
        <h1>大文章智能分类</h1>
        <p className="subtitle">前后端基础骨架已就绪，后续业务模块将在此基础上展开。</p>
        <div className={`status status-${healthState}`}>
          <span className="status-dot" />
          {healthMessage}
        </div>
        <p className="api-config">API 地址：<code>{apiBaseUrl}</code></p>
      </section>
    </main>
  )
}

export default App

