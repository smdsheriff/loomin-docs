import { useState, useCallback, useEffect, useRef } from 'react';
import Layout from '@/components/Layout';
import Editor from '@/components/Editor/Editor';
import type { EditorHandle } from '@/components/Editor/Editor';
import Sidebar from '@/components/Sidebar/Sidebar';
import {
  useDocuments,
  useChat,
  useFiles,
  useModels,
  useTokenCount,
} from '@/hooks/useApi';
import * as api from '@/services/api';
import type { Document } from '@/types';

export default function App() {
  // ─── State ────────────────────────────────────────────────────────
  const [currentDocument, setCurrentDocument] = useState<Document | null>(null);
  const [editorContent, setEditorContent] = useState('');
  const [selectedText, setSelectedText] = useState('');
  const [selectedModel, setSelectedModel] = useState('');
  const [actionLoading, setActionLoading] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'saved' | 'saving' | 'unsaved'>('saved');
  const editorRef = useRef<EditorHandle>(null);
  const initialDocCreated = useRef(false);

  // Word count derived from editor content
  const wordCount = editorContent
    ? editorContent.replace(/<[^>]*>/g, ' ').split(/\s+/).filter(Boolean).length
    : 0;

  // ─── Hooks ────────────────────────────────────────────────────────
  const { documents, loading: docsLoading, createDocument, updateDocument } = useDocuments();
  const {
    messages,
    isStreaming,
    error: chatError,
    sendMessage,
    addSystemMessage,
    cancelStream,
  } = useChat(currentDocument?.id);
  const {
    files,
    loading: filesLoading,
    uploading: filesUploading,
    error: filesError,
    uploadFile,
    toggleFile,
    removeFile,
  } = useFiles();
  const { models } = useModels();

  // Derive active file IDs for token calculation (updates when files toggled)
  const activeFileIds = files.filter((f) => f.is_active).map((f) => f.id);
  const { tokenInfo, loading: tokenLoading } = useTokenCount(
    editorContent,
    selectedModel || undefined,
    activeFileIds
  );

  // ─── Initialize: load existing doc or create first one in DB ────
  // CRITICAL: Wait for the documents API to finish loading before deciding
  // whether to create a new document.  Without this guard, a new empty doc
  // is created before the existing one loads, permanently hiding the real data.
  useEffect(() => {
    if (currentDocument) return;     // Already initialized
    if (docsLoading) return;         // Still fetching from backend — wait

    if (documents.length > 0) {
      // Existing document found in DB — restore it
      setCurrentDocument(documents[0]);
      setEditorContent(documents[0].content || '');
    } else if (!initialDocCreated.current) {
      // DB is truly empty — create the first document
      initialDocCreated.current = true;
      createDocument('Untitled Document', '').then((doc) => {
        setCurrentDocument(doc);
        setEditorContent('');
      }).catch(() => {
        setCurrentDocument({
          id: 'local-draft',
          title: 'Untitled Document',
          content: '',
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        });
      });
    }
  }, [documents, docsLoading, currentDocument, createDocument]);

  // Auto-select default model (llama3.2:1b) or fall back to first available
  useEffect(() => {
    if (!selectedModel && models.length > 0) {
      const preferred = models.find((m) => m.name.startsWith('llama3.2'));
      setSelectedModel(preferred ? preferred.name : models[0].name);
    }
  }, [models, selectedModel]);

  // ─── Model switch handler ────────────────────────────────────────
  const handleModelChange = useCallback(
    (newModel: string) => {
      if (selectedModel && newModel !== selectedModel) {
        addSystemMessage(
          'assistant',
          `Switched to **${newModel}**. Conversation history is preserved — I still have context from our previous messages.`
        );
      }
      setSelectedModel(newModel);
    },
    [selectedModel, addSystemMessage]
  );

  // ─── Document handlers ──────────────────────────────────────────
  const handleTitleChange = useCallback(
    async (title: string) => {
      if (!currentDocument) return;

      setCurrentDocument((prev) => (prev ? { ...prev, title } : prev));

      if (currentDocument.id !== 'local-draft') {
        try {
          await updateDocument(currentDocument.id, { title });
        } catch {
          setCurrentDocument((prev) =>
            prev ? { ...prev, title: currentDocument.title } : prev
          );
        }
      }
    },
    [currentDocument, updateDocument]
  );

  const handleContentChange = useCallback(
    (content: string) => {
      setEditorContent(content);
      setSaveStatus('unsaved');

      if (currentDocument && currentDocument.id !== 'local-draft') {
        debouncedSave(currentDocument.id, content);
      }
    },
    [currentDocument]
  );

  // Simple debounced save
  const saveTimerRef = useCallback(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    return (id: string, content: string) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(async () => {
        setSaveStatus('saving');
        try {
          await updateDocument(id, { content });
          setSaveStatus('saved');
        } catch {
          setSaveStatus('unsaved');
        }
      }, 2000);
    };
  }, [updateDocument]);

  const [debouncedSave] = useState(() => saveTimerRef());

  // ─── Selection handlers ─────────────────────────────────────────
  const handleSelectionChange = useCallback((text: string) => {
    setSelectedText(text);
  }, []);

  // ─── Contextual editing: Summarize/Improve with confirmation ──────
  const handleSummarize = useCallback(
    async (text: string) => {
      if (actionLoading) return;
      setActionLoading(true);

      addSystemMessage(
        'user',
        `Summarize: "${text.slice(0, 120)}${text.length > 120 ? '...' : ''}"`
      );

      // Show loading message in chat while AI processes
      addSystemMessage('assistant', 'Summarizing your selection...');

      try {
        const result = await api.summarizeText(text, selectedModel || undefined);
        const trace = result.trace as Record<string, unknown> | undefined;
        const citations = trace?.citations as Array<Record<string, unknown>> | undefined;
        // Replace the loading message content with the result via a new message
        addSystemMessage(
          'assistant',
          `**Suggested summary:**\n\n${result.summary}`,
          {
            type: 'summarize',
            resultText: result.summary,
            trace: trace ? {
              model: String(trace.model || selectedModel || ''),
              tokens_generated: Number(trace.tokens_generated || 0),
              retrieval_time_ms: Number(trace.retrieval_time_ms || 0),
              generation_time_ms: Number(trace.generation_time_ms || 0),
              citations: citations?.map((c) => ({
                source_file: String(c.source_file || ''),
                chunk_index: Number(c.chunk_index || 0),
                score: Number(c.score || 0),
                text: String(c.text || ''),
              })),
            } : undefined,
          }
        );
      } catch (err) {
        addSystemMessage(
          'assistant',
          `Failed to summarize: ${err instanceof Error ? err.message : 'Unknown error'}`
        );
      } finally {
        setActionLoading(false);
      }
    },
    [addSystemMessage, selectedModel, actionLoading]
  );

  const handleImprove = useCallback(
    async (text: string) => {
      if (actionLoading) return;
      setActionLoading(true);

      addSystemMessage(
        'user',
        `Improve: "${text.slice(0, 120)}${text.length > 120 ? '...' : ''}"`
      );

      // Show loading message in chat while AI processes
      addSystemMessage('assistant', 'Improving your selection...');

      try {
        const result = await api.improveText(text, undefined, selectedModel || undefined);
        const trace = result.trace as Record<string, unknown> | undefined;
        const citations = trace?.citations as Array<Record<string, unknown>> | undefined;
        addSystemMessage(
          'assistant',
          `**Suggested improvement:**\n\n${result.improved_text}`,
          {
            type: 'improve',
            resultText: result.improved_text,
            trace: trace ? {
              model: String(trace.model || selectedModel || ''),
              tokens_generated: Number(trace.tokens_generated || 0),
              retrieval_time_ms: Number(trace.retrieval_time_ms || 0),
              generation_time_ms: Number(trace.generation_time_ms || 0),
              citations: citations?.map((c) => ({
                source_file: String(c.source_file || ''),
                chunk_index: Number(c.chunk_index || 0),
                score: Number(c.score || 0),
                text: String(c.text || ''),
              })),
            } : undefined,
          }
        );
      } catch (err) {
        addSystemMessage(
          'assistant',
          `Failed to improve: ${err instanceof Error ? err.message : 'Unknown error'}`
        );
      } finally {
        setActionLoading(false);
      }
    },
    [addSystemMessage, selectedModel, actionLoading]
  );

  // Accept: replace the original selected text in editor
  const handleAcceptAction = useCallback(
    (_messageId: string, text: string) => {
      editorRef.current?.replaceSelection(text);
      addSystemMessage('assistant', 'Applied to document.');
    },
    [addSystemMessage]
  );

  // Reject: just clear the pending action
  const handleRejectAction = useCallback(
    (_messageId: string) => {
      addSystemMessage('assistant', 'Change discarded. Original text preserved.');
    },
    [addSystemMessage]
  );

  // ─── Version restore handler ────────────────────────────────────
  const handleRestoreVersion = useCallback(
    (content: string) => {
      if (!currentDocument || currentDocument.id === 'local-draft') return;
      // Update editor directly with restored HTML content
      editorRef.current?.setContent(content);
      setEditorContent(content);
      // Persist the restored version
      setSaveStatus('saving');
      updateDocument(currentDocument.id, { content }).then(() => {
        setSaveStatus('saved');
      }).catch(() => {
        setSaveStatus('unsaved');
      });
    },
    [currentDocument, updateDocument]
  );

  // ─── Chat handler ──────────────────────────────────────────────
  const handleSendMessage = useCallback(
    (content: string) => {
      sendMessage(content, selectedModel || undefined, editorContent || undefined);
    },
    [sendMessage, selectedModel, editorContent]
  );

  // ─── File handler ──────────────────────────────────────────────
  const handleUploadFile = useCallback(
    async (file: File) => {
      return uploadFile(file);
    },
    [uploadFile]
  );

  const handleToggleFile = useCallback(
    (id: string, isActive: boolean) => {
      toggleFile(id, isActive);
    },
    [toggleFile]
  );

  const handleDeleteFile = useCallback(
    (id: string) => {
      removeFile(id);
    },
    [removeFile]
  );

  // ─── Render ────────────────────────────────────────────────────
  return (
    <Layout
      title={currentDocument?.title || 'Untitled Document'}
      onTitleChange={handleTitleChange}
      wordCount={wordCount}
      saveStatus={saveStatus}
      editor={
        <Editor
          ref={editorRef}
          content={currentDocument?.content || ''}
          onContentChange={handleContentChange}
          onSelectionChange={handleSelectionChange}
          onSummarizeSelection={handleSummarize}
          onImproveSelection={handleImprove}
        />
      }
      sidebar={
        <Sidebar
          messages={messages}
          isStreaming={isStreaming || actionLoading}
          chatError={chatError}
          onSendMessage={handleSendMessage}
          onCancelStream={cancelStream}
          selectedText={selectedText}
          onSummarize={handleSummarize}
          onImprove={handleImprove}
          files={files}
          filesLoading={filesLoading}
          filesUploading={filesUploading}
          filesError={filesError}
          onUploadFile={handleUploadFile}
          onToggleFile={handleToggleFile}
          onDeleteFile={handleDeleteFile}
          models={models}
          selectedModel={selectedModel}
          onModelChange={handleModelChange}
          tokenInfo={tokenInfo}
          tokenLoading={tokenLoading}
          documentId={currentDocument?.id}
          onAcceptAction={handleAcceptAction}
          onRejectAction={handleRejectAction}
          onRestoreVersion={handleRestoreVersion}
        />
      }
    />
  );
}
