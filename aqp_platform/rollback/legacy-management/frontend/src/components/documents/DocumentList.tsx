'use client'

import Link from 'next/link'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2, FileText, Tag, AlertCircle } from 'lucide-react'

import { documentsApi, DocumentSummary } from '@/lib/api'

interface DocumentListProps {
  collectionFilter?: string
  queryFilter?: string
  tagFilter?: string[]
  limit?: number
}

export function DocumentList({
  collectionFilter,
  queryFilter,
  tagFilter,
  limit = 50,
}: DocumentListProps) {
  const queryClient = useQueryClient()
  const filters = {
    query: queryFilter || undefined,
    collection: collectionFilter || undefined,
    tag: tagFilter,
    limit,
  }
  const { data: documents, isLoading, error } = useQuery({
    queryKey: ['documents', filters],
    queryFn: () => documentsApi.list(filters),
  })
  const remove = useMutation({
    mutationFn: (id: string) => documentsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  })

  if (isLoading) {
    return (
      <div className="card p-6 space-y-2 animate-pulse">
        {[...Array(4)].map((_, i) => (
          <div key={i} className="h-12 bg-surface-800/50 rounded-lg" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="card p-6 text-red-400 flex items-center gap-2">
        <AlertCircle className="w-5 h-5" />
        Failed to load documents.
      </div>
    )
  }

  if (!documents || documents.length === 0) {
    return (
      <div className="card p-6 text-surface-400 text-center">
        No documents yet. Upload a file or ingest a MinIO artifact to get started.
      </div>
    )
  }

  return (
    <div className="card overflow-hidden">
      <table className="w-full text-sm">
        <thead className="bg-surface-900/50 text-surface-400 uppercase text-xs">
          <tr>
            <th className="text-left px-4 py-3">Title</th>
            <th className="text-left px-4 py-3">Collection</th>
            <th className="text-left px-4 py-3">Tags</th>
            <th className="text-right px-4 py-3">Chunks</th>
            <th className="text-right px-4 py-3">Size</th>
            <th className="text-right px-4 py-3">Created</th>
            <th className="text-right px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-surface-800">
          {documents.map((doc) => (
            <tr key={doc.id} className="hover:bg-surface-900/30">
              <td className="px-4 py-3">
                <Link
                  href={`/documents/${doc.id}`}
                  className="flex items-center gap-2 text-surface-100 hover:text-primary-300"
                >
                  <FileText className="w-4 h-4 text-primary-400" />
                  <span className="font-medium">{doc.title || doc.id}</span>
                </Link>
                <div className="text-xs text-surface-500 truncate max-w-xs">
                  {doc.source_uri || doc.description}
                </div>
              </td>
              <td className="px-4 py-3 text-surface-300">{doc.collection}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap gap-1">
                  {(doc.tags || []).slice(0, 3).map((t) => (
                    <span
                      key={t}
                      className="badge inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-800 text-xs text-surface-300"
                    >
                      <Tag className="w-3 h-3" />
                      {t}
                    </span>
                  ))}
                </div>
              </td>
              <td className="px-4 py-3 text-right text-surface-300">{doc.chunk_count}</td>
              <td className="px-4 py-3 text-right text-surface-300">{formatSize(doc.size_bytes)}</td>
              <td className="px-4 py-3 text-right text-surface-400">{formatTime(doc.created_at)}</td>
              <td className="px-4 py-3 text-right">
                <button
                  type="button"
                  onClick={() => {
                    if (window.confirm(`Delete ${doc.title}?`)) {
                      remove.mutate(doc.id)
                    }
                  }}
                  className="text-surface-400 hover:text-red-400 disabled:opacity-50"
                  disabled={remove.isPending}
                  title="Delete document"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

function formatTime(seconds: number): string {
  if (!seconds) return '-'
  const date = new Date(seconds * 1000)
  return date.toLocaleString()
}

export type { DocumentSummary }
