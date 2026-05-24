'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { SymbolSearch } from '@/components/alphavantage/SymbolSearch'
import { alphaVantageApi, type OhlcvBar, type TimeSeriesPayload } from '@/lib/api'

const FUNCTIONS = [
  { id: 'daily', label: 'Daily' },
  { id: 'daily_adjusted', label: 'Daily (adjusted)' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'weekly_adjusted', label: 'Weekly (adjusted)' },
  { id: 'monthly', label: 'Monthly' },
  { id: 'monthly_adjusted', label: 'Monthly (adjusted)' },
  { id: 'intraday', label: 'Intraday' },
]

const INTERVALS = ['1min', '5min', '15min', '30min', '60min']
const OUTPUT_SIZES = ['compact', 'full']

export default function TimeseriesPage() {
  const [symbol, setSymbol] = useState('IBM')
  const [fn, setFn] = useState('daily')
  const [interval, setInterval] = useState('5min')
  const [outputSize, setOutputSize] = useState('compact')

  const query = useQuery<TimeSeriesPayload>({
    queryKey: ['alphavantage', 'timeseries', fn, symbol, interval, outputSize],
    queryFn: async () => {
      const params: Record<string, string> = { symbol }
      if (fn === 'intraday') {
        params.interval = interval
        params.outputsize = outputSize
      }
      if (fn === 'daily' || fn === 'daily_adjusted') {
        params.outputsize = outputSize
      }
      return (await alphaVantageApi.timeseries(fn, params)) as TimeSeriesPayload
    },
    enabled: symbol.trim().length > 0,
  })

  const bars = useMemo(
    () => (query.data?.bars ?? []).slice().reverse(), // chronological for chart
    [query.data?.bars],
  )

  const columns: AvTableColumn<OhlcvBar>[] = [
    { key: 'timestamp', header: 'Timestamp' },
    { key: 'open', header: 'Open' },
    { key: 'high', header: 'High' },
    { key: 'low', header: 'Low' },
    { key: 'close', header: 'Close' },
    {
      key: 'adjusted_close',
      header: 'Adj close',
      render: (row) => row.adjusted_close ?? '-',
    },
    {
      key: 'volume',
      header: 'Volume',
      render: (row) => (row.volume ? row.volume.toLocaleString() : '-'),
    },
  ]

  return (
    <AvPageShell title="Time Series" subtitle="Intraday, daily, weekly, monthly OHLCV candles.">
      <div className="card p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div className="md:col-span-2">
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">
              Symbol
            </label>
            <SymbolSearch
              initialValue={symbol}
              onSelect={(match) => setSymbol(match.symbol)}
            />
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">
              Function
            </label>
            <select
              className="input w-full"
              value={fn}
              onChange={(e) => setFn(e.target.value)}
            >
              {FUNCTIONS.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">
              Output size
            </label>
            <select
              className="input w-full"
              value={outputSize}
              onChange={(e) => setOutputSize(e.target.value)}
            >
              {OUTPUT_SIZES.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
        </div>
        {fn === 'intraday' && (
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">
              Interval
            </label>
            <select
              className="input w-full max-w-xs"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
            >
              {INTERVALS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="card p-4">
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <h3 className="text-sm font-semibold text-surface-200">
              {symbol} - {FUNCTIONS.find((f) => f.id === fn)?.label}
            </h3>
            <p className="text-xs text-surface-500">
              {query.isLoading ? 'loading...' : `${bars.length} bars`}
            </p>
          </div>
          <button
            className="btn btn-ghost text-xs"
            onClick={() => query.refetch()}
            disabled={query.isFetching}
          >
            Refresh
          </button>
        </div>
        <AvLineChart
          data={bars as unknown as Record<string, unknown>[]}
          xKey="timestamp"
          series={[
            { dataKey: 'close', name: 'Close' },
            { dataKey: 'open', name: 'Open', strokeDasharray: '3 3' },
          ]}
          height={360}
        />
      </div>

      <AvDataTable
        caption={`${symbol} bars`}
        columns={columns}
        data={(query.data?.bars ?? []).slice(0, 200)}
        rowKey={(row) => row.timestamp}
        emptyMessage={query.isLoading ? 'Loading...' : 'No data.'}
      />
    </AvPageShell>
  )
}
