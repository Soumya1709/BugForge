import React, { useEffect, useState } from 'react'
import { Shuffle } from 'lucide-react'

function StatBox({ label, value, color }) {
  return (
    <div style={{
      padding: '10px 12px',
      borderRadius: 'var(--radius-sm)',
      background: 'var(--bg-elevated)',
      border: '1px solid var(--border)',
      textAlign: 'center',
      flex: 1,
    }}>
      <div style={{
        fontSize: 22,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        color: color || 'var(--text-primary)',
      }}>
        {value}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>
        {label}
      </div>
    </div>
  )
}

export default function Sidebar({ onLoadExample, stats }) {
  const [examples, setExamples] = useState([])
  const [bugFilter, setBugFilter] = useState('any')
  const [loading, setLoading] = useState(false)

 const fetchExamples = async (bugCount) => {
    setLoading(true)
    try {
      const url = bugCount === 'any' || bugCount === null
        ? '/api/examples?limit=50'
        : `/api/examples?bug_count=${bugCount}&limit=50`
      const res = await fetch(url)
      const data = await res.json()
      setExamples(Array.isArray(data) ? data : [])
    } catch (e) {
      setExamples([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchExamples(bugFilter === 'any' ? null : bugFilter) }, [])

  const handleFilterChange = (val) => {
    setBugFilter(val)
    fetchExamples(val === 'any' ? null : val)
  }

  const handleRandom = () => {
    const pool = examples.filter(e =>
      bugFilter === 'any' || e.bug_count === parseInt(bugFilter)
    )
    if (pool.length > 0) {
      onLoadExample(pool[Math.floor(Math.random() * pool.length)])
    }
  }

  const solveRate = stats.total > 0
    ? Math.round((stats.solved / stats.total) * 100)
    : null

  return (
    <aside style={{
      width: 260,
      flexShrink: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 20,
    }}>

      {/* Session stats */}
      <div style={{
        padding: '16px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
      }}>
        <div style={{
          fontSize: 12,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          color: 'var(--text-muted)',
          marginBottom: 12,
        }}>
          Session Stats
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <StatBox
            label="Total Runs"
            value={stats.total}
          />
          <StatBox
            label="Solved"
            value={stats.solved}
            color="var(--green)"
          />
          <StatBox
            label="Rate"
            value={solveRate !== null ? `${solveRate}%` : '—'}
            color={solveRate >= 60 ? 'var(--green)' : solveRate >= 30 ? 'var(--amber)' : 'var(--red)'}
          />
        </div>
      </div>

      {/* Example loader */}
      <div style={{
        padding: '16px',
        borderRadius: 'var(--radius-md)',
        background: 'var(--bg-surface)',
        border: '1px solid var(--border)',
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
      }}>
        <div style={{
          fontSize: 12,
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          color: 'var(--text-muted)',
          marginBottom: 12,
        }}>
          Try an Example
        </div>

        {/* Filter */}
        <div style={{ marginBottom: 10 }}>
          <label style={{ fontSize: 12, color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>
            Bug count
          </label>
          <select
            value={bugFilter}
            onChange={e => handleFilterChange(e.target.value)}
            style={{
              width: '100%',
              padding: '7px 10px',
              borderRadius: 'var(--radius-sm)',
              background: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
              fontSize: 13,
              outline: 'none',
              cursor: 'pointer',
            }}
          >
            <option value="any">Any</option>
            <option value="1">1 bug</option>
            <option value="2">2 bugs</option>
            <option value="3">3 bugs</option>
          </select>
        </div>

        <button
          onClick={handleRandom}
          disabled={loading || examples.length === 0}
          style={{
            width: '100%',
            padding: '9px',
            borderRadius: 'var(--radius-sm)',
            background: 'var(--accent)',
            border: 'none',
            color: '#fff',
            fontSize: 13,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 7,
            marginBottom: 12,
            opacity: loading || examples.length === 0 ? 0.5 : 1,
          }}
        >
          <Shuffle size={14} />
          Load Random Example
        </button>

        {/* Example list */}
        <div style={{
          flex: 1,
          overflowY: 'auto',
          maxHeight: 360,
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          {loading && (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 12, padding: 16 }}>
              Loading...
            </div>
          )}
          {!loading && examples.slice(0, 30).map(ex => (
            <button
              key={ex.id}
              onClick={() => onLoadExample(ex)}
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: 'var(--radius-sm)',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
                fontSize: 12,
                textAlign: 'left',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 6,
              }}
            >
              <span style={{
                fontFamily: 'var(--font-mono)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {ex.function_name}
              </span>
              <span style={{
                fontSize: 10,
                padding: '1px 6px',
                borderRadius: 99,
                background: ex.bug_count === 1
                  ? 'var(--green-bg)'
                  : ex.bug_count === 2
                    ? 'var(--amber-bg)'
                    : 'var(--red-bg)',
                color: ex.bug_count === 1
                  ? 'var(--green)'
                  : ex.bug_count === 2
                    ? 'var(--amber)'
                    : 'var(--red)',
                flexShrink: 0,
              }}>
                {ex.bug_count}b
              </span>
            </button>
          ))}
        </div>

        {!loading && examples.length > 0 && (
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textAlign: 'center', marginTop: 8 }}>
            {examples.length} examples available
          </div>
        )}
      </div>
    </aside>
  )
}