import React, { useState } from 'react';
import { 
  Radio, PhoneOff, PhoneCall, RefreshCw, Zap, Activity, 
  PhoneForwarded, Trash2, Terminal, Layers
} from 'lucide-react';
import { LogEvent, CallSession } from '../types';
import { useLiveCallMonitor } from '../hooks/useLiveCallMonitor';
import { MonitorMetrics } from '../components/live-monitor/MonitorMetrics';
import { CallCard } from '../components/live-monitor/CallCard';
import { Transcript } from '../components/live-monitor/Transcript';
import { CallDetails } from '../components/live-monitor/CallDetails';

interface LiveMonitorPageProps {
  logs: LogEvent[];
  activeCalls: CallSession[];
  allCalls?: CallSession[];
  onRefreshData?: () => void;
}

export const LiveMonitorPage: React.FC<LiveMonitorPageProps> = ({
  logs,
  activeCalls,
  allCalls = [],
  onRefreshData
}) => {
  // Custom hook encapsulating all WebSocket, idempotency, sequence, and call-scoped state logic
  const {
    calls,
    selectedCall,
    selectedCallId,
    selectedCallTranscripts,
    connectionState,
    metrics,
    isHangingUp,
    isCleaningStale,
    selectCall,
    hangupCall,
    purgeStaleCalls,
    getCallDuration
  } = useLiveCallMonitor({
    activeCallsProp: activeCalls,
    allCallsProp: allCalls,
    onRefreshData
  });

  const [activeTab, setActiveTab] = useState<'transcript' | 'events'>('transcript');
  const [autoScroll, setAutoScroll] = useState(true);

  // Test Call Modal State
  const [showTestCallModal, setShowTestCallModal] = useState(false);
  const [testPhone, setTestPhone] = useState('+919876543210');
  const [testVoice, setTestVoice] = useState('cartesia_hi_sonic');
  const [testMode, setTestMode] = useState<'INTERACTIVE_AI' | 'SCRIPT'>('INTERACTIVE_AI');
  const [testPrompt, setTestPrompt] = useState('You are Ananya, a helpful Superfone AI agent.');
  const [isDialing, setIsDialing] = useState(false);

  // Start Test Call Action
  const handleStartTestCall = async () => {
    setIsDialing(true);
    try {
      const resp = await fetch('/api/v1/calls/manual-dial', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: testPhone,
          call_mode: testMode,
          voice_model: testVoice,
          system_prompt: testPrompt
        })
      });
      if (resp.ok) {
        setShowTestCallModal(false);
        if (onRefreshData) onRefreshData();
      } else {
        const err = await resp.json().catch(() => ({}));
        alert(`Failed to start call: ${err.detail || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Call error: ${ex.message}`);
    } finally {
      setIsDialing(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 1. Top Banner & Telephony Command Bar */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-700/60 dark:border-slate-800 bg-white/70 dark:bg-dark-800/80 shadow-xl backdrop-blur-md flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 dark:text-slate-100 flex items-center space-x-3 tracking-tight">
            <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Radio className="w-6 h-6 animate-pulse" />
            </div>
            <span>Superfone Live Telephony Stream</span>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Authoritative, real-time telephony state, live speech transcript streaming, and human agent supervision.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          {/* Stale Purge Button */}
          <button
            onClick={purgeStaleCalls}
            disabled={isCleaningStale}
            className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold text-xs border border-slate-700 transition-all disabled:opacity-50"
            title="Clean up dead or orphaned calls from prior runs"
          >
            <Trash2 className="w-4 h-4 text-rose-400" />
            <span>{isCleaningStale ? 'Purging...' : 'Purge Dead Calls'}</span>
          </button>

          {/* Test Call Trigger */}
          <button
            onClick={() => setShowTestCallModal(true)}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs shadow-lg shadow-brand-500/25 transition-all"
          >
            <PhoneForwarded className="w-4 h-4" />
            <span>Start Test Call</span>
          </button>
        </div>
      </div>

      {/* 2. Telemetry Key Metrics (Constraint 1 & 4) */}
      <MonitorMetrics
        activeCount={metrics.activeCount}
        aiCount={metrics.aiCount}
        humanCount={metrics.humanCount}
        transferringCount={metrics.transferringCount}
        totalTurns={metrics.totalTurns}
        connectionState={connectionState}
      />

      {/* 3. Main Operational Telephony Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Authoritative Active Sessions List */}
        <div className="glass-panel p-5 rounded-2xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-700/50 dark:border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <Activity className="w-4 h-4 text-emerald-500" />
              <span>Active Telephony Sessions ({calls.length})</span>
            </h3>
            {calls.length > 0 && (
              <span className="text-[10px] bg-emerald-500/20 text-emerald-400 font-mono px-2 py-0.5 rounded border border-emerald-500/30 font-bold animate-pulse">
                CALL CONNECTED
              </span>
            )}
          </div>

          <div className="space-y-3 max-h-[620px] overflow-y-auto pr-1">
            {calls.length === 0 ? (
              <div className="text-center py-12 px-4 space-y-3">
                <PhoneOff className="w-10 h-10 text-slate-400 dark:text-slate-600 mx-auto" />
                <div>
                  <p className="text-sm font-bold text-slate-800 dark:text-slate-300">No calls currently active</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    Click "Start Test Call" or dial from CRM/Manual Dialer to connect softphone live.
                  </p>
                </div>
                <button
                  onClick={() => setShowTestCallModal(true)}
                  className="mt-2 text-xs font-bold text-brand-500 hover:text-brand-400 underline"
                >
                  Launch Test Call Now
                </button>
              </div>
            ) : (
              calls.map(call => (
                <CallCard
                  key={call.id}
                  call={call}
                  isSelected={call.id === selectedCallId}
                  durationText={getCallDuration(call)}
                  isHangingUp={isHangingUp === call.id}
                  onSelect={selectCall}
                  onHangup={(cid, e) => {
                    e.stopPropagation();
                    hangupCall(cid);
                  }}
                />
              ))
            )}
          </div>
        </div>

        {/* Middle Column: Call-Scoped Live Transcripts (Constraint 5) */}
        <div className="glass-panel p-5 rounded-2xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow-lg space-y-4 flex flex-col">
          <div className="flex items-center justify-between border-b border-slate-700/50 dark:border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setActiveTab('transcript')}
                className={`text-xs font-bold px-3 py-1.5 rounded-xl border transition-all ${
                  activeTab === 'transcript'
                    ? 'bg-brand-500/20 text-brand-400 border-brand-500/40'
                    : 'text-slate-400 border-transparent hover:text-slate-200'
                }`}
              >
                Live Speech Stream ({selectedCallTranscripts.length})
              </button>
              <button
                onClick={() => setActiveTab('events')}
                className={`text-xs font-bold px-3 py-1.5 rounded-xl border transition-all ${
                  activeTab === 'events'
                    ? 'bg-brand-500/20 text-brand-400 border-brand-500/40'
                    : 'text-slate-400 border-transparent hover:text-slate-200'
                }`}
              >
                Gateway Logs ({logs.length})
              </button>
            </div>

            {selectedCall && (
              <span className="text-[10px] font-mono text-slate-400">
                Call: {selectedCall.to_number || selectedCall.id.slice(0, 8)}
              </span>
            )}
          </div>

          {activeTab === 'transcript' ? (
            <Transcript
              turns={selectedCallTranscripts}
              callId={selectedCallId || undefined}
              autoScroll={autoScroll}
              onToggleAutoScroll={() => setAutoScroll(!autoScroll)}
            />
          ) : (
            <div className="flex-1 max-h-[580px] overflow-y-auto bg-slate-950 p-3 rounded-xl border border-slate-800 font-mono text-xs space-y-1">
              {logs.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs">
                  No gateway event logs captured yet.
                </div>
              ) : (
                logs.slice(-100).map((l, idx) => (
                  <div key={idx} className="text-slate-400 leading-relaxed break-all">
                    <span className="text-slate-600">[{l.timestamp}]</span>{' '}
                    <span className="text-brand-400 font-bold">{l.event_type || 'LOG'}</span>:{' '}
                    <span>{l.raw || (l.payload ? JSON.stringify(l.payload) : '')}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Right Column: Deep-Inspection Panel */}
        <div className="glass-panel p-5 rounded-2xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-700/50 dark:border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <Layers className="w-4 h-4 text-purple-400" />
              <span>Session Telemetry Metadata</span>
            </h3>
          </div>

          <CallDetails
            call={selectedCall}
            durationText={selectedCall ? getCallDuration(selectedCall) : '0s'}
            isHangingUp={selectedCall ? isHangingUp === selectedCall.id : false}
            onHangup={(cid) => hangupCall(cid)}
          />
        </div>
      </div>

      {/* Test Call Dialing Modal */}
      {showTestCallModal && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel max-w-md w-full p-6 rounded-2xl border border-slate-700 bg-white dark:bg-slate-900 shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                <PhoneForwarded className="w-5 h-5 text-brand-500" />
                <span>Originate Direct MicroSIP Call</span>
              </h3>
              <button
                onClick={() => setShowTestCallModal(false)}
                className="text-slate-400 hover:text-slate-200 font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  Destination Phone Number / SIP Extension
                </label>
                <input
                  type="text"
                  value={testPhone}
                  onChange={(e) => setTestPhone(e.target.value)}
                  placeholder="+919876543210 or test1000"
                  className="w-full px-3 py-2 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 font-mono focus:outline-none focus:border-brand-500"
                />
              </div>

              <div>
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  Call Mode
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setTestMode('INTERACTIVE_AI')}
                    className={`py-2 px-3 rounded-xl font-bold border transition-all ${
                      testMode === 'INTERACTIVE_AI'
                        ? 'bg-brand-500 text-white border-brand-500 shadow'
                        : 'bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-700'
                    }`}
                  >
                    Interactive AI Agent
                  </button>
                  <button
                    type="button"
                    onClick={() => setTestMode('SCRIPT')}
                    className={`py-2 px-3 rounded-xl font-bold border transition-all ${
                      testMode === 'SCRIPT'
                        ? 'bg-brand-500 text-white border-brand-500 shadow'
                        : 'bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-700'
                    }`}
                  >
                    Script Recitation
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  Voice Model
                </label>
                <select
                  value={testVoice}
                  onChange={(e) => setTestVoice(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 font-medium focus:outline-none focus:border-brand-500"
                >
                  <option value="cartesia_hi_sonic">Cartesia Hindi Sonic (Ultra Fast ~120ms)</option>
                  <option value="edge_hi-IN-MadhurNeural">EdgeTTS Hindi Madhur (Male)</option>
                  <option value="edge_mr-IN-AarohiNeural">EdgeTTS Marathi/Marwadi (Female)</option>
                  <option value="deepgram_aura_asteria">Deepgram Aura Asteria (Zero-Latency ~100ms)</option>
                  <option value="openai_alloy">OpenAI Alloy (Natural English)</option>
                  <option value="hi_pratham">Kokoro Hindi Pratham</option>
                  <option value="af_sarah">Kokoro English Sarah</option>
                  <option value="am_adam">Kokoro English Adam</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  System Persona / Prompt
                </label>
                <textarea
                  rows={3}
                  value={testPrompt}
                  onChange={(e) => setTestPrompt(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 font-sans focus:outline-none focus:border-brand-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end space-x-3 border-t border-slate-200 dark:border-slate-800 pt-3">
              <button
                type="button"
                onClick={() => setShowTestCallModal(false)}
                className="px-4 py-2 rounded-xl bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold text-xs hover:bg-slate-300 dark:hover:bg-slate-700 transition-all"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleStartTestCall}
                disabled={isDialing}
                className="flex items-center space-x-2 px-5 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs shadow-lg shadow-brand-500/25 transition-all disabled:opacity-50"
              >
                {isDialing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Dialing MicroSIP...</span>
                  </>
                ) : (
                  <>
                    <PhoneCall className="w-4 h-4" />
                    <span>Dial Now</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
