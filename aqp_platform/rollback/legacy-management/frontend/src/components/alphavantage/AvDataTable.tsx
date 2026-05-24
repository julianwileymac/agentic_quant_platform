'use client'

import { ReactNode } from 'react'

export type AvTableColumn<T> = {
  key: string
  header: string
  render?: (row: T) => ReactNode
  className?: string
}

type Props<T> = {
  columns: AvTableColumn<T>[]
  data: T[]
  rowKey?: (row: T, index: number) => string
  emptyMessage?: string
  caption?: string
}

export function AvDataTable<T>({ columns, data, rowKey, emptyMessage = 'No data.', caption }: Props<T>) {
  return (
    <div className="card overflow-hidden">
      {caption && (
        <div className="px-4 py-3 border-b border-surface-800 text-sm font-semibold text-surface-200">
          {caption}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-surface-900/80 text-xs uppercase tracking-wider text-surface-500">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className={`text-left px-4 py-2 font-medium ${c.className ?? ''}`}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-surface-800">
            {data.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-4 py-6 text-center text-surface-500">
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              data.map((row, idx) => (
                <tr key={rowKey ? rowKey(row, idx) : idx} className="hover:bg-surface-800/50">
                  {columns.map((c) => (
                    <td key={c.key} className={`px-4 py-2 text-surface-200 ${c.className ?? ''}`}>
                      {c.render
                        ? c.render(row)
                        : ((row as Record<string, unknown>)[c.key] as ReactNode) ?? '-'}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
