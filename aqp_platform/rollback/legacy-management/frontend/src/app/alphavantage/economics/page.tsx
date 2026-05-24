'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi } from '@/lib/api'

const INDICATORS = [
  { id: 'REAL_GDP', label: 'Real GDP' },
  { id: 'REAL_GDP_PER_CAPITA', label: 'Real GDP per capita' },
  { id: 'TREASURY_YIELD', label: 'Treasury yield' },
  { id: 'FEDERAL_FUNDS_RATE', label: 'Federal funds rate' },
  { id: 'CPI', label: 'CPI' },
  { id: 'INFLATION', label: 'Inflation' },
  { id: 'RETAIL_SALES', label: 'Retail sales' },
  { id: 'DURABLES', label: 'Durable goods' },
  { id: 'UNEMPLOYMENT', label: 'Unemployment' },
  { id: 'NONFARM_PAYROLL', label: 'Nonfarm payroll' },
]

type Point = { date: string; value?: number }

export default function EconomicsPage() {
  const [indicator, setIndicator] = useState('REAL_GDP')
  const [interval, setInterval] = useState('annual')
  const [maturity, setMaturity] = useState('10year')

  const query = useQuery({
    queryKey: ['alphavantage', 'economics', indicator, interval, maturity],
    queryFn: () => {
      const params: Record<string, string> = { interval }
      if (indicator === 'TREASURY_YIELD') params.maturity = maturity
      return alphaVantageApi.economic(indicator, params)
    },
  })

  const data = useMemo(() => {
    return (((query.data as { data?: Point[] })?.data) ?? [])
      .slice()
      .sort((a, b) => (a.date > b.date ? 1 : -1))
  }, [query.data])

  const columns: AvTableColumn<Point>[] = [
    { key: 'date', header: 'Date' },
    { key: 'value', header: 'Value' },
  ]

  return (
    <AvPageShell title="Economic Indicators" subtitle="Macro indicators from the AV Economic Indicators suite.">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-4 gap-3">
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Indicator</label>
          <select
            className="input w-full"
            value={indicator}
            onChange={(e) => setIndicator(e.target.value)}
          >
            {INDICATORS.map((i) => (
              <option key={i.id} value={i.id}>
                {i.label}
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
            {['daily', 'weekly', 'monthly', 'quarterly', 'semiannual', 'annual'].map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </div>
        {indicator === 'TREASURY_YIELD' && (
          <div>
            <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Maturity</label>
            <select className="input w-full" value={maturity} onChange={(e) => setMaturity(e.target.value)}>
              {['3month', '2year', '5year', '7year', '10year', '30year'].map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className="card p-4">
        <AvLineChart
          data={data as unknown as Record<string, unknown>[]}
          xKey="date"
          series={[{ dataKey: 'value', name: indicator }]}
          height={320}
        />
      </div>
      <AvDataTable caption={`${indicator} history`} columns={columns} data={data} rowKey={(r) => r.date} />
    </AvPageShell>
  )
}
