import React, { useState, useRef } from 'react';
import { Mic, Play, Volume2, Activity, Zap, Cpu, Upload, Square, Radio, FileText, CheckCircle2, Clock } from 'lucide-react';

export const VoiceStudioPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'tts' | 'stt'>('tts');

  // TTS Synthesis States
  const [text, setText] = useState('Namaste! Welcome to Superfone AI Voice Operations Platform.');
  const [voice, setVoice] = useState('cartesia_hi_female');
  const [speed, setSpeed] = useState(1.0);
  const [gain, setGain] = useState(0.0);
  const [loading, setLoading] = useState(false);
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<Record<string, string> | null>(null);

  // STT Transcription States
  const [isRecording, setIsRecording] = useState(false);
  const [sttLoading, setSttLoading] = useState(false);
  const [recordedAudioUrl, setRecordedAudioUrl] = useState<string | null>(null);
  const [transcriptResult, setTranscriptResult] = useState<{
    text: string;
    confidence: number;
    latency_ms: number;
    stt_engine: string;
    audio_bytes: number;
  } | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  // TTS Handler
  const handleSynthesize = async () => {
    if (!text.trim()) {
      alert('Please enter text to synthesize.');
      return;
    }
    setLoading(true);
    setAudioUrl(null);
    setMetrics(null);

    try {
      const resp = await fetch('/api/v1/voice/synthesize', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, voice, speed, volume_gain_db: gain })
      });

      if (!resp.ok) throw new Error('Synthesis failed');

      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      setAudioUrl(url);

      const m: Record<string, string> = {};
      ['X-Duration-Sec', 'X-Latency-MS', 'X-RTF', 'X-RMS-DBFS', 'X-Peak'].forEach(h => {
        const val = resp.headers.get(h);
        if (val) m[h] = val;
      });
      setMetrics(m);
    } catch (ex: any) {
      alert(`Synthesis Error: ${ex.message}`);
    } finally {
      setLoading(false);
    }
  };

  // STT Audio Upload Handler
  const handleFileUpload = async (file: File) => {
    setSttLoading(true);
    setTranscriptResult(null);

    const localUrl = URL.createObjectURL(file);
    setRecordedAudioUrl(localUrl);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const resp = await fetch('/api/v1/voice/transcribe', {
        method: 'POST',
        body: formData
      });

      if (!resp.ok) throw new Error('Transcription failed');
      const data = await resp.json();
      setTranscriptResult(data);
    } catch (ex: any) {
      alert(`Transcription Error: ${ex.message}`);
    } finally {
      setSttLoading(false);
    }
  };

  // Live Microphone Recording Toggle
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const recorder = new MediaRecorder(stream);
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      recorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/wav' });
        const localUrl = URL.createObjectURL(audioBlob);
        setRecordedAudioUrl(localUrl);

        const file = new File([audioBlob], 'mic_input.wav', { type: 'audio/wav' });
        handleFileUpload(file);

        // Stop all mic tracks
        stream.getTracks().forEach(t => t.stop());
      };

      recorder.start();
      setIsRecording(true);
    } catch (err: any) {
      alert(`Microphone access error: ${err.message}`);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Top Banner & Mode Toggle */}
      <div className="glass-panel p-4 md:p-6 rounded-2xl border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg md:text-xl font-bold text-slate-100 flex items-center space-x-2">
            <Mic className="w-5 h-5 text-brand-500 shrink-0" />
            <span>Voice & Audio Calibration Studio</span>
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-1">
            Speech Synthesis (TTS) & Real-time Speech-To-Text (STT) Transcription testing with latency telemetry.
          </p>
        </div>

        {/* Tab Selector Buttons */}
        <div className="flex bg-slate-900/80 p-1 rounded-xl border border-slate-800 shrink-0">
          <button
            onClick={() => setActiveTab('tts')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold flex items-center space-x-2 transition-all ${
              activeTab === 'tts'
                ? 'bg-brand-600 text-white shadow-lg shadow-brand-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Volume2 className="w-4 h-4" />
            <span>🗣️ TTS Voice Synthesis</span>
          </button>
          <button
            onClick={() => setActiveTab('stt')}
            className={`px-4 py-2 rounded-lg text-xs font-semibold flex items-center space-x-2 transition-all ${
              activeTab === 'stt'
                ? 'bg-brand-600 text-white shadow-lg shadow-brand-600/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Mic className="w-4 h-4" />
            <span>🎙️ STT Speech Transcription</span>
          </button>
        </div>
      </div>

      {activeTab === 'tts' ? (
        /* TTS SYNTHESIS TAB */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Synthesis Form */}
          <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
            <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-3">Synthesis Parameters</h3>

            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Language & Voice Model</label>
                <select
                  value={voice}
                  onChange={(e) => setVoice(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-xs"
                >
                  <optgroup label="☁️ Cloud Primary (Cartesia Sonic / Deepgram Aura)">
                    <option value="deepgram_aura_asteria">Deepgram Aura Asteria (Cloud Neural - Recommended)</option>
                    <option value="cartesia_hi_female">Hindi Female (hi-IN) — Cartesia Cloud Primary</option>
                    <option value="cartesia_hinglish_female">Hinglish Female (hinglish-IN) — Cartesia Cloud Primary</option>
                    <option value="cartesia_en_in_female">English India (en-IN) — Cartesia Cloud Primary</option>
                    <option value="cartesia_en_us_female">English US (en-US) — Cartesia Cloud Primary</option>
                  </optgroup>
                  <optgroup label="🖥️ Local Edge Backup (ONNX / Neural)">
                    <option value="hi_pratham">Piper Hindi Pratham (22kHz native ONNX)</option>
                    <option value="af_sarah">Kokoro Sarah (24kHz Neural)</option>
                    <option value="am_adam">Kokoro Adam (24kHz Male Neural)</option>
                  </optgroup>
                </select>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Spoken Input Text</label>
                <textarea
                  rows={4}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="Enter text to synthesize into spoken audio..."
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-slate-200 focus:outline-none focus:border-brand-500 text-xs"
                ></textarea>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Speech Speed Ratio ({speed}x)</label>
                <input
                  type="range"
                  min={0.5}
                  max={2.0}
                  step={0.1}
                  value={speed}
                  onChange={(e) => setSpeed(parseFloat(e.target.value))}
                  className="w-full accent-brand-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Volume Gain dB ({gain} dB)</label>
                <input
                  type="range"
                  min={-12}
                  max={12}
                  step={0.5}
                  value={gain}
                  onChange={(e) => setGain(parseFloat(e.target.value))}
                  className="w-full accent-brand-500"
                />
              </div>

              <button
                onClick={handleSynthesize}
                disabled={loading}
                className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-medium text-xs transition-colors shadow-lg shadow-brand-600/20 active:scale-95"
              >
                <Play className="w-4 h-4" />
                <span>{loading ? 'Synthesizing Audio...' : 'Generate & Test Voice'}</span>
              </button>
            </div>
          </div>

          {/* Audio Output & Telemetry */}
          <div className="lg:col-span-2 glass-panel p-5 rounded-2xl border border-slate-800 space-y-4 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-3">Audio Waveform & Performance Metrics</h3>

              {audioUrl ? (
                <div className="space-y-6 mt-4">
                  {/* Custom Audio Player */}
                  <div className="glass-card p-4 rounded-xl border border-brand-500/30">
                    <audio controls src={audioUrl} className="w-full" autoPlay />
                  </div>

                  {/* Metrics Grid */}
                  {metrics && (
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                      <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                        <span className="text-[11px] text-slate-400 block">Duration</span>
                        <span className="text-lg font-bold text-slate-100">{metrics['X-Duration-Sec']}s</span>
                      </div>

                      <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                        <span className="text-[11px] text-slate-400 block">Synthesis Latency</span>
                        <span className="text-lg font-bold text-emerald-400">{metrics['X-Latency-MS']} ms</span>
                      </div>

                      <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                        <span className="text-[11px] text-slate-400 block">Real-Time Factor</span>
                        <span className="text-lg font-bold text-brand-400">{metrics['X-RTF']} RTF</span>
                      </div>

                      <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                        <span className="text-[11px] text-slate-400 block">RMS Amplitude</span>
                        <span className="text-lg font-bold text-sky-400">{metrics['X-RMS-DBFS']} dBFS</span>
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="py-20 text-center text-slate-500 text-xs italic">
                  Click "Generate & Test Voice" to synthesize audio and display live RTF/RMS metrics
                </div>
              )}
            </div>
          </div>
        </div>
      ) : (
        /* STT TRANSCRIPTION TAB */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 md:gap-6">
          {/* Audio Input Panel */}
          <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-5">
            <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-3 flex items-center justify-between">
              <span>Speech Input Source</span>
              <span className="text-[10px] text-emerald-400 font-mono bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/20">
                Groq + Deepgram STT
              </span>
            </h3>

            {/* Live Mic Recording Control */}
            <div className="glass-card p-4 rounded-xl border border-slate-800 text-center space-y-3">
              <div className="text-xs font-semibold text-slate-300">Live Browser Microphone</div>
              <p className="text-[11px] text-slate-400">Record spoken audio via your browser microphone for live speech-to-text calibration.</p>

              {!isRecording ? (
                <button
                  onClick={startRecording}
                  disabled={sttLoading}
                  className="w-full flex items-center justify-center space-x-2 py-3 rounded-xl bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs transition-all shadow-lg shadow-rose-600/20 active:scale-95 disabled:opacity-50"
                >
                  <Radio className="w-4 h-4 animate-pulse" />
                  <span>Start Live Mic Recording</span>
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="w-full flex items-center justify-center space-x-2 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-rose-400 font-bold text-xs border border-rose-500/40 animate-pulse active:scale-95"
                >
                  <Square className="w-4 h-4" />
                  <span>Stop & Transcribe Now</span>
                </button>
              )}
            </div>

            {/* Local File Upload Selector */}
            <div className="glass-card p-4 rounded-xl border border-slate-800 text-center space-y-3">
              <div className="text-xs font-semibold text-slate-300">Upload Speech File</div>
              <p className="text-[11px] text-slate-400">Select any local WAV, MP3, M4A, or WebM audio file for transcription.</p>

              <label className="w-full flex items-center justify-center space-x-2 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs cursor-pointer border border-slate-700 transition-colors">
                <Upload className="w-4 h-4 text-brand-400" />
                <span>Choose Audio File</span>
                <input
                  type="file"
                  accept="audio/*"
                  className="hidden"
                  onChange={(e) => {
                    if (e.target.files && e.target.files[0]) {
                      handleFileUpload(e.target.files[0]);
                    }
                  }}
                />
              </label>
            </div>
          </div>

          {/* Transcript Output & Telemetry */}
          <div className="lg:col-span-2 glass-panel p-5 rounded-2xl border border-slate-800 space-y-4 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-200 border-b border-slate-800 pb-3 flex items-center justify-between">
                <span className="flex items-center space-x-2">
                  <FileText className="w-4 h-4 text-brand-500" />
                  <span>Real-Time Speech Transcript & Engine Metrics</span>
                </span>
                {transcriptResult && (
                  <span className="text-[10px] font-mono text-slate-400">
                    Engine: <span className="text-brand-400 font-semibold">{transcriptResult.stt_engine}</span>
                  </span>
                )}
              </h3>

              {recordedAudioUrl && (
                <div className="mt-4 glass-card p-3 rounded-xl border border-slate-800">
                  <span className="text-[11px] text-slate-400 block mb-1">Source Audio Playback:</span>
                  <audio controls src={recordedAudioUrl} className="w-full" />
                </div>
              )}

              {sttLoading ? (
                <div className="py-20 text-center space-y-3">
                  <div className="w-8 h-8 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mx-auto"></div>
                  <div className="text-xs font-semibold text-brand-400 animate-pulse">Transcribing speech with Cloud STT engine...</div>
                </div>
              ) : transcriptResult ? (
                <div className="space-y-5 mt-4">
                  {/* Transcript Output Card */}
                  <div className="glass-card p-4 rounded-xl border border-brand-500/30 bg-brand-500/5 space-y-2">
                    <div className="flex items-center justify-between text-xs text-brand-400 font-semibold border-b border-brand-500/20 pb-2">
                      <span className="flex items-center space-x-1.5">
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        <span>Captured Transcript Text</span>
                      </span>
                      <span>{transcriptResult.text.split(/\s+/).filter(Boolean).length} words</span>
                    </div>
                    <p className="text-sm text-slate-100 font-sans leading-relaxed pt-1">
                      "{transcriptResult.text}"
                    </p>
                  </div>

                  {/* Telemetry Metrics Grid */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                    <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                      <span className="text-[11px] text-slate-400 block">STT Latency</span>
                      <span className="text-lg font-bold text-emerald-400">{transcriptResult.latency_ms} ms</span>
                    </div>

                    <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                      <span className="text-[11px] text-slate-400 block">Confidence</span>
                      <span className="text-lg font-bold text-brand-400">{Math.round(transcriptResult.confidence * 100)}%</span>
                    </div>

                    <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                      <span className="text-[11px] text-slate-400 block">Payload Size</span>
                      <span className="text-lg font-bold text-sky-400">{Math.round(transcriptResult.audio_bytes / 1024)} KB</span>
                    </div>

                    <div className="glass-card p-3 rounded-xl border border-slate-800 text-center">
                      <span className="text-[11px] text-slate-400 block">Target Language</span>
                      <span className="text-lg font-bold text-purple-400">Hindi / English</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="py-20 text-center text-slate-500 text-xs italic">
                  Record live microphone audio or choose a speech file to generate real-time transcript & latency metrics.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VoiceStudioPage;
