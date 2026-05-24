'use client'

import Link from 'next/link'
import { Database, FileText, Layers } from 'lucide-react'

import { Sidebar } from '@/components/layout/Sidebar'
import { Header } from '@/components/layout/Header'
import { DocumentUploader } from '@/components/documents/DocumentUploader'
import { DocumentSearch } from '@/components/documents/DocumentSearch'
import { DocumentList } from '@/components/documents/DocumentList'
import { RedisHealthBadge } from '@/components/documents/RedisHealthBadge'

export default function DocumentsPage() {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Header title="Document Store" />
        <main className="flex-1 overflow-y-auto p-6 grid-pattern">
          <div className="max-w-7xl mx-auto space-y-6">
            <section className="card p-6 flex flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className="w-12 h-12 rounded-xl bg-primary-500/20 flex items-center justify-center">
                  <FileText className="w-6 h-6 text-primary-400" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-surface-100">Self-service Document Store</h2>
                  <p className="text-sm text-surface-400 max-w-2xl">
                    Upload documents or ingest existing JSON artifacts from MinIO, then search,
                    annotate, and reuse them across the framework. Powered by the shared Redis 8
                    Stack (RediSearch + RedisJSON + RedisVL).
                  </p>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <RedisHealthBadge />
                <Link
                  href="/documents/artifacts"
                  className="text-xs text-primary-300 hover:text-primary-200 inline-flex items-center gap-1"
                >
                  <Database className="w-3 h-3" />
                  Browse MinIO artifacts &rarr;
                </Link>
              </div>
            </section>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <DocumentUploader defaultCollection="general" />
              <DocumentSearch />
            </div>

            <section className="space-y-3">
              <h3 className="text-lg font-semibold text-surface-200 flex items-center gap-2">
                <Layers className="w-5 h-5 text-primary-400" /> Recent Documents
              </h3>
              <DocumentList limit={50} />
            </section>
          </div>
        </main>
      </div>
    </div>
  )
}
