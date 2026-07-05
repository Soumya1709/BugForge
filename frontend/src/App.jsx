import React, { useState, useEffect } from 'react'
import { useTheme } from './hooks/useTheme.js'
import Header from './components/Header.jsx'
import CodePanel from './components/CodePanel.jsx'
import StepsFeed from './components/StepsFeed.jsx'
import ResultPanel from './components/ResultPanel.jsx'
import Sidebar from './components/Sidebar.jsx'

export default function App() {
  const { theme, toggle } = useTheme()

  // Editor state
  const [code, setCode]         = useState('')
  const [testCode, setTestCode] = useState('')

  // UI state
  const [validating, setValidating] = useState(false)
  const [running, setRunning]       = useState(false)
  const [validation, setValidation] = useState(null)
  const [steps, setSteps]           = useState(null)
  const [result, setResult]         = useState(null)
  const [agentStatus, setAgentStatus] = useState(null)

  // Session stats
  const [stats, setStats] = useState({ total: 0, solved: 0 })

  // Fetch agent health on mount
  useEffect(() => {
    fetch('/api/health')
      .then(r => r.json())
      .then(setAgentStatus)
      .catch(() => setAgentStatus({ agent: 'Backend offline', dataset_size: 0 }))
  }, [])

  // ── Validate ──────────────────────────────────────────────────────────────
  const handleValidate = async () => {
    if (!testCode.trim()) return
    setValidating(true)
    try {
      const res = await fetch('/api/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ test_code: testCode }),
      })
      setValidation(await res.json())
    } catch {
      setValidation({ valid: false, issues: ['Could not reach backend'], assert_count: 0 })
    } finally {
      setValidating(false)
    }
  }

  // ── Run agent ─────────────────────────────────────────────────────────────
  const handleRun = async () => {
    if (!code.trim() || !testCode.trim()) return

    // Pre-validate
    const v = validation || { valid: true }
    const hard = (v.issues || []).filter(i => !i.includes('Recommend'))
    if (hard.length > 0) {
      setValidation(v)
      return
    }

    setRunning(true)
    setSteps(null)
    setResult(null)

    try {
      const res = await fetch('/api/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, test_code: testCode, max_attempts: 15 }),
      })

      if (!res.ok) {
        const err = await res.json()
        setResult({ error: err.detail || 'Unknown error' })
        return
      }

      const data = await res.json()
      setSteps(data.steps || [])
      setResult(data)
      setStats(prev => ({
        total: prev.total + 1,
        solved: prev.solved + (data.solved ? 1 : 0),
      }))
    } catch (e) {
      setResult({ error: 'Could not reach backend. Is FastAPI running?' })
    } finally {
      setRunning(false)
    }
  }

  // ── Load example from sidebar ─────────────────────────────────────────────
  const handleLoadExample = (ex) => {
    setCode(ex.buggy_code)
    setTestCode(ex.test_code)
    setSteps(null)
    setResult(null)
    setValidation(null)
  }

  // ── Clear ─────────────────────────────────────────────────────────────────
  const handleClear = () => {
    setCode('')
    setTestCode('')
    setSteps(null)
    setResult(null)
    setValidation(null)
  }

  const showResults = steps !== null || result !== null

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <Header
        theme={theme}
        onToggleTheme={toggle}
        agentStatus={agentStatus}
      />

      <div style={{
        flex: 1,
        display: 'flex',
        overflow: 'hidden',
      }}>
        {/* Main content */}
        <main style={{
          flex: 1,
          overflowY: 'auto',
          padding: '28px 32px',
          display: 'flex',
          flexDirection: 'column',
          gap: 28,
          minWidth: 0,
        }}>
          {/* Page title */}
          <div>
            <h1 style={{
              fontSize: 24,
              fontWeight: 700,
              color: 'var(--text-primary)',
              marginBottom: 4,
            }}>
              Debug with Reinforcement Learning
            </h1>
            <p style={{ fontSize: 14, color: 'var(--text-secondary)' }}>
              Paste a buggy Python function and test cases.
              The RL agent applies one fix at a time until all tests pass.
            </p>
          </div>

          {/* Editor panel */}
          <div style={{
            padding: '24px',
            borderRadius: 'var(--radius-lg)',
            background: 'var(--bg-surface)',
            border: '1px solid var(--border)',
            boxShadow: 'var(--shadow-sm)',
          }}>
            <CodePanel
              code={code}
              onCodeChange={setCode}
              testCode={testCode}
              onTestCodeChange={setTestCode}
              onValidate={handleValidate}
              onRun={handleRun}
              validating={validating}
              running={running}
              validation={validation}
            />
          </div>

          {/* Error message */}
          {result?.error && (
            <div style={{
              padding: '14px 16px',
              borderRadius: 'var(--radius-md)',
              background: 'var(--red-bg)',
              border: '1px solid var(--red-border)',
              color: 'var(--red)',
              fontSize: 13,
            }}>
              ⚠️ {result.error}
            </div>
          )}

          {/* Steps feed */}
          {(running || steps !== null) && (
            <div style={{
              padding: '20px 24px',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <StepsFeed steps={steps} running={running} />
            </div>
          )}

          {/* Result panel */}
          {result && !result.error && (
            <div style={{
              padding: '20px 24px',
              borderRadius: 'var(--radius-lg)',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border)',
              boxShadow: 'var(--shadow-sm)',
            }}>
              <ResultPanel result={result} />
            </div>
          )}

          {/* Clear button */}
          {showResults && !running && (
            <div>
              <button
                onClick={handleClear}
                style={{
                  padding: '8px 18px',
                  borderRadius: 'var(--radius-sm)',
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  color: 'var(--text-muted)',
                  fontSize: 13,
                }}
              >
                🔄 Clear & Start Over
              </button>
            </div>
          )}
        </main>

        {/* Sidebar */}
        <div style={{
          borderLeft: '1px solid var(--border)',
          padding: '24px 20px',
          overflowY: 'auto',
          background: 'var(--bg-surface)',
        }}>
          <Sidebar
            onLoadExample={handleLoadExample}
            stats={stats}
          />
        </div>
      </div>
    </div>
  )
}