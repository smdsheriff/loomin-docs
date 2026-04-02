import { useState, useRef, useCallback, useEffect } from 'react';
import {
  Upload,
  FileText,
  FileType,
  Trash2,
  Loader2,
  AlertCircle,
  FolderOpen,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import type { UploadedFile, FileChunkPreview } from '@/types';
import * as api from '@/services/api';

interface FilesPanelProps {
  files: UploadedFile[];
  loading: boolean;
  uploading: boolean;
  error: string | null;
  onUpload: (file: File) => Promise<UploadedFile>;
  onDelete: (id: string) => void;
  onToggle: (id: string, isActive: boolean) => void;
  highlightedFile?: string | null;
}

const ACCEPTED_TYPES = ['.pdf', '.md', '.txt'];
const ACCEPTED_MIME = 'application/pdf,text/markdown,text/plain,.pdf,.md,.txt';

export default function FilesPanel({
  files,
  loading,
  uploading,
  error,
  onUpload,
  onDelete,
  onToggle,
  highlightedFile,
}: FilesPanelProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [expandedFileId, setExpandedFileId] = useState<string | null>(null);
  const [chunks, setChunks] = useState<FileChunkPreview[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const validateFile = (file: File): boolean => {
    const ext = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!ACCEPTED_TYPES.includes(ext)) {
      setUploadError(`Unsupported: ${ext}. Use ${ACCEPTED_TYPES.join(', ')}`);
      return false;
    }
    if (file.size > 50 * 1024 * 1024) {
      setUploadError('File too large. Max 50 MB.');
      return false;
    }
    return true;
  };

  const handleUpload = useCallback(
    async (file: File) => {
      setUploadError(null);
      setUploadSuccess(null);
      if (!validateFile(file)) return;
      try {
        const result = await onUpload(file);
        setUploadSuccess(`${result.filename} uploaded (${result.chunk_count} chunks)`);
        setTimeout(() => setUploadSuccess(null), 4000);
      } catch (err) {
        setUploadError(err instanceof Error ? err.message : 'Upload failed');
      }
    },
    [onUpload]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) handleUpload(file);
    },
    [handleUpload]
  );

  const handleToggleChunks = useCallback(async (fileId: string) => {
    if (expandedFileId === fileId) {
      setExpandedFileId(null);
      setChunks([]);
      return;
    }
    setExpandedFileId(fileId);
    setChunksLoading(true);
    try {
      const result = await api.getFileChunks(fileId);
      setChunks(result);
    } catch {
      setChunks([]);
    } finally {
      setChunksLoading(false);
    }
  }, [expandedFileId]);

  // Close chunks when file is deleted
  useEffect(() => {
    if (expandedFileId && !files.find((f) => f.id === expandedFileId)) {
      setExpandedFileId(null);
      setChunks([]);
    }
  }, [files, expandedFileId]);

  const formatDate = (dateStr: string) => {
    // Backend returns UTC but SQLite may strip timezone — ensure it's parsed as UTC
    const s = dateStr.endsWith('Z') || dateStr.includes('+') ? dateStr : dateStr + 'Z';
    return new Date(s).toLocaleString('en-US', {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  };

  const getTypeBadge = (fileType: string) => {
    const t = fileType.toLowerCase().replace('.', '');
    switch (t) {
      case 'pdf': return { bg: 'bg-red-50 text-red-700 border-red-200', icon: 'bg-red-100 text-red-600' };
      case 'md': case 'markdown': return { bg: 'bg-blue-50 text-blue-700 border-blue-200', icon: 'bg-blue-100 text-blue-600' };
      default: return { bg: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: 'bg-emerald-100 text-emerald-600' };
    }
  };

  const activeCount = files.filter((f) => f.is_active).length;

  return (
    <div className="flex flex-col h-full">
      {/* Upload zone */}
      <div className="px-3 pt-3 shrink-0">
        <div
          onDrop={handleDrop}
          onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
          onDragLeave={(e) => { e.preventDefault(); setIsDragOver(false); }}
          onClick={() => fileInputRef.current?.click()}
          className={`flex flex-col items-center justify-center p-5 rounded-xl border-2 border-dashed cursor-pointer transition-all ${
            isDragOver
              ? 'border-blue-400 bg-blue-50 scale-[1.01]'
              : 'border-gray-300 hover:border-blue-300 hover:bg-blue-50/50'
          }`}
        >
          {uploading ? (
            <Loader2 size={22} className="text-blue-600 animate-spin mb-2" />
          ) : (
            <Upload size={22} className={`mb-2 ${isDragOver ? 'text-blue-600' : 'text-gray-400'}`} />
          )}
          <p className="text-xs font-medium text-gray-700 mb-0.5">
            {uploading ? 'Processing file...' : 'Drop files or click to upload'}
          </p>
          <p className="text-[10px] text-gray-400">PDF, Markdown, or Text (max 50 MB)</p>
        </div>

        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_MIME}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleUpload(f); e.target.value = ''; }}
          className="hidden"
        />
      </div>

      {/* Active files indicator */}
      {files.length > 0 && (
        <div className="mx-3 mt-2 flex items-center justify-between text-[10px] text-gray-500 shrink-0">
          <span>{activeCount} of {files.length} files active for RAG</span>
        </div>
      )}

      {/* Feedback messages */}
      {uploadSuccess && (
        <div className="mx-3 mt-2 flex items-center gap-2 p-2 rounded-lg bg-green-50 border border-green-200 shrink-0">
          <CheckCircle2 size={13} className="text-green-600 shrink-0" />
          <p className="text-xs text-green-700">{uploadSuccess}</p>
        </div>
      )}

      {(error || uploadError) && (
        <div className="mx-3 mt-2 flex items-start gap-2 p-2 rounded-lg bg-red-50 border border-red-200 shrink-0">
          <AlertCircle size={13} className="text-red-500 mt-0.5 shrink-0" />
          <p className="text-xs text-red-600">{error || uploadError}</p>
          <button onClick={() => setUploadError(null)} className="ml-auto text-red-400 hover:text-red-600 shrink-0">
            <span className="text-xs">&times;</span>
          </button>
        </div>
      )}

      {/* File list */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-2">
        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 size={20} className="text-gray-400 animate-spin" />
          </div>
        )}

        {!loading && files.length === 0 && (
          <div className="flex flex-col items-center justify-center py-10 text-center">
            <FolderOpen size={28} className="text-gray-300 mb-3" />
            <p className="text-xs font-medium text-gray-500">No files uploaded</p>
            <p className="text-[10px] text-gray-400 mt-1 max-w-[180px]">
              Upload documents to provide context for the AI assistant
            </p>
          </div>
        )}

        {files.map((file) => {
          const colors = getTypeBadge(file.file_type);
          const isHighlighted = highlightedFile === file.filename;
          const isExpanded = expandedFileId === file.id;
          return (
            <div key={file.id}>
              <div
                className={`group flex items-start gap-2.5 p-2.5 rounded-xl bg-white border transition-all ${
                  isHighlighted
                    ? 'border-blue-400 ring-2 ring-blue-100 shadow-md animate-pulse'
                    : !file.is_active
                      ? 'border-gray-200 opacity-60'
                      : 'border-gray-200 hover:border-gray-300 hover:shadow-sm'
                }`}
              >
                {/* Toggle switch */}
                <button
                  onClick={() => onToggle(file.id, !file.is_active)}
                  className="mt-1 shrink-0"
                  title={file.is_active ? 'Disable file from RAG context' : 'Enable file for RAG context'}
                  aria-label={`Toggle ${file.filename} ${file.is_active ? 'off' : 'on'}`}
                >
                  <div className={`w-8 h-[18px] rounded-full transition-colors relative ${
                    file.is_active ? 'bg-green-500' : 'bg-gray-300'
                  }`}>
                    <div className={`absolute top-[2px] w-[14px] h-[14px] rounded-full bg-white shadow-sm transition-all ${
                      file.is_active ? 'left-[15px]' : 'left-[2px]'
                    }`} />
                  </div>
                </button>

                {/* File type icon */}
                <div className={`w-9 h-9 rounded-lg ${colors.icon} flex items-center justify-center shrink-0`}>
                  {file.file_type.toLowerCase().includes('md') ? (
                    <FileType size={16} />
                  ) : (
                    <FileText size={16} />
                  )}
                </div>

                {/* File info */}
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-gray-800 truncate">{file.filename}</p>
                  <div className="flex items-center gap-2 mt-1">
                    <span className={`px-1.5 py-0.5 text-[9px] font-bold rounded border ${colors.bg}`}>
                      {file.file_type.replace('.', '').toUpperCase()}
                    </span>
                    <button
                      onClick={() => handleToggleChunks(file.id)}
                      className="flex items-center gap-0.5 text-[10px] text-blue-600 hover:text-blue-700 hover:underline"
                      title="View chunks"
                    >
                      {file.chunk_count} chunks
                      {isExpanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
                    </button>
                    <span className="text-[10px] text-gray-400">{formatDate(file.created_at)}</span>
                  </div>
                </div>

                {/* Delete */}
                <button
                  onClick={() => onDelete(file.id)}
                  className="p-1.5 rounded-md text-gray-300 hover:text-red-500 hover:bg-red-50 opacity-0 group-hover:opacity-100 transition-all shrink-0"
                  title="Delete file"
                >
                  <Trash2 size={13} />
                </button>
              </div>

              {/* Chunk preview panel */}
              {isExpanded && (
                <div className="mt-1 ml-11 mr-2 max-h-48 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 divide-y divide-gray-100">
                  {chunksLoading ? (
                    <div className="flex items-center justify-center py-4">
                      <Loader2 size={14} className="text-gray-400 animate-spin" />
                    </div>
                  ) : chunks.length === 0 ? (
                    <p className="text-[10px] text-gray-400 p-2">No chunks available</p>
                  ) : (
                    chunks.map((chunk) => (
                      <div key={chunk.chunk_index} className="p-2">
                        <span className="text-[9px] font-bold text-gray-400 mr-1.5">#{chunk.chunk_index}</span>
                        <span className="text-[10px] text-gray-600 leading-relaxed">
                          {chunk.content.length > 200
                            ? chunk.content.slice(0, 200) + '...'
                            : chunk.content}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
