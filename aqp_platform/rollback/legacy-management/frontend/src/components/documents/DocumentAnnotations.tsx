'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Trash2, MessageSquare } from 'lucide-react'
import { useState } from 'react'

import { documentsApi, AnnotationModel } from '@/lib/api'

interface DocumentAnnotationsProps {
  docId: string
}

export function DocumentAnnotations({ docId }: DocumentAnnotationsProps) {
  const queryClient = useQueryClient()
  const [body, setBody] = useState('')
  const [author, setAuthor] = useState('admin')
  const [tags, setTags] = useState('')
  const [anchor, setAnchor] = useState('')

  const list = useQuery({
    queryKey: ['annotations', docId],
    queryFn: () => documentsApi.listAnnotations(docId),
  })

  const create = useMutation({
    mutationFn: () =>
      documentsApi.addAnnotation(docId, {
        body,
        author,
        tags: tags.split(',').map((t) => t.trim()).filter(Boolean),
        anchor,
      }),
    onSuccess: () => {
      setBody('')
      setAnchor('')
      setTags('')
      queryClient.invalidateQueries({ queryKey: ['annotations', docId] })
    },
  })

  const remove = useMutation({
    mutationFn: (annId: string) => documentsApi.deleteAnnotation(docId, annId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['annotations', docId] }),
  })

  return (
    <div className="card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-surface-100 flex items-center gap-2">
          <MessageSquare className="w-5 h-5 text-primary-400" />
          Annotations
        </h3>
        <span className="text-xs text-surface-500">Stored as RedisJSON under ann:&#123;doc&#125;:&#123;id&#125;</span>
      </div>

      <div className="space-y-2">
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={3}
          placeholder="Freehand annotation - markdown supported"
          className="w-full bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
        />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="Author"
            className="bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="Tags (comma separated)"
            className="bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
          <input
            type="text"
            value={anchor}
            onChange={(e) => setAnchor(e.target.value)}
            placeholder="Anchor (e.g. chunk:5)"
            className="bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={() => create.mutate()}
            disabled={!body || create.isPending}
            className="btn btn-primary px-3 py-2 rounded-lg text-sm disabled:opacity-50"
          >
            {create.isPending ? 'Saving...' : 'Add annotation'}
          </button>
        </div>
      </div>

      {list.isLoading ? (
        <div className="text-sm text-surface-400">Loading annotations...</div>
      ) : list.data && list.data.length > 0 ? (
        <ul className="space-y-2">
          {list.data.map((ann) => (
            <AnnotationRow
              key={ann.id}
              ann={ann}
              onDelete={() => remove.mutate(ann.id)}
              isPending={remove.isPending}
            />
          ))}
        </ul>
      ) : (
        <div className="text-sm text-surface-500 text-center py-4">
          No annotations yet.
        </div>
      )}
    </div>
  )
}

interface AnnotationRowProps {
  ann: AnnotationModel
  onDelete: () => void
  isPending: boolean
}

function AnnotationRow({ ann, onDelete, isPending }: AnnotationRowProps) {
  return (
    <li className="border border-surface-800 rounded-lg p-3 bg-surface-900/30">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1">
          <div className="flex items-center gap-2 text-xs text-surface-500">
            <span className="text-surface-300 font-medium">{ann.author}</span>
            <span>•</span>
            <span>{new Date(ann.created_at * 1000).toLocaleString()}</span>
            {ann.anchor && (
              <>
                <span>•</span>
                <span>anchor: {ann.anchor}</span>
              </>
            )}
          </div>
          <p className="text-sm text-surface-100 whitespace-pre-wrap mt-1">{ann.body}</p>
          {ann.tags?.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {ann.tags.map((tag) => (
                <span
                  key={tag}
                  className="badge px-2 py-0.5 rounded bg-surface-800 text-xs text-surface-300"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => onDelete()}
          disabled={isPending}
          className="text-surface-400 hover:text-red-400 disabled:opacity-50"
          title="Delete annotation"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </li>
  )
}
