import { useEffect, useState } from 'react'
import { getRequirements, saveRequirements } from '../api'

export default function Requirements() {
  const [content, setContent] = useState('')
  const [path, setPath] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    void (async () => {
      try {
        const data = await getRequirements()
        setContent(data.content)
        setPath(data.path)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load')
      }
    })()
  }, [])

  async function onSave() {
    setBusy(true)
    setError(null)
    setSaved(false)
    try {
      const data = await saveRequirements(content)
      setContent(data.content)
      setPath(data.path)
      setSaved(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="panel">
      <div className="row between">
        <div>
          <h1>Requirements</h1>
          <p className="muted">
            Admin-defined markdown template for extraction and call agents.
            {path ? ` Saved at ${path}` : ''}
          </p>
        </div>
        <button className="button" type="button" disabled={busy} onClick={() => void onSave()}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>

      {error && <p className="error">{error}</p>}
      {saved && <p className="ok">Saved.</p>}

      <textarea
        className="editor"
        value={content}
        onChange={(e) => {
          setContent(e.target.value)
          setSaved(false)
        }}
        spellCheck={false}
      />
    </section>
  )
}
