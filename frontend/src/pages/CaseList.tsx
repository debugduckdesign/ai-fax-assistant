import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listCases } from '../api'
import type { CaseSummary } from '../api'

const STATUS_LABEL: Record<string, string> = {
  extracting: 'Extracting',
  awaiting_call: 'Awaiting call',
  calling: 'Calling',
  complete: 'Complete',
  needs_human: 'Needs human',
  error: 'Error',
}

export default function CaseList() {
  const [cases, setCases] = useState<CaseSummary[]>([])
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let alive = true
    async function load() {
      try {
        const data = await listCases()
        if (alive) setCases(data)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : 'Failed to load')
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 4000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [])

  return (
    <section className="panel">
      <div className="row between">
        <h1>Cases</h1>
        <Link className="button" to="/upload">
          New upload
        </Link>
      </div>

      {error && <p className="error">{error}</p>}

      {cases.length === 0 ? (
        <div className="empty-state">
          <p className="muted">No cases yet. Upload a fax to begin.</p>
          <Link className="button" to="/upload">
            New upload
          </Link>
        </div>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Status</th>
                <th>Scan</th>
                <th>Missing</th>
                <th>Call to</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {cases.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link to={`/cases/${c.id}`}>{c.id}</Link>
                  </td>
                  <td>
                    <span className={`chip status-${c.status}`}>
                      {STATUS_LABEL[c.status] ?? c.status}
                    </span>
                  </td>
                  <td>{c.scan_filename}</td>
                  <td>{c.missing_required.join(', ') || '—'}</td>
                  <td>{c.call_to || '—'}</td>
                  <td className="muted">
                    {new Date(c.updated_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
