"use client";

/**
 * Runbook editor — TipTap WYSIWYG.
 *
 * Lazy-loaded by the route page so the TipTap bundle (~150KB) only
 * lands when the editor is actually opened. Mirrors the dynamic
 * import pattern used in the legacy Vite UI.
 */
import StarterKit from "@tiptap/starter-kit";
import { EditorContent, useEditor } from "@tiptap/react";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { adminGet } from "@/lib/api/client";

export function RunbookEditor({ runbookId }: { runbookId: string }) {
  const { data } = useQuery({
    queryKey: ["admin", "runbooks", runbookId],
    queryFn: () =>
      adminGet<{ id: string; title: string; body: string }>(
        `/runbooks/${runbookId}`,
      ),
    enabled: runbookId !== "new",
  });
  const editor = useEditor({
    extensions: [StarterKit],
    content: "",
    immediatelyRender: false,
  });
  useEffect(() => {
    if (editor && data?.body) {
      editor.commands.setContent(data.body);
    }
  }, [editor, data?.body]);
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">
        {data?.title ?? (runbookId === "new" ? "New runbook" : runbookId)}
      </h1>
      <div className="rounded-md border bg-white p-6">
        <EditorContent editor={editor} className="prose max-w-none" />
      </div>
    </div>
  );
}
