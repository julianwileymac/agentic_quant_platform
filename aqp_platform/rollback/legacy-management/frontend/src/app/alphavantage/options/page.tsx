'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { SymbolSearch } from '@/components/alphavantage/SymbolSearch'
import { alphaVantageApi } from '@/lib/api'

const KINDS = [
  { id: 'realtime', label: 'Realtime chain' },
  { id: 'historical', label: 'Historical chain' },
  { id: 'pcr-realtime', label: 'Put/Call ratio (realtime)' },
  { id: 'pcr-historical', label: 'Put/Call ratio (historical)' },
  { id: 'voi-realtime', label: 'VOI ratio (realtime)' },
  { id: 'voi-historical', label: 'VOI ratio (historical)' },
]

type OptionContract = {
  contractID?: string
  expiration?: string
  strike?: number
  type?: string
  last?: number
  mark?: number
  bid?: number
  ask?: number
  volume?: number
  open_interest?: number
  implied_volatility?: number
  delta?: number
  gamma?: number
  theta?: number
  vega?: number
  rho?: number
}

export default function OptionsPage() {
  const [symbol, setSymbol] = useState('SPY')
  const [kind, setKind] = useState('realtime')
  const [date, setDate] = useState('')
  const query = useQuery({
    queryKey: ['alphavantage', 'options', kind, symbol, date],
    queryFn: () =>
      alphaVantageApi.options(kind, {
        symbol,
        date: kind.includes('historical') ? date || undefined : undefined,
      }),
    enabled: symbol.trim().length > 0,
  })

  const columns: AvTableColumn<OptionContract>[] = [
    { key: 'contractID', header: 'Contract' },
    { key: 'expiration', header: 'Expiry' },
    { key: 'type', header: 'Type' },
    { key: 'strike', header: 'Strike' },
    { key: 'last', header: 'Last' },
    { key: 'bid', header: 'Bid' },
    { key: 'ask', header: 'Ask' },
    { key: 'volume', header: 'Volume' },
    { key: 'open_interest', header: 'OI' },
    { key: 'implied_volatility', header: 'IV' },
    { key: 'delta', header: 'Delta' },
    { key: 'gamma', header: 'Gamma' },
    { key: 'theta', header: 'Theta' },
    { key: 'vega', header: 'Vega' },
  ]

  const data = query.data as unknown
  return (
    <AvPageShell title="Options" subtitle="Realtime + historical option chains and ratios.">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Symbol</label>
          <SymbolSearch initialValue={symbol} onSelect={(m) => setSymbol(m.symbol)} />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Kind</label>
          <select className="input w-full" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
        </div>
        {kind.includes('historical') && (
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Date (YYYY-MM-DD)</label>
            <input className="input w-full" value={date} onChange={(e) => setDate(e.target.value)} />
          </div>
        )}
      </div>

      {kind.endsWith('realtime') && !kind.includes('pcr') && !kind.includes('voi') || kind.endsWith('historical') && !kind.includes('pcr') && !kind.includes('voi') ? (
        <AvDataTable
          caption={`${symbol} option chain`}
          columns={columns}
          data={((data as { data?: OptionContract[] })?.data) ?? []}
          rowKey={(r) => r.contractID ?? `${r.expiration}-${r.strike}-${r.type}`}
        />
      ) : (
        <div className="card p-4">
          <h3 className="text-sm font-semibold mb-2">{symbol} ratios</h3>
          <pre className="text-xs text-surface-300 overflow-auto">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )}
    </AvPageShell>
  )
}
