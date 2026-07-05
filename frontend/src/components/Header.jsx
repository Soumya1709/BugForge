import React from 'react'
import { Sun, Moon} from 'lucide-react'

export default function Header({ theme, onToggleTheme, agentStatus }) {
  const isReady = agentStatus?.agent?.startsWith('DQN')

  return (
    <header style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 28px',
      height: 56,
      borderBottom: '1px solid var(--border)',
      background: 'var(--bg-surface)',
      position: 'sticky',
      top: 0,
      zIndex: 100,
      backdropFilter: 'blur(8px)',
    }}>
      {/* Logo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <span style={{ fontSize: 22 }}>🔧</span>
        <span style={{
          fontFamily: 'var(--font-mono)',
          fontWeight: 600,
          fontSize: 17,
          color: 'var(--text-primary)',
          letterSpacing: '-0.3px',
        }}>
          Bug<span style={{ color: 'var(--accent)' }}>Forge</span>
        </span>
        <span style={{
          fontSize: 11,
          fontWeight: 500,
          padding: '2px 8px',
          borderRadius: 99,
          background: 'var(--accent-glow)',
          color: 'var(--accent)',
          border: '1px solid var(--accent)',
          opacity: 0.8,
          marginLeft: 4,
        }}>
          RL Debugger
        </span>
      </div>

      {/* Right side */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        {/* Agent status pill */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 12px',
          borderRadius: 99,
          background: isReady ? 'var(--green-bg)' : 'var(--amber-bg)',
          border: `1px solid ${isReady ? 'var(--green-border)' : 'var(--amber)'}`,
          fontSize: 12,
          fontWeight: 500,
          color: isReady ? 'var(--green)' : 'var(--amber)',
        }}>
          <span style={{
            width: 6, height: 6,
            borderRadius: '50%',
            background: isReady ? 'var(--green)' : 'var(--amber)',
            animation: isReady ? 'none' : 'pulse 1.5s ease infinite',
          }} />
          {agentStatus ? agentStatus.agent : 'Connecting...'}
        </div>

        {/* Theme toggle */}
        <button
          onClick={onToggleTheme}
          style={{
            width: 36, height: 36,
            borderRadius: 'var(--radius-sm)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: 'var(--text-secondary)',
          }}
          title="Toggle theme"
        >
          {theme === 'dark'
            ? <Sun size={16} />
            : <Moon size={16} />
          }
        </button>
      </div>
    </header>
  )
}