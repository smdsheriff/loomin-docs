import { ChevronDown, Cpu, Loader2 } from 'lucide-react';
import type { OllamaModel } from '@/types';

interface ModelSelectorProps {
  models: OllamaModel[];
  selectedModel: string;
  onModelChange: (model: string) => void;
}

function formatSize(bytes: number): string {
  if (!bytes || bytes === 0) return '';
  const gb = bytes / (1024 * 1024 * 1024);
  if (gb >= 1) return `${gb.toFixed(1)} GB`;
  const mb = bytes / (1024 * 1024);
  return `${mb.toFixed(0)} MB`;
}

export default function ModelSelector({
  models,
  selectedModel,
  onModelChange,
}: ModelSelectorProps) {
  const isLoading = models.length === 0;
  const currentModel = models.find((m) => m.name === selectedModel);

  return (
    <div>
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-gray-100 flex items-center justify-center shrink-0">
          <Cpu size={12} className="text-gray-500" />
        </div>
        <div className="relative flex-1">
          {isLoading ? (
            <div className="flex items-center gap-2 px-2.5 py-1.5 text-xs text-gray-400">
              <Loader2 size={12} className="animate-spin" />
              <span>Loading models...</span>
            </div>
          ) : (
            <>
              <select
                value={selectedModel}
                onChange={(e) => onModelChange(e.target.value)}
                className="w-full appearance-none bg-white text-gray-800 text-xs font-medium px-2.5 py-1.5 pr-7 rounded-lg border border-gray-200 outline-none focus:border-blue-400 focus:ring-2 focus:ring-blue-50 transition-all cursor-pointer hover:border-gray-300"
              >
                {models.map((model) => {
                  const size = formatSize(model.size);
                  return (
                    <option key={model.name} value={model.name}>
                      {model.name}{size ? ` (${size})` : ''}
                    </option>
                  );
                })}
              </select>
              <ChevronDown
                size={12}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none"
              />
            </>
          )}
        </div>
      </div>
      {/* Model size indicator */}
      {currentModel && currentModel.size > 0 && (
        <div className="flex items-center gap-1.5 mt-1 pl-8">
          <div className="w-1.5 h-1.5 rounded-full bg-green-400" />
          <span className="text-[10px] text-gray-400">
            Active &middot; {formatSize(currentModel.size)}
          </span>
        </div>
      )}
    </div>
  );
}
