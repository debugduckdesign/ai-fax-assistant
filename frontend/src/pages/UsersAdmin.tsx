import { useEffect, useState, type FormEvent } from 'react'
import {
  createUser,
  listUsers,
  updateUser,
  type User,
  type UserRole,
} from '../api'

export default function UsersAdmin() {
  const [users, setUsers] = useState<User[]>([])
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<UserRole>('operator')
  const [busy, setBusy] = useState(false)

  async function reload() {
    const data = await listUsers()
    setUsers(data)
  }

  useEffect(() => {
    void (async () => {
      try {
        await reload()
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load users')
      }
    })()
  }, [])

  async function onCreate(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      await createUser({ username: username.trim(), password, role })
      setUsername('')
      setPassword('')
      setRole('operator')
      setMessage('User created.')
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Create failed')
    } finally {
      setBusy(false)
    }
  }

  async function toggleActive(user: User) {
    setError(null)
    setMessage(null)
    try {
      await updateUser(user.id, { is_active: !user.is_active })
      setMessage(`Updated ${user.username}.`)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    }
  }

  async function changeRole(user: User, next: UserRole) {
    setError(null)
    setMessage(null)
    try {
      await updateUser(user.id, { role: next })
      setMessage(`Role updated for ${user.username}.`)
      await reload()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Update failed')
    }
  }

  async function resetPassword(user: User) {
    const next = window.prompt(`New password for ${user.username}`)
    if (!next) return
    setError(null)
    setMessage(null)
    try {
      await updateUser(user.id, { password: next })
      setMessage(`Password reset for ${user.username}.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed')
    }
  }

  return (
    <section className="panel">
      <h1>Users</h1>
      <p className="muted">Create operators and admins for the fax intake UI.</p>

      {error && <p className="error">{error}</p>}
      {message && <p className="ok">{message}</p>}

      <form className="login-form" onSubmit={(e) => void onCreate(e)}>
        <h2>Create user</h2>
        <div className="row gap wrap">
          <label>
            Username
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              maxLength={72}
            />
          </label>
          <label>
            Role
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as UserRole)}
            >
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <button className="button" type="submit" disabled={busy}>
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </form>

      <h2>All users</h2>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Username</th>
              <th>Role</th>
              <th>Active</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id}>
                <td>{u.username}</td>
                <td>
                  <select
                    value={u.role}
                    onChange={(e) =>
                      void changeRole(u, e.target.value as UserRole)
                    }
                  >
                    <option value="operator">operator</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td>{u.is_active ? 'yes' : 'no'}</td>
                <td className="muted">{u.created_at || '—'}</td>
                <td className="row gap">
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() => void toggleActive(u)}
                  >
                    {u.is_active ? 'Deactivate' : 'Activate'}
                  </button>
                  <button
                    className="button secondary"
                    type="button"
                    onClick={() => void resetPassword(u)}
                  >
                    Reset password
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
