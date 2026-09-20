import React from 'react';
import { Bot, User, PhoneForwarded, PhoneOff, PhoneCall, Mic, Clock, AlertTriangle } from 'lucide-react';
import { CallSession } from '../../types';

interface CallCardProps {
  call: CallSession;
  isSelected: boolean;
  durationText: string;
  isHangingUp: boolean;
  onSelect: (callId: string) => void;
  onHangup: (callId: string, e: React.MouseEvent) => void;
}

export const CallCard: React.FC<CallCardProps> = ({
  call,
  isSelected,
  durationText,
  isHangingUp,
  onSelect,
  onHangup
}) => {
  const isHuman = call.handler?.type === 'HUMAN';
  const isTransfer = call.handler?.type === 'TRANSFERRING';
  const isRecovery = call.status === 'RECOVERY_PENDING';

  return (
    <div
      onClick={() => onSelect(call.id)}
      className={`cursor-pointer glass-card p-4 rounded-xl border transition-all space-y-3 shadow-md ${
        isSelected
          ? 'border-brand-500 bg-brand-500/10 ring-1 ring-brand-500/50'
          : isRecovery
          ? 'border-amber-500/60 bg-amber-500/5'
          : 'border-slate-700/50 hover:border-slate-600 bg-slate-900/40'
      }`}
    >
      {/* 1. Call Status Header & ID */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          {isRecovery ? (
            <>
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
              <span className="text-xs font-bold text-amber-400 uppercase">
                RECOVERY PENDING
              </span>
            </>
          ) : (
            <>
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
              <span className="text-xs font-bold text-emerald-400 uppercase">
                {call.status || 'CONNECTED'}
              </span>
            </>
          )}
        </div>
        <span className="text-[10px] font-mono text-slate-400">
          ID: {call.id.slice(0, 8)}
        </span>
      </div>

      {/* 2. Telephony Numbers & Direction */}
      <div className="flex items-center justify-between">
        <div className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
          <PhoneCall className="w-4 h-4 text-emerald-400" />
          <span>{call.to_number || call.from_number}</span>
        </div>
        <span className="text-[10px] px-2 py-0.5 rounded uppercase font-bold bg-slate-800 text-slate-300">
          {call.direction || 'Outbound'}
        </span>
      </div>

      {/* 3. Authoritative Handler Attribution Badge (Constraint 1) */}
      <div
        className={`p-2.5 rounded-xl border text-xs flex items-center justify-between ${
          isHuman
            ? 'bg-sky-500/10 border-sky-500/30 text-sky-300'
            : isTransfer
            ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
            : 'bg-purple-500/10 border-purple-500/30 text-purple-300'
        }`}
      >
        <div className="flex items-center space-x-2">
          {isHuman ? (
            <User className="w-4 h-4 text-sky-400" />
          ) : isTransfer ? (
            <PhoneForwarded className="w-4 h-4 text-amber-400 animate-pulse" />
          ) : (
            <Bot className="w-4 h-4 text-purple-400" />
          )}
          <div>
            <p className="font-bold leading-none">
              {call.handler?.name || (isHuman ? 'Human Agent' : 'Superfone AI')}
            </p>
            <p className="text-[10px] opacity-75 mt-0.5">
              {isHuman ? 'Human Operator' : isTransfer ? 'Transferring Call' : 'Autonomous AI Agent'}
            </p>
          </div>
        </div>

        <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded-full bg-black/30">
          {isHuman ? 'HUMAN' : isTransfer ? 'RINGING' : 'AI'}
        </span>
      </div>

      {/* 4. Media Health & VAD Indicator (Independent Dimension) */}
      <div className="bg-slate-950/60 p-2.5 rounded-lg border border-slate-800 flex items-center justify-between">
        <span className="text-[11px] font-mono text-emerald-400 font-semibold flex items-center space-x-1.5">
          <Mic className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
          <span>RTP {call.media?.rtp || 'RECEIVING'}</span>
        </span>
        <div className="flex items-center space-x-1 h-3.5">
          <span className="w-1 bg-emerald-400 h-2 animate-bounce rounded-full" style={{ animationDelay: '0ms' }}></span>
          <span className="w-1 bg-emerald-400 h-3.5 animate-bounce rounded-full" style={{ animationDelay: '150ms' }}></span>
          <span className="w-1 bg-emerald-400 h-2.5 animate-bounce rounded-full" style={{ animationDelay: '300ms' }}></span>
          <span className="w-1 bg-emerald-400 h-1 animate-bounce rounded-full" style={{ animationDelay: '450ms' }}></span>
        </div>
      </div>

      {/* 5. Monotonic 1s Live Duration & Instant Hang Up Button */}
      <div className="text-xs text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-2 font-mono">
        <div className="flex items-center space-x-1">
          <Clock className="w-3 h-3 text-slate-500" />
          <span>{durationText}</span>
        </div>

        <button
          onClick={(e) => onHangup(call.id, e)}
          disabled={isHangingUp}
          className="flex items-center space-x-1 px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/30 text-[11px] font-bold transition-all disabled:opacity-50"
          title="Instantly hang up and terminate this softphone call"
        >
          <PhoneOff className="w-3 h-3" />
          <span>{isHangingUp ? 'Ending...' : 'Hang Up'}</span>
        </button>
      </div>
    </div>
  );
};
