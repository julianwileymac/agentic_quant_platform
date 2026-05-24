'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { clsx } from 'clsx'
import {
  LayoutDashboard,
  Server,
  Boxes,
  HardDrive,
  Activity,
  FlaskConical,
  Settings,
  BookOpen,
  Radio,
  Waves,
  FileText,
  LineChart,
  Workflow,
} from 'lucide-react'

const navigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard, exact: true },
  { name: 'Nodes', href: '/nodes', icon: Server },
  { name: 'Deployments', href: '/deployments', icon: Boxes },
  { name: 'Services', href: '/services', icon: Workflow },
  { name: 'Hardware', href: '/hardware', icon: HardDrive },
  { name: 'Monitoring', href: '/monitoring', icon: Activity },
  { name: 'MLFlow', href: '/mlflow', icon: FlaskConical },
  { name: 'Kafka', href: '/kafka', icon: Radio },
  { name: 'Flink', href: '/flink', icon: Waves },
  { name: 'Documents', href: '/documents', icon: FileText },
  { name: 'Alpha Vantage', href: '/alphavantage', icon: LineChart },
]

const secondaryNavigation = [
  { name: 'Documentation', href: '/docs', icon: BookOpen },
  { name: 'Settings', href: '/settings', icon: Settings },
]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="w-64 bg-surface-900/50 border-r border-surface-800 flex flex-col">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-surface-800">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary-500/20 flex items-center justify-center">
            <Server className="w-5 h-5 text-primary-400" />
          </div>
          <div>
            <h1 className="font-bold text-surface-100">RPi K8s</h1>
            <p className="text-xs text-surface-500">Control Panel</p>
          </div>
        </div>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navigation.map((item) => {
          const isActive = item.exact
            ? pathname === item.href
            : pathname === item.href || pathname.startsWith(`${item.href}/`)
          return (
            <Link
              key={item.name}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-primary-500/10 text-primary-400 border border-primary-500/20'
                  : 'text-surface-400 hover:text-surface-100 hover:bg-surface-800'
              )}
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </Link>
          )
        })}
      </nav>

      {/* Secondary Navigation */}
      <div className="px-3 py-4 border-t border-surface-800 space-y-1">
        {secondaryNavigation.map((item) => {
          const isActive = pathname === item.href
          return (
            <Link
              key={item.name}
              href={item.href}
              className={clsx(
                'flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200',
                isActive
                  ? 'bg-surface-800 text-surface-100'
                  : 'text-surface-500 hover:text-surface-300 hover:bg-surface-800/50'
              )}
            >
              <item.icon className="w-5 h-5" />
              {item.name}
            </Link>
          )
        })}
      </div>

      {/* Cluster Status + Identity (Phase 8 of multi-tenant rollout) */}
      <div className="px-4 py-4 border-t border-surface-800 space-y-2">
        <div className="flex items-center gap-2 text-xs text-surface-500">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary-400 opacity-75"></span>
            <span className="relative inline-flex rounded-full h-2 w-2 bg-primary-500"></span>
          </span>
          Cluster Online
        </div>
        <MgmtIdentityChip />
      </div>
    </aside>
  )
}


function MgmtIdentityChip() {
  // Lazy import + dynamic check so the Sidebar renders cleanly in
  // local-mode (Auth0 not installed / env not set). The Auth0 SDK
  // requires <Auth0Provider> in the tree; the chip degrades to
  // "local mode" when that isn't present.
  if (typeof window === 'undefined') return null

  const domain = process.env.NEXT_PUBLIC_AUTH0_DOMAIN || ''
  if (!domain) {
    return (
      <div className="text-[10px] text-surface-600">
        Local mode (no IdP)
      </div>
    )
  }
  return (
    <a
      href="/auth/profile"
      className="block text-[10px] font-mono text-surface-500 hover:text-surface-300"
    >
      Auth0 protected ({domain})
    </a>
  )
}
