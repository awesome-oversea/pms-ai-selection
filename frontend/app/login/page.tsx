'use client'

import { FormEvent, Suspense, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'next/navigation'

import { API_BASE, apiFetch } from '@/lib/api'
import { setToken } from '@/lib/auth'

type OIDCDiscovery = {
  enabled?: boolean
  issuer?: string | null
}

type OIDCAuthorize = {
  enabled?: boolean
  authorize_url?: string | null
}

function LoginPageInner() {
  const searchParams = useSearchParams()
  const nextPath = useMemo(() => searchParams.get('next') || '/workbench/selection', [searchParams])
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [oidcEnabled, setOidcEnabled] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const loadOIDC = async () => {
      try {
        const discovery = await apiFetch<OIDCDiscovery>('/auth/oidc/discovery')
        setOidcEnabled(Boolean(discovery.enabled))
      } catch {
        setOidcEnabled(false)
      }
    }
    void loadOIDC()
  }, [])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const payload = await response.json()
      if (!response.ok) {
        throw new Error(payload?.message || payload?.detail || '登录失败')
      }
      const token = payload?.data?.access_token ?? payload?.access_token
      if (!token) {
        throw new Error('未获取到 access token')
      }
      setToken(token)
      if (typeof window !== 'undefined') {
        window.location.replace(nextPath)
        return
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '登录失败')
    } finally {
      setLoading(false)
    }
  }

  const handleSSOLogin = async () => {
    setLoading(true)
    setError(null)
    try {
      const redirectUri = typeof window !== 'undefined' ? `${window.location.origin}/login` : '/login'
      const data = await apiFetch<OIDCAuthorize>(`/auth/oidc/authorize-url?redirect_uri=${encodeURIComponent(redirectUri)}&state=${encodeURIComponent(nextPath)}`)
      if (!data.enabled || !data.authorize_url) {
        throw new Error('SSO 尚未启用')
      }
      if (typeof window !== 'undefined') {
        window.location.assign(data.authorize_url)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'SSO 登录失败')
      setLoading(false)
    }
  }

  return (
    <main className="container" style={{ maxWidth: 520 }}>
      <div className="card">
        <h1>工作台登录</h1>
        <p className="muted">请使用有效账号登录正式工作台。系统不再执行硬编码自动登录。</p>
        <form className="inline-form" onSubmit={handleSubmit}>
          <input
            className="input"
            type="text"
            autoComplete="username"
            placeholder="用户名"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            required
          />
          <input
            className="input"
            type="password"
            autoComplete="current-password"
            placeholder="密码"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
          <button className="btn btn-primary" type="submit" disabled={loading}>
            {loading ? '登录中...' : '登录'}
          </button>
          {oidcEnabled ? (
            <button className="btn btn-secondary" type="button" disabled={loading} onClick={() => void handleSSOLogin()}>
              SSO 登录
            </button>
          ) : null}
        </form>
        <div className="muted" style={{ marginTop: 12 }}>登录成功后跳转到：{nextPath}</div>
        {error ? <div className="card" style={{ marginTop: 12, borderLeft: '4px solid #dc2626' }}><strong>登录失败：</strong>{error}</div> : null}
      </div>
    </main>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="container" style={{ maxWidth: 520 }}><div className="card">正在加载登录参数...</div></main>}>
      <LoginPageInner />
    </Suspense>
  )
}
