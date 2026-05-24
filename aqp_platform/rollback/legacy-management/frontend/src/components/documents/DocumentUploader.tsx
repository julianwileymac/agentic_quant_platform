'use client'

import { useMutation, useQueryClient } from '@tanstack/react-query'
import { ChangeEvent, DragEvent, useRef, useState } from 'react'
import { Upload, CheckCircle, AlertCircle } from 'lucide-react'

import { documentsApi } from '@/lib/api'

interface DocumentUploaderProps {
  defaultCollection?: string
}

const COLLECTION_PRESETS = ['general', 'rag', 'mlops', 'observability', 'manuals']

export function DocumentUploader({ defaultCollection = 'general' }: DocumentUploaderProps) {
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [tags, setTags] = useState('')
  const [collection, setCollection] = useState(defaultCollection)
  const [description, setDescription] = useState('')
  const [owner, setOwner] = useState('admin')
  const [dragActive, setDragActive] = useState(false)

  const upload = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Pick a file first')
      return documentsApi.upload(file, {
        title: title || file.name,
        tags,
        collection,
        owner,
        description,
      })
    },
    onSuccess: () => {
      setFile(null)
      setTitle('')
      setTags('')
      setDescription('')
      if (fileInput.current) fileInput.current.value = ''
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
  })

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) {
      setFile(f)
      if (!title) setTitle(f.name)
    }
  }

  const onDrop = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    const f = e.dataTransfer.files?.[0]
    if (f) {
      setFile(f)
      if (!title) setTitle(f.name)
    }
  }

  const onDragOver = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(true)
  }

  const onDragLeave = (e: DragEvent<HTMLLabelElement>) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
  }

  return (
    <div className="card p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-surface-100">Upload Document</h3>
        <p className="text-xs text-surface-500">
          Stored in MinIO + indexed via Redis 8 Stack
        </p>
      </div>

      <label
        htmlFor="document-file-input"
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={`flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-xl py-10 cursor-pointer transition-colors ${
          dragActive
            ? 'border-primary-400 bg-primary-500/10'
            : 'border-surface-700 hover:border-surface-500 hover:bg-surface-800/50'
        }`}
      >
        <Upload className="w-8 h-8 text-surface-400" />
        <p className="text-sm text-surface-300">
          {file ? `Ready: ${file.name} (${formatBytes(file.size)})` : 'Drop a file here or click to browse'}
        </p>
        <p className="text-xs text-surface-500">
          PDF, JSON, Markdown, plain text - up to 50 MB
        </p>
        <input
          id="document-file-input"
          ref={fileInput}
          type="file"
          accept=".pdf,.json,.md,.txt,.csv"
          className="hidden"
          onChange={onFileChange}
        />
      </label>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className="block text-xs uppercase tracking-wide text-surface-400 mb-1">
            Title
          </label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Defaults to filename"
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wide text-surface-400 mb-1">
            Collection
          </label>
          <input
            type="text"
            list="docstore-collections"
            value={collection}
            onChange={(e) => setCollection(e.target.value)}
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
          <datalist id="docstore-collections">
            {COLLECTION_PRESETS.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wide text-surface-400 mb-1">
            Tags (comma separated)
          </label>
          <input
            type="text"
            value={tags}
            onChange={(e) => setTags(e.target.value)}
            placeholder="rag, runbook"
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
        <div>
          <label className="block text-xs uppercase tracking-wide text-surface-400 mb-1">
            Owner
          </label>
          <input
            type="text"
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
        <div className="md:col-span-2">
          <label className="block text-xs uppercase tracking-wide text-surface-400 mb-1">
            Description
          </label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            placeholder="Optional notes / context"
            className="w-full bg-surface-900/50 border border-surface-800 rounded-lg px-3 py-2 text-sm text-surface-100 focus:border-primary-400 outline-none"
          />
        </div>
      </div>

      <div className="flex items-center justify-between pt-2">
        <div className="text-xs">
          {upload.isError && (
            <span className="inline-flex items-center gap-1 text-red-400">
              <AlertCircle className="w-4 h-4" />
              {(upload.error as Error)?.message ?? 'Upload failed'}
            </span>
          )}
          {upload.isSuccess && (
            <span className="inline-flex items-center gap-1 text-green-400">
              <CheckCircle className="w-4 h-4" />
              Uploaded {upload.data.title} ({upload.data.chunk_count} chunks)
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => upload.mutate()}
          disabled={!file || upload.isPending}
          className="btn btn-primary px-4 py-2 rounded-lg text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {upload.isPending ? 'Uploading...' : 'Upload + Index'}
        </button>
      </div>
    </div>
  )
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
