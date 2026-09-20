import React, { useState, useRef, useEffect } from 'react';
import { Bot, User, Play, Pause, Copy, Check, Search, Download, Terminal, Volume2 } from 'lucide-react';
import { TranscriptTurn } from '../../types';

interface TranscriptProps {
  turns: TranscriptTurn[];
  callId?: string;
  autoScroll?: boolean;
  onToggleAutoScroll?: () => void;
}

export const Transcript: React.FC<TranscriptProps> = ({
  turns,
  callId,
  autoScroll = true,
  onToggleAutoScroll
}) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [speakerFilter, setSpeakerFilter] = useState<'ALL' | 'USER' | 'AI'>('ALL');
  const [playingWav, setPlayingWav] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const scrollEndRef = useRef<HTMLDivElement | null>(null);

  // Filtered turns
  const filteredTurns = turns.filter(turn => {
    const matchesSearch = turn.text.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSpeaker = speakerFilter === 'ALL' || turn.speaker === speakerFilter;
    return matchesSearch && matchesSpeaker;
  });

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollEndRef.current) {
      scrollEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [filteredTurns.length, autoScroll]);

  // Audio WAV playback
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
    audio.play().catch(err => console.error('Audio playback error:', err));
    audio.onended = () => setPlayingWav(null);
  };

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleDownload = () => {
    const dataStr = 'data:text/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(turns, null, 2));
    const a = document.createElement('a');
    a.href = dataStr;
    a.download = `call_transcript_${callId || 'live'}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  };

  return (
    <div className="flex flex-col h-[580px] bg-slate-900/60 rounded-xl border border-slate-700/50 overflow-hidden">
      {/* Controls Bar */}
      <div className="p-3 border-b border-slate-700/50 bg-slate-950/40 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center space-x-2 flex-1 min-w-[200px]">
          <div className="relative flex-1">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              placeholder="Search transcript..."
              className="w-full pl-8 pr-3 py-1 text-xs rounded-lg bg-slate-900 border border-slate-700 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-brand-500"
            />
          </div>

          <div className="flex items-center bg-slate-900 rounded-lg p-0.5 border border-slate-700">
            {(['ALL', 'USER', 'AI'] as const).map(role => (
              <button
                key={role}
                onClick={() => setSpeakerFilter(role)}
                className={`px-2 py-0.5 text-[10px] font-bold rounded-md transition-all ${
                  speakerFilter === role
                    ? 'bg-brand-500 text-white'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {role}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center space-x-2">
          {onToggleAutoScroll && (
            <button
              onClick={onToggleAutoScroll}
              className={`px-2 py-1 text-[11px] font-bold rounded-lg border transition-all ${
                autoScroll
                  ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
            >
              Auto-Scroll {autoScroll ? 'ON' : 'OFF'}
            </button>
          )}

          <button
            onClick={handleDownload}
            disabled={turns.length === 0}
            className="flex items-center space-x-1 px-2 py-1 text-[11px] font-bold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all disabled:opacity-40"
            title="Download JSON transcript"
          >
            <Download className="w-3 h-3" />
            <span>Export</span>
          </button>
        </div>
      </div>

      {/* Transcript Turn Stream */}
      <div className="flex-1 p-4 overflow-y-auto space-y-3 font-sans">
        {filteredTurns.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 text-xs space-y-2">
            <Terminal className="w-8 h-8 opacity-40" />
            <p>No speech turns recorded yet for this session.</p>
            <p className="text-[10px] opacity-70">Speak into softphone microphone to see live transcript.</p>
          </div>
        ) : (
          filteredTurns.map((turn, index) => {
            const isUser = turn.speaker === 'USER' || turn.role === 'user';
            const isPartial = !!turn.partial;

            return (
              <div
                key={turn.id || `${turn.call_id}-${index}`}
                className={`flex flex-col ${isUser ? 'items-end' : 'items-start'} group`}
              >
                <div className="flex items-center space-x-1.5 mb-1 px-1 text-[10px] text-slate-400 font-mono">
                  {isUser ? (
                    <>
                      <span>{turn.audio_dur_s ? `${turn.audio_dur_s}s` : ''}</span>
                      <span className="font-bold text-sky-400">Caller (User)</span>
                      <User className="w-3 h-3 text-sky-400" />
                    </>
                  ) : (
                    <>
                      <Bot className="w-3 h-3 text-purple-400" />
                      <span className="font-bold text-purple-400">Superfone AI</span>
                      {turn.confidence && <span>({Math.round(turn.confidence * 100)}%)</span>}
                    </>
                  )}
                </div>

                <div
                  className={`relative max-w-[85%] px-3.5 py-2.5 rounded-2xl text-xs leading-relaxed shadow ${
                    isUser
                      ? isPartial
                        ? 'bg-sky-600/60 text-sky-100 border border-sky-400/40 rounded-tr-sm animate-pulse'
                        : 'bg-sky-600/90 text-white rounded-tr-sm border border-sky-500/50'
                      : isPartial
                      ? 'bg-purple-900/60 text-purple-100 border border-purple-500/40 rounded-tl-sm animate-pulse'
                      : 'bg-slate-800 text-slate-100 rounded-tl-sm border border-slate-700'
                  }`}
                >
                  <p>{turn.text}</p>

                  {isPartial && (
                    <span className="inline-flex items-center space-x-1 mt-1 text-[10px] opacity-75">
                      <span className="w-1.5 h-1.5 rounded-full bg-current animate-ping"></span>
                      <span>transcribing live...</span>
                    </span>
                  )}

                  {/* Actions on hover */}
                  <div className="absolute top-1.5 right-1.5 hidden group-hover:flex items-center space-x-1 bg-black/60 rounded px-1 py-0.5 backdrop-blur">
                    {turn.wav_file && (
                      <button
                        onClick={() => handlePlayAudio(turn.wav_file!)}
                        className="p-1 hover:text-emerald-400 transition-all text-slate-300"
                        title="Listen to recorded audio turn"
                      >
                        {playingWav === turn.wav_file ? (
                          <Pause className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Play className="w-3 h-3" />
                        )}
                      </button>
                    )}

                    <button
                      onClick={() => handleCopy(turn.id, turn.text)}
                      className="p-1 hover:text-brand-400 transition-all text-slate-300"
                      title="Copy text"
                    >
                      {copiedId === turn.id ? (
                        <Check className="w-3 h-3 text-emerald-400" />
                      ) : (
                        <Copy className="w-3 h-3" />
                      )}
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
        <div ref={scrollEndRef} />
      </div>
    </div>
  );
};
