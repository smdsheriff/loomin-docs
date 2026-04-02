import React, { useState, useCallback, useRef, useEffect } from 'react';
import { FileText, PenLine, Check, X, Cloud, CloudOff, Download, Keyboard, Type, ChevronDown } from 'lucide-react';

interface LayoutProps {
  title: string;
  onTitleChange: (title: string) => void;
  editor: React.ReactNode;
  sidebar: React.ReactNode;
  wordCount?: number;
  saveStatus?: 'saved' | 'saving' | 'unsaved';
}

const MIN_SIDEBAR_WIDTH = 320;
const MAX_SIDEBAR_WIDTH = 600;
const DEFAULT_SIDEBAR_WIDTH = 380;

export default function Layout({
  title,
  onTitleChange,
  editor,
  sidebar,
  wordCount = 0,
  saveStatus = 'saved',
}: LayoutProps) {
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [isResizing, setIsResizing] = useState(false);
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitle, setEditTitle] = useState(title);
  const [showShortcuts, setShowShortcuts] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setEditTitle(title);
  }, [title]);

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setIsResizing(true);
  }, []);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      if (!containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const newWidth = containerRect.right - e.clientX;
      setSidebarWidth(Math.min(MAX_SIDEBAR_WIDTH, Math.max(MIN_SIDEBAR_WIDTH, newWidth)));
    };
    const handleMouseUp = () => setIsResizing(false);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  const handleTitleClick = () => {
    setIsEditingTitle(true);
    setTimeout(() => titleInputRef.current?.select(), 0);
  };

  const commitTitle = () => {
    setIsEditingTitle(false);
    const trimmed = editTitle.trim();
    if (trimmed && trimmed !== title) {
      onTitleChange(trimmed);
    } else {
      setEditTitle(title);
    }
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') commitTitle();
    else if (e.key === 'Escape') { setEditTitle(title); setIsEditingTitle(false); }
  };

  const [showExportMenu, setShowExportMenu] = useState(false);

  const downloadFile = (content: string, filename: string, mime: string) => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const htmlToMarkdown = (html: string): string => {
    // Lightweight HTML→Markdown conversion for common TipTap elements
    let md = html;
    md = md.replace(/<h1[^>]*>(.*?)<\/h1>/gi, '# $1\n\n');
    md = md.replace(/<h2[^>]*>(.*?)<\/h2>/gi, '## $1\n\n');
    md = md.replace(/<h3[^>]*>(.*?)<\/h3>/gi, '### $1\n\n');
    md = md.replace(/<strong>(.*?)<\/strong>/gi, '**$1**');
    md = md.replace(/<b>(.*?)<\/b>/gi, '**$1**');
    md = md.replace(/<em>(.*?)<\/em>/gi, '*$1*');
    md = md.replace(/<i>(.*?)<\/i>/gi, '*$1*');
    md = md.replace(/<u>(.*?)<\/u>/gi, '$1');
    md = md.replace(/<s>(.*?)<\/s>/gi, '~~$1~~');
    md = md.replace(/<code>(.*?)<\/code>/gi, '`$1`');
    md = md.replace(/<pre[^>]*><code[^>]*>([\s\S]*?)<\/code><\/pre>/gi, '```\n$1\n```\n\n');
    md = md.replace(/<blockquote[^>]*>([\s\S]*?)<\/blockquote>/gi, '> $1\n\n');
    md = md.replace(/<li[^>]*>(.*?)<\/li>/gi, '- $1\n');
    md = md.replace(/<\/?(ul|ol|li|p|div|span|br|hr)[^>]*>/gi, (tag) => {
      if (tag.match(/<br\s*\/?>/i)) return '\n';
      if (tag.match(/<hr\s*\/?>/i)) return '\n---\n\n';
      if (tag.match(/<\/p>/i)) return '\n\n';
      return '';
    });
    md = md.replace(/<[^>]+>/g, '');
    md = md.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"');
    md = md.replace(/\n{3,}/g, '\n\n');
    return md.trim();
  };

  const handleExportTxt = () => {
    const editorEl = document.querySelector('.ProseMirror');
    if (!editorEl) return;
    downloadFile(editorEl.textContent || '', `${title || 'document'}.txt`, 'text/plain');
    setShowExportMenu(false);
  };

  const handleExportMd = () => {
    const editorEl = document.querySelector('.ProseMirror');
    if (!editorEl) return;
    const md = htmlToMarkdown(editorEl.innerHTML || '');
    downloadFile(md, `${title || 'document'}.md`, 'text/markdown');
    setShowExportMenu(false);
  };

  const handleExportHtml = () => {
    const editorEl = document.querySelector('.ProseMirror');
    if (!editorEl) return;
    const html = `<!DOCTYPE html>\n<html><head><meta charset="utf-8"><title>${title || 'document'}</title></head><body>\n${editorEl.innerHTML}\n</body></html>`;
    downloadFile(html, `${title || 'document'}.html`, 'text/html');
    setShowExportMenu(false);
  };

  return (
    <div ref={containerRef} className="flex flex-col h-screen bg-white">
      {/* Top bar */}
      <header className="flex items-center h-12 px-4 border-b border-gray-200 bg-white shrink-0">
        {/* Brand */}
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-blue-600 flex items-center justify-center">
            <FileText size={14} className="text-white" />
          </div>
          <span className="font-bold text-sm text-gray-900 tracking-tight">
            Loomin Docs
          </span>
        </div>

        <div className="mx-3 h-5 w-px bg-gray-200" />

        {/* Document title */}
        <div className="flex items-center gap-2 min-w-0 flex-1">
          {isEditingTitle ? (
            <div className="flex items-center gap-1.5">
              <input
                ref={titleInputRef}
                type="text"
                value={editTitle}
                onChange={(e) => setEditTitle(e.target.value)}
                onBlur={commitTitle}
                onKeyDown={handleTitleKeyDown}
                className="bg-blue-50 text-gray-900 text-sm px-2.5 py-1 rounded-md border border-blue-300 outline-none ring-2 ring-blue-100 min-w-0 w-64 font-medium"
                autoFocus
              />
              <button onClick={commitTitle} className="p-1 rounded hover:bg-green-50 text-green-600" title="Save">
                <Check size={14} />
              </button>
              <button onClick={() => { setEditTitle(title); setIsEditingTitle(false); }} className="p-1 rounded hover:bg-red-50 text-red-500" title="Cancel">
                <X size={14} />
              </button>
            </div>
          ) : (
            <button
              onClick={handleTitleClick}
              className="flex items-center gap-1.5 text-sm text-gray-700 hover:text-blue-600 transition-colors truncate group"
              title="Click to rename"
            >
              <PenLine size={12} className="text-gray-400 group-hover:text-blue-500 shrink-0" />
              <span className="truncate font-medium">{title || 'Untitled Document'}</span>
            </button>
          )}
        </div>

        {/* Right side: status indicators and actions */}
        <div className="flex items-center gap-3 shrink-0">
          {/* Save status */}
          <div className="flex items-center gap-1.5 text-[11px]" title={`Status: ${saveStatus}`}>
            {saveStatus === 'saved' && (
              <>
                <Cloud size={13} className="text-green-500" />
                <span className="text-green-600 font-medium">Saved</span>
              </>
            )}
            {saveStatus === 'saving' && (
              <>
                <Cloud size={13} className="text-amber-500 animate-pulse" />
                <span className="text-amber-600 font-medium">Saving...</span>
              </>
            )}
            {saveStatus === 'unsaved' && (
              <>
                <CloudOff size={13} className="text-gray-400" />
                <span className="text-gray-500">Unsaved</span>
              </>
            )}
          </div>

          <div className="h-4 w-px bg-gray-200" />

          {/* Word count */}
          <div className="flex items-center gap-1 text-[11px] text-gray-500" title="Word count">
            <Type size={12} />
            <span>{wordCount.toLocaleString()} words</span>
          </div>

          <div className="h-4 w-px bg-gray-200" />

          {/* Export dropdown */}
          <div className="relative">
            <button
              onClick={() => setShowExportMenu(!showExportMenu)}
              className="flex items-center gap-0.5 p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              title="Export document"
            >
              <Download size={14} />
              <ChevronDown size={10} />
            </button>
            {showExportMenu && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowExportMenu(false)} />
                <div className="absolute right-0 top-full mt-1 w-40 bg-white border border-gray-200 rounded-lg shadow-xl z-50 py-1">
                  <button onClick={handleExportTxt} className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50">Export as .txt</button>
                  <button onClick={handleExportMd} className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50">Export as .md</button>
                  <button onClick={handleExportHtml} className="w-full text-left px-3 py-1.5 text-xs text-gray-700 hover:bg-gray-50">Export as .html</button>
                </div>
              </>
            )}
          </div>

          {/* Keyboard shortcuts */}
          <div className="relative">
            <button
              onClick={() => setShowShortcuts(!showShortcuts)}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
              title="Keyboard shortcuts"
            >
              <Keyboard size={14} />
            </button>
            {showShortcuts && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setShowShortcuts(false)} />
                <div className="absolute right-0 top-full mt-2 w-56 bg-white border border-gray-200 rounded-lg shadow-xl z-50 p-3">
                  <h4 className="text-xs font-semibold text-gray-700 mb-2">Keyboard Shortcuts</h4>
                  <div className="space-y-1.5 text-[11px]">
                    {[
                      ['Ctrl+B', 'Bold'],
                      ['Ctrl+I', 'Italic'],
                      ['Ctrl+U', 'Underline'],
                      ['Ctrl+Z', 'Undo'],
                      ['Ctrl+Shift+Z', 'Redo'],
                      ['Enter', 'Send message'],
                      ['Shift+Enter', 'New line in chat'],
                    ].map(([key, desc]) => (
                      <div key={key} className="flex justify-between">
                        <span className="text-gray-500">{desc}</span>
                        <kbd className="px-1.5 py-0.5 bg-gray-100 rounded text-[10px] font-mono text-gray-600 border border-gray-200">{key}</kbd>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        <main className="flex-1 overflow-auto min-w-0 bg-white">{editor}</main>

        <div
          onMouseDown={handleMouseDown}
          title="Drag to resize"
          className={`w-1 cursor-col-resize hover:w-1.5 hover:bg-blue-400/50 transition-all shrink-0 ${
            isResizing ? 'w-1.5 bg-blue-400/50' : 'bg-gray-200'
          }`}
        />

        <aside
          style={{ width: sidebarWidth }}
          className="bg-gray-50 border-l border-gray-200 overflow-hidden flex flex-col shrink-0"
        >
          {sidebar}
        </aside>
      </div>

      {isResizing && <div className="fixed inset-0 z-50 cursor-col-resize" />}
    </div>
  );
}
