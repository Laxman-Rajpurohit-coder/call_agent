import React from 'react';
import { Cpu, Activity, Clock, Zap } from 'lucide-react';
import { LoadTestSummary } from '../types';

interface LoadTestingPageProps {
  loadTests: LoadTestSummary[];
}

export const LoadTestingPage: React.FC<LoadTestingPageProps> = ({ loadTests }) => {
  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center space-x-2">
            <Cpu className="w-5 h-5 text-indigo-400" />
            <span>Load Testing & Concurrency Analytics</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">Multi-call concurrency capacity tests, queue wait latency percentiles, and LLM lock wait distributions.</p>
        </div>
      </div>

      {/* Grid of Load Test Benchmarks */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {loadTests.map((lt, idx) => (
          <div key={idx} className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
            <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-3 min-w-0">
              <span className="text-xs md:text-sm font-bold text-slate-100 truncate min-w-0 flex-1" title={lt.filename}>{lt.filename}</span>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] md:text-xs font-bold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 shrink-0 whitespace-nowrap">
                N={lt.concurrency} Calls
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between text-slate-400">
                <span>Total Concurrent Calls</span>
                <span className="font-bold text-slate-200">{lt.total_calls}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>Accepted / Succeeded</span>
                <span className="font-bold text-emerald-400">{lt.accepted} / {lt.succeeded}</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>STT Queue Wait P95</span>
                <span className="font-mono text-brand-400">{lt.stt_p95.toFixed(1)} ms</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>LLM Lock Wait P95</span>
                <span className="font-mono text-amber-400">{lt.llm_lock_p95.toFixed(1)} ms</span>
              </div>
              <div className="flex justify-between text-slate-400">
                <span>TTS Queue Wait P95</span>
                <span className="font-mono text-emerald-400">{lt.tts_p95.toFixed(1)} ms</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
