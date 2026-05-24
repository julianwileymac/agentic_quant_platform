'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi, type OhlcvBar } from '@/lib/api'

const INDICES = [
  { id: 'dji', label: 'Dow Jones Industrial Average' },
  { id: 'spx', label: 'S&P 500' },
  { id: 'ixic', label: 'NASDAQ Composite' },
  { id: 'ndx', label: 'NASDAQ 100' },
  { id: 'vix', label: 'CBOE VIX' },
  { id: 'rut', label: 'Russell 2000' },
]

export default function IndicesPage() {
  const [index, setIndex] = useState('spx')

  const series = useQuery({
    queryKey: ['alphavantage', 'indices', index],
    queryFn: () => alphaVantageApi.indices(index),
  })

  const catalog = useQuery({
    queryKey: ['alphavantage', 'indices', 'catalog'],
    queryFn: () => alphaVantageApi.indicesCatalog(),
  })

  const bars = useMemo(() => {
    return (((series.data as { bars?: OhlcvBar[] })?.bars) ?? []).slice().reverse()
  }, [series.data])

  const columns: AvTableColumn<OhlcvBar>[] = [
    { key: 'timestamp', header: 'Timestamp' },
    { key: 'open', header: 'Open' },
    { key: 'high', header: 'High' },
    { key: 'low', header: 'Low' },
    { key: 'close', header: 'Close' },
    { key: 'volume', header: 'Volume' },
  ]

  const catalogRows = (catalog.data as Array<Record<string, unknown>>) ?? []
  const catalogColumns: AvTableColumn<Record<string, unknown>>[] = catalogRows[0]
    ? Object.keys(catalogRows[0]).map((k) => ({
        key: k,
        header: k.replace(/_/g, ' '),
        render: (row) => String(row[k] ?? '-'),
      }))
    : []

  return (
    <AvPageShell title="Indices" subtitle="Major US indices (DJI, SPX, IXIC, NDX, VIX, RUT) + Index Catalog.">
      <div className="card p-4 flex flex-wrap gap-2">
        {INDICES.map((i) => (
          <button
            key={i.id}
            onClick={() => setIndex(i.id)}
            className={`btn text-xs ${index === i.id ? 'btn-primary' : 'btn-ghost'}`}
          >
            {i.label}
          </button>
        ))}
      </div>

      <div className="card p-4">
        <AvLineChart
          data={bars as unknown as Record<string, unknown>[]}
          xKey="timestamp"
          series={[{ dataKey: 'close', name: 'Close' }]}
          height={320}
        />
      </div>
      <AvDataTable caption="Bars" columns={columns} data={bars.slice(0, 200)} rowKey={(r) => r.timestamp} />

      <AvDataTable
        caption="Index catalog"
        columns={catalogColumns}
        data={catalogRows}
        rowKey={(_, i) => `cat-${i}`}
        emptyMessage={catalog.isLoading ? 'Loading catalog...' : 'No catalog entries returned.'}
      />
    </AvPageShell>
  )
}
