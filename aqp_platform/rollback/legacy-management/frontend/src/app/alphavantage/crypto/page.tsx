'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi } from '@/lib/api'

const FUNCTIONS = [
  { id: 'rate', label: 'Realtime rate' },
  { id: 'intraday', label: 'Intraday' },
  { id: 'daily', label: 'Daily' },
  { id: 'weekly', label: 'Weekly' },
  { id: 'monthly', label: 'Monthly' },
]

const PRESETS = [
  { symbol: 'BTC', market: 'USD' },
  { symbol: 'ETH', market: 'USD' },
  { symbol: 'SOL', market: 'USD' },
  { symbol: 'ADA', market: 'USD' },
  { symbol: 'DOT', market: 'USD' },
]

type CryptoBar = { timestamp: string; open?: number; high?: number; low?: number; close?: number; volume?: number }

export default function CryptoPage() {
  const [symbol, setSymbol] = useState('BTC')
  const [market, setMarket] = useState('USD')
  const [fn, setFn] = useState('daily')
  const [interval, setInterval] = useState('5min')

  const query = useQuery({
    queryKey: ['alphavantage', 'crypto', fn, symbol, market, interval],
    queryFn: () => {
      const params: Record<string, string> = { symbol, market }
      if (fn === 'intraday') params.interval = interval
      return alphaVantageApi.crypto(fn, params)
    },
  })

  const bars = useMemo(() => {
    if (fn === 'rate') return []
    return (((query.data as { bars?: CryptoBar[] })?.bars) ?? []).slice().reverse()
  }, [query.data, fn])

  const columns: AvTableColumn<CryptoBar>[] = [
    { key: 'timestamp', header: 'Timestamp' },
    { key: 'open', header: 'Open' },
    { key: 'high', header: 'High' },
    { key: 'low', header: 'Low' },
    { key: 'close', header: 'Close' },
    { key: 'volume', header: 'Volume' },
  ]

  return (
    <AvPageShell title="Crypto" subtitle="Digital currency rates + intraday / daily / weekly / monthly bars.">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-5 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Symbol</label>
          <input
            className="input w-full"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value.toUpperCase())}
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Market</label>
          <input
            className="input w-full"
            value={market}
            onChange={(e) => setMarket(e.target.value.toUpperCase())}
          />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Function</label>
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
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Interval</label>
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
          {PRESETS.map((p) => (
            <button
              key={`${p.symbol}-${p.market}`}
              className="btn btn-ghost text-xs"
              onClick={() => {
                setSymbol(p.symbol)
                setMarket(p.market)
              }}
            >
              {p.symbol}/{p.market}
            </button>
          ))}
        </div>
      </div>

      {fn === 'rate' ? (
        <div className="card p-4">
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
          <AvDataTable columns={columns} data={bars.slice(0, 200)} rowKey={(r) => r.timestamp} />
        </>
      )}
    </AvPageShell>
  )
}
