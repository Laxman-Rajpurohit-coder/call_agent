import React from 'react';
import { PhoneCall, ShieldCheck, Layers, Bot, User, PhoneForwarded, PhoneOff, Activity, Clock } from 'lucide-react';
import { CallSession } from '../../types';

interface CallDetailsProps {
  call: CallSession | null;
  durationText: string;
  isHangingUp: boolean;
  onHangup: (callId: string) => void;
}

export const CallDetails: React.FC<CallDetailsProps> = ({
  call,
  durationText,
  isHangingUp,
  onHangup
}) => {
  if (!call) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-6 text-center text-slate-500 text-xs">
        <Activity className="w-8 h-8 opacity-40 mb-2" />
        <p>No call selected for inspection.</p>
        <p className="text-[10px] opacity-70 mt-1">Select an active call card to view telemetry metadata.</p>
      </div>
    );
  }

  const isHuman = call.handler?.type === 'HUMAN';
  const isTransfer = call.handler?.type === 'TRANSFERRING';

  return (
    <div className="p-4 space-y-4 text-xs font-sans text-slate-300">
      {/* Header Info */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-3">
        <div>
          <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider block">
            Session ID
          </span>
          <span className="font-mono font-bold text-slate-200">
            {call.id}
          </span>
        </div>
        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 uppercase">
          {call.status}
        </span>
      </div>

      {/* Handler Box */}
      <div className={`p-3 rounded-xl border ${
        isHuman 
          ? 'bg-sky-500/10 border-sky-500/30' 
          : isTransfer
          ? 'bg-amber-500/10 border-amber-500/30'
          : 'bg-purple-500/10 border-purple-500/30'
      }`}>
        <div className="flex items-center space-x-2 mb-1">
          {isHuman ? (
            <User className="w-4 h-4 text-sky-400" />
          ) : isTransfer ? (
            <PhoneForwarded className="w-4 h-4 text-amber-400 animate-pulse" />
          ) : (
            <Bot className="w-4 h-4 text-purple-400" />
          )}
          <span className="font-bold text-slate-100">
            {call.handler?.name || (isHuman ? 'Human Operator' : 'Superfone AI')}
          </span>
        </div>
        <p className="text-[10px] text-slate-400">
          Role: {call.handler?.role || 'Autonomous Voice Agent'}
        </p>
      </div>

      {/* Telephony Specs Grid */}
      <div className="space-y-2 font-mono text-[11px]">
        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800">
          <span className="text-slate-500">Destination:</span>
          <span className="text-slate-200 font-semibold">{call.to_number}</span>
        </div>

        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800">
          <span className="text-slate-500">Caller ID:</span>
          <span className="text-slate-200 font-semibold">{call.from_number}</span>
        </div>

        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800">
          <span className="text-slate-500">RTP Codec:</span>
          <span className="text-emerald-400 font-semibold">G.711 PCMU (8 kHz)</span>
        </div>

        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800">
          <span className="text-slate-500">RTP Media State:</span>
          <span className="text-emerald-400 font-semibold">{call.media?.rtp || 'RECEIVING'}</span>
        </div>

        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800">
          <span className="text-slate-500">VAD State:</span>
          <span className="text-brand-400 font-semibold">{call.vad_state || 'LISTENING'}</span>
        </div>

        <div className="flex items-center justify-between p-2 rounded-lg bg-slate-950/60 border border-slate-800">
          <span className="text-slate-500">Elapsed Duration:</span>
          <span className="text-amber-400 font-semibold">{durationText}</span>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="pt-2 border-t border-slate-800">
        <button
          onClick={() => onHangup(call.id)}
          disabled={isHangingUp}
          className="w-full flex items-center justify-center space-x-2 py-2 px-3 rounded-xl bg-rose-500 hover:bg-rose-600 text-white font-bold text-xs shadow-lg shadow-rose-500/20 transition-all disabled:opacity-50"
        >
          <PhoneOff className="w-4 h-4" />
          <span>{isHangingUp ? 'Terminating Call...' : 'Disconnect Call Now'}</span>
        </button>
      </div>
    </div>
  );
};
