'use client'

import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvUsageMeter } from '@/components/alphavantage/AvUsageMeter'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi, type AvWorkflowEntry } from '@/lib/api'

const BULK_CATEGORIES = [
  'timeseries',
  'intraday-backfill',
  'fundamentals',
  'universe',
  'news',
  'earnings',
  'fx',
  'crypto',
  'technicals',
  'commodities',
  'economics',
]

export default function AvAdminPage() {
  const queryClient = useQueryClient()
  const [category, setCategory] = useState('timeseries')
  const [symbols, setSymbols] = useState('IBM,AAPL,MSFT')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [extraJson, setExtraJson] = useState('{}')
  const [streamReplicas, setStreamReplicas] = useState(1)
  const [lastResult, setLastResult] = useState<string | null>(null)

  const workflows = useQuery({
    queryKey: ['alphavantage', 'workflows'],
    queryFn: () => alphaVantageApi.listWorkflows(50),
    refetchInterval: 30_000,
  })

  const submitBulk = useMutation({
    mutationFn: async () => {
      const extras = extraJson.trim() ? JSON.parse(extraJson) : {}
      return alphaVantageApi.bulkLoad({
        category,
        symbols: symbols.split(',').map((s) => s.trim()).filter(Boolean),
        date_range: startDate || endDate ? { start: startDate || undefined, end: endDate || undefined } : undefined,
        extra_params: extras,
        target_bucket: 'av-raw',
      })
    },
    onSuccess: (data) => {
      setLastResult(JSON.stringify(data, null, 2))
      queryClient.invalidateQueries({ queryKey: ['alphavantage', 'workflows'] })
    },
    onError: (error) => setLastResult(`Error: ${(error as Error).message}`),
  })

  const toggleStream = useMutation({
    mutationFn: async (enable: boolean) => alphaVantageApi.toggleStream(enable, streamReplicas),
    onSuccess: (data) => setLastResult(JSON.stringify(data, null, 2)),
    onError: (error) => setLastResult(`Error: ${(error as Error).message}`),
  })

  const columns: AvTableColumn<AvWorkflowEntry>[] = [
    { key: 'name', header: 'Workflow' },
    { key: 'category', header: 'Category' },
    {
      key: 'phase',
      header: 'Phase',
      render: (row) => {
        const palette =
          row.phase === 'Succeeded'
            ? 'bg-emerald-500/20 text-emerald-400'
            : row.phase === 'Failed'
              ? 'bg-red-500/20 text-red-400'
              : row.phase === 'Running'
                ? 'bg-primary-500/20 text-primary-400'
                : 'bg-surface-700 text-surface-300'
        return (
          <span className={`badge ${palette}`}>{row.phase}</span>
        )
      },
    },
    { key: 'started_at', header: 'Started' },
    { key: 'finished_at', header: 'Finished' },
  ]

  return (
    <AvPageShell
      title="Alpha Vantage Admin"
      subtitle="Trigger Argo bulk loads, toggle the streaming producer, inspect workflow history."
    >
      <AvUsageMeter />

      <div className="card p-4 space-y-4">
        <div>
          <h3 className="text-sm font-semibold text-surface-200">Submit bulk load</h3>
          <p className="text-xs text-surface-500">
            Kicks off an Argo ``Workflow`` from the matching ``av-*`` WorkflowTemplate.
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Category</label>
            <select className="input w-full" value={category} onChange={(e) => setCategory(e.target.value)}>
              {BULK_CATEGORIES.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Symbols (comma)</label>
            <input className="input w-full" value={symbols} onChange={(e) => setSymbols(e.target.value)} />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Start date</label>
            <input
              className="input w-full"
              placeholder="YYYY-MM or YYYY-MM-DD"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">End date</label>
            <input
              className="input w-full"
              placeholder="YYYY-MM or YYYY-MM-DD"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">
              Extra params (JSON)
            </label>
            <textarea
              className="input w-full font-mono text-xs"
              rows={3}
              value={extraJson}
              onChange={(e) => setExtraJson(e.target.value)}
            />
          </div>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => submitBulk.mutate()}
          disabled={submitBulk.isPending}
        >
          {submitBulk.isPending ? 'Submitting...' : 'Submit workflow'}
        </button>
      </div>

      <div className="card p-4 space-y-3">
        <div>
          <h3 className="text-sm font-semibold text-surface-200">Streaming producer</h3>
          <p className="text-xs text-surface-500">
            Scale the alphavantage-producer Deployment to fetch live quotes / bars / news.
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Replicas</label>
            <input
              type="number"
              min={0}
              max={5}
              className="input w-24"
              value={streamReplicas}
              onChange={(e) => setStreamReplicas(parseInt(e.target.value, 10) || 0)}
            />
          </div>
          <button
            className="btn btn-primary"
            onClick={() => toggleStream.mutate(true)}
            disabled={toggleStream.isPending}
          >
            Enable
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => toggleStream.mutate(false)}
            disabled={toggleStream.isPending}
          >
            Disable
          </button>
        </div>
      </div>

      <AvDataTable
        caption="Recent AV workflows"
        columns={columns}
        data={workflows.data ?? []}
        rowKey={(r) => r.name}
        emptyMessage={workflows.isLoading ? 'Loading workflows...' : 'No AV workflows yet.'}
      />

      {lastResult && (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-surface-200">Last action</h3>
          <pre className="text-xs text-surface-300 whitespace-pre-wrap mt-2">{lastResult}</pre>
        </div>
      )}
    </AvPageShell>
  )
}
