'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { healthApi, observabilityApi } from '@/lib/api'
import { Settings as Cog, RefreshCw, Save, Trash2 } from 'lucide-react'
import { clsx } from 'clsx'

const PREFS_KEY = 'rpi-control-panel-prefs-v1'

interface UiPrefs {
  refreshIntervalSec: number
  defaultMonitoringTab: 'grafana' | 'jaeger' | 'loki' | 'prometheus'
  showDeprecatedNav: boolean
}

const DEFAULT_PREFS: UiPrefs = {
  refreshIntervalSec: 30,
  defaultMonitoringTab: 'grafana',
  showDeprecatedNav: false,
}

function loadPrefs(): UiPrefs {
  if (typeof window === 'undefined') return DEFAULT_PREFS
  try {
    const raw = window.localStorage.getItem(PREFS_KEY)
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS
  } catch {
    return DEFAULT_PREFS
  }
}

export default function SettingsPage() {
  const [prefs, setPrefs] = useState<UiPrefs>(DEFAULT_PREFS)
  const [savedAt, setSavedAt] = useState<number | null>(null)

  useEffect(() => {
    setPrefs(loadPrefs())
  }, [])

  const { data: health, refetch: refetchHealth } = useQuery({
    queryKey: ['settings-health'],
    queryFn: healthApi.getStatus,
  })
  const { data: links } = useQuery({
    queryKey: ['observability', 'links'],
    queryFn: observabilityApi.getLinks,
  })

  const save = () => {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
    setSavedAt(Date.now())
  }
  const reset = () => {
    setPrefs(DEFAULT_PREFS)
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(PREFS_KEY)
    }
    setSavedAt(Date.now())
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Settings" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-3xl mx-auto space-y-6">
            <section className="card p-5 space-y-4">
              <div className="flex items-center gap-3">
                <Cog className="w-5 h-5 text-primary-400" />
                <h3 className="font-semibold text-surface-100">UI preferences</h3>
              </div>
              <p className="text-xs text-surface-500">
                Stored locally in your browser - they don&apos;t affect other users.
              </p>

              <Field label="Auto-refresh interval (seconds)" htmlFor="refresh">
                <input
                  id="refresh"
                  type="number"
                  min={5}
                  max={300}
                  value={prefs.refreshIntervalSec}
                  onChange={(e) => setPrefs({ ...prefs, refreshIntervalSec: Number(e.target.value) })}
                  className="w-32 px-3 py-1.5 rounded bg-surface-900/50 border border-surface-800 text-sm text-surface-100"
                />
              </Field>

              <Field label="Default Monitoring tab" htmlFor="monitoring-tab">
                <select
                  id="monitoring-tab"
                  value={prefs.defaultMonitoringTab}
                  onChange={(e) =>
                    setPrefs({ ...prefs, defaultMonitoringTab: e.target.value as UiPrefs['defaultMonitoringTab'] })
                  }
                  className="px-3 py-1.5 rounded bg-surface-900/50 border border-surface-800 text-sm text-surface-100"
                >
                  <option value="grafana">Grafana</option>
                  <option value="jaeger">Jaeger</option>
                  <option value="loki">Loki</option>
                  <option value="prometheus">Prometheus</option>
                </select>
              </Field>

              <Field label="Show deprecated nav items" htmlFor="show-deprecated">
                <input
                  id="show-deprecated"
                  type="checkbox"
                  checked={prefs.showDeprecatedNav}
                  onChange={(e) => setPrefs({ ...prefs, showDeprecatedNav: e.target.checked })}
                  className="h-4 w-4"
                />
              </Field>

              <div className="flex items-center gap-2 pt-2">
                <button
                  onClick={save}
                  className="px-3 py-1.5 rounded bg-primary-500/20 hover:bg-primary-500/30 text-primary-200 text-sm flex items-center gap-1"
                >
                  <Save className="w-4 h-4" /> Save
                </button>
                <button
                  onClick={reset}
                  className="px-3 py-1.5 rounded bg-surface-800/50 hover:bg-surface-800 text-surface-300 text-sm flex items-center gap-1"
                >
                  <Trash2 className="w-4 h-4" /> Reset
                </button>
                {savedAt && (
                  <span className="text-xs text-emerald-400">
                    Saved {new Date(savedAt).toLocaleTimeString()}
                  </span>
                )}
              </div>
            </section>

            <section className="card p-5 space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-surface-100">Cluster connection</h3>
                <button
                  onClick={() => refetchHealth()}
                  className="px-2 py-1 rounded text-surface-400 hover:text-surface-100 hover:bg-surface-800 text-xs flex items-center gap-1"
                >
                  <RefreshCw className="w-3.5 h-3.5" /> Recheck
                </button>
              </div>
              {health ? (
                <ul className="text-sm text-surface-300 space-y-1">
                  <Row k="API status" v={<Pill ok={health.status === 'healthy'}>{health.status}</Pill>} />
                  <Row k="API version" v={<span className="font-mono text-xs">{health.version}</span>} />
                  <Row
                    k="Kubernetes"
                    v={<Pill ok={health.kubernetes_connected}>{health.kubernetes_connected ? 'connected' : 'down'}</Pill>}
                  />
                  <Row
                    k="MLflow"
                    v={<Pill ok={health.mlflow_connected}>{health.mlflow_connected ? 'connected' : 'down'}</Pill>}
                  />
                  <Row
                    k="MinIO"
                    v={
                      <Pill ok={health.minio_connected ?? false}>
                        {health.minio_connected ? 'connected' : 'down'}
                      </Pill>
                    }
                  />
                  <Row
                    k="Redis"
                    v={
                      <Pill ok={health.redis_connected ?? false}>
                        {health.redis_connected ? 'connected' : 'down'}
                      </Pill>
                    }
                  />
                </ul>
              ) : (
                <p className="text-sm text-surface-500">Loading health...</p>
              )}
            </section>

            <section className="card p-5 space-y-3">
              <h3 className="font-semibold text-surface-100">Dashboard URLs</h3>
              <p className="text-xs text-surface-500">
                Resolved by the management backend at <code>/api/observability/links</code>.
              </p>
              <ul className="text-sm space-y-1">
                {links &&
                  Object.entries(links).map(([key, url]) => (
                    <li key={key} className="flex items-center justify-between border-b border-surface-800 pb-1">
                      <span className="text-surface-400 capitalize">{key.replace(/-/g, ' ')}</span>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="font-mono text-xs text-primary-300 hover:text-primary-200"
                      >
                        {url}
                      </a>
                    </li>
                  ))}
              </ul>
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <label htmlFor={htmlFor} className="text-sm text-surface-300">
        {label}
      </label>
      {children}
    </div>
  )
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <li className="flex items-center justify-between">
      <span className="text-surface-400">{k}</span>
      <span>{v}</span>
    </li>
  )
}

function Pill({ ok, children }: { ok: boolean; children: React.ReactNode }) {
  return (
    <span
      className={clsx(
        'text-xs px-2 py-0.5 rounded-full',
        ok ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300',
      )}
    >
      {children}
    </span>
  )
}
