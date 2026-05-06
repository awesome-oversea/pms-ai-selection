'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import type { ReactNode } from 'react'
import { useEffect, useMemo, useState } from 'react'

import { clearToken, getToken } from '@/lib/auth'

const navItems = [
  { href: '/', label: '蓝图总览' },
  { href: '/workbench/selection', label: '选品工作台' },
  { href: '/dashboard', label: '利润中枢' },
  { href: '/manager', label: '管理者工作台' },
  { href: '/competitors', label: '竞品监控' },
  { href: '/trends', label: '趋势榜单' },
  { href: '/kpi', label: '管理KPI' },
  { href: '/analyst', label: '分析师工作台' },
  { href: '/models', label: '模型调优' },
  { href: '/procurement', label: '采购工作台' },
  { href: '/finance', label: '财务工作台' },
  { href: '/agents', label: 'Agent 平台' },
  { href: '/knowledge', label: '知识库工作台' },
  { href: '/reports', label: '报告中心' },
  { href: '/operations', label: '运营台' },
]

function matchesPath(pathname: string, href: string): boolean {
  if (href === '/') {
    return pathname === '/'
  }
  return pathname === href || pathname.startsWith(`${href}/`)
}

export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [authenticated, setAuthenticated] = useState(false)

  useEffect(() => {
    setAuthenticated(Boolean(getToken()))
  }, [pathname])

  const currentSection = useMemo(() => {
    const current = navItems.find((item) => matchesPath(pathname, item.href))
    return current?.label ?? '企业级 AI 选品中枢'
  }, [pathname])

  const handleLogout = () => {
    clearToken()
    setAuthenticated(false)
    if (typeof window !== 'undefined') {
      window.location.assign('/')
    }
  }

  return (
    <div className="app-shell">
      <header className="shell-header">
        <div className="shell-header-inner">
          <Link href="/" className="shell-brand" aria-label="返回蓝图总览">
            <span className="shell-brand-mark">PMS</span>
            <span className="shell-brand-copy">
              <strong>企业级 AI 选品中枢</strong>
              <span>{currentSection}</span>
            </span>
          </Link>

          <nav className="shell-nav" aria-label="正式工作台导航">
            {navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className={matchesPath(pathname, item.href) ? 'shell-link shell-link-active' : 'shell-link'}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="shell-actions">
            <span className={authenticated ? 'shell-status shell-status-good' : 'shell-status'}>
              {authenticated ? '已登录工作台' : '蓝图预览'}
            </span>
            {authenticated ? (
              <button type="button" className="btn btn-secondary shell-ghost" onClick={handleLogout}>
                退出
              </button>
            ) : (
              <Link href="/login" className="btn btn-secondary shell-ghost">
                登录
              </Link>
            )}
          </div>
        </div>
      </header>
      <div className="shell-main">{children}</div>
    </div>
  )
}
