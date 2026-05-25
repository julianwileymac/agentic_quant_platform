/**
 * TipTap runbook editor — starter-kit only, no collaboration.
 *
 * Imported lazily by ``routes/runbooks/index`` so the editor bundle
 * stays out of the dashboard / accounts paths.
 */
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect } from "react";

export type RunbookEditorProps = {
  initialDoc: unknown;
  onChange(next: unknown): void;
};

export default function RunbookEditor({ initialDoc, onChange }: RunbookEditorProps) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: initialDoc as object,
    onUpdate({ editor: instance }) {
      onChange(instance.getJSON());
    },
  });
  // Re-sync if the parent swaps the doc (e.g. after loading another runbook).
  useEffect(() => {
    if (!editor) return;
    editor.commands.setContent(initialDoc as object, false);
  }, [editor, initialDoc]);
  return (
    <div className="prose prose-sm max-w-none rounded border p-3">
      <EditorContent editor={editor} />
    </div>
  );
}
