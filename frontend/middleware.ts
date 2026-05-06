import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

const PROTECTED_PREFIXES = ['/workbench', '/agents', '/reports', '/dashboard', '/manager', '/knowledge', '/operations']

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  const isProtected = PROTECTED_PREFIXES.some((prefix) => pathname.startsWith(prefix))
  if (!isProtected) {
    return NextResponse.next()
  }

  const token = request.cookies.get('pms_workbench_token')?.value
  if (token) {
    return NextResponse.next()
  }

  const loginUrl = new URL('/login', request.url)
  loginUrl.searchParams.set('next', `${pathname}${search}`)
  return NextResponse.redirect(loginUrl)
}

export const config = {
  matcher: [
    '/workbench/:path*',
    '/agents/:path*',
    '/reports/:path*',
    '/dashboard/:path*',
    '/manager/:path*',
    '/knowledge/:path*',
    '/operations/:path*',
    '/competitors/:path*',
    '/trends/:path*',
    '/kpi/:path*',
    '/analyst/:path*',
    '/models/:path*',
    '/procurement/:path*',
    '/finance/:path*',
  ],
}
