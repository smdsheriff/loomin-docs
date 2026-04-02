import { useState, useEffect, useCallback } from 'react';
import { History, RotateCcw, Eye, Loader2, Clock } from 'lucide-react';
import type { DocumentVersion } from '@/types';
import * as api from '@/services/api';

interface VersionPanelProps {
  documentId?: string;
  onRestore: (content: string) => void;
}

export default function VersionPanel({ documentId, onRestore }: VersionPanelProps) {
  const [versions, setVersions] = useState<DocumentVersion[]>([]);
  const [loading, setLoading] = useState(false);
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [previewContent, setPreviewContent] = useState<string | null>(null);

  const fetchVersions = useCallback(async () => {
    if (!documentId) return;
    setLoading(true);
    try {
      const result = await api.getDocumentVersions(documentId);
      setVersions(result);
    } catch {
      setVersions([]);
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  const handlePreview = (version: DocumentVersion) => {
    if (previewId === version.id) {
      setPreviewId(null);
      setPreviewContent(null);
    } else {
      setPreviewId(version.id);
      // Strip HTML tags for preview
      const plain = version.content.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
      setPreviewContent(plain);
    }
  };

  const handleRestore = (version: DocumentVersion) => {
    onRestore(version.content);
    setPreviewId(null);
    setPreviewContent(null);
  };

  const parseDate = (dateStr: string) => {
    // Backend returns UTC but SQLite may strip timezone — ensure it's parsed as UTC
    const s = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z';
    return new Date(s);
  };

  const formatDate = (dateStr: string) => {
    const d = parseDate(dateStr);
    return d.toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };

  const timeAgo = (dateStr: string) => {
    const now = Date.now();
    const then = parseDate(dateStr).getTime();
    const diffMs = now - then;
    const mins = Math.floor(diffMs / 60000);
    if (mins < 1) return 'Just now';
    if (mins < 60) return `${mins}m ago`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 pt-3 pb-2 shrink-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History size={14} className="text-gray-500" />
            <span className="text-xs font-semibold text-gray-700">Version History</span>
          </div>
          <button
            onClick={fetchVersions}
            className="text-[10px] text-blue-600 hover:underline"
            title="Refresh"
          >
            Refresh
          </button>
        </div>
        <p className="text-[10px] text-gray-400 mt-1">
          {versions.length} version{versions.length !== 1 ? 's' : ''} saved
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-2">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="text-gray-400 animate-spin" />
          </div>
        )}

        {!loading && versions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <History size={28} className="text-gray-300 mb-3" />
            <p className="text-xs font-medium text-gray-500">No versions yet</p>
            <p className="text-[10px] text-gray-400 mt-1">Versions are created on every save</p>
          </div>
        )}

        {versions.map((v, i) => (
          <div key={v.id} className="rounded-xl bg-white border border-gray-200 overflow-hidden">
            <div className="flex items-center gap-2 p-2.5">
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 text-[10px] font-bold ${
                i === 0 ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-500'
              }`}>
                v{v.version_number}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold text-gray-700">
                    Version {v.version_number}
                  </span>
                  {i === 0 && (
                    <span className="px-1.5 py-0.5 text-[8px] font-bold bg-green-50 text-green-600 border border-green-200 rounded">
                      CURRENT
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 mt-0.5">
                  <Clock size={9} className="text-gray-400" />
                  <span className="text-[10px] text-gray-400">{formatDate(v.created_at)}</span>
                  <span className="text-[10px] text-gray-300">·</span>
                  <span className="text-[10px] text-gray-400">{timeAgo(v.created_at)}</span>
                </div>
              </div>
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => handlePreview(v)}
                  className={`p-1.5 rounded-md transition-colors ${
                    previewId === v.id
                      ? 'bg-blue-100 text-blue-600'
                      : 'text-gray-400 hover:text-blue-600 hover:bg-blue-50'
                  }`}
                  title="Preview content"
                >
                  <Eye size={12} />
                </button>
                {i > 0 && (
                  <button
                    onClick={() => handleRestore(v)}
                    className="p-1.5 rounded-md text-gray-400 hover:text-amber-600 hover:bg-amber-50 transition-colors"
                    title="Restore this version"
                  >
                    <RotateCcw size={12} />
                  </button>
                )}
              </div>
            </div>

            {/* Preview panel */}
            {previewId === v.id && previewContent !== null && (
              <div className="px-2.5 pb-2.5">
                <div className="max-h-32 overflow-y-auto rounded-lg bg-gray-50 border border-gray-100 p-2 text-[10px] text-gray-600 leading-relaxed">
                  {previewContent.length > 500
                    ? previewContent.slice(0, 500) + '...'
                    : previewContent || '(empty)'}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
