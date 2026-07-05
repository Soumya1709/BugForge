import React, { useState } from 'react'
import { CheckCircle, AlertCircle, Loader } from 'lucide-react'

const editorStyle = {
  width: '100%',
  minHeight: 240,
  padding: '14px 16px',
  background: 'var(--bg-base)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--text-primary)',
  fontFamily: 'var(--font-mono)',
  fontSize: 13.5,
  lineHeight: 1.7,
  resize: 'vertical',
  outline: 'none',
  transition: 'border-color 0.15s',
}

function Label({ children, hint }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)' }}>
        {children}
      </div>
      {hint && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
          {hint}
        </div>
      )}
    </div>
  )
}

export default function CodePanel({
  code, onCodeChange,
  testCode, onTestCodeChange,
  onValidate, onRun,
  validating, running,
  validation,
}) {
  const [codeFocused, setCodeFocused] = useState(false)
  const [testFocused, setTestFocused] = useState(false)

  const canRun = code.trim() && testCode.trim() && !running

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr 1fr',
      gap: 20,
    }}>
      {/* Code editor */}
      <div>
        <Label hint="Paste a single Python function with a bug in it">
          🐛 Buggy Code
        </Label>
        <textarea
          value={code}
          onChange={e => onCodeChange(e.target.value)}
          onFocus={() => setCodeFocused(true)}
          onBlur={() => setCodeFocused(false)}
          placeholder={
            "def factorial(n):\n    result = 0   # bug: should be 1\n    for i in range(1, n + 1):\n        result *= i\n    return result"
          }
          style={{
            ...editorStyle,
            borderColor: codeFocused ? 'var(--accent)' : 'var(--border)',
          }}
          spellCheck={false}
        />
      </div>

      {/* Test editor */}
      <div>
        <Label hint="One assert per line · At least 2 recommended">
          🧪 Test Cases
        </Label>
        <textarea
          value={testCode}
          onChange={e => onTestCodeChange(e.target.value)}
          onFocus={() => setTestFocused(true)}
          onBlur={() => setTestFocused(false)}
          placeholder={
            "assert factorial(5) == 120\nassert factorial(0) == 1\nassert factorial(3) == 6"
          }
          style={{
            ...editorStyle,
            borderColor: testFocused
              ? 'var(--accent)'
              : validation?.valid === false
                ? 'var(--red)'
                : validation?.valid === true
                  ? 'var(--green)'
                  : 'var(--border)',
          }}
          spellCheck={false}
        />

        {/* Validation feedback */}
        {validation && (
          <div style={{ marginTop: 8 }}>
            {validation.issues?.map((issue, i) => (
              <div key={i} style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: 6,
                padding: '6px 10px',
                borderRadius: 'var(--radius-sm)',
                background: issue.includes('Recommend') ? 'var(--amber-bg)' : 'var(--red-bg)',
                border: `1px solid ${issue.includes('Recommend') ? 'var(--amber)' : 'var(--red-border)'}`,
                marginBottom: 4,
                fontSize: 12,
                color: issue.includes('Recommend') ? 'var(--amber)' : 'var(--red)',
              }}>
                <AlertCircle size={13} style={{ marginTop: 2, flexShrink: 0 }} />
                {issue}
              </div>
            ))}
            {validation.valid && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 12,
                color: 'var(--green)',
              }}>
                <CheckCircle size={13} />
                {validation.assert_count} test(s) — looks good!
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action buttons — full width below both editors */}
      <div style={{
        gridColumn: '1 / -1',
        display: 'flex',
        gap: 10,
        alignItems: 'center',
      }}>
        <button
          onClick={onValidate}
          disabled={!testCode.trim() || validating}
          style={{
            padding: '9px 18px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            color: 'var(--text-secondary)',
            fontSize: 13,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          {validating
            ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Validating...</>
            : '🔍 Validate Tests'
          }
        </button>

        <button
          onClick={onRun}
          disabled={!canRun}
          style={{
            padding: '9px 24px',
            borderRadius: 'var(--radius-sm)',
            background: canRun ? 'var(--accent)' : 'var(--bg-elevated)',
            border: 'none',
            color: canRun ? '#fff' : 'var(--text-muted)',
            fontSize: 13,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            boxShadow: canRun ? '0 0 20px var(--accent-glow)' : 'none',
          }}
        >
          {running
            ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Running Agent...</>
            : '▶ Run Agent'
          }
        </button>

        {running && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            Agent is analysing your code...
          </span>
        )}
      </div>
    </div>
  )
}