import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { fetchScanObjectUrl, getCase, placeCall } from '../api'
import type { CaseRecord } from '../api'

const STATUS_LABEL: Record<string, string> = {
  extracting: 'Extracting',
  awaiting_call: 'Awaiting call',
  calling: 'Calling',
  complete: 'Complete',
  needs_human: 'Needs human',
  error: 'Error',
}

export default function CaseDetail() {
  const { id = '' } = useParams()
  const [record, setRecord] = useState<CaseRecord | null>(null)
  const [scanSrc, setScanSrc] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [calling, setCalling] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)

  useEffect(() => {
    if (!id) return
    let alive = true
    async function load() {
      try {
        const data = await getCase(id)
        if (alive) setRecord(data)
      } catch (err) {
        if (alive) setError(err instanceof Error ? err.message : 'Failed to load')
      }
    }
    void load()
    const timer = window.setInterval(() => void load(), 3000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [id])

  useEffect(() => {
    if (!id || !record) return
    let cancelled = false
    let created: string | null = null
    void fetchScanObjectUrl(id)
      .then((url) => {
        if (cancelled) {
          URL.revokeObjectURL(url)
          return
        }
        created = url
        setScanSrc(url)
      })
      .catch(() => {
        if (!cancelled) setScanSrc(null)
      })
    return () => {
      cancelled = true
      if (created) URL.revokeObjectURL(created)
      setScanSrc(null)
    }
  }, [id, record?.scan_filename])

  async function confirmCall() {
    if (!id) return
    setCalling(true)
    setError(null)
    try {
      await placeCall(id)
      const data = await getCase(id)
      setRecord(data)
      setConfirmOpen(false)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Call failed')
    } finally {
      setCalling(false)
    }
  }

  if (!record) {
    return (
      <section className="panel">
        <p className="muted">{error || 'Loading case…'}</p>
      </section>
    )
  }

  const canCall =
    Boolean(record.call.to) &&
    ['awaiting_call', 'needs_human', 'complete'].includes(record.status)

  const isImage = (record.scan_content_type || '').startsWith('image/') ||
    /\.(png|jpe?g|webp|gif)$/i.test(record.scan_filename)

  return (
    <section className="panel">
      <div className="row between">
        <div>
          <Link to="/" className="muted">
            ← Cases
          </Link>
          <h1>Case {record.id}</h1>
        </div>
        <span className={`chip status-${record.status}`}>
          {STATUS_LABEL[record.status] ?? record.status}
        </span>
      </div>

      {error && <p className="error">{error}</p>}
      {record.error && <p className="error">{record.error}</p>}

      <div className="grid-2">
        <div>
          <h2>Scan</h2>
          {isImage ? (
            scanSrc ? (
              <img className="scan" src={scanSrc} alt={record.scan_filename} />
            ) : (
              <p className="muted">Loading scan…</p>
            )
          ) : scanSrc ? (
            <p>
              <a href={scanSrc} target="_blank" rel="noreferrer">
                Open {record.scan_filename}
              </a>
            </p>
          ) : (
            <p className="muted">Loading scan…</p>
          )}
        </div>

        <div>
          <h2>Extracted fields</h2>
          <table className="table">
            <thead>
              <tr>
                <th>Field</th>
                <th>Value</th>
                <th>Confidence</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(record.fields).map(([name, field]) => (
                <tr key={name}>
                  <td>{name}</td>
                  <td>{field.value || '—'}</td>
                  <td>{field.confidence.toFixed(2)}</td>
                  <td>{field.source}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2>Missing required</h2>
          <p>{record.missing_required.join(', ') || 'None'}</p>

          <h2>Call</h2>
          <ul className="meta">
            <li>
              <strong>To:</strong> {record.call.to || '—'}
            </li>
            <li>
              <strong>Reason:</strong> {record.call.reason || '—'}
            </li>
            <li>
              <strong>Conversation:</strong> {record.call.conversation_id || '—'}
            </li>
            <li>
              <strong>Status:</strong> {record.call.status || '—'}
            </li>
          </ul>

          {canCall && (
            <button
              className="button"
              type="button"
              disabled={calling}
              onClick={() => setConfirmOpen(true)}
            >
              Place call
            </button>
          )}
        </div>
      </div>

      <h2>Transcript</h2>
      <pre className="transcript">{record.call.transcript || 'No transcript yet.'}</pre>

      <h2>case.md</h2>
      <pre className="case-md">{record.case_md || 'Not generated yet.'}</pre>

      {confirmOpen && (
        <div className="modal-backdrop">
          <div className="modal">
            <h3>Place outbound call?</h3>
            <p>
              Call <strong>{record.call.to}</strong> via ElevenLabs to collect:{' '}
              {record.missing_required.join(', ') || 'follow-up details'}.
            </p>
            <div className="row gap">
              <button
                className="button"
                type="button"
                disabled={calling}
                onClick={() => void confirmCall()}
              >
                {calling ? 'Calling…' : 'Confirm call'}
              </button>
              <button
                className="button secondary"
                type="button"
                disabled={calling}
                onClick={() => setConfirmOpen(false)}
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
