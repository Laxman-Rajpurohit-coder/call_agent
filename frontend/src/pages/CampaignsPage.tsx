import React, { useState } from 'react';
import { Megaphone, Play, Plus, PhoneCall, CheckCircle2, Clock, Zap, Mic } from 'lucide-react';
import { Campaign } from '../types';

interface CampaignsPageProps {
  campaigns: Campaign[];
  onCreateCampaign: (campaign: any) => void;
  onStartCampaign: (id: string) => void;
}

export const CampaignsPage: React.FC<CampaignsPageProps> = ({ campaigns, onCreateCampaign, onStartCampaign }) => {
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState('');
  const [type, setType] = useState<'SCRIPT' | 'AI'>('SCRIPT');
  const [scriptContent, setScriptContent] = useState('');
  const [voiceModel, setVoiceModel] = useState('hi_pratham');
  const [concurrency, setConcurrency] = useState(5);

  // Edit Campaign Script States
  const [editingCampaign, setEditingCampaign] = useState<Campaign | null>(null);
  const [editScript, setEditScript] = useState('');
  const [editVoice, setEditVoice] = useState('hi_pratham');

  const handleOpenEdit = (c: Campaign) => {
    setEditingCampaign(c);
    setEditScript(c.script_content || '');
    setEditVoice(c.voice_model || 'hi_pratham');
  };

  const handleSaveEdit = async () => {
    if (!editingCampaign) return;
    try {
      await fetch(`/api/v1/campaigns/${editingCampaign.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          script_content: editScript,
          voice_model: editVoice
        })
      });
      setEditingCampaign(null);
      window.location.reload();
    } catch (e) {
      alert("Failed to update campaign script.");
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onCreateCampaign({
      name,
      type,
      script_content: scriptContent,
      max_concurrency: concurrency,
      voice_model: voiceModel
    });
    setShowModal(false);
    setName('');
    setScriptContent('');
    setVoiceModel('hi_pratham');
  };

  return (
    <div className="space-y-4 md:space-y-6">
      {/* Top Banner */}
      <div className="glass-panel p-4 md:p-6 rounded-2xl border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg md:text-xl font-bold text-slate-100 flex items-center space-x-2">
            <Megaphone className="w-5 h-5 text-brand-500 shrink-0" />
            <span>Campaign & Auto Calling Engine</span>
          </h2>
          <p className="text-xs md:text-sm text-slate-400 mt-1">Script-based & AI-driven batch outreach campaigns with queue concurrency manager.</p>
        </div>

        <button
          onClick={() => setShowModal(true)}
          className="flex items-center justify-center space-x-2 px-4 py-2.5 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-xs transition-colors shadow-lg shadow-brand-600/20 shrink-0"
        >
          <Plus className="w-4 h-4" />
          <span>New Campaign</span>
        </button>
      </div>

      {/* Campaigns Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 md:gap-6">
        {campaigns.map((c) => (
          <div key={c.id} className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4 flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-semibold uppercase ${
                  c.status === 'RUNNING' ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' :
                  c.status === 'COMPLETED' ? 'bg-brand-500/10 text-brand-400 border border-brand-500/20' :
                  'bg-slate-800 text-slate-400'
                }`}>
                  {c.status}
                </span>
                <span className="text-xs font-mono text-slate-500">{c.type} Mode</span>
              </div>

              <h3 className="text-base font-bold text-slate-100">{c.name}</h3>
              <p className="text-xs text-slate-400 mt-1 line-clamp-2">{c.script_content || 'No custom script attached'}</p>
            </div>

            <div className="space-y-3 pt-3 border-t border-slate-800/80">
              <div className="flex items-center justify-between text-xs text-slate-400">
                <span className="flex items-center space-x-1">
                  <Mic className="w-3.5 h-3.5 text-brand-400" />
                  <span>Voice Model</span>
                </span>
                <span className="font-semibold text-brand-400 font-mono bg-brand-500/10 px-2 py-0.5 rounded border border-brand-500/20">
                  {c.voice_model || 'hi_pratham'}
                </span>
              </div>

              <div className="flex justify-between text-xs text-slate-400">
                <span>Concurrency Limit</span>
                <span className="font-semibold text-slate-200">{c.max_concurrency} workers</span>
              </div>

              <div className="flex space-x-2">
                <button
                  type="button"
                  onClick={() => handleOpenEdit(c)}
                  className="flex-1 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs border border-slate-700"
                >
                  ✏️ Edit Script
                </button>
                {c.status !== 'RUNNING' && c.status !== 'COMPLETED' ? (
                  <button
                    onClick={() => onStartCampaign(c.id)}
                    className="flex-1 flex items-center justify-center space-x-2 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-colors shadow-lg shadow-emerald-600/20"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>Start</span>
                  </button>
                ) : (
                  <div className="flex-1 text-center py-2 text-xs font-medium text-emerald-400 bg-emerald-500/10 rounded-xl border border-emerald-500/20">
                    {c.status === 'RUNNING' ? 'Active' : 'Finished'}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-panel p-6 rounded-2xl border border-slate-800 w-full max-w-lg space-y-4">
            <h3 className="text-lg font-bold text-slate-100">Create New Campaign</h3>
            
            <form onSubmit={handleSubmit} className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-300 font-medium mb-1">Campaign Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Event Announcement Campaign"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Outreach Mode</label>
                  <select
                    value={type}
                    onChange={(e: any) => setType(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                  >
                    <option value="SCRIPT">Script Calling (Predefined)</option>
                    <option value="AI">AI Agent Conversation</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-300 font-medium mb-1 flex items-center space-x-1">
                    <Mic className="w-3.5 h-3.5 text-brand-400" />
                    <span>Neural Voice Model</span>
                  </label>
                  <select
                    value={voiceModel}
                    onChange={(e) => setVoiceModel(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                  >
                    <optgroup label="⚡ Cloud Ultra-Realistic Voices (Cartesia / Deepgram / ElevenLabs / OpenAI)">
                      <option value="cartesia_hi_sonic">⚡ Cartesia Cloud — Hindi Sonic (Ultra-Realistic & Low Latency)</option>
                      <option value="cartesia_hi_female">⚡ Cartesia Cloud — Hindi Female (hi-IN)</option>
                      <option value="cartesia_en_sonic">⚡ Cartesia Cloud — English Sonic (Ultra-Realistic)</option>
                      <option value="deepgram_aura_asteria">⚡ Deepgram Cloud — Aura Asteria (Female)</option>
                      <option value="deepgram_aura_orion">⚡ Deepgram Cloud — Aura Orion (Male)</option>
                      <option value="elevenlabs_multilingual">⚡ ElevenLabs Cloud — Multilingual Studio Voice</option>
                      <option value="openai_alloy">⚡ OpenAI Cloud — Alloy (Neutral)</option>
                      <option value="openai_echo">⚡ OpenAI Cloud — Echo (Male Clear)</option>
                      <option value="openai_nova">⚡ OpenAI Cloud — Nova (Female Warm)</option>
                      <option value="openai_shimmer">⚡ OpenAI Cloud — Shimmer (Female Expressive)</option>
                    </optgroup>
                    <optgroup label="🇮🇳 Regional Indian Languages (Cartesia Cloud)">
                      <option value="cartesia_ta_female">🇮🇳 Cartesia — Tamil Female (ta-IN)</option>
                      <option value="cartesia_te_female">🇮🇳 Cartesia — Telugu Female (te-IN)</option>
                      <option value="cartesia_bn_female">🇮🇳 Cartesia — Bengali Female (bn-IN)</option>
                      <option value="cartesia_mr_female">🇮🇳 Cartesia — Marathi Female (mr-IN)</option>
                      <option value="cartesia_gu_female">🇮🇳 Cartesia — Gujarati Female (gu-IN)</option>
                      <option value="cartesia_kn_female">🇮🇳 Cartesia — Kannada Female (kn-IN)</option>
                      <option value="cartesia_ml_female">🇮🇳 Cartesia — Malayalam Female (ml-IN)</option>
                      <option value="cartesia_pa_female">🇮🇳 Cartesia — Punjabi Female (pa-IN)</option>
                      <option value="cartesia_ur_female">🇮🇳 Cartesia — Urdu Female (ur-IN)</option>
                    </optgroup>
                    <optgroup label="🧠 Kokoro-82M Neural On-Premise (Fast Local)">
                      <option value="af_sarah">🧠 Kokoro Neural — Sarah (Female 24kHz)</option>
                      <option value="am_adam">🧠 Kokoro Neural — Adam (Male 24kHz)</option>
                    </optgroup>
                    <optgroup label="🏠 Local On-Premise Offline Voices">
                      <option value="hi_pratham">🏠 Local On-Premise — Hindi Pratham (Male Outreach)</option>
                      <option value="hi_aditi">🏠 Local On-Premise — Hindi Aditi (Female Clear)</option>
                      <option value="en_sarah">🏠 Local On-Premise — English Sarah (Female)</option>
                      <option value="en_bella">🏠 Local On-Premise — English Bella (Female Expressive)</option>
                      <option value="en_michael">🏠 Local On-Premise — English Michael (Male)</option>
                    </optgroup>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Spoken Script / Prompt Text</label>
                <textarea
                  rows={4}
                  required
                  placeholder="Type your campaign script text here..."
                  value={scriptContent}
                  onChange={(e) => setScriptContent(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-slate-200 focus:outline-none focus:border-brand-500 text-sm"
                ></textarea>
              </div>

              <div>
                <label className="block text-slate-300 font-medium mb-1">Max Queue Concurrency ({concurrency} parallel slots)</label>
                <input
                  type="range"
                  min={1}
                  max={20}
                  value={concurrency}
                  onChange={(e) => setConcurrency(parseInt(e.target.value))}
                  className="w-full accent-brand-500"
                />
              </div>

              <div className="flex justify-end space-x-3 pt-2">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 font-medium text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white font-medium text-xs shadow-lg shadow-brand-600/20"
                >
                  Create & Load Contacts
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Script Modal */}
      {editingCampaign && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="glass-panel w-full max-w-lg p-6 rounded-2xl border border-slate-800 space-y-4">
            <h3 className="text-lg font-bold text-slate-100">✏️ Edit Campaign Script</h3>
            <div>
              <label className="block text-slate-300 font-medium mb-1 text-xs">Neural Voice Model</label>
              <select
                value={editVoice}
                onChange={(e) => setEditVoice(e.target.value)}
                className="w-full bg-slate-900 border border-slate-800 rounded-xl p-2.5 text-slate-200 text-xs focus:outline-none focus:border-brand-500"
              >
                <option value="deepgram_aura_asteria">Deepgram Aura Asteria (Cloud Neural)</option>
                <option value="cartesia_hi_sonic">Cartesia Hindi Sonic (Cloud Neural)</option>
                <option value="hi_female">Kokoro Female Sarah (Local ONNX)</option>
                <option value="hi_pratham">Piper Hindi Pratham (Local)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1 text-xs">Spoken Campaign Script</label>
              <textarea
                rows={5}
                value={editScript}
                onChange={(e) => setEditScript(e.target.value)}
                placeholder="Type your new custom campaign script text here..."
                className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-slate-200 text-xs focus:outline-none focus:border-brand-500"
              />
            </div>
            <div className="flex justify-end space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setEditingCampaign(null)}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 text-xs font-medium"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                className="px-5 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-white text-xs font-bold shadow-lg shadow-brand-600/20"
              >
                Save Updated Script
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
