'use client'

import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { ArtifactBrowser } from '@/components/documents/ArtifactBrowser'
import { DocumentList } from '@/components/documents/DocumentList'

export default function DocumentsArtifactsPage() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="MinIO Artifacts" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            <Link
              href="/documents"
              className="inline-flex items-center gap-1 text-sm text-surface-400 hover:text-surface-200"
            >
              <ArrowLeft className="w-4 h-4" /> Back to documents
            </Link>

            <section className="card p-6">
              <h2 className="text-lg font-semibold text-surface-100">
                Ingest existing JSON artifacts
              </h2>
              <p className="text-sm text-surface-400 mt-1">
                Browse MinIO buckets such as <code className="px-1 rounded bg-surface-800">dagster-artifacts</code>,{' '}
                <code className="px-1 rounded bg-surface-800">mlflow-artifacts</code>, and{' '}
                <code className="px-1 rounded bg-surface-800">pipeline-raw</code>. Selecting an
                object posts it to the Redis-backed document store for semantic search and
                annotation alongside uploaded files.
              </p>
            </section>

            <ArtifactBrowser />

            <section className="space-y-3">
              <h3 className="text-lg font-semibold text-surface-200">
                Recent ingestions (tagged "artifact")
              </h3>
              <DocumentList tagFilter={['artifact']} limit={20} />
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}
