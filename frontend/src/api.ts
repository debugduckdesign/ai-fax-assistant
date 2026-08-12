export type CaseStatus =
  | 'extracting'
  | 'awaiting_call'
  | 'calling'
  | 'complete'
  | 'needs_human'
  | 'error'

export type UserRole = 'admin' | 'operator'

export type User = {
  id: string
  username: string
  role: UserRole
  is_active: boolean
  created_at: string
}

export type FieldValue = {
  value: string | null
  confidence: number
  source: string
}

export type CallInfo = {
  to: string | null
  conversation_id: string | null
  status: string | null
  transcript: string | null
  reason: string | null
}

export type CaseRecord = {
  id: string
  status: CaseStatus
  created_at: string
  updated_at: string
  scan_filename: string
  scan_content_type: string | null
  created_by_user_id: string | null
  fields: Record<string, FieldValue>
  missing_required: string[]
  call_recommended: boolean
  call: CallInfo
  error: string | null
  case_md: string | null
}

export type CaseSummary = {
  id: string
  status: CaseStatus
  created_at: string
  updated_at: string
  scan_filename: string
  call_recommended: boolean
  missing_required: string[]
  call_to: string | null
  created_by_user_id: string | null
}

export type CallEvent = {
  id: string
  case_id: string
  user_id: string | null
  username: string | null
  conversation_id: string | null
  to_number: string | null
  status: string
  reason: string | null
  transcript_excerpt: string | null
  created_at: string
  updated_at: string
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  const res = await fetch(path, {
    ...init,
    headers,
    credentials: 'include',
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new ApiError(
      res.status,
      typeof detail === 'string' ? detail : JSON.stringify(detail),
    )
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}

export function login(username: string, password: string): Promise<User> {
  return request('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
}

export function logout(): Promise<{ status: string }> {
  return request('/api/auth/logout', { method: 'POST' })
}

export function getMe(): Promise<User> {
  return request('/api/auth/me')
}

export function listUsers(): Promise<User[]> {
  return request('/api/users')
}

export function createUser(body: {
  username: string
  password: string
  role: UserRole
}): Promise<User> {
  return request('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function updateUser(
  id: string,
  body: { role?: UserRole; is_active?: boolean; password?: string },
): Promise<User> {
  return request(`/api/users/${encodeURIComponent(id)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

export function listCalls(params?: {
  case_id?: string
  status?: string
  user_id?: string
}): Promise<CallEvent[]> {
  const qs = new URLSearchParams()
  if (params?.case_id) qs.set('case_id', params.case_id)
  if (params?.status) qs.set('status', params.status)
  if (params?.user_id) qs.set('user_id', params.user_id)
  const suffix = qs.toString() ? `?${qs}` : ''
  return request(`/api/calls${suffix}`)
}

export function listCases(): Promise<CaseSummary[]> {
  return request('/api/cases')
}

export function getCase(id: string): Promise<CaseRecord> {
  return request(`/api/cases/${encodeURIComponent(id)}`)
}

export function uploadCase(file: File): Promise<CaseRecord> {
  const form = new FormData()
  form.append('file', file)
  return request('/api/cases', { method: 'POST', body: form })
}

export function placeCall(id: string): Promise<{
  case_id: string
  conversation_id: string | null
  status: CaseStatus
  message: string
}> {
  return request(`/api/cases/${encodeURIComponent(id)}/call`, { method: 'POST' })
}

export function getRequirements(): Promise<{ content: string; path: string }> {
  return request('/api/requirements')
}

export function saveRequirements(
  content: string,
): Promise<{ content: string; path: string }> {
  return request('/api/requirements', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export async function fetchScanObjectUrl(id: string): Promise<string> {
  const res = await fetch(`/api/cases/${encodeURIComponent(id)}/scan`, {
    credentials: 'include',
  })
  if (!res.ok) {
    throw new Error('Failed to load scan')
  }
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}
