import { useState, useEffect, useCallback, useRef } from 'react';
import type {
  Document,
  ChatMessage,
  ResponseMetadata,
  UploadedFile,
  OllamaModel,
  TokenInfo,
} from '@/types';
import * as api from '@/services/api';

// ─── useDocuments ────────────────────────────────────────────────────

export function useDocuments() {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const docs = await api.getDocuments();
      setDocuments(Array.isArray(docs) ? docs : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch documents');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const createDocument = useCallback(
    async (title: string, content: string = '') => {
      const doc = await api.createDocument(title, content);
      setDocuments((prev) => [doc, ...prev]);
      return doc;
    },
    []
  );

  const updateDocument = useCallback(
    async (id: string, data: Partial<Pick<Document, 'title' | 'content'>>) => {
      const updated = await api.updateDocument(id, data);
      setDocuments((prev) =>
        prev.map((d) => (d.id === id ? updated : d))
      );
      return updated;
    },
    []
  );

  return {
    documents,
    loading,
    error,
    fetchDocuments,
    createDocument,
    updateDocument,
  };
}

// ─── useChat ─────────────────────────────────────────────────────────

export function useChat(documentId?: string) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cancelRef = useRef<(() => void) | null>(null);

  const loadHistory = useCallback(async () => {
    if (!documentId) return; // Wait until document is loaded from DB
    try {
      const history = await api.getChatHistory(documentId);
      if (history.length > 0) {
        setMessages(history);
      }
    } catch {
      // History may not be available; that's fine
    }
  }, [documentId]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const sendMessage = useCallback(
    async (content: string, model?: string, documentContent?: string) => {
      const userMessage: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content,
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsStreaming(true);
      setError(null);

      const assistantId = crypto.randomUUID();
      const assistantMessage: ChatMessage = {
        id: assistantId,
        role: 'assistant',
        content: '',
        created_at: new Date().toISOString(),
      };

      setMessages((prev) => [...prev, assistantMessage]);

      try {
        const stream = await api.sendMessage(content, documentId, model, documentContent);
        let fullContent = '';
        let metadata: ResponseMetadata | undefined;

        const cancel = api.parseSSEStream(
          stream,
          (event) => {
            try {
              const parsed = JSON.parse(event.data);

              // Final metadata event: {done: true, metadata: {...}}
              if (parsed.done && parsed.metadata) {
                metadata = parsed.metadata as ResponseMetadata;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, metadata }
                      : m
                  )
                );
                return;
              }

              // Streaming token event: {token: "..."} or {content: "..."}
              const token = parsed.token || parsed.content || '';
              if (token) {
                fullContent += token;
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === assistantId
                      ? { ...m, content: fullContent }
                      : m
                  )
                );
              }
            } catch {
              // Plain text token (not JSON)
              fullContent += event.data;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, content: fullContent }
                    : m
                )
              );
            }

            if (event.event === 'error') {
              setError(event.data);
            }
          },
          () => {
            setIsStreaming(false);
          },
          (err) => {
            setError(err.message);
            setIsStreaming(false);
          }
        );

        cancelRef.current = cancel;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to send message');
        setIsStreaming(false);
        // Remove the empty assistant message on error
        setMessages((prev) => prev.filter((m) => m.id !== assistantId));
      }
    },
    [documentId]
  );

  const addSystemMessage = useCallback(
    (role: 'user' | 'assistant', content: string, pendingAction?: ChatMessage['pendingAction']) => {
      const msg: ChatMessage = {
        id: crypto.randomUUID(),
        role,
        content,
        pendingAction,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, msg]);

      // Persist to SQLite so it survives page refresh
      // (fire-and-forget — don't block the UI)
      const metadataJson = pendingAction?.trace
        ? JSON.stringify({ action_type: pendingAction.type, ...pendingAction.trace })
        : undefined;
      api.persistMessage(role, content, documentId, metadataJson).catch(() => {
        // Non-critical — message is already shown in the UI
      });
    },
    [documentId]
  );

  const cancelStream = useCallback(() => {
    if (cancelRef.current) {
      cancelRef.current();
      cancelRef.current = null;
      setIsStreaming(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return {
    messages,
    isStreaming,
    error,
    sendMessage,
    addSystemMessage,
    cancelStream,
    clearMessages,
  };
}

// ─── useFiles ────────────────────────────────────────────────────────

export function useFiles() {
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getFiles();
      setFiles(Array.isArray(result) ? result : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch files');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  const uploadFile = useCallback(async (file: File) => {
    setUploading(true);
    setError(null);
    try {
      const uploaded = await api.uploadFile(file);
      setFiles((prev) => [uploaded, ...prev]);
      return uploaded;
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to upload file');
      throw err;
    } finally {
      setUploading(false);
    }
  }, []);

  const toggleFile = useCallback(async (id: string, isActive: boolean) => {
    setError(null);
    try {
      const updated = await api.toggleFile(id, isActive);
      setFiles((prev) => prev.map((f) => (f.id === id ? updated : f)));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle file');
    }
  }, []);

  const removeFile = useCallback(async (id: string) => {
    setError(null);
    try {
      await api.deleteFile(id);
      setFiles((prev) => prev.filter((f) => f.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete file');
    }
  }, []);

  return {
    files,
    loading,
    uploading,
    error,
    fetchFiles,
    uploadFile,
    toggleFile,
    removeFile,
  };
}

// ─── useModels ───────────────────────────────────────────────────────

export function useModels() {
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchModels = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await api.getModels();
      setModels(Array.isArray(result) ? result : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch models');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchModels();
  }, [fetchModels]);

  return { models, loading, error, fetchModels };
}

// ─── useTokenCount ───────────────────────────────────────────────────

export function useTokenCount(text: string, model?: string, activeFileIds?: string[]) {
  const [tokenInfo, setTokenInfo] = useState<TokenInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Serialize IDs to avoid reference-equality churn in useEffect
  const fileIdsKey = activeFileIds?.join(',') ?? '';

  useEffect(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    // Strip HTML tags to check if there's actual content (TipTap returns <p></p> for empty)
    const plainText = text.replace(/<[^>]*>/g, '').trim();
    if (!plainText && (!fileIdsKey)) {
      setTokenInfo(null);
      return;
    }

    timerRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const ids = fileIdsKey ? fileIdsKey.split(',') : undefined;
        const info = await api.getTokenCount(text, model, ids);
        setTokenInfo(info);
      } catch {
        // Token counting is non-critical; fail silently
        setTokenInfo(null);
      } finally {
        setLoading(false);
      }
    }, 300);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [text, model, fileIdsKey]);

  return { tokenInfo, loading };
}
