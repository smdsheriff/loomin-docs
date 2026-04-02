import type {
  Document,
  DocumentVersion,
  ChatMessage,
  FileChunkPreview,
  UploadedFile,
  OllamaModel,
  TokenInfo,
} from '@/types';

const BASE_URL = import.meta.env.VITE_API_URL || '';

class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const url = `${BASE_URL}${endpoint}`;
  const config: RequestInit = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    ...options,
  };

  const response = await fetch(url, config);

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.message || message;
    } catch {
      // Use default message
    }
    throw new ApiError(message, response.status);
  }

  return response.json();
}

// ─── Documents ───────────────────────────────────────────────────────

export async function getDocuments(): Promise<Document[]> {
  return request<Document[]>('/api/documents');
}

export async function getDocument(id: string): Promise<Document> {
  return request<Document>(`/api/documents/${id}`);
}

export async function createDocument(
  title: string,
  content: string = ''
): Promise<Document> {
  return request<Document>('/api/documents', {
    method: 'POST',
    body: JSON.stringify({ title, content }),
  });
}

export async function updateDocument(
  id: string,
  data: Partial<Pick<Document, 'title' | 'content'>>
): Promise<Document> {
  return request<Document>(`/api/documents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function getDocumentVersions(
  id: string
): Promise<DocumentVersion[]> {
  return request<DocumentVersion[]>(`/api/documents/${id}/versions`);
}

// ─── Chat (Streaming SSE) ───────────────────────────────────────────

export async function sendMessage(
  message: string,
  documentId?: string,
  model?: string,
  documentContent?: string
): Promise<ReadableStream<Uint8Array>> {
  const url = `${BASE_URL}/api/chat`;
  const body: Record<string, unknown> = { message };
  if (documentId) body.document_id = documentId;
  if (model) body.model = model;
  if (documentContent) body.document_content = documentContent;

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    let message = `Chat request failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.message || message;
    } catch {
      // Use default
    }
    throw new ApiError(message, response.status);
  }

  if (!response.body) {
    throw new Error('Response body is null — streaming not supported');
  }

  return response.body;
}

export interface StreamEvent {
  event: string;
  data: string;
}

export function parseSSEStream(
  stream: ReadableStream<Uint8Array>,
  onEvent: (event: StreamEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void
): () => void {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let cancelled = false;

  async function read() {
    try {
      while (true) {
        if (cancelled) break;
        const { done, value } = await reader.read();
        if (done) {
          onDone();
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = 'message';
        for (const line of lines) {
          if (line.startsWith('event:')) {
            currentEvent = line.slice(6).trim();
          } else if (line.startsWith('data:')) {
            const data = line.slice(5).trim();
            onEvent({ event: currentEvent, data });
            currentEvent = 'message';
          } else if (line.trim() === '') {
            currentEvent = 'message';
          }
        }
      }
    } catch (err) {
      if (!cancelled) {
        onError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  }

  read();

  return () => {
    cancelled = true;
    reader.cancel().catch(() => {});
  };
}

// ─── Text Operations (direct JSON endpoints, not streaming) ─────────

export interface SummarizeResult {
  summary: string;
  model: string;
  trace: Record<string, unknown>;
}

export interface ImproveResult {
  improved_text: string;
  model: string;
  trace: Record<string, unknown>;
}

export async function summarizeText(
  text: string,
  model?: string
): Promise<SummarizeResult> {
  const body: Record<string, unknown> = { text };
  if (model) body.model = model;
  return request<SummarizeResult>('/api/chat/summarize', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function improveText(
  text: string,
  instruction?: string,
  model?: string
): Promise<ImproveResult> {
  const body: Record<string, unknown> = { text };
  if (instruction) body.instruction = instruction;
  if (model) body.model = model;
  return request<ImproveResult>('/api/chat/improve', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ─── Persist individual message (for system/action messages) ────────

export async function persistMessage(
  role: string,
  content: string,
  documentId?: string,
  metadataJson?: string
): Promise<void> {
  const body: Record<string, unknown> = { role, content };
  if (documentId) body.document_id = documentId;
  if (metadataJson) body.metadata_json = metadataJson;
  await request<unknown>('/api/chat/message', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ─── Files ──────────────────────────────────────────────────────────

export async function uploadFile(file: File): Promise<UploadedFile> {
  const url = `${BASE_URL}/api/files/upload`;
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(url, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    let message = `Upload failed with status ${response.status}`;
    try {
      const errorData = await response.json();
      message = errorData.detail || errorData.message || message;
    } catch {
      // Use default
    }
    throw new ApiError(message, response.status);
  }

  return response.json();
}

export async function getFiles(): Promise<UploadedFile[]> {
  return request<UploadedFile[]>('/api/files');
}

export async function toggleFile(id: string, isActive: boolean): Promise<UploadedFile> {
  return request<UploadedFile>(`/api/files/${id}/toggle`, {
    method: 'PATCH',
    body: JSON.stringify({ is_active: isActive }),
  });
}

export async function getFileChunks(id: string): Promise<FileChunkPreview[]> {
  return request<FileChunkPreview[]>(`/api/files/${id}/chunks`);
}

export async function deleteFile(id: string): Promise<void> {
  await request<void>(`/api/files/${id}`, { method: 'DELETE' });
}

// ─── Models ─────────────────────────────────────────────────────────

export async function getModels(): Promise<OllamaModel[]> {
  const data = await request<{ models: OllamaModel[] }>('/api/models');
  return data.models || [];
}

// ─── Tokens ─────────────────────────────────────────────────────────

export async function getTokenCount(
  text: string,
  model?: string,
  activeFileIds?: string[]
): Promise<TokenInfo> {
  const body: Record<string, unknown> = { text };
  if (model) body.model = model;
  if (activeFileIds && activeFileIds.length > 0) body.active_file_ids = activeFileIds;
  return request<TokenInfo>('/api/tokens/count', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// ─── Chat History ───────────────────────────────────────────────────

interface RawChatMessage {
  id: number;
  document_id?: string;
  role: string;
  content: string;
  metadata_json?: string | null;
  created_at: string;
}

export async function getChatHistory(
  documentId?: string
): Promise<ChatMessage[]> {
  const params = documentId ? `?document_id=${documentId}` : '';
  const raw = await request<RawChatMessage[]>(`/api/chat/history${params}`);
  return raw.map((msg) => {
    let metadata: ChatMessage['metadata'] | undefined;
    if (msg.metadata_json) {
      try {
        metadata = JSON.parse(msg.metadata_json);
      } catch {
        // Corrupt metadata — skip
      }
    }
    return {
      id: String(msg.id),
      role: msg.role as 'user' | 'assistant',
      content: msg.content,
      metadata,
      created_at: msg.created_at,
    };
  });
}
