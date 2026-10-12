import { FormEvent, useEffect, useState } from 'react'

type Severity = 'low' | 'medium' | 'high' | 'critical'
type Risk = {
  title: string
  category: string
  severity: Severity
  explanation: string
  evidence: string[]
  affected_files: string[]
  recommendation: string
}
type Report = {
  repository: string
  summary: string
  overall_risk: Severity
  risks: Risk[]
  confidence: number
  files_inspected: number
  issues_inspected: number
}
type Analysis = { report: Report; trace: string[]; request_id: string }

const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

function RepositoryForm({ onSubmit, busy }: { onSubmit: (repository: string, question: string) => void; busy: boolean }) {
  const [repository, setRepository] = useState('')
  const [question, setQuestion] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit(repository.trim(), question.trim())
  }
  return <form onSubmit={submit} className="panel form">
    <div className="panel-heading"><div><p className="eyebrow">Start an investigation</p><h3>Choose a public repository</h3></div><span className="form-step">01 / 02</span></div>
    <div className="field"><label htmlFor="repository">GitHub repository URL <span aria-hidden="true">*</span></label><input id="repository" type="url" required autoComplete="url" placeholder="https://github.com/owner/repository" value={repository} onChange={event => setRepository(event.target.value)} /></div>
    <div className="field"><label htmlFor="question">Focus area <span className="optional">Optional</span></label><input id="question" maxLength={500} placeholder="e.g. Focus on security and reliability" value={question} onChange={event => setQuestion(event.target.value)} /></div>
    <div className="form-actions"><p>We inspect a bounded sample of public code and issues.</p><button className="primary-button" disabled={busy}>{busy ? 'Investigating…' : 'Analyze repository'}<span aria-hidden="true">↗</span></button></div>
  </form>
}

function InvestigationTrace({ trace }: { trace: string[] }) {
  return <section className="panel trace-panel"><div className="panel-heading"><div><p className="eyebrow">Process</p><h2>Investigation trace</h2></div><span className="count-pill">{trace.length} steps</span></div><ol className="trace">{trace.map(step => <li key={step}><span className="trace-check" aria-hidden="true">✓</span>{step}</li>)}</ol></section>
}

function RepositorySummary({ report }: { report: Report }) {
  return <section className="panel summary"><div className="summary-top"><div><p className="eyebrow">Repository summary</p><h2>{report.repository}</h2></div><span className={`badge ${report.overall_risk}`}>{report.overall_risk} risk</span></div><p className="summary-copy">{report.summary}</p><div className="stats"><div><strong>{Math.round(report.confidence * 100)}%</strong><span>Confidence</span></div><div><strong>{report.files_inspected}</strong><span>Files inspected</span></div><div><strong>{report.issues_inspected}</strong><span>Issues inspected</span></div></div></section>
}

function RiskCard({ risk }: { risk: Risk }) {
  return <article className="panel risk"><div className="risk-heading"><div><p className="category">{risk.category}</p><h3>{risk.title}</h3></div><span className={`badge ${risk.severity}`}>{risk.severity}</span></div><p>{risk.explanation}</p><h4>Evidence</h4><ul>{risk.evidence.map((item, index) => <li key={index}><code>{item}</code></li>)}</ul>{risk.affected_files.length > 0 && <p className="files">Affected: {risk.affected_files.join(', ')}</p>}<h4>Recommendation</h4><p>{risk.recommendation}</p></article>
}

export default function App() {
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [theme, setTheme] = useState<'light' | 'dark'>(() => {
    try { return localStorage.getItem('repopilot-theme') === 'dark' ? 'dark' : 'light' } catch { return 'light' }
  })

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#101923' : '#f6f7f5')
    try { localStorage.setItem('repopilot-theme', theme) } catch { /* Storage may be unavailable. */ }
  }, [theme])

  async function analyze(repository_url: string, question: string) {
    setBusy(true)
    setError('')
    setAnalysis(null)
    try {
      const response = await fetch(`${apiBase}/api/analyze`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ repository_url, question: question || null }) })
      const data = await response.json()
      if (!response.ok) throw new Error(data.error || (response.status === 429 ? 'GitHub rate limit reached.' : 'Analysis failed.'))
      setAnalysis(data as Analysis)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Could not connect to RepoPilot.')
    } finally {
      setBusy(false)
    }
  }

  return <main className="shell">
    <header className="header"><div className="brand"><div className="mark" aria-hidden="true">R<span>.</span></div><div><h1>RepoPilot</h1><p>Repository intelligence</p></div></div><button type="button" className="theme-toggle" aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} mode`} aria-pressed={theme === 'dark'} onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}><span aria-hidden="true">{theme === 'light' ? '◐' : '◑'}</span>{theme === 'light' ? 'Dark mode' : 'Light mode'}</button></header>
    <section className="hero"><div className="hero-label"><span className="status-dot" />Public repository analysis</div><h2>Engineering risks,<br /><em>backed by evidence.</em></h2><p>Get a focused review of a GitHub repository’s code, dependencies, and open issues—with every finding tied to what was inspected.</p></section>
    <RepositoryForm onSubmit={analyze} busy={busy} />
    {busy && <div className="panel loading" role="status"><span className="spinner" />Investigating repository… This can take up to a minute.</div>}
    {error && <div className="panel error" role="alert"><strong>Analysis could not finish</strong><p>{error}</p></div>}
    {analysis && <div className="results"><div className="results-heading"><div><p className="eyebrow">Investigation complete</p><h2>Review results</h2></div><span className="request-id">ID {analysis.request_id.slice(0, 8)}</span></div><RepositorySummary report={analysis.report} /><div className="results-grid"><section className="findings"><div className="section-title"><p className="eyebrow">Findings</p><h2>Priority risks <span>{analysis.report.risks.length}</span></h2></div>{analysis.report.risks.length ? analysis.report.risks.map((risk, index) => <RiskCard risk={risk} key={`${risk.title}-${index}`} />) : <div className="panel empty-state"><strong>No supported risks found</strong><p>The inspected evidence did not support a specific finding. This does not guarantee the repository is risk-free.</p></div>}</section><InvestigationTrace trace={analysis.trace} /></div></div>}
    <footer><span>RepoPilot</span><span>Public repositories only · Findings are limited to inspected evidence.</span></footer>
  </main>
}
