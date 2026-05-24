'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi } from '@/lib/api'

const PAIRS = [
  { from: 'EUR', to: 'USD' },
  { from: 'USD', to: 'JPY' },
  { from: 'GBP', to: 'USD' },
  { from: 'USD', to: 'CHF' },
  { from: 'USD', to: 'CAD' },
  { from: 'AUD', to: 'USD' },
]

const FUNCTIONS = [
  { id: 'rate', label: 'Realtime rate' },
  { id: 'intraday', label: 'Intraday' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'monthly', label: 'Monthly' },
]

type FxBar = { timestamp: string; open?: number; high?: number; low?: number; close?: number }

export default function ForexPage() {
  const [fromCurrency, setFromCurrency] = useState('EUR')
  const [toCurrency, setToCurrency] = useState('USD')
  const [fn, setFn] = useState('daily')
  const [interval, setInterval] = useState('5min')

  const query = useQuery({
    queryKey: ['alphavantage', 'forex', fn, fromCurrency, toCurrency, interval],
    queryFn: () => {
      if (fn === 'rate') {
        return alphaVantageApi.forex('rate', { from: fromCurrency, to: toCurrency })
      }
      const params: Record<string, string> = { from_symbol: fromCurrency, to_symbol: toCurrency }
      if (fn === 'intraday') params.interval = interval
      return alphaVantageApi.forex(fn, params)
    },
  })

  const bars = useMemo(() => {
    if (fn === 'rate') return []
    return (((query.data as { bars?: FxBar[] })?.bars) ?? []).slice().reverse()
  }, [query.data, fn])

  const barColumns: AvTableColumn<FxBar>[] = [
    { key: 'timestamp', header: 'Timestamp' },
    { key: 'open', header: 'Open' },
    { key: 'high', header: 'High' },
    { key: 'low', header: 'Low' },
    { key: 'close', header: 'Close' },
  ]

  return (
    <AvPageShell title="Forex" subtitle="Currency pair rates + intraday / daily / weekly / monthly bars.">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-5 gap-3">
        <div>
          <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">From</label>
          <input
            className="input w-full"
            value={fromCurrency}
            onChange={(e) => setFromCurrency(e.target.value.toUpperCase())}
          />
        </div>
        <div>
          <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">To</label>
          <input
            className="input w-full"
            value={toCurrency}
            onChange={(e) => setToCurrency(e.target.value.toUpperCase())}
          />
        </div>
        <div>
          <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Function</label>
          <select className="input w-full" value={fn} onChange={(e) => setFn(e.target.value)}>
            {FUNCTIONS.map((f) => (
              <option key={f.id} value={f.id}>
                {f.label}
              </option>
            ))}
          </select>
        </div>
        {fn === 'intraday' && (
          <div>
            <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Interval</label>
            <select className="input w-full" value={interval} onChange={(e) => setInterval(e.target.value)}>
              {['1min', '5min', '15min', '30min', '60min'].map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>
        )}
        <div className="md:col-span-full flex flex-wrap gap-2">
          {PAIRS.map((p) => (
            <button
              key={`${p.from}-${p.to}`}
              className="btn btn-ghost text-xs"
              onClick={() => {
                setFromCurrency(p.from)
                setToCurrency(p.to)
              }}
            >
              {p.from}/{p.to}
            </button>
          ))}
        </div>
      </div>

      {fn === 'rate' ? (
        <div className="card p-4">
          <h3 className="text-sm font-semibold text-surface-200 mb-2">
            {fromCurrency}/{toCurrency} realtime
          </h3>
          <pre className="text-xs text-surface-300 whitespace-pre-wrap">
            {JSON.stringify(query.data ?? {}, null, 2)}
          </pre>
        </div>
      ) : (
        <>
          <div className="card p-4">
            <AvLineChart
              data={bars as unknown as Record<string, unknown>[]}
              xKey="timestamp"
              series={[{ dataKey: 'close', name: 'Close' }]}
              height={320}
            />
          </div>
          <AvDataTable
            caption={`${fromCurrency}/${toCurrency} bars`}
            columns={barColumns}
            data={(((query.data as { bars?: FxBar[] })?.bars) ?? []).slice(0, 200)}
            rowKey={(r) => r.timestamp}
          />
        </>
      )}
    </AvPageShell>
  )
}
