'use client'

import { ReactNode } from 'react'
import { Header } from '@/components/layout/Header'
import { Sidebar } from '@/components/layout/Sidebar'
import { AvHealthBadge } from './AvHealthBadge'

type Props = {
  title: string
  subtitle?: string
  children: ReactNode
  actions?: ReactNode
}

export function AvPageShell({ title, subtitle, children, actions }: Props) {
  return (
    <div className="flex h-screen bg-surface-950 text-surface-100">
      <Sidebar />
      <div className="flex-1 overflow-auto">
        <Header title={title} />
        <main className="max-w-7xl mx-auto px-6 py-8 space-y-6">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-surface-100">Alpha Vantage</h2>
              {subtitle && <p className="text-sm text-surface-400 mt-1">{subtitle}</p>}
            </div>
            <div className="flex items-center gap-2">
              <AvHealthBadge />
              {actions}
            </div>
          </div>
          {children}
        </main>
      </div>
    </div>
  )
}
