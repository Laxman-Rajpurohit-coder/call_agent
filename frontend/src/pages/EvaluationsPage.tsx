import React from 'react';
import { TestTube2, CheckCircle2, AlertCircle, FileText } from 'lucide-react';
import { EvaluationReport } from '../types';

interface EvaluationsPageProps {
  evaluations: EvaluationReport[];
}

export const EvaluationsPage: React.FC<EvaluationsPageProps> = ({ evaluations }) => {
  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center space-x-2">
            <TestTube2 className="w-5 h-5 text-emerald-400" />
            <span>Evaluation & QA Quality Benchmarks</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">Automated test runs, Word Error Rate (WER), barge-in response, and speech defect tracking.</p>
        </div>
      </div>

      {/* Reports Table */}
      <div className="glass-panel p-4 md:p-5 rounded-2xl border border-slate-800 overflow-hidden space-y-3">
        <div className="sm:hidden flex items-center justify-between text-[11px] text-slate-400 bg-slate-900/60 px-3 py-1.5 rounded-lg border border-slate-800/80">
          <span>↔ Swipe table horizontally for full QA metrics</span>
          <span className="font-semibold text-emerald-400">{evaluations.length} runs</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[620px] text-left text-sm text-slate-300">
            <thead className="text-xs text-slate-400 uppercase bg-slate-900/50 border-b border-slate-800">
              <tr>
                <th className="px-4 py-3 whitespace-nowrap">Run ID</th>
                <th className="px-4 py-3 whitespace-nowrap">Test Suite</th>
                <th className="px-4 py-3 whitespace-nowrap">Transport</th>
                <th className="px-4 py-3 whitespace-nowrap">Total Tests</th>
                <th className="px-4 py-3 whitespace-nowrap">Passed</th>
                <th className="px-4 py-3 whitespace-nowrap">Pass Rate</th>
                <th className="px-4 py-3 whitespace-nowrap">Timestamp</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {evaluations.map((ev, i) => (
                <tr key={i} className="hover:bg-slate-800/40">
                  <td className="px-4 py-3.5 font-mono text-xs font-semibold text-brand-400 whitespace-nowrap">{ev.run_id}</td>
                  <td className="px-4 py-3.5 font-medium text-slate-200 uppercase text-xs whitespace-nowrap">{ev.suite}</td>
                  <td className="px-4 py-3.5 text-xs text-slate-400 whitespace-nowrap">{ev.transport}</td>
                  <td className="px-4 py-3.5 font-mono text-slate-300 whitespace-nowrap">{ev.total}</td>
                  <td className="px-4 py-3.5 font-mono text-emerald-400 whitespace-nowrap">{ev.passed}</td>
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                      ev.pass_rate >= 0.95 ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}>
                      {(ev.pass_rate * 100).toFixed(1)}%
                    </span>
                  </td>
                  <td className="px-4 py-3.5 text-xs text-slate-500 whitespace-nowrap">{ev.timestamp}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
