export interface Document {
  id: string;
  title: string;
  content: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: string;
  document_id: string;
  content: string;
  version_number: number;
  created_at: string;
}

export interface ActionTrace {
  model: string;
  tokens_generated: number;
  retrieval_time_ms: number;
  generation_time_ms: number;
  citations?: Citation[];
}

export interface PendingAction {
  type: 'summarize' | 'improve';
  resultText: string;
  trace?: ActionTrace;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata?: ResponseMetadata;
  pendingAction?: PendingAction;
  created_at: string;
}

export interface ResponseMetadata {
  request_id: string;
  retrieval_time_ms: number;
  generation_time_ms: number;
  total_time_ms: number;
  tokens_generated: number;
  tokens_per_second: number;
  model: string;
  chunks_retrieved: number;
  citations?: Citation[];
}

export interface Citation {
  source_file: string;
  chunk_index: number;
  text: string;
  score: number;
}

export interface UploadedFile {
  id: string;
  filename: string;
  file_type: string;
  chunk_count: number;
  is_active: boolean;
  created_at: string;
}

export interface FileChunkPreview {
  chunk_index: number;
  content: string;
}

export interface OllamaModel {
  name: string;
  size: number;
  modified_at: string;
}

export interface TokenInfo {
  tokens: number;
  percentage: number;
  context_window: number;
  doc_tokens: number;
  chunk_tokens: number;
  free_tokens: number;
}
