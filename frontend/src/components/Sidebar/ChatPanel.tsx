import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Send,
  Square,
  User,
  Bot,
  Clock,
  Zap,
  FileText,
  ChevronDown,
  ChevronUp,
  Sparkles,
  AlertCircle,
  Check,
  X,
  Cpu,
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { ChatMessage, Citation, ActionTrace } from '@/types';

interface ChatPanelProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;
  onSendMessage: (content: string) => void;
  onCancelStream: () => void;
  selectedText: string;
  onSummarize: (text: string) => void;
  onImprove: (text: string) => void;
  onCitationClick?: (sourceFile: string, chunkIndex: number) => void;
  onAcceptAction?: (messageId: string, text: string) => void;
  onRejectAction?: (messageId: string) => void;
}

export default function ChatPanel({
  messages,
  isStreaming,
  error,
  onSendMessage,
  onCancelStream,
  selectedText,
  onSummarize,
  onImprove,
  onCitationClick,
  onAcceptAction,
  onRejectAction,
}: ChatPanelProps) {
  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [input]);

  const handleSend = useCallback(() => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;
    onSendMessage(trimmed);
    setInput('');
  }, [input, isStreaming, onSendMessage]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Selection action banner */}
      {selectedText && (
        <div className="px-3 py-2.5 bg-blue-50 border-b border-blue-100 shrink-0">
          <div className="flex items-start gap-2 mb-2">
            <FileText size={13} className="text-blue-600 mt-0.5 shrink-0" />
            <p className="text-xs text-blue-700 leading-relaxed line-clamp-2">
              <span className="font-medium">Selected:</span>{' '}
              <span className="text-blue-600/80">
                "{selectedText.length > 80 ? selectedText.slice(0, 80) + '...' : selectedText}"
              </span>
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => onSummarize(selectedText)}
              disabled={isStreaming}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:opacity-50 shadow-sm"
            >
              <FileText size={11} />
              Summarize
            </button>
            <button
              onClick={() => onImprove(selectedText)}
              disabled={isStreaming}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-purple-600 text-white hover:bg-purple-700 transition-colors disabled:opacity-50 shadow-sm"
            >
              <Sparkles size={11} />
              Improve
            </button>
          </div>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && <EmptyState />}

        {messages.map((msg) => (
          <MessageBubble
            key={msg.id}
            message={msg}
            onCitationClick={onCitationClick}
            onAcceptAction={onAcceptAction}
            onRejectAction={onRejectAction}
          />
        ))}

        {isStreaming &&
          messages.length > 0 &&
          messages[messages.length - 1].role === 'assistant' &&
          messages[messages.length - 1].content === '' && (
            <TypingIndicator />
          )}

        {error && (
          <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200">
            <AlertCircle size={14} className="text-red-500 mt-0.5 shrink-0" />
            <p className="text-xs text-red-600">{error}</p>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="px-3 py-3 border-t border-gray-200 bg-white shrink-0">
        <div className={`flex items-end gap-2 rounded-xl border transition-all ${
          isStreaming
            ? 'bg-gray-50 border-gray-200'
            : 'bg-white border-gray-300 focus-within:border-blue-400 focus-within:shadow-[0_0_0_3px_rgba(59,130,246,0.1)]'
        }`}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isStreaming ? 'Waiting for response...' : 'Ask about your document...'}
            disabled={isStreaming}
            rows={1}
            className="flex-1 bg-transparent text-gray-800 text-sm px-3.5 py-2.5 resize-none outline-none placeholder:text-gray-400 disabled:cursor-not-allowed disabled:text-gray-400"
          />
          {isStreaming ? (
            <button
              onClick={onCancelStream}
              className="p-2 mr-1 mb-1 rounded-lg text-red-500 hover:bg-red-50 transition-colors shrink-0"
              title="Stop generating"
            >
              <Square size={16} />
            </button>
          ) : (
            <button
              onClick={handleSend}
              disabled={!input.trim()}
              className="p-2 mr-1 mb-1 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed shrink-0"
              title="Send message"
            >
              <Send size={14} />
            </button>
          )}
        </div>
        <p className="text-[10px] text-gray-400 mt-1.5 px-1 text-center">
          {isStreaming ? 'AI is generating...' : 'Enter to send \u00B7 Shift+Enter for new line'}
        </p>
      </div>
    </div>
  );
}

// ─── Subcomponents ───────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-14 px-6 text-center">
      <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-50 to-indigo-100 border border-blue-100 flex items-center justify-center mb-4 shadow-sm">
        <Bot size={20} className="text-blue-600" />
      </div>
      <h3 className="text-sm font-semibold text-gray-800 mb-1.5">
        AI Document Assistant
      </h3>
      <p className="text-xs text-gray-500 leading-relaxed max-w-[220px] mb-5">
        Ask questions about your uploaded files, summarize content, or improve your writing.
      </p>
      <div className="flex flex-col gap-2.5 w-full max-w-[220px] text-left">
        {[
          ['Upload files in the Files tab', '1'],
          ['Ask a question below', '2'],
          ['Get answers grounded in your docs', '3'],
        ].map(([text, num]) => (
          <div key={num} className="flex items-center gap-2.5 text-[11px] text-gray-500">
            <span className="w-5 h-5 rounded-md bg-blue-50 flex items-center justify-center text-blue-600 font-semibold shrink-0 text-[10px]">{num}</span>
            {text}
          </div>
        ))}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-2.5 px-3 py-2">
      <div className="w-6 h-6 rounded-full bg-gray-100 flex items-center justify-center">
        <Bot size={12} className="text-gray-500" />
      </div>
      <div className="flex gap-1 items-center">
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]" />
      </div>
      <span className="text-xs text-gray-400">Thinking...</span>
    </div>
  );
}

function MessageBubble({ message, onCitationClick, onAcceptAction, onRejectAction }: {
  message: ChatMessage;
  onCitationClick?: (sourceFile: string, chunkIndex: number) => void;
  onAcceptAction?: (messageId: string, text: string) => void;
  onRejectAction?: (messageId: string) => void;
}) {
  const isUser = message.role === 'user';

  return (
    <div className={`flex gap-2 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
      {/* Avatar */}
      <div
        className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5 ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-gradient-to-br from-gray-100 to-gray-200 text-gray-600'
        }`}
      >
        {isUser ? <User size={13} /> : <Bot size={13} />}
      </div>

      {/* Content */}
      <div className={`flex flex-col min-w-0 max-w-[85%] ${isUser ? 'items-end' : 'items-start'}`}>
        <div
          className={`rounded-2xl px-3.5 py-2 text-[13px] leading-relaxed ${
            isUser
              ? 'bg-blue-600 text-white rounded-br-md'
              : message.pendingAction
                ? 'bg-amber-50 text-gray-800 border border-amber-200 rounded-bl-md'
                : 'bg-white text-gray-800 border border-gray-200 shadow-sm rounded-bl-md'
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap">{message.content}</p>
          ) : (
            <div className="prose prose-sm max-w-none text-[13px] [&_p]:mb-1.5 [&_p:last-child]:mb-0 [&_pre]:bg-gray-50 [&_pre]:border [&_pre]:border-gray-200 [&_pre]:rounded-lg [&_pre]:p-2.5 [&_code]:text-xs [&_ul]:pl-4 [&_ol]:pl-4 [&_li]:mb-0.5 [&_strong]:text-gray-900">
              <ReactMarkdown>{message.content || ' '}</ReactMarkdown>
              <InlineCitations text={message.content || ''} onCitationClick={onCitationClick} citations={message.metadata?.citations || message.pendingAction?.trace?.citations} />
            </div>
          )}
        </div>

        {/* Pending action: trace + accept/reject */}
        {message.pendingAction && (
          <div className="mt-2 space-y-2 w-full">
            {message.pendingAction.trace && (
              <ActionTraceBadge
                trace={message.pendingAction.trace}
                actionType={message.pendingAction.type}
                onCitationClick={onCitationClick}
              />
            )}
            <div className="flex items-center gap-2">
              <button
                onClick={() => onAcceptAction?.(message.id, message.pendingAction!.resultText)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-green-600 text-white hover:bg-green-700 transition-colors shadow-sm"
              >
                <Check size={12} />
                Apply to document
              </button>
              <button
                onClick={() => onRejectAction?.(message.id)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-white text-gray-600 border border-gray-300 hover:bg-gray-50 transition-colors"
              >
                <X size={12} />
                Discard
              </button>
            </div>
          </div>
        )}

        {/* Metadata badge for streamed chat responses */}
        {!isUser && message.metadata && (
          <MetadataBadge metadata={message.metadata} onCitationClick={onCitationClick} />
        )}
      </div>
    </div>
  );
}

function MetadataBadge({
  metadata,
  onCitationClick,
}: {
  metadata: NonNullable<ChatMessage['metadata']>;
  onCitationClick?: (sourceFile: string, chunkIndex: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="mt-1.5">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 text-[10px] text-gray-400 hover:text-gray-600 transition-colors"
      >
        <Zap size={10} />
        <span>{(metadata.tokens_per_second ?? 0).toFixed(1)} tok/s</span>
        <span className="text-gray-300">|</span>
        <Clock size={10} />
        <span>{(metadata.total_time_ms ?? 0).toFixed(0)}ms</span>
        {expanded ? <ChevronUp size={10} /> : <ChevronDown size={10} />}
      </button>

      {expanded && (
        <div className="mt-1.5 p-2.5 rounded-lg bg-white border border-gray-200 text-[10px] text-gray-500 space-y-1 shadow-sm">
          <div className="flex justify-between">
            <span>Model:</span>
            <span className="text-gray-700 font-medium">{metadata.model}</span>
          </div>
          <div className="flex justify-between">
            <span>Tokens:</span>
            <span className="text-gray-700">{metadata.tokens_generated}</span>
          </div>
          <div className="flex justify-between">
            <span>Retrieval:</span>
            <span className="text-gray-700">{(metadata.retrieval_time_ms ?? 0).toFixed(0)}ms</span>
          </div>
          <div className="flex justify-between">
            <span>Generation:</span>
            <span className="text-gray-700">{(metadata.generation_time_ms ?? 0).toFixed(0)}ms</span>
          </div>
          <div className="flex justify-between">
            <span>Chunks:</span>
            <span className="text-gray-700">{metadata.chunks_retrieved}</span>
          </div>

          {metadata.citations && metadata.citations.length > 0 && (
            <CitationsList citations={metadata.citations} onCitationClick={onCitationClick} />
          )}
        </div>
      )}
    </div>
  );
}

function CitationsList({ citations, onCitationClick }: { citations: Citation[]; onCitationClick?: (sourceFile: string, chunkIndex: number) => void }) {
  const [showAll, setShowAll] = useState(false);
  const displayed = showAll ? citations : citations.slice(0, 3);

  return (
    <div className="mt-2 pt-2 border-t border-gray-100">
      <p className="text-gray-500 font-medium mb-1.5">
        Sources ({citations.length})
      </p>
      {displayed.map((c, i) => (
        <button
          key={i}
          onClick={() => onCitationClick?.(c.source_file, c.chunk_index)}
          className="block w-full text-left p-2 rounded-md bg-gray-50 mb-1 last:mb-0 hover:bg-blue-50 hover:border-blue-200 border border-transparent transition-colors cursor-pointer"
          title={`View ${c.source_file} - chunk #${c.chunk_index}`}
        >
          <div className="flex items-center gap-1 mb-0.5">
            <FileText size={9} className="text-blue-600" />
            <span className="text-blue-600 font-medium truncate">{c.source_file}</span>
            <span className="text-gray-400 ml-auto text-[9px]">
              #{c.chunk_index} ({(c.score * 100).toFixed(0)}%)
            </span>
          </div>
          <p className="text-gray-500 line-clamp-2 leading-tight text-[10px]">
            {c.text}
          </p>
        </button>
      ))}
      {citations.length > 3 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="text-blue-600 hover:underline mt-1"
        >
          {showAll ? 'Show less' : `Show ${citations.length - 3} more`}
        </button>
      )}
    </div>
  );
}

function ActionTraceBadge({ trace, actionType, onCitationClick }: {
  trace: ActionTrace;
  actionType: 'summarize' | 'improve';
  onCitationClick?: (sourceFile: string, chunkIndex: number) => void;
}) {
  return (
    <div className="text-[10px] text-gray-500 bg-white rounded-lg px-2.5 py-1.5 border border-gray-200 shadow-sm space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span className={`font-semibold ${actionType === 'summarize' ? 'text-blue-600' : 'text-purple-600'}`}>
          {actionType === 'summarize' ? 'Summarized' : 'Improved'}
        </span>
        <span className="flex items-center gap-1">
          <Cpu size={10} className="text-gray-400" />
          {trace.model}
        </span>
        <span className="flex items-center gap-1">
          <Zap size={10} className="text-gray-400" />
          {trace.tokens_generated} tokens
        </span>
        <span className="flex items-center gap-1">
          <Clock size={10} className="text-gray-400" />
          {(trace.generation_time_ms / 1000).toFixed(1)}s
        </span>
      </div>

      {/* Inline citations from RAG-grounded rewrite */}
      {trace.citations && trace.citations.length > 0 && (
        <div className="pt-1.5 border-t border-gray-100">
          <p className="text-gray-500 font-medium mb-1">Grounded in {trace.citations.length} source{trace.citations.length > 1 ? 's' : ''}:</p>
          {trace.citations.map((c, i) => (
            <button
              key={i}
              onClick={() => onCitationClick?.(c.source_file, c.chunk_index)}
              className="block w-full text-left p-1.5 rounded bg-gray-50 mb-1 last:mb-0 hover:bg-blue-50 transition-colors"
            >
              <span className="flex items-center gap-1">
                <FileText size={9} className="text-blue-600" />
                <span className="text-blue-600 font-medium">[Source {i + 1}] {c.source_file}</span>
                <span className="text-gray-400 ml-auto text-[9px]">({(c.score * 100).toFixed(0)}%)</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Renders inline citation badges when [Source N] patterns are detected in AI output. */
function InlineCitations({ text, citations, onCitationClick }: {
  text: string;
  citations?: Citation[];
  onCitationClick?: (sourceFile: string, chunkIndex: number) => void;
}) {
  if (!citations || citations.length === 0) return null;
  const sourcePattern = /\[Source\s+(\d+)\]/g;
  const matches = [...text.matchAll(sourcePattern)];
  if (matches.length === 0) return null;

  const seen = new Set<number>();
  const refs: { num: number; citation: Citation }[] = [];
  for (const m of matches) {
    const num = parseInt(m[1], 10);
    if (!seen.has(num) && num >= 1 && num <= citations.length) {
      seen.add(num);
      refs.push({ num, citation: citations[num - 1] });
    }
  }
  if (refs.length === 0) return null;

  return (
    <div className="flex flex-wrap gap-1 mt-1.5 pt-1.5 border-t border-gray-100">
      {refs.map(({ num, citation: c }) => (
        <button
          key={num}
          onClick={() => onCitationClick?.(c.source_file, c.chunk_index)}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-blue-50 text-blue-700 text-[10px] font-medium hover:bg-blue-100 transition-colors border border-blue-200"
          title={`${c.source_file} — chunk #${c.chunk_index} (${(c.score * 100).toFixed(0)}% match)`}
        >
          <FileText size={8} />
          [Source {num}] {c.source_file}
        </button>
      ))}
    </div>
  );
}
