export type CurrentUser = {
  user_id?: string
  username?: string
  tenant_id?: string
  tenant_key?: string
  tenant_name?: string
  roles?: string[]
  is_superuser?: boolean
}

export const TOKEN_KEY = 'pms_workbench_token'
export const TOKEN_COOKIE_KEY = 'pms_workbench_token'

function writeCookie(name: string, value: string, maxAgeSeconds = 60 * 60 * 12): void {
  document.cookie = `${name}=${encodeURIComponent(value)}; Path=/; Max-Age=${maxAgeSeconds}; SameSite=Lax`
}

function deleteCookie(name: string): void {
  document.cookie = `${name}=; Path=/; Max-Age=0; SameSite=Lax`
}

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return window.localStorage.getItem(TOKEN_KEY)
}

export function setToken(token: string): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(TOKEN_KEY, token)
  writeCookie(TOKEN_COOKIE_KEY, token)
}

export function clearToken(): void {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(TOKEN_KEY)
  deleteCookie(TOKEN_COOKIE_KEY)
}
