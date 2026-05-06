import type { Metadata, Viewport } from 'next'
import type { ReactNode } from 'react'

import AppShell from '@/components/common/AppShell'

import './globals.css'

export const metadata: Metadata = {
  title: 'FMS / PMS 企业级 AI 选品中枢',
  applicationName: 'FMS / PMS 企业级 AI 选品中枢',
  description: '企业级选品工作台、AI 中台、数据平台与交付运维统一入口',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    statusBarStyle: 'black-translucent',
    title: 'AI 选品中枢',
  },
  formatDetection: {
    telephone: false,
  },
  other: {
    'mobile-web-app-capable': 'yes',
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
  themeColor: '#07111f',
}

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  )
}
