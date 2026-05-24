'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi } from '@/lib/api'

const COMMODITIES = [
  'WTI',
  'BRENT',
  'NATURAL_GAS',
  'COPPER',
  'ALUMINUM',
  'WHEAT',
  'CORN',
  'COTTON',
  'SUGAR',
  'COFFEE',
  'ALL_COMMODITIES',
]

type CommodityPoint = { date: string; value?: number }

export default function CommoditiesPage() {
  const [commodity, setCommodity] = useState('WTI')
  const [interval, setInterval] = useState('monthly')

  const query = useQuery({
    queryKey: ['alphavantage', 'commodities', commodity, interval],
    queryFn: () => alphaVantageApi.commodity(commodity, interval),
  })

  const data = useMemo(() => {
    return (((query.data as { data?: CommodityPoint[] })?.data) ?? [])
      .slice()
      .sort((a, b) => (a.date > b.date ? 1 : -1))
  }, [query.data])

  const columns: AvTableColumn<CommodityPoint>[] = [
    { key: 'date', header: 'Date' },
    { key: 'value', header: 'Value' },
  ]

  return (
    <AvPageShell title="Commodities" subtitle="WTI, Brent, natural gas, metals, ags, and the global commodity index.">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Commodity</label>
          <select
            className="input w-full"
            value={commodity}
            onChange={(e) => setCommodity(e.target.value)}
          >
            {COMMODITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Interval</label>
          <select
            className="input w-full"
            value={interval}
            onChange={(e) => setInterval(e.target.value)}
          >
            {['daily', 'weekly', 'monthly', 'quarterly', 'annual'].map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="card p-4">
        <AvLineChart
          data={data as unknown as Record<string, unknown>[]}
          xKey="date"
          series={[{ dataKey: 'value', name: commodity }]}
          height={320}
        />
      </div>

      <AvDataTable caption={`${commodity} history`} columns={columns} data={data} rowKey={(r) => r.date} />
    </AvPageShell>
  )
}
