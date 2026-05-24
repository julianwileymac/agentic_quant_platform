'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Database, FolderOpen, FileJson, ArrowRight, AlertCircle } from 'lucide-react'

import { documentsApi, ArtifactListEntry } from '@/lib/api'

export function ArtifactBrowser() {
  const queryClient = useQueryClient()
  const [bucket, setBucket] = useState<string>('')
  const [prefix, setPrefix] = useState('')

  const buckets = useQuery({
    queryKey: ['artifact-buckets'],
    queryFn: documentsApi.listArtifactBuckets,
  })

  const items = useQuery({
    queryKey: ['artifact-list', bucket, prefix],
    queryFn: () => documentsApi.browseArtifacts(bucket, prefix),
    enabled: Boolean(bucket),
  })

  const ingest = useMutation({
    mutationFn: (entry: ArtifactListEntry) =>
      documentsApi.ingestArtifact({
        bucket: entry.bucket,
        key: entry.key,
        title: entry.key.split('/').pop() || entry.key,
        tags: ['artifact', 'minio'],
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  return (
    <div className="card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-surface-100 flex items-center gap-2">
          <Database className="w-5 h-5 text-primary-400" />
          MinIO Artifact Browser
        </h3>
        <p className="text-xs text-surface-500">
          Self-service ingestion of JSON artifacts from the data lake
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[200px_1fr] gap-2">
        <select
          value={bucket}
          onChange={(e) => setBucket(e.target.value)}
          className="bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
        >
          <option value="">Select bucket...</option>
          {(buckets.data || []).map((b) => (
            <option key={b} value={b}>
              {b}
            </option>
          ))}
        </select>
        <div className="relative">
          <FolderOpen className="w-4 h-4 absolute top-2.5 left-3 text-surface-500" />
          <input
            type="text"
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            placeholder="Object key prefix (optional)"
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg pl-10 pr-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
      </div>

      {bucket ? (
        <div className="border border-surface-800 rounded-lg divide-y divide-surface-800 max-h-[420px] overflow-y-auto">
          {items.isLoading && (
            <div className="text-sm text-surface-400 px-4 py-3">Loading objects...</div>
          )}
          {items.isError && (
            <div className="text-sm text-red-400 px-4 py-3 flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              Failed to browse bucket.
            </div>
          )}
          {items.data?.length === 0 && (
            <div className="text-sm text-surface-500 px-4 py-3">No objects found.</div>
          )}
          {(items.data || []).map((entry) => (
            <div
              key={`${entry.bucket}/${entry.key}`}
              className="flex items-center justify-between px-4 py-2 hover:bg-surface-900/40"
            >
              <div className="flex items-center gap-2 min-w-0">
                {entry.is_json ? (
                  <FileJson className="w-4 h-4 text-yellow-400 flex-shrink-0" />
                ) : (
                  <FolderOpen className="w-4 h-4 text-surface-500 flex-shrink-0" />
                )}
                <div className="min-w-0">
                  <div className="text-sm text-surface-100 truncate">{entry.key}</div>
                  <div className="text-xs text-surface-500">
                    {formatBytes(entry.size)}
                    {entry.last_modified
                      ? ` • ${new Date(entry.last_modified * 1000).toLocaleString()}`
                      : ''}
                  </div>
                </div>
              </div>
              <button
                type="button"
                onClick={() => ingest.mutate(entry)}
                disabled={ingest.isPending}
                className="btn btn-primary inline-flex items-center gap-1 px-2 py-1 rounded-lg text-xs disabled:opacity-50"
                title="Ingest into document store"
              >
                Ingest
                <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-surface-500 px-4 py-3 border border-surface-800 rounded-lg">
          Pick a bucket to start browsing artifacts.
        </div>
      )}

      {ingest.isSuccess && (
        <div className="text-xs text-green-400">
          Ingested {ingest.data.title} as document {ingest.data.id}.
        </div>
      )}
      {ingest.isError && (
        <div className="text-xs text-red-400">
          {(ingest.error as Error)?.message ?? 'Ingestion failed'}
        </div>
      )}
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
