import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { uploadCase } from '../api'

export default function Upload() {
  const navigate = useNavigate()
  const [dragging, setDragging] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFile(file: File | null) {
    if (!file) return
    setBusy(true)
    setError(null)
    try {
      const record = await uploadCase(file)
      navigate(`/cases/${record.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <h1>Upload fax</h1>
      <p className="muted">
        Drop a PDF or image scan. Claude vision extracts fields against the
        requirements template.
      </p>

      <label
        className={`dropzone ${dragging ? 'dragging' : ''}`}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          void handleFile(e.dataTransfer.files?.[0] ?? null)
        }}
      >
        <input
          type="file"
          accept=".pdf,image/png,image/jpeg,image/webp,image/gif"
          disabled={busy}
          onChange={(e) => void handleFile(e.target.files?.[0] ?? null)}
        />
        <span className="dropzone-icon" aria-hidden="true">
          ↑
        </span>
        {busy ? (
          <span className="dropzone-title">Uploading and starting extraction…</span>
        ) : (
          <>
            <span className="dropzone-title">Drop fax here or click to browse</span>
            <span className="dropzone-hint">PDF, PNG, JPEG, WebP, or GIF</span>
          </>
        )}
      </label>

      {error && <p className="error">{error}</p>}
    </section>
  )
}
