import type {
  InferenceResultOut,
  OverrideIn,
  OverrideOut,
  ProfileIngestedOut,
  ReprocessResultOut,
  RoleOut,
  SSOProfileIn,
  UserSummaryOut,
} from './types'

const API_BASE = '/api'

export class ApiError extends Error {}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? detail
    } catch {
      // response had no JSON body -- keep statusText
    }
    throw new ApiError(`${res.status}: ${detail}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

export const api = {
  getUsers: () => request<UserSummaryOut[]>('/users'),
  getRoles: () => request<RoleOut[]>('/roles'),
  getInference: (userId: string) => request<InferenceResultOut>(`/users/${encodeURIComponent(userId)}/inference`),

  setOverride: (userId: string, payload: OverrideIn) =>
    request<OverrideOut>(`/users/${encodeURIComponent(userId)}/override`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    }),

  resetOverride: (userId: string) =>
    request<void>(`/users/${encodeURIComponent(userId)}/override`, { method: 'DELETE' }),

  reinfer: (userId: string) =>
    request<InferenceResultOut>('/infer', {
      method: 'POST',
      body: JSON.stringify({ user_id: userId }),
    }),

  ingestProfile: (payload: SSOProfileIn) =>
    request<ProfileIngestedOut>('/profiles', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  reprocessAll: () =>
    request<ReprocessResultOut>('/reprocess', {
      method: 'POST',
      body: JSON.stringify({ scope: 'all', respect_pins: true }),
    }),
}
