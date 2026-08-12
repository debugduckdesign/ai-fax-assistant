import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listCalls, placeCall, type CallEvent } from '../api'
import { useAuth } from '../auth'

function canRetry(call: CallEvent): boolean {
  return (
    Boolean(call.to_number) &&
    (call.status === 'failed' ||
      call.status === 'canceled' ||
      call.status === 'completed')
  )
}

export default function Calls() {
  const { isAdmin } = useAuth()
  const [calls, setCalls] = useState<CallEvent[]>([])
  const [status, setStatus] = useState('')
  const [caseId, setCaseId] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [retryingId, setRetryingId] = useState<string | null>(null)
  const [confirmCall, setConfirmCall] = useState<CallEvent | null>(null)

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

  async function confirmRetry() {
    if (!confirmCall) return
    setRetryingId(confirmCall.id)
    setError(null)
    setMessage(null)
    try {
      const result = await placeCall(confirmCall.case_id)
      setMessage(result.message || `Call started for case ${confirmCall.case_id}`)
      setConfirmCall(null)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Retry failed')
    } finally {
      setRetryingId(null)
    }
  }

  const colSpan = isAdmin ? 7 : 6

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
            <option value="canceled">canceled</option>
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
      {message && <p className="ok">{message}</p>}

      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>When</th>
              <th>Case</th>
              {isAdmin && <th>User</th>}
              <th>To</th>
              <th>Status</th>
              <th>Excerpt</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {calls.length === 0 && (
              <tr>
                <td colSpan={colSpan} className="muted">
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
                <td>
                  {canRetry(c) && (
                    <button
                      className="button secondary"
                      type="button"
                      disabled={retryingId === c.id}
                      onClick={() => {
                        setError(null)
                        setMessage(null)
                        setConfirmCall(c)
                      }}
                    >
                      {c.status === 'failed' || c.status === 'canceled'
                        ? 'Retry'
                        : 'Call again'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {confirmCall && (
        <div className="modal-backdrop">
          <div className="modal">
            <h3>
              {confirmCall.status === 'failed' ||
              confirmCall.status === 'canceled'
                ? 'Retry outbound call?'
                : 'Place another call?'}
            </h3>
            <p>
              Call <strong>{confirmCall.to_number}</strong> for case{' '}
              <strong>{confirmCall.case_id}</strong>
              {confirmCall.reason ? (
                <>
                  {' '}
                  — {confirmCall.reason}
                </>
              ) : null}
              .
            </p>
            <div className="row gap">
              <button
                className="button"
                type="button"
                disabled={retryingId === confirmCall.id}
                onClick={() => void confirmRetry()}
              >
                {retryingId === confirmCall.id ? 'Calling…' : 'Confirm'}
              </button>
              <button
                className="button secondary"
                type="button"
                disabled={retryingId === confirmCall.id}
                onClick={() => setConfirmCall(null)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
