'use client'

import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvLineChart } from '@/components/alphavantage/AvLineChart'
import { SymbolSearch } from '@/components/alphavantage/SymbolSearch'
import { alphaVantageApi } from '@/lib/api'

const INDICATORS = [
  'SMA', 'EMA', 'WMA', 'DEMA', 'TEMA', 'TRIMA', 'KAMA', 'MAMA', 'VWAP', 'T3',
  'MACD', 'MACDEXT', 'STOCH', 'STOCHF', 'RSI', 'STOCHRSI', 'WILLR', 'ADX', 'ADXR',
  'APO', 'PPO', 'MOM', 'BOP', 'CCI', 'CMO', 'ROC', 'ROCR', 'AROON', 'AROONOSC',
  'MFI', 'TRIX', 'ULTOSC', 'DX', 'MINUS_DI', 'PLUS_DI', 'MINUS_DM', 'PLUS_DM',
  'BBANDS', 'MIDPOINT', 'MIDPRICE', 'SAR', 'TRANGE', 'ATR', 'NATR', 'AD', 'ADOSC',
  'OBV', 'HT_TRENDLINE', 'HT_SINE', 'HT_TRENDMODE', 'HT_DCPERIOD', 'HT_DCPHASE',
  'HT_PHASOR',
]

type IndicatorSeries = {
  function?: string
  symbol?: string
  interval?: string | null
  time_period?: number | null
  series_type?: string | null
  indicator_name?: string | null
  points: Array<{ timestamp: string; values: Record<string, number | null> }>
  metadata?: Record<string, unknown>
}

export default function TechnicalsPage() {
  const [indicator, setIndicator] = useState('SMA')
  const [symbol, setSymbol] = useState('IBM')
  const [interval, setInterval] = useState('daily')
  const [timePeriod, setTimePeriod] = useState(20)
  const [seriesType, setSeriesType] = useState('close')

  const query = useQuery<IndicatorSeries>({
    queryKey: ['alphavantage', 'technical', indicator, symbol, interval, timePeriod, seriesType],
    queryFn: async () =>
      (await alphaVantageApi.technicals(indicator, {
        symbol,
        interval,
        time_period: timePeriod,
        series_type: seriesType,
      })) as IndicatorSeries,
    enabled: symbol.trim().length > 0,
  })

  const chartData = useMemo(() => {
    return (query.data?.points ?? [])
      .slice()
      .sort((a, b) => (a.timestamp > b.timestamp ? 1 : -1))
      .map((p) => ({ timestamp: p.timestamp, ...p.values }))
  }, [query.data?.points])

  const seriesKeys = useMemo(() => {
    const keys = new Set<string>()
    for (const p of query.data?.points ?? []) {
      for (const k of Object.keys(p.values ?? {})) {
        keys.add(k)
      }
    }
    return Array.from(keys)
  }, [query.data?.points])

  return (
    <AvPageShell
      title="Technical Indicators"
      subtitle="All 52 Alpha Vantage indicators behind one UI."
    >
      <div className="card p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-5 gap-3">
          <div className="md:col-span-2">
            <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Symbol</label>
            <SymbolSearch initialValue={symbol} onSelect={(m) => setSymbol(m.symbol)} />
          </div>
          <div>
            <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Indicator</label>
            <select className="input w-full" value={indicator} onChange={(e) => setIndicator(e.target.value)}>
              {INDICATORS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Interval</label>
            <select
              className="input w-full"
              value={interval}
              onChange={(e) => setInterval(e.target.value)}
            >
              {['1min', '5min', '15min', '30min', '60min', 'daily', 'weekly', 'monthly'].map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Period</label>
              <input
                type="number"
                min={1}
                max={500}
                className="input w-full"
                value={timePeriod}
                onChange={(e) => setTimePeriod(parseInt(e.target.value, 10) || 20)}
              />
            </div>
            <div>
              <label className="text-xs text-surface-500 uppercase tracking-wide mb-1 block">Series</label>
              <select
                className="input w-full"
                value={seriesType}
                onChange={(e) => setSeriesType(e.target.value)}
              >
                {['close', 'open', 'high', 'low'].map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="card p-4">
        <div className="flex justify-between items-baseline mb-3">
          <h3 className="text-sm font-semibold">
            {indicator} - {symbol} ({interval})
          </h3>
          <span className="text-xs text-surface-500">{chartData.length} points</span>
        </div>
        <AvLineChart
          data={chartData}
          xKey="timestamp"
          series={seriesKeys.map((k) => ({ dataKey: k, name: k }))}
          height={360}
          emptyMessage={query.isLoading ? 'Loading...' : 'No indicator data.'}
        />
      </div>
    </AvPageShell>
  )
}
