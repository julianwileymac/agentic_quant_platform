'use client'

import Link from 'next/link'
import { useQuery } from '@tanstack/react-query'
import {
  BarChart3,
  Briefcase,
  Building2,
  Coins,
  CandlestickChart,
  Globe2,
  Landmark,
  LineChart as LineChartIcon,
  Newspaper,
  Settings as SettingsIcon,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvUsageMeter } from '@/components/alphavantage/AvUsageMeter'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { alphaVantageApi, type TopMover } from '@/lib/api'

const categoryTiles = [
  { href: '/alphavantage/timeseries', label: 'Time Series', icon: CandlestickChart, desc: 'Intraday / daily / weekly / monthly OHLCV' },
  { href: '/alphavantage/fundamentals', label: 'Fundamentals', icon: Briefcase, desc: 'Company overview, IS/BS/CF, dividends' },
  { href: '/alphavantage/technicals', label: 'Technical Indicators', icon: LineChartIcon, desc: '52 indicators: SMA/EMA/MACD/RSI/...' },
  { href: '/alphavantage/intelligence', label: 'Alpha Intelligence', icon: Sparkles, desc: 'News sentiment, movers, insider' },
  { href: '/alphavantage/forex', label: 'Forex', icon: Globe2, desc: 'FX rates + intraday/daily/weekly/monthly' },
  { href: '/alphavantage/crypto', label: 'Crypto', icon: Coins, desc: 'Digital currency rates + bars' },
  { href: '/alphavantage/options', label: 'Options', icon: TrendingUp, desc: 'Realtime + historical chains, PCR, VOI' },
  { href: '/alphavantage/commodities', label: 'Commodities', icon: Landmark, desc: 'WTI, Brent, metals, ags, global index' },
  { href: '/alphavantage/economics', label: 'Economic Indicators', icon: BarChart3, desc: 'GDP, CPI, treasury yields, FFR' },
  { href: '/alphavantage/indices', label: 'Indices', icon: Building2, desc: 'DJI, SPX, IXIC, NDX, VIX, RUT' },
  { href: '/alphavantage/admin', label: 'Admin', icon: SettingsIcon, desc: 'Bulk loads, streaming toggle, workflows' },
]

export default function AlphaVantageHome() {
  const topMovers = useQuery({
    queryKey: ['alphavantage', 'top-movers'],
    queryFn: () => alphaVantageApi.topMovers(),
    refetchInterval: 60_000,
  })

  const news = useQuery({
    queryKey: ['alphavantage', 'news', 'dashboard'],
    queryFn: () => alphaVantageApi.news({ limit: 25 }),
    refetchInterval: 5 * 60_000,
  })

  const moverColumns: AvTableColumn<TopMover>[] = [
    { key: 'ticker', header: 'Ticker' },
    { key: 'price', header: 'Price' },
    { key: 'change_amount', header: 'Change' },
    { key: 'change_percentage', header: 'Change %' },
    { key: 'volume', header: 'Volume' },
  ]

  return (
    <AvPageShell
      title="Alpha Vantage"
      subtitle="Primary market data provider: quotes, fundamentals, news, options, FX, crypto, commodities, economics, and 50+ technical indicators."
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AvUsageMeter />
        <div className="card p-4 md:col-span-2 space-y-3">
          <h3 className="text-sm font-semibold text-surface-200">Quick links</h3>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {categoryTiles.map((tile) => (
              <Link
                key={tile.href}
                href={tile.href}
                className="p-3 rounded-lg border border-surface-800 hover:border-primary-500/40 hover:bg-surface-800 transition"
              >
                <div className="flex items-center gap-2 mb-1 text-surface-100">
                  <tile.icon className="w-4 h-4 text-primary-400" />
                  <span className="text-sm font-semibold">{tile.label}</span>
                </div>
                <p className="text-xs text-surface-400">{tile.desc}</p>
              </Link>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AvDataTable
          caption="Top gainers"
          columns={moverColumns}
          data={topMovers.data?.top_gainers ?? []}
          rowKey={(row) => `g-${row.ticker}`}
        />
        <AvDataTable
          caption="Top losers"
          columns={moverColumns}
          data={topMovers.data?.top_losers ?? []}
          rowKey={(row) => `l-${row.ticker}`}
        />
      </div>

      <div className="card p-4">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-sm font-semibold text-surface-200 flex items-center gap-2">
              <Newspaper className="w-4 h-4 text-primary-400" />
              Latest market news
            </h3>
            <p className="text-xs text-surface-500">Sentiment-enriched feed from NEWS_SENTIMENT.</p>
          </div>
          <Link href="/alphavantage/intelligence" className="text-xs text-primary-400 hover:text-primary-300">
            View all
          </Link>
        </div>
        {news.isLoading ? (
          <div className="text-sm text-surface-500">Loading news...</div>
        ) : (
          <ul className="space-y-3">
            {(news.data?.feed ?? []).slice(0, 8).map((article) => (
              <li key={article.url} className="border-b border-surface-800 pb-3 last:border-b-0 last:pb-0">
                <a
                  href={article.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-sm font-semibold text-surface-100 hover:text-primary-300"
                >
                  {article.title}
                </a>
                <div className="text-xs text-surface-500 mt-1">
                  {article.source} - {article.time_published} - sentiment{' '}
                  <SentimentPill label={article.overall_sentiment_label} score={article.overall_sentiment_score} />
                </div>
                {article.summary && (
                  <p className="text-xs text-surface-400 mt-1 line-clamp-2">{article.summary}</p>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </AvPageShell>
  )
}

function SentimentPill({ label, score }: { label?: string; score?: number }) {
  if (!label) return <span className="text-surface-500">n/a</span>
  const palette =
    (score ?? 0) > 0.15
      ? 'bg-emerald-500/20 text-emerald-400'
      : (score ?? 0) < -0.15
        ? 'bg-red-500/20 text-red-400'
        : 'bg-surface-700 text-surface-300'
  return (
    <span className={`inline-block text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded ${palette}`}>
      {label} {(score ?? 0).toFixed(2)}
    </span>
  )
}
