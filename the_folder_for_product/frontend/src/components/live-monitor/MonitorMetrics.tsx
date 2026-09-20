import React from 'react';
import { PhoneCall, Bot, User, Zap, Mic, Radio } from 'lucide-react';
import { ConnectionState } from '../../hooks/useLiveCallMonitor';

interface MonitorMetricsProps {
  activeCount: number;
  aiCount: number;
  humanCount: number;
  transferringCount: number;
  totalTurns: number;
  connectionState: ConnectionState;
}

export const MonitorMetrics: React.FC<MonitorMetricsProps> = ({
  activeCount,
  aiCount,
  humanCount,
  transferringCount,
  totalTurns,
  connectionState
}) => {
  return (
    <div className="grid grid-cols-2 md:grid-cols-6 gap-4">
      {/* 1. Active Calls */}
      <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
          <PhoneCall className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Active Calls</p>
          <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{activeCount}</p>
        </div>
      </div>

      {/* 2. AI Handled */}
      <div className="glass-card p-4 rounded-xl border border-purple-500/30 dark:border-purple-500/20 bg-purple-500/5 shadow flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
          <Bot className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs font-medium text-purple-400">AI Handled</p>
          <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{aiCount}</p>
        </div>
      </div>

      {/* 3. Human Handled */}
      <div className="glass-card p-4 rounded-xl border border-sky-500/30 dark:border-sky-500/20 bg-sky-500/5 shadow flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-400">
          <User className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs font-medium text-sky-400">Human Handled</p>
          <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{humanCount}</p>
        </div>
      </div>

      {/* 4. Transferring */}
      <div className="glass-card p-4 rounded-xl border border-amber-500/30 dark:border-amber-500/20 bg-amber-500/5 shadow flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
          <Zap className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs font-medium text-amber-400">Transferring</p>
          <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{transferringCount}</p>
        </div>
      </div>

      {/* 5. Transcribed Turns */}
      <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
        <div className="p-2.5 rounded-xl bg-brand-500/10 border border-brand-500/20 text-brand-400">
          <Mic className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Turns Logged</p>
          <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{totalTurns}</p>
        </div>
      </div>

      {/* 6. WebSocket Stream Status (Constraint 4) */}
      <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
        <div className={`p-2.5 rounded-xl border ${
          connectionState === 'connected'
            ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400'
            : connectionState === 'reconnecting' || connectionState === 'connecting'
            ? 'bg-amber-500/10 border-amber-500/20 text-amber-400 animate-pulse'
            : 'bg-rose-500/10 border-rose-500/20 text-rose-400'
        }`}>
          <Radio className="w-5 h-5" />
        </div>
        <div>
          <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Stream Status</p>
          <p className={`text-xs font-bold uppercase tracking-wider ${
            connectionState === 'connected'
              ? 'text-emerald-400'
              : connectionState === 'reconnecting' || connectionState === 'connecting'
              ? 'text-amber-400'
              : 'text-rose-400'
          }`}>
            {connectionState}
          </p>
        </div>
      </div>
    </div>
  );
};
