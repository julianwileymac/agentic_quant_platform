'use client'

import {
  CartesianGrid,
  Line,
  LineChart as RLineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

type Series = {
  dataKey: string
  name?: string
  stroke?: string
  strokeDasharray?: string
}

type Props = {
  data: Array<Record<string, unknown>>
  xKey: string
  series: Series[]
  height?: number
  yDomain?: ['auto' | number, 'auto' | number]
  emptyMessage?: string
}

const DEFAULT_COLORS = ['#38bdf8', '#fbbf24', '#f472b6', '#34d399', '#a78bfa', '#f87171']

export function AvLineChart({
  data,
  xKey,
  series,
  height = 320,
  yDomain = ['auto', 'auto'],
  emptyMessage = 'No data to plot.',
}: Props) {
  if (!data || data.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-surface-500 border border-dashed border-surface-800 rounded-lg"
        style={{ height }}
      >
        {emptyMessage}
      </div>
    )
  }
  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <RLineChart data={data} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
          <XAxis
            dataKey={xKey}
            stroke="#6b7280"
            fontSize={11}
            tickMargin={8}
            minTickGap={24}
          />
          <YAxis stroke="#6b7280" fontSize={11} domain={yDomain} width={64} />
          <Tooltip
            contentStyle={{
              backgroundColor: '#0f172a',
              border: '1px solid #1f2937',
              borderRadius: 8,
              color: '#f1f5f9',
              fontSize: 12,
            }}
          />
          {series.map((s, idx) => (
            <Line
              key={s.dataKey}
              type="monotone"
              dataKey={s.dataKey}
              name={s.name ?? s.dataKey}
              stroke={s.stroke ?? DEFAULT_COLORS[idx % DEFAULT_COLORS.length]}
              strokeWidth={2}
              dot={false}
              strokeDasharray={s.strokeDasharray}
              isAnimationActive={false}
            />
          ))}
        </RLineChart>
      </ResponsiveContainer>
    </div>
  )
}
