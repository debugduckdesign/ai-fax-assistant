import { NavLink, Navigate, Outlet, Route, Routes, useLocation } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth'
import CaseDetail from './pages/CaseDetail'
import CaseList from './pages/CaseList'
import Calls from './pages/Calls'
import Login from './pages/Login'
import Requirements from './pages/Requirements'
import Upload from './pages/Upload'
import UsersAdmin from './pages/UsersAdmin'
import './App.css'

function RequireAuth({ adminOnly = false }: { adminOnly?: boolean }) {
  const { user, loading, isAdmin } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <section className="panel">
        <p className="muted">Loading…</p>
      </section>
    )
  }
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }
  if (adminOnly && !isAdmin) {
    return <Navigate to="/" replace />
  }
  return <Outlet />
}

function Shell() {
  const { user, isAdmin, logout } = useAuth()

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">AI Fax Assistant</div>
        {user && (
          <nav>
            <NavLink to="/" end>
              Cases
            </NavLink>
            <NavLink to="/upload">Upload</NavLink>
            <NavLink to="/calls">Calls</NavLink>
            {isAdmin && (
              <>
                <NavLink to="/admin/users">Users</NavLink>
                <NavLink to="/admin/requirements">Requirements</NavLink>
                <NavLink to="/admin/calls">All calls</NavLink>
              </>
            )}
            <span className="user-chip">{user.username}</span>
            <button
              className="button secondary"
              type="button"
              onClick={() => void logout()}
            >
              Log out
            </button>
          </nav>
        )}
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route element={<Shell />}>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<CaseList />} />
            <Route path="/upload" element={<Upload />} />
            <Route path="/cases/:id" element={<CaseDetail />} />
            <Route path="/calls" element={<Calls />} />
          </Route>
          <Route element={<RequireAuth adminOnly />}>
            <Route path="/admin/users" element={<UsersAdmin />} />
            <Route path="/admin/requirements" element={<Requirements />} />
            <Route path="/admin/calls" element={<Calls />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}
