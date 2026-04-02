import { Activity } from 'lucide-react';
import type { TokenInfo } from '@/types';

interface TokenBarProps {
  tokenInfo: TokenInfo | null;
  loading: boolean;
}

function formatTokenCount(count: number): string {
  if (count >= 1000) {
    return `${(count / 1000).toFixed(1)}k`;
  }
  return count.toString();
}

function getOverallColor(percentage: number): string {
  if (percentage < 50) return 'text-emerald-600';
  if (percentage < 80) return 'text-amber-600';
  return 'text-red-600';
}

export default function TokenBar({ tokenInfo, loading }: TokenBarProps) {
  if (!tokenInfo && !loading) {
    return (
      <div className="px-3 py-2.5 border-t border-gray-200 bg-gray-50/50 shrink-0">
        <div className="flex items-center gap-2 text-[11px] text-gray-400">
          <Activity size={12} />
          <span>Start typing to see token usage</span>
        </div>
      </div>
    );
  }

  const percentage = tokenInfo?.percentage ?? 0;
  const tokens = tokenInfo?.tokens ?? 0;
  const contextWindow = tokenInfo?.context_window ?? 1;
  const docTokens = tokenInfo?.doc_tokens ?? 0;
  const chunkTokens = tokenInfo?.chunk_tokens ?? 0;

  const docPct = contextWindow > 0 ? (docTokens / contextWindow) * 100 : 0;
  const chunkPct = contextWindow > 0 ? (chunkTokens / contextWindow) * 100 : 0;
  const freePct = Math.max(0, 100 - docPct - chunkPct);

  return (
    <div className="px-3 py-2.5 border-t border-gray-200 bg-gray-50/50 shrink-0">
      {/* Header row */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-1.5">
          <Activity size={12} className="text-gray-400" />
          <span className="text-[11px] text-gray-500 font-medium">Context</span>
        </div>
        <span className={`text-[11px] font-semibold ${getOverallColor(percentage)}`}>
          {loading ? (
            <span className="text-gray-400 animate-pulse">Counting...</span>
          ) : (
            <>
              {formatTokenCount(tokens)} / {formatTokenCount(contextWindow)}{' '}
              ({percentage.toFixed(1)}%)
            </>
          )}
        </span>
      </div>

      {/* Segmented progress bar */}
      <div className="w-full h-2 rounded-full bg-gray-200 overflow-hidden flex">
        {docPct > 0 && (
          <div
            className="h-full bg-blue-500 transition-all duration-500 ease-out"
            style={{ width: `${Math.min(docPct, 100)}%` }}
            title={`Document: ${formatTokenCount(docTokens)} tokens`}
          />
        )}
        {chunkPct > 0 && (
          <div
            className="h-full bg-amber-500 transition-all duration-500 ease-out"
            style={{ width: `${Math.min(chunkPct, 100 - docPct)}%` }}
            title={`File chunks: ${formatTokenCount(chunkTokens)} tokens`}
          />
        )}
      </div>

      {/* Legend */}
      {!loading && (docTokens > 0 || chunkTokens > 0) && (
        <div className="flex items-center gap-3 mt-1.5 text-[10px] text-gray-500">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-blue-500 shrink-0" />
            <span>Doc {docPct.toFixed(0)}%</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-amber-500 shrink-0" />
            <span>Files {chunkPct.toFixed(0)}%</span>
          </div>
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm bg-gray-200 shrink-0" />
            <span>Free {freePct.toFixed(0)}%</span>
          </div>
        </div>
      )}
    </div>
  );
}
