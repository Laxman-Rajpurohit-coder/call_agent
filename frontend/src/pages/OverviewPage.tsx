import React from 'react';
import { PhoneCall, Users, CheckCircle2, UserCheck, ShieldCheck, Server } from 'lucide-react';
import { SystemOverview, LogEvent } from '../types';

interface OverviewPageProps {
  overview: SystemOverview | null;
  logs: LogEvent[];
}

export const OverviewPage: React.FC<OverviewPageProps> = React.memo(({ overview, logs }) => {
  const kpis = [
    { label: 'Total Calls Processed', value: overview?.total_calls || 0, icon: PhoneCall, color: 'text-indigo-400', bg: 'bg-indigo-500/15 border-indigo-500/30', glow: 'glow-card' },
    { label: 'Active Live Calls', value: overview?.active_calls || 0, icon: PhoneCall, color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/30', glow: 'glow-card-emerald' },
    { label: 'Completed Cleanly', value: overview?.completed_calls || 0, icon: CheckCircle2, color: 'text-cyan-400', bg: 'bg-cyan-500/15 border-cyan-500/30', glow: 'glow-card' },
    { label: 'Human Handoffs', value: overview?.human_handoffs || 0, icon: UserCheck, color: 'text-amber-400', bg: 'bg-amber-500/15 border-amber-500/30', glow: 'glow-card' },
    { label: 'Registered Contacts', value: overview?.total_contacts || 0, icon: Users, color: 'text-purple-400', bg: 'bg-purple-500/15 border-purple-500/30', glow: 'glow-card-purple' },
    { label: 'Overall QA Pass Rate', value: `${overview?.overall_pass_rate || 100}%`, icon: ShieldCheck, color: 'text-teal-400', bg: 'bg-teal-500/15 border-teal-500/30', glow: 'glow-card-emerald' },
  ];

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-5 md:p-6 rounded-2xl border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative overflow-hidden shadow-xl">
        <div className="absolute top-0 right-0 w-96 h-96 bg-gradient-to-br from-indigo-500/10 via-purple-500/5 to-transparent rounded-full blur-3xl pointer-events-none" />
        <div>
          <h2 className="text-xl md:text-2xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-indigo-200 tracking-tight">
            Superfone AI Voice Operations Platform
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-1 font-medium">
            Real-time telemetry, campaign automation, and microservices health monitoring.
          </p>
        </div>
        <div className="flex items-center space-x-3 shrink-0">
          <span className="flex items-center space-x-2 text-xs font-bold px-3.5 py-1.5 rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-md shadow-emerald-500/10">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
            <span>Cluster Operational</span>
          </span>
        </div>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 md:gap-4">
        {kpis.map((kpi, idx) => {
          const Icon = kpi.icon;
          return (
            <div key={idx} className={`glass-panel p-4 rounded-2xl border border-slate-800 flex flex-col justify-between transition-all hover:scale-[1.02] ${kpi.glow}`}>
              <div className="flex items-center justify-between">
                <span className="text-[11px] md:text-xs font-semibold text-slate-400 leading-tight">{kpi.label}</span>
                <div className={`p-2 rounded-xl border ${kpi.bg} shrink-0 shadow-inner`}>
                  <Icon className={`w-4 h-4 ${kpi.color}`} />
                </div>
              </div>
              <div className="mt-3 text-2xl md:text-3xl font-extrabold text-slate-100 tracking-tight">{kpi.value}</div>
            </div>
          );
        })}
      </div>

      {/* Microservices Health Matrix & Live Log Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Microservices Cluster Column */}
        <div className="glass-panel p-5.5 rounded-2xl border border-slate-800 space-y-4 shadow-xl">
          <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2.5">
            <Server className="w-4 h-4 text-indigo-400" />
            <span>Microservices Status Matrix</span>
          </h3>

          <div className="space-y-3">
            {overview?.services.map((svc) => (
              <div key={svc.port} className="glass-card p-3.5 rounded-xl flex items-center justify-between gap-3 border border-slate-800/80 hover:border-indigo-500/30 transition-all">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-bold text-slate-200 truncate">{svc.name}</div>
                  <div className="text-[11px] text-slate-400 font-mono truncate">Port {svc.port} • {svc.url}</div>
                </div>
                <div className="flex items-center space-x-2 shrink-0 whitespace-nowrap">
                  {svc.latency_ms !== undefined && svc.latency_ms !== null && (
                    <span className="text-[11px] text-slate-300 font-mono bg-slate-900/80 px-2 py-0.5 rounded border border-slate-800">{svc.latency_ms} ms</span>
                  )}
                  <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-wider ${
                    svc.status === 'healthy'
                      ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30'
                      : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'
                  }`}>
                    {svc.status}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Real-time Gateway Event Stream */}
        <div className="lg:col-span-2 glass-panel p-5.5 rounded-2xl border border-slate-800 space-y-3 flex flex-col h-[420px] shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-200 flex items-center space-x-2.5">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
              <span>Live AudioSocket Event Stream</span>
            </h3>
            <span className="text-xs text-slate-400 font-mono bg-slate-800/50 px-2.5 py-1 rounded-full border border-slate-700/50">{logs.length} events captured</span>
          </div>

          <div className="flex-1 overflow-y-auto font-mono text-xs space-y-2 pr-2">
            {logs.length === 0 ? (
              <div className="text-slate-500 italic py-16 text-center font-sans text-sm">Tailing live gateway audio events...</div>
            ) : (
              logs.map((log, i) => (
                <div key={i} className="p-2.5 rounded-xl bg-slate-900/80 border border-slate-800 flex items-start space-x-2.5 hover:border-slate-700 transition-all">
                  <span className="text-slate-400 text-[11px] font-mono">{log.timestamp || '00:00:00'}</span>
                  <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase tracking-wide ${
                    log.event_type === 'USER_UTTERANCE' ? 'bg-sky-500/20 text-sky-300 border border-sky-500/30' :
                    log.event_type === 'AI_RESPONSE' ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' :
                    log.event_type === 'BARGE_IN_TRIGGERED' ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' :
                    log.event_type === 'DTMF_HANDOFF' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' :
                    'bg-slate-800 text-slate-300 border border-slate-700'
                  }`}>
                    {log.event_type}
                  </span>
                  <span className="text-slate-200 font-medium break-all">{log.payload?.text || log.raw}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
});
