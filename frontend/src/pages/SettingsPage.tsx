import React from 'react';
import { Settings, Server, Shield, Sliders } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center space-x-2">
            <Settings className="w-5 h-5 text-slate-400" />
            <span>System Settings & Operational Parameters</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">Configure microservice ports, barge-in threshold, DB connections, and speech model defaults.</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-3 flex items-center space-x-2">
            <Server className="w-4 h-4 text-brand-500" />
            <span>Microservice Endpoint Configuration</span>
          </h3>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Call Gateway AudioSocket URL</label>
              <input type="text" readOnly value="http://127.0.0.1:9092" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">LLM Qwen Server URL</label>
              <input type="text" readOnly value="http://127.0.0.1:9093" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Faster-Whisper STT Worker URL</label>
              <input type="text" readOnly value="http://127.0.0.1:9094" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Kokoro / Piper TTS Worker URL</label>
              <input type="text" readOnly value="http://127.0.0.1:9095" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Audio Studio Server URL</label>
              <input type="text" readOnly value="http://127.0.0.1:9096" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>
          </div>
        </div>

        <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
          <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-3 flex items-center space-x-2">
            <Sliders className="w-4 h-4 text-emerald-400" />
            <span>Audio Pipeline & Barge-In Thresholds</span>
          </h3>

          <div className="space-y-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">VAD Speech Energy Threshold (dBFS)</label>
              <input type="text" readOnly value="-38.0 dBFS" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Barge-In Fade Duration</label>
              <input type="text" readOnly value="40 ms soft attack fade" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>

            <div>
              <label className="block text-slate-400 mb-1">Database Engine Target</label>
              <input type="text" readOnly value="SQLite (voice_crm.db) / PostgreSQL 18 Compatible" className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-300 font-mono" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
