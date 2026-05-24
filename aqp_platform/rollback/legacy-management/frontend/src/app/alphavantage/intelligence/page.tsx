'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AvPageShell } from '@/components/alphavantage/AvPageShell'
import { AvDataTable, type AvTableColumn } from '@/components/alphavantage/AvDataTable'
import { SymbolSearch } from '@/components/alphavantage/SymbolSearch'
import { alphaVantageApi, type NewsArticle, type TopMover } from '@/lib/api'

const TABS = [
  { id: 'news', label: 'News sentiment' },
  { id: 'top-movers', label: 'Top movers' },
  { id: 'insider', label: 'Insider transactions' },
  { id: 'institutional', label: 'Institutional holdings' },
  { id: 'transcript', label: 'Earnings transcript' },
]

export default function IntelligencePage() {
  const [tab, setTab] = useState('news')

  return (
    <AvPageShell
      title="Alpha Intelligence"
      subtitle="News sentiment, earnings transcripts, top movers, insider + institutional holdings."
    >
      <div className="flex flex-wrap gap-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`btn text-xs ${tab === t.id ? 'btn-primary' : 'btn-ghost'}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'news' && <NewsTab />}
      {tab === 'top-movers' && <TopMoversTab />}
      {tab === 'insider' && <InsiderTab />}
      {tab === 'institutional' && <InstitutionalTab />}
      {tab === 'transcript' && <TranscriptTab />}
    </AvPageShell>
  )
}

function NewsTab() {
  const [tickers, setTickers] = useState('')
  const [topics, setTopics] = useState('')
  const query = useQuery({
    queryKey: ['alphavantage', 'news', tickers, topics],
    queryFn: () =>
      alphaVantageApi.news({
        tickers: tickers || undefined,
        topics: topics || undefined,
        limit: 50,
      }),
  })
  return (
    <div className="space-y-4">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <input
          className="input"
          placeholder="Tickers e.g. AAPL,MSFT"
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
        />
        <input
          className="input"
          placeholder="Topics e.g. technology,earnings"
          value={topics}
          onChange={(e) => setTopics(e.target.value)}
        />
        <button className="btn btn-primary text-xs" onClick={() => query.refetch()}>
          Refresh
        </button>
      </div>
      <div className="space-y-3">
        {(query.data?.feed ?? []).map((article: NewsArticle) => (
          <article key={article.url} className="card p-4">
            <a
              href={article.url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-semibold text-surface-100 hover:text-primary-300"
            >
              {article.title}
            </a>
            <div className="mt-1 text-xs text-surface-500">
              {article.source} - {article.time_published} - sentiment {article.overall_sentiment_label} (
              {(article.overall_sentiment_score ?? 0).toFixed(2)})
            </div>
            <p className="text-sm text-surface-300 mt-2">{article.summary}</p>
            {article.ticker_sentiment && article.ticker_sentiment.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1 text-xs">
                {article.ticker_sentiment.slice(0, 6).map((ts) => (
                  <span
                    key={ts.ticker}
                    className="px-1.5 py-0.5 rounded bg-surface-800 text-surface-300"
                  >
                    {ts.ticker} ({(ts.ticker_sentiment_score ?? 0).toFixed(2)})
                  </span>
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </div>
  )
}

function TopMoversTab() {
  const query = useQuery({
    queryKey: ['alphavantage', 'intel', 'top-movers'],
    queryFn: () => alphaVantageApi.topMovers(),
  })
  const columns: AvTableColumn<TopMover>[] = [
    { key: 'ticker', header: 'Ticker' },
    { key: 'price', header: 'Price' },
    { key: 'change_amount', header: 'Change' },
    { key: 'change_percentage', header: 'Change %' },
    { key: 'volume', header: 'Volume' },
  ]
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <AvDataTable caption="Top gainers" columns={columns} data={query.data?.top_gainers ?? []} rowKey={(r) => `g-${r.ticker}`} />
      <AvDataTable caption="Top losers" columns={columns} data={query.data?.top_losers ?? []} rowKey={(r) => `l-${r.ticker}`} />
      <AvDataTable
        caption="Most actively traded"
        columns={columns}
        data={query.data?.most_actively_traded ?? []}
        rowKey={(r) => `m-${r.ticker}`}
      />
    </div>
  )
}

function InsiderTab() {
  const [symbol, setSymbol] = useState('AAPL')
  const query = useQuery({
    queryKey: ['alphavantage', 'insider', symbol],
    queryFn: () => alphaVantageApi.intelligence('insider', { symbol }),
    enabled: symbol.length > 0,
  })
  const rows = (query.data as Array<Record<string, unknown>>) ?? []
  const columns: AvTableColumn<Record<string, unknown>>[] = rows[0]
    ? Object.keys(rows[0]).map((k) => ({ key: k, header: k.replace(/_/g, ' '), render: (r) => String(r[k] ?? '-') }))
    : []
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Symbol</label>
        <SymbolSearch initialValue={symbol} onSelect={(m) => setSymbol(m.symbol)} />
      </div>
      <AvDataTable columns={columns} data={rows} rowKey={(_, i) => `i-${i}`} />
    </div>
  )
}

function InstitutionalTab() {
  const [symbol, setSymbol] = useState('AAPL')
  const query = useQuery({
    queryKey: ['alphavantage', 'institutional', symbol],
    queryFn: () => alphaVantageApi.intelligence('institutional', { symbol }),
    enabled: symbol.length > 0,
  })
  const rows = (query.data as Array<Record<string, unknown>>) ?? []
  const columns: AvTableColumn<Record<string, unknown>>[] = rows[0]
    ? Object.keys(rows[0]).map((k) => ({ key: k, header: k.replace(/_/g, ' '), render: (r) => String(r[k] ?? '-') }))
    : []
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Symbol</label>
        <SymbolSearch initialValue={symbol} onSelect={(m) => setSymbol(m.symbol)} />
      </div>
      <AvDataTable columns={columns} data={rows} rowKey={(_, i) => `ih-${i}`} />
    </div>
  )
}

function TranscriptTab() {
  const [symbol, setSymbol] = useState('IBM')
  const [quarter, setQuarter] = useState('2024Q1')
  const query = useQuery({
    queryKey: ['alphavantage', 'transcript', symbol, quarter],
    queryFn: () => alphaVantageApi.intelligence('transcript', { symbol, quarter }),
    enabled: symbol.length > 0 && quarter.length > 0,
  })
  const transcript =
    ((query.data as { transcript?: Array<Record<string, unknown>> } | undefined)?.transcript) ?? []
  return (
    <div className="space-y-4">
      <div className="card p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <div className="md:col-span-2">
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Symbol</label>
          <SymbolSearch initialValue={symbol} onSelect={(m) => setSymbol(m.symbol)} />
        </div>
        <div>
          <label className="text-xs uppercase tracking-wide text-surface-500 mb-1 block">Quarter</label>
          <input
            className="input w-full"
            value={quarter}
            onChange={(e) => setQuarter(e.target.value)}
            placeholder="YYYYQN e.g. 2024Q1"
          />
        </div>
      </div>
      <div className="space-y-2">
        {transcript.map((turn: Record<string, unknown>, idx: number) => (
          <div key={idx} className="card p-3 space-y-1">
            <div className="text-xs text-surface-400">
              {String(turn.speaker ?? '')} - {String(turn.title ?? '')}
            </div>
            <div className="text-sm text-surface-100 whitespace-pre-wrap">
              {String(turn.content ?? '')}
            </div>
          </div>
        ))}
        {transcript.length === 0 && (
          <p className="text-sm text-surface-500">
            {query.isLoading ? 'Loading transcript...' : 'No transcript for this quarter.'}
          </p>
        )}
      </div>
    </div>
  )
}
