import React, { useState } from 'react'
import { Copy, CheckCheck } from 'lucide-react'
import DiffView from './DiffView.jsx'

export default function ResultPanel({ result }) {
  const [copied, setCopied] = useState(false)

  if (!result) return null

  const handleCopy = () => {
    navigator.clipboard.writeText(result.final_code)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  if (result.already_passing) {
    return (
      <div className="fade-in" style={{
        padding: '18px 20px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--green-bg)',
        border: '1px solid var(--green-border)',
      }}>
        <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--green)', marginBottom: 4 }}>
          ✅ Already Passing
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
          Your code passes all tests — no fix needed.
        </div>
      </div>
    )
  }

  if (result.solved) {
    return (
      <div className="fade-in">
        {/* Solved banner */}
        <div style={{
          padding: '16px 20px',
          borderRadius: 'var(--radius-md)',
          background: 'var(--green-bg)',
          border: '1px solid var(--green-border)',
          marginBottom: 20,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--green)', marginBottom: 2 }}>
              ✅ Bug Fixed!
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
              Solved in {result.steps.length} step{result.steps.length !== 1 ? 's' : ''} ·{' '}
              All {result.final_total} tests passing
            </div>
          </div>
          <button
            onClick={handleCopy}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: '8px 14px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              color: 'var(--text-secondary)',
              fontSize: 12,
              fontWeight: 500,
            }}
          >
            {copied
              ? <><CheckCheck size={13} style={{ color: 'var(--green)' }} /> Copied!</>
              : <><Copy size={13} /> Copy fixed code</>
            }
          </button>
        </div>

        {/* Diff view */}
        <DiffView original={result.original_code} fixed={result.final_code} />
      </div>
    )
  }

  // Not solved
  return (
    <div className="fade-in">
      <div style={{
        padding: '16px 20px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--red-bg)',
        border: '1px solid var(--red-border)',
        marginBottom: 16,
      }}>
        <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--red)', marginBottom: 6 }}>
          ❌ Not Solved
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.7 }}>
          The agent used all its attempts without fully fixing the bug.
          Final pass rate: <strong style={{ color: 'var(--text-primary)' }}>
            {result.final_passed}/{result.final_total} tests
          </strong>
        </div>
      </div>

      <div style={{
        padding: '14px 16px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
        fontSize: 13,
        color: 'var(--text-secondary)',
        lineHeight: 1.8,
      }}>
        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 8 }}>
          Why this happens
        </div>
        <ul style={{ paddingLeft: 18 }}>
          <li>The bug type may be outside the agent's 8 supported actions</li>
          <li>Your tests may not be specific enough to guide the agent</li>
          <li>Try adding more edge-case tests that would only pass on correct code</li>
        </ul>
      </div>

      {/* Show partial result code */}
      {result.final_code !== result.original_code && (
        <div style={{ marginTop: 16 }}>
          <DiffView original={result.original_code} fixed={result.final_code} />
        </div>
      )}
    </div>
  )
}