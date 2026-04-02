import { useState } from 'react';
import { MessageSquare, FolderOpen, History } from 'lucide-react';
import ChatPanel from './ChatPanel';
import FilesPanel from './FilesPanel';
import VersionPanel from './VersionPanel';
import ModelSelector from './ModelSelector';
import TokenBar from '@/components/TokenVisualization/TokenBar';
import type { ChatMessage, UploadedFile, OllamaModel, TokenInfo } from '@/types';

type Tab = 'chat' | 'files' | 'history';

interface SidebarProps {
  messages: ChatMessage[];
  isStreaming: boolean;
  chatError: string | null;
  onSendMessage: (content: string) => void;
  onCancelStream: () => void;
  selectedText: string;
  onSummarize: (text: string) => void;
  onImprove: (text: string) => void;
  files: UploadedFile[];
  filesLoading: boolean;
  filesUploading: boolean;
  filesError: string | null;
  onUploadFile: (file: File) => Promise<UploadedFile>;
  onToggleFile: (id: string, isActive: boolean) => void;
  onDeleteFile: (id: string) => void;
  models: OllamaModel[];
  selectedModel: string;
  onModelChange: (model: string) => void;
  tokenInfo: TokenInfo | null;
  tokenLoading: boolean;
  documentId?: string;
  onCitationClick?: (sourceFile: string, chunkIndex: number) => void;
  onAcceptAction?: (messageId: string, text: string) => void;
  onRejectAction?: (messageId: string) => void;
  onRestoreVersion?: (content: string) => void;
}

export default function Sidebar({
  messages,
  isStreaming,
  chatError,
  onSendMessage,
  onCancelStream,
  selectedText,
  onSummarize,
  onImprove,
  files,
  filesLoading,
  filesUploading,
  filesError,
  onUploadFile,
  onToggleFile,
  onDeleteFile,
  models,
  selectedModel,
  onModelChange,
  tokenInfo,
  tokenLoading,
  documentId,
  onCitationClick,
  onAcceptAction,
  onRejectAction,
  onRestoreVersion,
}: SidebarProps) {
  const [activeTab, setActiveTab] = useState<Tab>('chat');
  const [highlightedFile, setHighlightedFile] = useState<string | null>(null);

  const handleCitationClick = (sourceFile: string, chunkIndex: number) => {
    setHighlightedFile(sourceFile);
    setActiveTab('files');
    onCitationClick?.(sourceFile, chunkIndex);
    setTimeout(() => setHighlightedFile(null), 5000);
  };

  return (
    <div className="flex flex-col h-full bg-gray-50">
      {/* Model selector header */}
      <div className="px-3 py-2.5 bg-white border-b border-gray-200">
        <ModelSelector
          models={models}
          selectedModel={selectedModel}
          onModelChange={onModelChange}
        />
      </div>

      {/* Tab bar */}
      <div className="flex bg-white border-b border-gray-200 px-1">
        <TabButton
          active={activeTab === 'chat'}
          onClick={() => setActiveTab('chat')}
          icon={<MessageSquare size={14} />}
          label="Chat"
        />
        <TabButton
          active={activeTab === 'files'}
          onClick={() => setActiveTab('files')}
          icon={<FolderOpen size={14} />}
          label="Files"
          badge={files.length > 0 ? files.length : undefined}
        />
        <TabButton
          active={activeTab === 'history'}
          onClick={() => setActiveTab('history')}
          icon={<History size={14} />}
          label="History"
        />
      </div>

      {/* Tab content — both mounted for state preservation */}
      <div className="flex-1 overflow-hidden relative">
        <div className={`absolute inset-0 flex flex-col ${activeTab === 'chat' ? '' : 'invisible pointer-events-none'}`}>
          <ChatPanel
            messages={messages}
            isStreaming={isStreaming}
            error={chatError}
            onSendMessage={onSendMessage}
            onCancelStream={onCancelStream}
            selectedText={selectedText}
            onSummarize={onSummarize}
            onImprove={onImprove}
            onCitationClick={handleCitationClick}
            onAcceptAction={onAcceptAction}
            onRejectAction={onRejectAction}
          />
        </div>
        <div className={`absolute inset-0 flex flex-col ${activeTab === 'files' ? '' : 'invisible pointer-events-none'}`}>
          <FilesPanel
            files={files}
            loading={filesLoading}
            uploading={filesUploading}
            error={filesError}
            onUpload={onUploadFile}
            onToggle={onToggleFile}
            onDelete={onDeleteFile}
            highlightedFile={highlightedFile}
          />
        </div>
        <div className={`absolute inset-0 flex flex-col ${activeTab === 'history' ? '' : 'invisible pointer-events-none'}`}>
          <VersionPanel
            documentId={documentId}
            onRestore={(content) => onRestoreVersion?.(content)}
          />
        </div>
      </div>

      {/* Token bar footer */}
      <TokenBar tokenInfo={tokenInfo} loading={tokenLoading} />
    </div>
  );
}

function TabButton({ active, onClick, icon, label, badge }: {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
  badge?: number;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-1.5 px-3.5 py-2 text-xs font-medium transition-all relative ${
        active
          ? 'text-blue-700'
          : 'text-gray-500 hover:text-gray-700'
      }`}
    >
      {icon}
      {label}
      {badge !== undefined && (
        <span className={`ml-1 min-w-[18px] h-[18px] flex items-center justify-center text-[10px] font-bold rounded-full ${
          active ? 'bg-blue-100 text-blue-700' : 'bg-gray-200 text-gray-600'
        }`}>
          {badge}
        </span>
      )}
      {active && (
        <div className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full bg-blue-600" />
      )}
    </button>
  );
}
