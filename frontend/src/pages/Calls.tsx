import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listCalls, type CallEvent } from '../api'
import { useAuth } from '../auth'

export default function Calls() {
  const { isAdmin } = useAuth()
  const [calls, setCalls] = useState<CallEvent[]>([])
  const [status, setStatus] = useState('')
  const [caseId, setCaseId] = useState('')
  const [error, setError] = useState<string | null>(null)

  async function reload() {
    const data = await listCalls({
      status: status || undefined,
      case_id: caseId.trim() || undefined,
    })
    setCalls(data)
  }

  useEffect(() => {
    void (async () => {
      try {
        await reload()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load calls')
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <section className="panel">
      <h1>{isAdmin ? 'Call history' : 'My calls'}</h1>
      <p className="muted">
        Outbound ElevenLabs calls indexed in SQLite. Full transcripts remain on
        each case.
      </p>

      <div className="row gap wrap filters">
        <label>
          Status
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All</option>
            <option value="in_progress">in_progress</option>
            <option value="completed">completed</option>
            <option value="failed">failed</option>
          </select>
        </label>
        <label>
          Case ID
          <input
            value={caseId}
            onChange={(e) => setCaseId(e.target.value)}
            placeholder="optional"
          />
        </label>
        <button
          className="button secondary"
          type="button"
          onClick={() =>
            void reload().catch((err) =>
              setError(err instanceof Error ? err.message : 'Failed'),
            )
          }
        >
          Filter
        </button>
      </div>

      {error && <p className="error">{error}</p>}

      <table className="table">
        <thead>
          <tr>
            <th>When</th>
            <th>Case</th>
            {isAdmin && <th>User</th>}
            <th>To</th>
            <th>Status</th>
            <th>Excerpt</th>
          </tr>
        </thead>
        <tbody>
          {calls.length === 0 && (
            <tr>
              <td colSpan={isAdmin ? 6 : 5} className="muted">
                No calls yet.
              </td>
            </tr>
          )}
          {calls.map((c) => (
            <tr key={c.id}>
              <td className="muted">{c.created_at}</td>
              <td>
                <Link to={`/cases/${c.case_id}`}>{c.case_id}</Link>
              </td>
              {isAdmin && <td>{c.username || '—'}</td>}
              <td>{c.to_number || '—'}</td>
              <td>
                <span className={`chip status-${c.status}`}>{c.status}</span>
              </td>
              <td className="muted">
                {(c.transcript_excerpt || c.reason || '—').slice(0, 80)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
