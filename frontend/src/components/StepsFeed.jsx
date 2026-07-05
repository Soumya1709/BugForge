import React, { useEffect, useState } from 'react'

const ACTION_COLORS = {
  progress:   { bg: 'var(--green-bg)',  border: 'var(--green-border)', text: 'var(--green)'  },
  solved:     { bg: 'var(--green-bg)',  border: 'var(--green-border)', text: 'var(--green)'  },
  noop:       { bg: 'var(--gray-bg)',   border: 'var(--gray-border)',  text: 'var(--text-muted)' },
  regressed:  { bg: 'var(--red-bg)',    border: 'var(--red-border)',   text: 'var(--red)'    },
  timeout:    { bg: 'var(--red-bg)',    border: 'var(--red-border)',   text: 'var(--red)'    },
}

function stepType(step) {
  if (step.timed_out)               return 'timeout'
  if (step.reward >= 10)            return 'solved'
  if (step.reward > 0)              return 'progress'
  if (step.reward <= -1)            return 'regressed'
  return 'noop'
}

function RewardBadge({ reward }) {
  const colors =
    reward >= 10  ? { bg: 'var(--green-bg)',  color: 'var(--green)',       label: `+10 solved`    } :
    reward > 0    ? { bg: 'var(--green-bg)',  color: 'var(--green)',       label: `+${reward.toFixed(1)} progress` } :
    reward === -0.5 ? { bg: 'var(--gray-bg)', color: 'var(--text-muted)', label: '-0.5 no-op'    } :
    reward <= -1  ? { bg: 'var(--red-bg)',    color: 'var(--red)',         label: `${reward.toFixed(1)}` } :
                    { bg: 'var(--amber-bg)',  color: 'var(--amber)',       label: `${reward.toFixed(1)}` }

  return (
    <span style={{
      padding: '2px 9px',
      borderRadius: 99,
      background: colors.bg,
      color: colors.color,
      fontSize: 11,
      fontWeight: 600,
      fontFamily: 'var(--font-mono)',
      whiteSpace: 'nowrap',
    }}>
      {colors.label}
    </span>
  )
}

function PassRateBar({ before, after }) {
  const improved = after > before
  const worsened = after < before
  const color = improved ? 'var(--green)' : worsened ? 'var(--red)' : 'var(--text-muted)'
  const arrow = improved ? '↑' : worsened ? '↓' : '→'

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-secondary)' }}>
        {(before * 100).toFixed(0)}%
      </span>
      <span style={{ color, fontWeight: 700 }}>{arrow}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color }}>
        {(after * 100).toFixed(0)}%
      </span>
    </div>
  )
}

function StepCard({ step, index }) {
  const type = stepType(step)
  const colors = ACTION_COLORS[type]

  return (
    <div
      className="fade-in"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '10px 14px',
        borderRadius: 'var(--radius-sm)',
        background: colors.bg,
        border: `1px solid ${colors.border}`,
        marginBottom: 6,
        animationDelay: `${index * 0.06}s`,
      }}
    >
      {/* Step number */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--text-muted)',
        minWidth: 28,
      }}>
        #{step.attempt}
      </span>

      {/* Action name */}
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
        color: 'var(--text-primary)',
        fontWeight: 500,
        flex: 1,
        minWidth: 0,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
      }}>
        {step.action_name.replace(/_/g, ' ')}
        {!step.applied && (
          <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}> · no-op</span>
        )}
        {step.timed_out && (
          <span style={{ color: 'var(--red)', fontWeight: 400 }}> · timeout</span>
        )}
      </span>

      {/* Pass rate */}
      <PassRateBar before={step.pass_before} after={step.pass_after} />

      {/* Reward */}
      <RewardBadge reward={step.reward} />
    </div>
  )
}

export default function StepsFeed({ steps, running }) {
  const [visible, setVisible] = useState([])

  // Animate steps in one by one
  useEffect(() => {
    if (!steps || steps.length === 0) { setVisible([]); return }
    setVisible([])
    steps.forEach((step, i) => {
      setTimeout(() => {
        setVisible(prev => [...prev, step])
      }, i * 80)
    })
  }, [steps])

  if (!steps && !running) return null

  return (
    <div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: 12,
      }}>
        <h3 style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
          Agent Steps
        </h3>
        {steps && (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            {steps.length} step{steps.length !== 1 ? 's' : ''} taken
          </span>
        )}
      </div>

      {running && visible.length === 0 && (
        <div style={{
          padding: '20px',
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: 13,
        }}>
          <div style={{
            width: 20, height: 20,
            border: '2px solid var(--border)',
            borderTopColor: 'var(--accent)',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
            margin: '0 auto 10px',
          }} />
          Agent is thinking...
        </div>
      )}

      {/* Header row */}
      {visible.length > 0 && (
        <div style={{
          display: 'flex',
          gap: 12,
          padding: '4px 14px',
          marginBottom: 4,
          fontSize: 11,
          color: 'var(--text-muted)',
          fontWeight: 500,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}>
          <span style={{ minWidth: 28 }}>#</span>
          <span style={{ flex: 1 }}>Action</span>
          <span>Pass Rate</span>
          <span>Reward</span>
        </div>
      )}

      {visible.map((step, i) => (
        <StepCard key={i} step={step} index={i} />
      ))}
    </div>
  )
}