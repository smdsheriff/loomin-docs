import { useCallback, useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import { useEditor, EditorContent, BubbleMenu } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Highlight from '@tiptap/extension-highlight';
import Typography from '@tiptap/extension-typography';
import UnderlineExt from '@tiptap/extension-underline';
import Placeholder from '@tiptap/extension-placeholder';
import Toolbar from './Toolbar';
import { Sparkles, FileText } from 'lucide-react';

export interface EditorHandle {
  replaceSelection: (text: string) => void;
  setContent: (html: string) => void;
}

interface EditorProps {
  content: string;
  onContentChange: (content: string) => void;
  onSelectionChange: (text: string) => void;
  onSummarizeSelection: (text: string) => void;
  onImproveSelection: (text: string) => void;
}

const EditorComponent = forwardRef<EditorHandle, EditorProps>(function Editor(
  {
    content,
    onContentChange,
    onSelectionChange,
    onSummarizeSelection,
    onImproveSelection,
  },
  ref
) {
  const contentInitialized = useRef(false);
  const selectionRange = useRef<{ from: number; to: number } | null>(null);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [1, 2, 3] },
        codeBlock: { HTMLAttributes: { class: 'code-block' } },
      }),
      Highlight.configure({ multicolor: false }),
      Typography,
      UnderlineExt,
      Placeholder.configure({
        placeholder: 'Start writing your document...',
      }),
    ],
    content: '',
    editorProps: {
      attributes: {
        class: 'focus:outline-none',
      },
    },
    onUpdate: ({ editor: ed }) => {
      onContentChange(ed.getHTML());
    },
    onSelectionUpdate: ({ editor: ed }) => {
      const { from, to } = ed.state.selection;
      if (from !== to) {
        const text = ed.state.doc.textBetween(from, to, ' ');
        selectionRange.current = { from, to };
        onSelectionChange(text);
      } else {
        selectionRange.current = null;
        onSelectionChange('');
      }
    },
  });

  // Expose replaceSelection and setContent to parent via ref
  useImperativeHandle(ref, () => ({
    replaceSelection(text: string) {
      if (!editor) return;
      const range = selectionRange.current;
      if (range) {
        editor.chain().focus().insertContentAt(
          { from: range.from, to: range.to },
          text
        ).run();
      } else {
        // No selection stored — append at cursor
        editor.chain().focus().insertContent(text).run();
      }
    },
    setContent(html: string) {
      if (!editor) return;
      editor.commands.setContent(html, false);
    },
  }), [editor]);

  // Set content from DB when editor is ready. The guard prevents re-setting during
  // normal user edits (onUpdate fires setContent → prop change → this effect).
  useEffect(() => {
    if (!editor) return;
    if (!contentInitialized.current && content) {
      // Initial load: set the full HTML content from the database
      editor.commands.setContent(content, false);
      contentInitialized.current = true;
    }
  }, [editor, content]);

  const handleSummarize = useCallback(() => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const text = editor.state.doc.textBetween(from, to, ' ');
    if (text.trim()) {
      onSummarizeSelection(text);
    }
  }, [editor, onSummarizeSelection]);

  const handleImprove = useCallback(() => {
    if (!editor) return;
    const { from, to } = editor.state.selection;
    const text = editor.state.doc.textBetween(from, to, ' ');
    if (text.trim()) {
      onImproveSelection(text);
    }
  }, [editor, onImproveSelection]);

  return (
    <div className="flex flex-col h-full bg-white">
      <Toolbar editor={editor} />

      <div className="flex-1 overflow-auto">
        {editor && (
          <BubbleMenu
            editor={editor}
            shouldShow={({ editor: ed }) => {
              const { from, to } = ed.state.selection;
              return from !== to;
            }}
            tippyOptions={{
              duration: 150,
              placement: 'top-start',
              appendTo: () => document.body,
              sticky: 'reference',
              popperOptions: {
                modifiers: [
                  { name: 'flip', options: { fallbackPlacements: ['bottom-start', 'top', 'bottom'] } },
                  { name: 'preventOverflow', options: { boundary: 'viewport', padding: 8, altAxis: true, tether: false } },
                ],
              },
            }}
            className="flex items-center gap-1 bg-white border border-gray-200 rounded-lg shadow-lg p-1 z-50"
          >
            <button
              onClick={handleSummarize}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-blue-50 hover:text-blue-700 rounded transition-colors"
            >
              <FileText size={13} />
              Summarize
            </button>
            <button
              onClick={handleImprove}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-gray-700 hover:bg-purple-50 hover:text-purple-700 rounded transition-colors"
            >
              <Sparkles size={13} />
              Improve
            </button>
          </BubbleMenu>
        )}

        <EditorContent editor={editor} className="h-full" />
      </div>
    </div>
  );
});

export default EditorComponent;
