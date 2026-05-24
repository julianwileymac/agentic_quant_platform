'use client'

import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, FileText, Trash2, Tag } from 'lucide-react'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { DocumentAnnotations } from '@/components/documents/DocumentAnnotations'
import { documentsApi } from '@/lib/api'

export default function DocumentDetailPage() {
  const params = useParams()
  const router = useRouter()
  const queryClient = useQueryClient()
  const docId = params?.id as string

  const document = useQuery({
    queryKey: ['document', docId],
    queryFn: () => documentsApi.get(docId),
    enabled: Boolean(docId),
  })

  const remove = useMutation({
    mutationFn: () => documentsApi.remove(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      router.push('/documents')
    },
  })

  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Document" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-5xl mx-auto space-y-6">
            <Link
              href="/documents"
              className="inline-flex items-center gap-1 text-sm text-surface-400 hover:text-surface-200"
            >
              <ArrowLeft className="w-4 h-4" /> Back to documents
            </Link>

            {document.isLoading && (
              <div className="card p-6 animate-pulse text-surface-400">Loading...</div>
            )}

            {document.isError && (
              <div className="card p-6 text-red-400">Failed to load document.</div>
            )}

            {document.data && (
              <>
                <section className="card p-6 space-y-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-4">
                      <div className="w-12 h-12 rounded-xl bg-primary-500/20 flex items-center justify-center">
                        <FileText className="w-6 h-6 text-primary-400" />
                      </div>
                      <div>
                        <h2 className="text-xl font-semibold text-surface-100">
                          {document.data.title}
                        </h2>
                        <p className="text-sm text-surface-400 mt-1 max-w-2xl">
                          {document.data.description || 'No description'}
                        </p>
                        <div className="mt-3 flex flex-wrap gap-1">
                          {document.data.tags?.map((tag) => (
                            <span
                              key={tag}
                              className="badge inline-flex items-center gap-1 px-2 py-0.5 rounded bg-surface-800 text-xs text-surface-300"
                            >
                              <Tag className="w-3 h-3" /> {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        if (window.confirm(`Delete ${document.data.title}?`)) {
                          remove.mutate()
                        }
                      }}
                      disabled={remove.isPending}
                      className="btn btn-ghost text-red-400 hover:text-red-300 inline-flex items-center gap-1 px-3 py-1.5 rounded-lg"
                    >
                      <Trash2 className="w-4 h-4" />
                      Delete
                    </button>
                  </div>

                  <dl className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
                    <Field label="Collection" value={document.data.collection} />
                    <Field label="Source" value={document.data.source} />
                    <Field label="Owner" value={document.data.owner} />
                    <Field label="MIME type" value={document.data.mime_type} />
                    <Field label="Size" value={formatSize(document.data.size_bytes)} />
                    <Field label="Chunks" value={String(document.data.chunk_count)} />
                    <Field label="Created" value={new Date(document.data.created_at * 1000).toLocaleString()} />
                    <Field label="Updated" value={new Date(document.data.updated_at * 1000).toLocaleString()} />
                    <Field label="Checksum" value={document.data.checksum.slice(0, 16) + '…'} mono />
                    <Field label="Source URI" value={document.data.source_uri || '-'} mono className="md:col-span-3" />
                  </dl>
                </section>

                <DocumentAnnotations docId={document.data.id} />
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  )
}

interface FieldProps {
  label: string
  value: string
  mono?: boolean
  className?: string
}

function Field({ label, value, mono, className = '' }: FieldProps) {
  return (
    <div className={className}>
      <dt className="text-xs uppercase tracking-wide text-surface-500">{label}</dt>
      <dd className={`text-surface-200 ${mono ? 'font-mono text-xs break-all' : ''}`}>{value}</dd>
    </div>
  )
}

function formatSize(bytes: number): string {
  if (!bytes) return '-'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
