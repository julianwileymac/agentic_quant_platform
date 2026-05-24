'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { SymbolSearch } from '@/components/alphavantage/SymbolSearch'
import { alphaVantageApi } from '@/lib/api'

const TABS: Array<{ id: string; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'income', label: 'Income' },
  { id: 'balance', label: 'Balance Sheet' },
  { id: 'cashflow', label: 'Cash Flow' },
  { id: 'earnings', label: 'Earnings' },
  { id: 'estimates', label: 'Estimates' },
  { id: 'dividends', label: 'Dividends' },
  { id: 'splits', label: 'Splits' },
  { id: 'etf', label: 'ETF Profile' },
  { id: 'shares', label: 'Shares Outstanding' },
]

export default function FundamentalsPage() {
  const [symbol, setSymbol] = useState('IBM')
  const [tab, setTab] = useState('overview')

  const query = useQuery({
    queryKey: ['alphavantage', 'fundamentals', tab, symbol],
    queryFn: () => alphaVantageApi.fundamentals(tab, { symbol }),
    enabled: symbol.trim().length > 0,
  })

  return (
    <AvPageShell
      title="Fundamentals"
      subtitle="Company overview, financial statements, earnings, dividends & splits."
    >
      <div className="card p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">
              Symbol
            </label>
            <SymbolSearch initialValue={symbol} onSelect={(m) => setSymbol(m.symbol)} />
          </div>
          <div className="flex items-end">
            <div className="flex flex-wrap gap-2">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setTab(t.id)}
                  className={`btn text-xs ${
                    tab === t.id ? 'btn-primary' : 'btn-ghost'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="card p-4">
        {query.isLoading && <p className="text-sm text-surface-500">Loading...</p>}
        {query.isError && (
          <p className="text-sm text-red-400">
            Failed to load: {(query.error as Error).message}
          </p>
        )}
        {!query.isLoading && !query.isError && <FundamentalsRenderer tab={tab} data={query.data} />}
      </div>
    </AvPageShell>
  )
}

function FundamentalsRenderer({ tab, data }: { tab: string; data: unknown }) {
  if (!data) {
    return <p className="text-sm text-surface-500">No data.</p>
  }
  if (tab === 'overview') {
    return <OverviewPanel data={data as Record<string, unknown>} />
  }
  if (['income', 'balance', 'cashflow'].includes(tab)) {
    return <StatementPanel data={data as { annual: Array<Record<string, unknown>>; quarterly: Array<Record<string, unknown>> }} />
  }
  if (tab === 'earnings') {
    const d = data as { annual_earnings: Array<Record<string, unknown>>; quarterly_earnings: Array<Record<string, unknown>> }
    return (
      <div className="space-y-4">
        <SimpleTable caption="Annual earnings" rows={d.annual_earnings ?? []} />
        <SimpleTable caption="Quarterly earnings" rows={d.quarterly_earnings ?? []} />
      </div>
    )
  }
  if (['estimates', 'dividends', 'splits', 'shares'].includes(tab)) {
    return <SimpleTable rows={(data as Array<Record<string, unknown>>) ?? []} />
  }
  if (tab === 'etf') {
    return <OverviewPanel data={data as Record<string, unknown>} />
  }
  return <pre className="text-xs text-surface-400 overflow-auto">{JSON.stringify(data, null, 2)}</pre>
}

function OverviewPanel({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data).filter(([, v]) => v !== null && v !== undefined && v !== '')
  return (
    <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
      {entries.map(([k, v]) => (
        <div key={k} className="p-2 rounded bg-surface-800">
          <dt className="text-xs uppercase tracking-wide text-surface-500">{k.replace(/_/g, ' ')}</dt>
          <dd className="text-surface-100 mt-1 truncate" title={String(v)}>
            {String(v)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function StatementPanel({ data }: { data: { annual: Array<Record<string, unknown>>; quarterly: Array<Record<string, unknown>> } }) {
  return (
    <div className="space-y-4">
      <SimpleTable caption="Annual" rows={data.annual ?? []} />
      <SimpleTable caption="Quarterly" rows={data.quarterly ?? []} />
    </div>
  )
}

function SimpleTable({ rows, caption }: { rows: Array<Record<string, unknown>>; caption?: string }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="text-xs text-surface-500">
        {caption ? `${caption}: ` : ''}no rows
      </div>
    )
  }
  const columns: AvTableColumn<Record<string, unknown>>[] = Object.keys(rows[0]).map((k) => ({
    key: k,
    header: k.replace(/_/g, ' '),
    render: (row) => {
      const value = row[k]
      if (value === null || value === undefined) return '-'
      if (typeof value === 'object') return JSON.stringify(value)
      return String(value)
    },
  }))
  return <AvDataTable caption={caption} columns={columns} data={rows} rowKey={(_, i) => `${caption}-${i}`} />
}
