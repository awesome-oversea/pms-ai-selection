import { getToken } from '@/lib/auth'

const LOCAL_HOST_API_BASE = 'http://127.0.0.1:18000/api/v1'
const GATEWAY_API_BASE = 'http://127.0.0.1:8000/api/v1'

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE
  ?? (process.env.NODE_ENV === 'production' ? GATEWAY_API_BASE : LOCAL_HOST_API_BASE)

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken()
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  })
  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload?.message || payload?.detail || '请求失败')
  }
  return (payload?.data ?? payload) as T
}
