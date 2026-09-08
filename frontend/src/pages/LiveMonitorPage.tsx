import React, { useState, useEffect, useRef } from 'react';
import { 
  Radio, Mic, User, Bot, PhoneOff, PhoneCall, Play, Pause, Download, 
  Search, Volume2, RefreshCw, Zap, Activity, Filter, Sparkles, 
  PhoneForwarded, Copy, Check, Terminal, Layers
} from 'lucide-react';
import { LogEvent, CallSession } from '../types';

interface LiveMonitorPageProps {
  logs: LogEvent[];
  activeCalls: CallSession[];
  allCalls?: CallSession[];
  onRefreshData?: () => void;
}

export const LiveMonitorPage: React.FC<LiveMonitorPageProps> = ({ logs, activeCalls, allCalls = [], onRefreshData }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [roleFilter, setRoleFilter] = useState<'ALL' | 'user' | 'assistant'>('ALL');
  const [autoScroll, setAutoScroll] = useState(true);
  const [playingWav, setPlayingWav] = useState<string | null>(null);
  const [copiedTurnId, setCopiedTurnId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'transcript' | 'events'>('transcript');
  
  // Test Call Modal State
  const [showTestCallModal, setShowTestCallModal] = useState(false);
  const [testPhone, setTestPhone] = useState('+919876543210');
  const [testVoice, setTestVoice] = useState('cartesia_hi_sonic');
  const [testMode, setTestMode] = useState<'INTERACTIVE_AI' | 'SCRIPT'>('INTERACTIVE_AI');
  const [testPrompt, setTestPrompt] = useState('You are Ananya, a helpful Superfone AI agent.');
  const [isDialing, setIsDialing] = useState(false);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);

  // Controlled 3s polling loop for call state refresh
  useEffect(() => {
    if (onRefreshData) {
      onRefreshData();
      const interval = setInterval(onRefreshData, 3000);
      return () => clearInterval(interval);
    }
  }, [onRefreshData]);


  // Aggregate transcript turns from active calls or recent calls
  const displayCalls = activeCalls.length > 0 ? activeCalls : allCalls.slice(0, 10);

  const dbTurns: Array<{
    id: string;
    role: string;
    content: string;
    timestamp: string;
    callId: string;
    audio_dur_s?: number;
    wav_file?: string;
  }> = [];

  displayCalls.forEach(call => {
    if (call.transcript && Array.isArray(call.transcript)) {
      call.transcript.forEach((turn: any, index: number) => {
        dbTurns.push({
          id: `${call.id}-${index}`,
          role: turn.role,
          content: turn.content,
          timestamp: call.created_at || 'Live',
          callId: call.id,
          audio_dur_s: turn.audio_dur_s,
          wav_file: turn.wav_file
        });
      });
    }
  });

  // Also extract live speech turns from real-time WebSocket logs
  const wsTurns: typeof dbTurns = [];
  logs.forEach((log, index) => {
    if (log.event_type === 'USER_UTTERANCE' && log.payload?.text) {
      wsTurns.push({
        id: `ws-user-${index}-${log.timestamp}`,
        role: 'user',
        content: log.payload.text,
        timestamp: log.timestamp || 'Just now',
        callId: log.call_id || 'live-stream'
      });
    } else if (log.event_type === 'AI_RESPONSE' && log.payload?.text) {
      wsTurns.push({
        id: `ws-ai-${index}-${log.timestamp}`,
        role: 'assistant',
        content: log.payload.text,
        timestamp: log.timestamp || 'Just now',
        callId: log.call_id || 'live-stream'
      });
    }
  });

  // Combine DB turns with any new WebSocket turns seamlessly
  const aggregatedTurns = dbTurns.length > 0 ? dbTurns : wsTurns;

  // Filtered turns
  const filteredTurns = aggregatedTurns.filter(turn => {
    const matchesSearch = turn.content.toLowerCase().includes(searchTerm.toLowerCase()) ||
                          turn.callId.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesRole = roleFilter === 'ALL' || turn.role === roleFilter;
    return matchesSearch && matchesRole;
  });


  // Auto scroll to bottom when new turns arrive
  useEffect(() => {
    if (autoScroll && transcriptEndRef.current) {
      transcriptEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [filteredTurns.length, autoScroll]);

  // Audio turn playback
  const handlePlayAudio = (wavFile: string) => {
    if (playingWav === wavFile && audioRef.current) {
      audioRef.current.pause();
      setPlayingWav(null);
      return;
    }
    if (audioRef.current) {
      audioRef.current.pause();
    }
    const audio = new Audio(`/api/v1/calls/audio/${wavFile}`);
    audioRef.current = audio;
    setPlayingWav(wavFile);
    audio.play().catch(err => console.error("Audio playback failed:", err));
    audio.onended = () => setPlayingWav(null);
  };

  // Copy turn text
  const handleCopyTurn = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedTurnId(id);
    setTimeout(() => setCopiedTurnId(null), 2000);
  };

  // Download Transcript JSON
  const handleDownloadTranscript = () => {
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(aggregatedTurns, null, 2));
    const downloadAnchor = document.createElement('a');
    downloadAnchor.setAttribute("href", dataStr);
    downloadAnchor.setAttribute("download", `live_call_transcript_${new Date().toISOString().slice(0, 10)}.json`);
    document.body.appendChild(downloadAnchor);
    downloadAnchor.click();
    downloadAnchor.remove();
  };

  // Trigger test call
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
      {/* Top Banner & Control Bar */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-700/60 dark:border-slate-800 bg-white/70 dark:bg-dark-800/80 shadow-xl backdrop-blur-md flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-black text-slate-900 dark:text-slate-100 flex items-center space-x-3 tracking-tight">
            <div className="p-2 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Radio className="w-6 h-6 animate-pulse" />
            </div>
            <span>Live Call Monitor & Speech Studio</span>
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1 font-medium">
            Real-time VAD detection, Speech-to-Text stream (Groq Whisper / Deepgram Nova 2), and AI turn audio playback.
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto justify-between md:justify-end">
          <div className="flex items-center space-x-2 text-xs font-semibold text-emerald-700 dark:text-emerald-300 bg-emerald-500/10 px-3.5 py-2 rounded-xl border border-emerald-500/30">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping"></span>
            <span>WebSocket Live Stream (8kHz G.711)</span>
          </div>

          <button
            onClick={() => setShowTestCallModal(true)}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-semibold text-xs shadow-lg shadow-brand-500/25 transition-all transform hover:scale-[1.02] active:scale-95"
          >
            <PhoneForwarded className="w-4 h-4" />
            <span>Start Test Call</span>
          </button>
        </div>
      </div>

      {/* Telemetry Key Metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400">
            <PhoneCall className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Active Live Calls</p>
            <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{activeCalls.length}</p>
          </div>
        </div>

        <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-400">
            <Mic className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Turns Transcribed</p>
            <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{aggregatedTurns.length}</p>
          </div>
        </div>

        <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">VAD Silence Cutoff</p>
            <p className="text-xl font-bold text-purple-500 dark:text-purple-400">350ms</p>
          </div>
        </div>

        <div className="glass-card p-4 rounded-xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow flex items-center space-x-3">
          <div className="p-2.5 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400">
            <Activity className="w-5 h-5" />
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 dark:text-slate-400">Primary STT Model</p>
            <p className="text-sm font-bold text-slate-900 dark:text-slate-100 truncate">Whisper v3 / Nova 2</p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Active Telephony Sessions */}
        <div className="glass-panel p-5 rounded-2xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow-lg space-y-4">
          <div className="flex items-center justify-between border-b border-slate-700/50 dark:border-slate-800 pb-3">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <Activity className="w-4 h-4 text-emerald-500" />
              <span>Active Telephony Sessions ({activeCalls.length})</span>
            </h3>
            {activeCalls.length > 0 && (
              <span className="text-[10px] bg-emerald-500/20 text-emerald-400 font-mono px-2 py-0.5 rounded border border-emerald-500/30 font-bold">
                RTP ACTIVE
              </span>
            )}
          </div>

          {activeCalls.length === 0 ? (
            <div className="p-8 text-center glass-card rounded-xl border border-slate-700/40 dark:border-slate-800/80 space-y-3">
              <PhoneOff className="w-10 h-10 text-slate-400 dark:text-slate-600 mx-auto" />
              <div>
                <p className="text-sm font-bold text-slate-800 dark:text-slate-300">No calls currently active</p>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  Click "Start Test Call" or dial from CRM/Manual Dialer to stream live audio telemetry.
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
            activeCalls.map((call) => (
              <div key={call.id} className="glass-card p-4 rounded-xl border border-emerald-500/40 bg-emerald-500/5 space-y-3 shadow-md">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-emerald-400 font-bold">ID: {call.id.slice(0, 8)}</span>
                  <span className="flex items-center space-x-1 text-xs text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded-full border border-emerald-500/30 font-semibold">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                    <span>Live RTP Stream</span>
                  </span>
                </div>

                <div className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                  <PhoneCall className="w-4 h-4 text-emerald-400" />
                  <span>{call.to_number || call.from_number}</span>
                </div>

                {/* VAD Speech Wave Visualizer */}
                <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800 flex items-center justify-between">
                  <span className="text-[11px] font-mono text-emerald-400 font-semibold flex items-center space-x-1.5">
                    <Mic className="w-3.5 h-3.5 text-emerald-400 animate-pulse" />
                    <span>VAD Active</span>
                  </span>
                  <div className="flex items-center space-x-1 h-4">
                    <span className="w-1 bg-emerald-400 h-2 animate-bounce rounded-full" style={{ animationDelay: '0ms' }}></span>
                    <span className="w-1 bg-emerald-400 h-4 animate-bounce rounded-full" style={{ animationDelay: '150ms' }}></span>
                    <span className="w-1 bg-emerald-400 h-3 animate-bounce rounded-full" style={{ animationDelay: '300ms' }}></span>
                    <span className="w-1 bg-emerald-400 h-1 animate-bounce rounded-full" style={{ animationDelay: '450ms' }}></span>
                  </div>
                </div>

                <div className="text-xs text-slate-500 dark:text-slate-400 flex items-center justify-between border-t border-slate-800/80 pt-2 font-mono">
                  <span>Duration: <strong className="text-slate-800 dark:text-slate-200">{call.duration_s}s</strong></span>
                  <span>G.711 PCMU 8kHz</span>
                </div>
              </div>
            ))
          )}

          {/* Quick Info Card */}
          <div className="p-4 rounded-xl bg-slate-100 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400 space-y-2">
            <div className="font-bold text-slate-800 dark:text-slate-200 flex items-center space-x-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-400" />
              <span>Real-Time Features Enabled</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-[11px]">
              <li>Zero-latency VAD speech segmenting</li>
              <li>Dual Cloud STT fallback (Groq & Deepgram)</li>
              <li>Per-turn WAV audio recording & instant playback</li>
              <li>Instant WebSocket event broadcasting</li>
            </ul>
          </div>
        </div>

        {/* Right Column: Live Conversation & Speech Stream Log */}
        <div className="lg:col-span-2 glass-panel p-5 rounded-2xl border border-slate-700/50 dark:border-slate-800 bg-white/60 dark:bg-dark-800/60 shadow-lg flex flex-col h-[640px] space-y-4">
          {/* Header Controls */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-b border-slate-700/50 dark:border-slate-800 pb-3">
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setActiveTab('transcript')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center space-x-1.5 ${
                  activeTab === 'transcript'
                    ? 'bg-brand-500 text-white shadow-md'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                }`}
              >
                <Mic className="w-3.5 h-3.5" />
                <span>Live Speech Transcript ({filteredTurns.length})</span>
              </button>

              <button
                onClick={() => setActiveTab('events')}
                className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center space-x-1.5 ${
                  activeTab === 'events'
                    ? 'bg-brand-500 text-white shadow-md'
                    : 'text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-800'
                }`}
              >
                <Terminal className="w-3.5 h-3.5" />
                <span>Live System Events ({logs.length})</span>
              </button>
            </div>

            <div className="flex items-center space-x-2 w-full sm:w-auto">
              <button
                onClick={() => setAutoScroll(!autoScroll)}
                className={`px-2.5 py-1 rounded-lg text-[11px] font-semibold border transition-all ${
                  autoScroll
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                    : 'bg-slate-200 dark:bg-slate-800 text-slate-500 border-slate-300 dark:border-slate-700'
                }`}
              >
                Auto-scroll: {autoScroll ? 'ON' : 'OFF'}
              </button>

              <button
                onClick={handleDownloadTranscript}
                disabled={aggregatedTurns.length === 0}
                className="p-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 border border-slate-300 dark:border-slate-700 disabled:opacity-40 transition-all"
                title="Download JSON Transcript"
              >
                <Download className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Search & Filter Toolbar */}
          {activeTab === 'transcript' && (
            <div className="flex flex-col sm:flex-row items-center gap-2">
              <div className="relative flex-1 w-full">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter live speech text..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl bg-slate-100 dark:bg-slate-900 border border-slate-300 dark:border-slate-700 text-slate-900 dark:text-slate-100 focus:outline-none focus:border-brand-500"
                />
              </div>

              <div className="flex items-center space-x-1 bg-slate-100 dark:bg-slate-900 p-1 rounded-xl border border-slate-300 dark:border-slate-700">
                {(['ALL', 'user', 'assistant'] as const).map(role => (
                  <button
                    key={role}
                    onClick={() => setRoleFilter(role)}
                    className={`px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase transition-all ${
                      roleFilter === role
                        ? 'bg-brand-500 text-white shadow'
                        : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200'
                    }`}
                  >
                    {role === 'ALL' ? 'All Roles' : role === 'user' ? 'User' : 'AI Agent'}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Main Content View */}
          {activeTab === 'transcript' ? (
            <div className="flex-1 overflow-y-auto space-y-3.5 pr-2 custom-scrollbar">
              {filteredTurns.length === 0 ? (
                <div className="text-slate-500 text-sm py-24 text-center space-y-3">
                  <Mic className="w-10 h-10 text-slate-400 dark:text-slate-600 mx-auto animate-pulse" />
                  <p className="font-semibold text-slate-700 dark:text-slate-300">
                    Waiting for spoken dialogue in active calls...
                  </p>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    Speak into your softphone or MicroSIP microphone during a call to see speech turns transcribed instantly!
                  </p>
                </div>
              ) : (
                filteredTurns.map((turn) => (
                  <div key={turn.id} className="flex items-start space-x-3 group">
                    {turn.role === 'user' ? (
                      <div className="w-9 h-9 rounded-full bg-sky-500/20 text-sky-400 flex items-center justify-center shrink-0 border border-sky-500/30 shadow-md">
                        <User className="w-4 h-4" />
                      </div>
                    ) : (
                      <div className="w-9 h-9 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center shrink-0 border border-emerald-500/30 shadow-md">
                        <Bot className="w-4 h-4" />
                      </div>
                    )}

                    <div className={`flex-1 glass-card p-3.5 rounded-2xl border text-sm shadow-sm transition-all ${
                      turn.role === 'user'
                        ? 'border-sky-500/30 bg-sky-500/5 hover:border-sky-500/50'
                        : 'border-emerald-500/30 bg-emerald-500/5 hover:border-emerald-500/50'
                    }`}>
                      <div className="flex items-center justify-between text-xs mb-1.5">
                        <div className="flex items-center space-x-2">
                          <span className={`font-bold ${turn.role === 'user' ? 'text-sky-400' : 'text-emerald-400'}`}>
                            {turn.role === 'user' ? '👤 USER (MIC SPEECH)' : '🤖 AI AGENT'}
                          </span>
                          {turn.role === 'user' && turn.audio_dur_s && (
                            <span className="text-[10px] bg-sky-500/20 text-sky-300 px-2 py-0.5 rounded-full border border-sky-500/30 font-mono font-semibold">
                              VAD ({turn.audio_dur_s}s)
                            </span>
                          )}
                        </div>

                        <div className="flex items-center space-x-2">
                          <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500">
                            {turn.timestamp}
                          </span>
                          <button
                            onClick={() => handleCopyTurn(turn.id, turn.content)}
                            className="text-slate-400 hover:text-slate-200 opacity-0 group-hover:opacity-100 transition-opacity"
                            title="Copy turn text"
                          >
                            {copiedTurnId === turn.id ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                          </button>
                        </div>
                      </div>

                      <p className="text-slate-900 dark:text-slate-100 font-sans leading-relaxed font-medium">
                        {turn.content}
                      </p>

                      {/* Turn Audio WAV Player */}
                      {turn.wav_file && (
                        <div className="mt-2.5 pt-2 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between">
                          <button
                            onClick={() => handlePlayAudio(turn.wav_file!)}
                            className="flex items-center space-x-2 px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-semibold transition-all"
                          >
                            {playingWav === turn.wav_file ? (
                              <>
                                <Pause className="w-3.5 h-3.5 animate-pulse" />
                                <span>Pause Audio</span>
                              </>
                            ) : (
                              <>
                                <Play className="w-3.5 h-3.5" />
                                <span>Play Recorded Audio</span>
                              </>
                            )}
                          </button>
                          <span className="text-[10px] font-mono text-slate-400 dark:text-slate-500 truncate max-w-[200px]">
                            {turn.wav_file}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                ))
              )}
              <div ref={transcriptEndRef} />
            </div>
          ) : (
            /* System Event Feed Tab */
            <div className="flex-1 overflow-y-auto space-y-2 pr-2 font-mono text-xs custom-scrollbar">
              {logs.length === 0 ? (
                <div className="text-slate-500 py-20 text-center">
                  <Terminal className="w-8 h-8 text-slate-600 mx-auto mb-2" />
                  <p>No system events recorded yet.</p>
                </div>
              ) : (
                logs.map((log, i) => (
                  <div key={i} className="p-2.5 rounded-lg bg-slate-900/80 border border-slate-800 flex items-start space-x-2 text-slate-300">
                    <span className="text-slate-500 text-[10px] shrink-0 mt-0.5">{log.timestamp || 'Live'}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                      log.event_type === 'USER_UTTERANCE' ? 'bg-sky-500/20 text-sky-400' :
                      log.event_type === 'AI_RESPONSE' ? 'bg-emerald-500/20 text-emerald-400' :
                      log.event_type === 'CALL_STARTED' ? 'bg-purple-500/20 text-purple-400' :
                      'bg-slate-800 text-slate-400'
                    }`}>
                      {log.event_type}
                    </span>
                    <span className="break-all font-sans text-slate-200">{log.raw || JSON.stringify(log.payload)}</span>
                  </div>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Start Test Call Modal */}
      {showTestCallModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="glass-panel p-6 rounded-2xl border border-slate-700 dark:border-slate-800 bg-white dark:bg-dark-800 max-w-md w-full shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
                <PhoneForwarded className="w-5 h-5 text-brand-500" />
                <span>Start Test Call & Live Transcribe</span>
              </h3>
              <button
                onClick={() => setShowTestCallModal(false)}
                className="text-slate-400 hover:text-slate-200 text-sm font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  Target Phone Number / SIP Extension
                </label>
                <input
                  type="text"
                  value={testPhone}
                  onChange={(e) => setTestPhone(e.target.value)}
                  placeholder="+919876543210 or 100"
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
