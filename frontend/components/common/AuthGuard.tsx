'use client'

import type { ReactNode } from 'react'
import { useEffect, useState } from 'react'

import { apiFetch } from '@/lib/api'
import type { CurrentUser } from '@/lib/auth'
import { clearToken } from '@/lib/auth'

export default function AuthGuard({ children, requireSuperuser = false }: { children: ReactNode; requireSuperuser?: boolean }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const current = await apiFetch<CurrentUser>('/auth/me')
        if (requireSuperuser && !current.is_superuser) {
          setError('需要管理员权限')
          if (typeof window !== 'undefined') {
            window.location.replace('/')
            return
          }
        }
        setUser(current)
      } catch (e) {
        clearToken()
        setError(e instanceof Error ? e.message : '鉴权失败')
        if (typeof window !== 'undefined') {
          const next = encodeURIComponent(window.location.pathname + window.location.search)
          window.location.replace(`/login?next=${next}`)
          return
        }
      } finally {
        setLoading(false)
      }
    }
    void bootstrap()
  }, [])

  if (loading) {
    return <div className="card">正在校验登录态...</div>
  }

  if (error || !user) {
    return <div className="card" style={{ borderLeft: '4px solid #dc2626' }}><strong>工作台鉴权失败：</strong>{error ?? '未登录'}</div>
  }

  return <>{children}</>
}
