'use client'

import { useEffect, useRef } from 'react'
import 'xterm/css/xterm.css'
import { buildExecWsUrl } from '@/lib/api'

/**
 * In-browser pod exec terminal backed by xterm.js + the management backend's
 * WebSocket exec endpoint.  Mounts an xterm instance, opens a WebSocket to
 * `/api/cluster/pods/{ns}/{name}/exec`, and pumps bytes both directions.
 */
export function PodTerminal({
  namespace,
  podName,
  container,
  command = '/bin/sh',
  className,
}: {
  namespace: string
  podName: string
  container?: string
  command?: string
  className?: string
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!containerRef.current) return

    let term: import('xterm').Terminal | null = null
    let fit: import('xterm-addon-fit').FitAddon | null = null
    let ws: WebSocket | null = null
    let resizeObserver: ResizeObserver | null = null
    let isMounted = true

    const boot = async () => {
      const [{ Terminal }, { FitAddon }, { WebLinksAddon }] = await Promise.all([
        import('xterm'),
        import('xterm-addon-fit'),
        import('xterm-addon-web-links'),
      ])

      if (!isMounted || !containerRef.current) return

      term = new Terminal({
        convertEol: true,
        cursorBlink: true,
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 13,
        theme: {
          background: '#0b0f17',
          foreground: '#e6e8eb',
          cursor: '#5eead4',
        },
      })
      fit = new FitAddon()
      term.loadAddon(fit)
      term.loadAddon(new WebLinksAddon())
      term.open(containerRef.current)
      fit.fit()

      const url = buildExecWsUrl(namespace, podName, { container, command })
      ws = new WebSocket(url)

      ws.onopen = () => {
        term?.writeln(
          `\x1b[1;32m[connected]\x1b[0m exec ns=${namespace} pod=${podName}` +
            (container ? ` container=${container}` : ''),
        )
      }
      ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
          term?.write(event.data)
        }
      }
      ws.onerror = (event) => {
        term?.writeln(`\r\n\x1b[1;31m[error]\x1b[0m ${String((event as ErrorEvent).message ?? 'socket error')}`)
      }
      ws.onclose = () => {
        term?.writeln('\r\n\x1b[1;33m[disconnected]\x1b[0m')
      }

      term.onData((data) => {
        if (ws?.readyState === WebSocket.OPEN) {
          ws.send(data)
        }
      })

      resizeObserver = new ResizeObserver(() => {
        try {
          fit?.fit()
        } catch {
          /* xterm not yet attached */
        }
      })
      resizeObserver.observe(containerRef.current)
    }

    void boot()

    return () => {
      isMounted = false
      try {
        ws?.close()
      } catch {
        /* ignore */
      }
      resizeObserver?.disconnect()
      term?.dispose()
    }
  }, [namespace, podName, container, command])

  return (
    <div
      ref={containerRef}
      className={className ?? 'w-full h-96 rounded-lg bg-[#0b0f17] border border-surface-800 overflow-hidden'}
    />
  )
}
