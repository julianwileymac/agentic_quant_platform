'use client'

import Link from 'next/link'
import { useMutation } from '@tanstack/react-query'
import { Search, Sparkles, Type, Layers } from 'lucide-react'
import { useState } from 'react'

import { documentsApi, DocumentSearchHit } from '@/lib/api'

const MODES = [
  { id: 'hybrid', label: 'Hybrid', icon: Layers },
  { id: 'semantic', label: 'Semantic', icon: Sparkles },
  { id: 'keyword', label: 'Keyword', icon: Type },
] as const

type Mode = (typeof MODES)[number]['id']

export function DocumentSearch() {
  const [query, setQuery] = useState('')
  const [mode, setMode] = useState<Mode>('hybrid')
  const [topK, setTopK] = useState(10)
  const [collection, setCollection] = useState('')

  const search = useMutation({
    mutationFn: () =>
      documentsApi.search({
        query,
        mode,
        top_k: topK,
        collection: collection || null,
      }),
  })

  return (
    <div className="card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-surface-100">Search the Document Store</h3>
        <p className="text-xs text-surface-500">
          Powered by RediSearch (BM25 + HNSW vector)
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {MODES.map((m) => (
          <button
            key={m.id}
            type="button"
            onClick={() => setMode(m.id)}
            className={`inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border text-sm transition-colors ${
              mode === m.id
                ? 'bg-primary-500/10 text-primary-300 border-primary-500/30'
                : 'bg-surface-900/40 text-surface-400 border-surface-800 hover:border-surface-700'
            }`}
          >
            <m.icon className="w-4 h-4" />
            {m.label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_200px_120px_auto] gap-2">
        <div className="relative">
          <Search className="w-4 h-4 absolute top-2.5 left-3 text-surface-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && search.mutate()}
            placeholder="Ask a question or search keywords..."
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg pl-10 pr-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
        <input
          type="text"
          value={collection}
          onChange={(e) => setCollection(e.target.value)}
          placeholder="Filter collection (optional)"
          className="bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
        />
        <input
          type="number"
          value={topK}
          min={1}
          max={50}
          onChange={(e) => setTopK(parseInt(e.target.value, 10) || 10)}
          className="bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
        />
        <button
          type="button"
          onClick={() => search.mutate()}
          disabled={!query || search.isPending}
          className="btn btn-primary px-4 py-2 rounded-lg text-sm disabled:opacity-50"
        >
          {search.isPending ? 'Searching...' : 'Search'}
        </button>
      </div>

      <div className="space-y-2">
        {search.isError && (
          <div className="text-sm text-red-400">
            {(search.error as Error)?.message ?? 'Search failed'}
          </div>
        )}
        {search.data?.length === 0 && (
          <div className="text-sm text-surface-500 text-center py-6">
            No matches found.
          </div>
        )}
        {(search.data || []).map((hit) => (
          <SearchResultRow key={`${hit.id}-${hit.score}`} hit={hit} />
        ))}
      </div>
    </div>
  )
}

function SearchResultRow({ hit }: { hit: DocumentSearchHit }) {
  return (
    <Link
      href={`/documents/${hit.doc_id || hit.id.split(':').slice(-2, -1)[0]}`}
      className="block p-3 rounded-lg border border-surface-800 hover:border-primary-500/40 hover:bg-surface-900/40"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-surface-100">
          {hit.title || hit.doc_id || hit.id}
        </span>
        <span className="text-xs text-surface-500">score {hit.score.toFixed(3)}</span>
      </div>
      <p className="text-sm text-surface-300 mt-1 line-clamp-3 whitespace-pre-wrap">
        {hit.text}
      </p>
      {hit.collection && (
        <span className="text-xs text-surface-500 mt-2 inline-block">
          collection: {hit.collection}
        </span>
      )}
    </Link>
  )
}
