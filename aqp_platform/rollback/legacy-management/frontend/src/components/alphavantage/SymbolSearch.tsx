'use client'

import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Search } from 'lucide-react'
import { alphaVantageApi, type SymbolSearchMatch } from '@/lib/api'

type Props = {
  onSelect?: (match: SymbolSearchMatch) => void
  placeholder?: string
  initialValue?: string
}

function useDebouncedValue<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(t)
  }, [value, delay])
  return debounced
}

export function SymbolSearch({
  onSelect,
  placeholder = 'Search ticker (e.g. IBM, AAPL)...',
  initialValue = '',
}: Props) {
  const [term, setTerm] = useState(initialValue)
  const debounced = useDebouncedValue(term, 400)
  const query = useQuery({
    queryKey: ['alphavantage', 'search', debounced],
    queryFn: () => alphaVantageApi.searchSymbols(debounced),
    enabled: debounced.trim().length > 0,
  })

  return (
    <div className="relative">
      <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-surface-800 border border-surface-700">
        <Search className="w-4 h-4 text-surface-400" />
        <input
          className="bg-transparent flex-1 text-sm text-surface-100 outline-none"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          placeholder={placeholder}
        />
      </div>
      {debounced && query.data && query.data.length > 0 && (
        <div className="absolute z-20 mt-1 left-0 right-0 card p-2 max-h-80 overflow-auto">
          {query.data.slice(0, 20).map((match) => (
            <button
              key={`${match.symbol}-${match.region ?? ''}`}
              onClick={() => {
                onSelect?.(match)
                setTerm(match.symbol)
              }}
              className="w-full text-left px-2 py-2 rounded-lg hover:bg-surface-800"
            >
              <div className="flex items-center justify-between">
                <span className="font-semibold text-surface-100">{match.symbol}</span>
                <span className="text-xs text-surface-500">{match.region}</span>
              </div>
              <div className="text-xs text-surface-400 truncate">
                {match.name ?? ''} {match.type ? `- ${match.type}` : ''}{' '}
                {match.currency ? `- ${match.currency}` : ''}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
