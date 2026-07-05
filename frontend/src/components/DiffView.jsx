import React, { useMemo } from 'react'

function computeDiff(original, fixed) {
  const origLines = original.split('\n')
  const fixedLines = fixed.split('\n')
  const result = []
  const maxLen = Math.max(origLines.length, fixedLines.length)

  for (let i = 0; i < maxLen; i++) {
    const o = origLines[i] ?? ''
    const f = fixedLines[i] ?? ''
    result.push({ orig: o, fixed: f, changed: o !== f, lineNum: i + 1 })
  }
  return result
}

function CodeLine({ text, highlight, side, lineNum }) {
  const bg = highlight
    ? side === 'orig' ? 'var(--red-bg)' : 'var(--green-bg)'
    : 'transparent'
  const color = highlight
    ? side === 'orig' ? 'var(--red)' : 'var(--green)'
    : 'var(--text-primary)'

  return (
    <div style={{
      display: 'flex',
      background: bg,
      borderLeft: highlight
        ? `2px solid ${side === 'orig' ? 'var(--red)' : 'var(--green)'}`
        : '2px solid transparent',
    }}>
      <span style={{
        minWidth: 36,
        padding: '0 8px',
        color: 'var(--text-muted)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        userSelect: 'none',
        textAlign: 'right',
        flexShrink: 0,
      }}>
        {lineNum}
      </span>
      <span style={{
        padding: '0 12px',
        fontFamily: 'var(--font-mono)',
        fontSize: 13,
        color,
        whiteSpace: 'pre',
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
      }}>
        {text || ' '}
      </span>
    </div>
  )
}

export default function DiffView({ original, fixed }) {
  const diff = useMemo(() => computeDiff(original, fixed), [original, fixed])
  const changedCount = diff.filter(d => d.changed).length

  return (
    <div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 10,
      }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          What Changed
        </h3>
        <span style={{
          fontSize: 12,
          color: 'var(--green)',
          background: 'var(--green-bg)',
          padding: '2px 10px',
          borderRadius: 99,
          border: '1px solid var(--green-border)',
        }}>
          {changedCount} line{changedCount !== 1 ? 's' : ''} modified
        </span>
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 2,
        borderRadius: 'var(--radius-md)',
        overflow: 'hidden',
        border: '1px solid var(--border)',
      }}>
        {/* Headers */}
        <div style={{
          padding: '8px 12px',
          background: 'var(--red-bg)',
          borderBottom: '1px solid var(--border)',
          fontSize: 12,
          fontWeight: 600,
          color: 'var(--red)',
        }}>
          ❌ Buggy
        </div>
        <div style={{
          padding: '8px 12px',
          background: 'var(--green-bg)',
          borderBottom: '1px solid var(--border)',
          fontSize: 12,
          fontWeight: 600,
          color: 'var(--green)',
        }}>
          ✅ Fixed
        </div>

        {/* Diff lines */}
        <div style={{ background: 'var(--bg-surface)', overflow: 'auto' }}>
          {diff.map((line, i) => (
            <CodeLine
              key={i}
              text={line.orig}
              highlight={line.changed}
              side="orig"
              lineNum={line.lineNum}
            />
          ))}
        </div>
        <div style={{ background: 'var(--bg-surface)', overflow: 'auto' }}>
          {diff.map((line, i) => (
            <CodeLine
              key={i}
              text={line.fixed}
              highlight={line.changed}
              side="fixed"
              lineNum={line.lineNum}
            />
          ))}
        </div>
      </div>
    </div>
  )
}