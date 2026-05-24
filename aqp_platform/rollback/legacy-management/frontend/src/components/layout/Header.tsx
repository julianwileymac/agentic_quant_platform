'use client'

import { RefreshCw, Bell, User } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

interface HeaderProps {
  title: string
}

export function Header({ title }: HeaderProps) {
  const queryClient = useQueryClient()
  const [isRefreshing, setIsRefreshing] = useState(false)

  const handleRefresh = async () => {
    setIsRefreshing(true)
    await queryClient.invalidateQueries()
    setTimeout(() => setIsRefreshing(false), 500)
  }

  return (
    <header className="h-16 bg-surface-900/30 border-b border-surface-800 flex items-center justify-between px-6">
      <div>
        <h1 className="text-xl font-semibold text-surface-100">{title}</h1>
        <p className="text-sm text-surface-500">
          {new Date().toLocaleDateString('en-US', {
            weekday: 'long',
            year: 'numeric',
            month: 'long',
            day: 'numeric',
          })}
        </p>
      </div>

      <div className="flex items-center gap-4">
        {/* Refresh Button */}
        <button
          onClick={handleRefresh}
          className="btn btn-ghost p-2 rounded-lg"
          title="Refresh data"
        >
          <RefreshCw
            className={`w-5 h-5 ${isRefreshing ? 'animate-spin' : ''}`}
          />
        </button>

        {/* Notifications */}
        <button className="btn btn-ghost p-2 rounded-lg relative" title="Notifications">
          <Bell className="w-5 h-5" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-primary-500 rounded-full"></span>
        </button>

        {/* User Menu */}
        <div className="flex items-center gap-3 pl-4 border-l border-surface-800">
          <div className="text-right">
            <p className="text-sm font-medium text-surface-200">Admin</p>
            <p className="text-xs text-surface-500">rpi-k8s-cluster</p>
          </div>
          <div className="w-9 h-9 rounded-lg bg-primary-500/20 flex items-center justify-center">
            <User className="w-5 h-5 text-primary-400" />
          </div>
        </div>
      </div>
    </header>
  )
}
