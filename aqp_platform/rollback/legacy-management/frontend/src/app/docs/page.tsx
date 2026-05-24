'use client'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { BookOpen, ExternalLink, FileCode, Layers, Workflow, FlaskConical, Database } from 'lucide-react'

const SECTIONS: Array<{
  title: string
  description: string
  icon: React.ElementType
  links: Array<{ label: string; href: string; description?: string }>
}> = [
  {
    title: 'Management API',
    description: 'OpenAPI spec for the FastAPI backend (cluster, deployments, observability, traces).',
    icon: FileCode,
    links: [
      { label: 'Swagger UI', href: '/api/docs', description: 'Interactive request/response sandbox' },
      { label: 'ReDoc', href: '/api/redoc', description: 'Read-only API reference' },
      { label: 'OpenAPI JSON', href: '/api/openapi.json', description: 'Machine-readable schema' },
    ],
  },
  {
    title: 'Cluster surfaces',
    description: 'Quick links to every dashboard that the management console proxies.',
    icon: Layers,
    links: [
      { label: 'Grafana', href: '/api/observability/iframe/grafana' },
      { label: 'Jaeger', href: '/api/observability/iframe/jaeger' },
      { label: 'Loki', href: '/api/observability/iframe/loki' },
      { label: 'Prometheus', href: '/api/observability/iframe/prometheus' },
      { label: 'DataHub', href: '/api/observability/iframe/datahub' },
      { label: 'Argo Workflows', href: '/api/observability/iframe/argo' },
      { label: 'Dagster', href: '/api/observability/iframe/dagster' },
    ],
  },
  {
    title: 'Operational runbooks',
    description: 'In-repo guides for operating the platform.',
    icon: Workflow,
    links: [
      { label: 'README', href: 'https://github.com/julianwiley/rpi_kubernetes#readme' },
      { label: 'Bootstrap scripts', href: 'https://github.com/julianwiley/rpi_kubernetes/tree/main/bootstrap' },
      { label: 'Deployment status', href: 'https://github.com/julianwiley/rpi_kubernetes/blob/main/DEPLOYMENT_STATUS.md' },
      { label: 'KServe install', href: 'https://github.com/julianwiley/rpi_kubernetes/tree/main/kubernetes/mlops/kserve/install' },
    ],
  },
  {
    title: 'SDK + integrations',
    description: 'Python SDK for talking to the cluster from a developer laptop.',
    icon: FlaskConical,
    links: [
      { label: 'rpi_k8s_sdk source', href: 'https://github.com/julianwiley/rpi_kubernetes/tree/main/management/sdk' },
      { label: 'AQP integration helpers', href: 'https://github.com/julianwiley/rpi_kubernetes/blob/main/management/sdk/src/rpi_k8s_sdk/aqp.py' },
      { label: 'Tracing helper', href: 'https://github.com/julianwiley/rpi_kubernetes/blob/main/management/sdk/src/rpi_k8s_sdk/tracing.py' },
    ],
  },
  {
    title: 'Data plane',
    description: 'Iceberg + MinIO + DuckDB; how raw data lands and how to query it.',
    icon: Database,
    links: [
      { label: 'Pipelines tasks', href: 'https://github.com/julianwiley/rpi_kubernetes/tree/main/pipelines' },
      { label: 'Dagster user code', href: 'https://github.com/julianwiley/rpi_kubernetes/tree/main/pipelines/dagster_user_code' },
      { label: 'Argo workflow templates', href: 'https://github.com/julianwiley/rpi_kubernetes/tree/main/kubernetes/mlops/pipelines' },
    ],
  },
]

export default function DocsPage() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Documentation" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-5xl mx-auto space-y-6">
            <section className="card p-5 flex items-start gap-4">
              <BookOpen className="w-6 h-6 text-primary-400 mt-1" />
              <div>
                <h2 className="text-lg font-semibold text-surface-100">Platform documentation</h2>
                <p className="text-sm text-surface-400 mt-1">
                  This page links to every documentation surface the rpi-kubernetes platform exposes.
                  Use the Management API docs to explore endpoints, the dashboard iframes to embed
                  Grafana / Jaeger / Loki, and the GitHub links for runbooks and source.
                </p>
              </div>
            </section>

            {SECTIONS.map((section) => (
              <section key={section.title} className="card p-5 space-y-3">
                <div className="flex items-center gap-3">
                  <section.icon className="w-5 h-5 text-primary-400" />
                  <h3 className="font-semibold text-surface-100">{section.title}</h3>
                </div>
                <p className="text-sm text-surface-400">{section.description}</p>
                <ul className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-2">
                  {section.links.map((link) => (
                    <li key={link.href}>
                      <a
                        href={link.href}
                        target={link.href.startsWith('http') ? '_blank' : undefined}
                        rel={link.href.startsWith('http') ? 'noopener noreferrer' : undefined}
                        className="flex items-start gap-2 px-3 py-2 rounded-lg bg-surface-900/40 hover:bg-surface-800 transition-colors group"
                      >
                        <ExternalLink className="w-3.5 h-3.5 text-surface-500 group-hover:text-primary-400 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-surface-200 font-medium truncate">{link.label}</div>
                          {link.description && (
                            <div className="text-xs text-surface-500">{link.description}</div>
                          )}
                        </div>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </main>
      </div>
    </div>
  )
}
