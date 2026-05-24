'use client'

import { useEffect, useRef, useState } from 'react'
import { buildLogStreamWsUrl } from '@/lib/api'
import { Pause, Play, Trash2, Download } from 'lucide-react'

/** Live tailing log viewer backed by the management backend WS endpoint. */
export function LogStream({
  namespace,
  podName,
  container,
  tailLines = 200,
  className,
}: {
  namespace: string
  podName: string
  container?: string
  tailLines?: number
  className?: string
}) {
  const [lines, setLines] = useState<string[]>([])
  const [paused, setPaused] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const pendingRef = useRef<string[]>([])

  useEffect(() => {
    setLines([])
    pendingRef.current = []
    const url = buildLogStreamWsUrl(namespace, podName, { container, tailLines })
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onmessage = (event) => {
      if (typeof event.data !== 'string') return
      pendingRef.current.push(event.data)
    }

    const flush = window.setInterval(() => {
      if (paused || pendingRef.current.length === 0) return
      const batch = pendingRef.current.splice(0, pendingRef.current.length)
      setLines((prev) => {
        const next = [...prev, ...batch]
        return next.length > 5000 ? next.slice(next.length - 5000) : next
      })
    }, 200)

    return () => {
      window.clearInterval(flush)
      try {
        ws.close()
      } catch {
        /* ignore */
      }
    }
  }, [namespace, podName, container, tailLines, paused])

  useEffect(() => {
    if (paused) return
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [lines, paused])

  return (
    <div className={className ?? 'rounded-lg border border-surface-800 bg-surface-900/40'}>
      <div className="flex items-center justify-between border-b border-surface-800 px-3 py-2 text-xs text-surface-400">
        <div>
          <span className="text-surface-200 font-medium">{podName}</span>
          <span className="ml-2 text-surface-500">{namespace}</span>
          {container && <span className="ml-2 text-surface-500">/ {container}</span>}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setPaused((p) => !p)}
            className="btn btn-ghost px-2 py-1 rounded text-surface-300 hover:text-surface-100"
            title={paused ? 'Resume' : 'Pause'}
          >
            {paused ? <Play className="w-4 h-4" /> : <Pause className="w-4 h-4" />}
          </button>
          <button
            onClick={() => setLines([])}
            className="btn btn-ghost px-2 py-1 rounded text-surface-300 hover:text-surface-100"
            title="Clear"
          >
            <Trash2 className="w-4 h-4" />
          </button>
          <button
            onClick={() => {
              const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
              const url = URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `${podName}-${Date.now()}.log`
              a.click()
              URL.revokeObjectURL(url)
            }}
            className="btn btn-ghost px-2 py-1 rounded text-surface-300 hover:text-surface-100"
            title="Download"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>
      <div
        ref={scrollRef}
        className="h-80 overflow-y-auto p-3 font-mono text-xs leading-5 text-surface-200"
      >
        {lines.length === 0 ? (
          <div className="text-surface-500 italic">Waiting for log lines...</div>
        ) : (
          lines.map((line, idx) => (
            <div key={idx} className="whitespace-pre-wrap break-words">
              {line}
            </div>
          ))
        )}
      </div>
    </div>
  )
}
