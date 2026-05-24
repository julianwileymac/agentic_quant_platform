'use client'

import { useQuery } from '@tanstack/react-query'
import { clusterApi, healthApi, ServiceInfo } from '@/lib/api'
import {
  XCircle,
  ExternalLink,
  Database,
  HardDrive,
  Activity,
  FlaskConical,
  BookOpen,
  Boxes,
  Gauge,
} from 'lucide-react'
import { clsx } from 'clsx'

const serviceIcons: Record<string, React.ElementType> = {
  postgresql: Database,
  minio: HardDrive,
  mlflow: FlaskConical,
  jupyterhub: BookOpen,
  prometheus: Activity,
  grafana: Gauge,
  jaeger: Activity,
  dask: Boxes,
  ray: Boxes,
}

const serviceUrls: Record<string, string> = {
  grafana: 'http://grafana.local:3000',
  mlflow: 'http://mlflow.local:5000',
  jupyterhub: 'http://jupyter.local',
  minio: 'http://minio.local:9001',
  jaeger: 'http://jaeger.local:16686',
  prometheus: 'http://prometheus.local:9090',
  dask: 'http://dask.local:8787',
  ray: 'http://ray.local:8265',
}

function ServiceCard({
  service,
  healthStatus,
}: {
  service: ServiceInfo
  healthStatus?: boolean | null
}) {
  const Icon = serviceIcons[service.name.toLowerCase()] || Boxes
  const url = serviceUrls[service.name.toLowerCase()]
  const hasExternalAccess = service.external_ip || service.type === 'LoadBalancer'
  const hasHealthStatus = healthStatus !== undefined

  const statusClasses = hasHealthStatus
    ? healthStatus === null
      ? 'bg-yellow-500'
      : healthStatus
      ? 'bg-green-500'
      : 'bg-red-500'
    : 'bg-green-500'

  const statusLabel = hasHealthStatus
    ? healthStatus === null
      ? 'Health unknown'
      : healthStatus
      ? 'Healthy'
      : 'Unhealthy'
    : 'Running'

  // Determine ports display
  const mainPort = service.ports[0]
  const portDisplay = mainPort
    ? `${mainPort.port}${mainPort.node_port ? `:${mainPort.node_port}` : ''}`
    : '-'

  return (
    <div className="flex items-center justify-between py-3 px-4 rounded-lg bg-surface-800/30 hover:bg-surface-800/50 transition-colors">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-lg bg-primary-500/20 flex items-center justify-center">
          <Icon className="w-4 h-4 text-primary-400" />
        </div>
        <div>
          <div className="font-medium text-surface-100 flex items-center gap-2">
            {service.name}
            {url && (
              <a
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-surface-500 hover:text-primary-400 transition-colors"
              >
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          <div className="text-xs text-surface-500">
            {service.namespace} • {service.type} • {portDisplay}
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {hasExternalAccess && (
          <span className="text-xs text-surface-500">
            {service.external_ip || 'Pending IP'}
          </span>
        )}
        <div
          className={`w-2 h-2 rounded-full status-indicator ${statusClasses}`}
          title={statusLabel}
        ></div>
      </div>
    </div>
  )
}

export function ServicesStatus() {
  const { data: services, isLoading, error } = useQuery({
    queryKey: ['services'],
    queryFn: () => clusterApi.getServices(),
  })
  const {
    data: health,
    isLoading: isHealthLoading,
    isError: isHealthError,
  } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.getStatus,
  })

  if (isLoading) {
    return (
      <div className="card">
        <div className="card-body space-y-3">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 animate-pulse">
              <div className="w-8 h-8 bg-surface-800 rounded-lg"></div>
              <div className="flex-1">
                <div className="h-4 w-24 bg-surface-800 rounded"></div>
                <div className="h-3 w-32 bg-surface-800 rounded mt-1"></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error || !services) {
    return (
      <div className="card p-6">
        <div className="flex items-center gap-3 text-red-400">
          <XCircle className="w-5 h-5" />
          <span>Failed to load services</span>
        </div>
      </div>
    )
  }

  // Filter to show key services from our base services namespaces
  const keyNamespaces = ['data-services', 'ml-platform', 'observability', 'development']
  const keyServices = services.filter(
    (s) =>
      keyNamespaces.includes(s.namespace) &&
      !s.name.includes('headless') &&
      !s.name.endsWith('-metrics')
  )

  const minioHealthStatus =
    isHealthLoading || isHealthError ? null : (health?.minio_connected ?? null)

  // Group by namespace
  const grouped = keyServices.reduce((acc, service) => {
    const ns = service.namespace
    if (!acc[ns]) acc[ns] = []
    acc[ns].push(service)
    return acc
  }, {} as Record<string, ServiceInfo[]>)

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <span className="font-medium text-surface-200">Service Status</span>
        <span className="text-xs text-surface-500">
          {keyServices.length} services
        </span>
      </div>
      <div className="card-body space-y-4">
        {Object.entries(grouped).map(([namespace, namespaceServices]) => (
          <div key={namespace}>
            <div className="text-xs font-medium text-surface-500 uppercase tracking-wider mb-2">
              {namespace}
            </div>
            <div className="space-y-2">
              {namespaceServices.map((service) => {
                const isMinioService = service.name.toLowerCase().startsWith('minio')
                return (
                  <ServiceCard
                    key={`${service.namespace}-${service.name}`}
                    service={service}
                    healthStatus={isMinioService ? minioHealthStatus : undefined}
                  />
                )
              })}
            </div>
          </div>
        ))}
        {keyServices.length === 0 && (
          <div className="text-center py-8 text-surface-500">
            <Boxes className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>No base services deployed yet</p>
            <p className="text-xs mt-1">
              Run <code className="text-primary-400">kubectl apply -k kubernetes/</code>
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
