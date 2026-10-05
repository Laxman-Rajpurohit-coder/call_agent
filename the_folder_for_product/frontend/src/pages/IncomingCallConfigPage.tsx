import React, { useState, useEffect } from 'react';
import { AgentSession } from '../types';
import { Settings, PhoneIncoming, MessageSquare, Bot, Cpu, X, Save, Clock, PhoneForwarded } from 'lucide-react';

interface IncomingCallConfigPageProps {
  agentSession: AgentSession | null;
}

export const IncomingCallConfigPage: React.FC<IncomingCallConfigPageProps> = ({ agentSession }) => {
  const [configs, setConfigs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Modal State
  const [isEditing, setIsEditing] = useState(false);
  const [editForm, setEditForm] = useState<any>(null);

  useEffect(() => {
    fetchConfigs();
  }, []);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/v1/incoming-configs');
      if (res.ok) {
        const data = await res.json();
        setConfigs(data);
      }
    } catch (err) {
      console.error('Failed to fetch incoming configs', err);
    }
    setLoading(false);
  };

  const handleCreateConfig = async () => {
    try {
      const res = await fetch('/api/v1/incoming-configs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: 'Org Default Configuration',
          phone_number_id: null,
          ai_name: 'Ananya',
          ai_model: 'gpt-4o',
          primary_language: 'en'
        })
      });
      if (res.ok) {
        fetchConfigs();
      } else {
        const error = await res.json();
        alert('Failed to create config: ' + (error.detail || 'Unknown error'));
      }
    } catch (err) {
      console.error(err);
      alert('Error creating config');
    }
  };

  const openEditModal = async (configId: string) => {
    try {
      const res = await fetch(`/api/v1/incoming-configs/${configId}`);
      if (res.ok) {
        const data = await res.json();
        setEditForm(data);
        setIsEditing(true);
      }
    } catch(err) {
      console.error(err);
    }
  };

  const handleSaveConfig = async () => {
    try {
      const { id, config_version, created_at, updated_at, ...updateData } = editForm;
      
      const res = await fetch(`/api/v1/incoming-configs/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expected_config_version: config_version,
          ...updateData
        })
      });
      if (res.ok) {
        setIsEditing(false);
        setEditForm(null);
        fetchConfigs();
      } else {
        const error = await res.json();
        alert('Failed to save config: ' + (error.detail || 'Unknown error'));
      }
    } catch (err) {
      console.error(err);
      alert('Error saving config');
    }
  };

  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    setEditForm((prev: any) => ({ ...prev, [name]: value }));
  };

  return (
    <div className="p-4 md:p-8 max-w-7xl mx-auto space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center space-x-2">
            <PhoneIncoming className="w-6 h-6 text-indigo-400" />
            <span>AI Incoming Call Routing</span>
          </h1>
          <p className="text-slate-400 mt-1">Configure AI inbound agents, voices, prompts, and CRM behaviors.</p>
        </div>
        <button 
          onClick={handleCreateConfig}
          className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium rounded-lg shadow-lg shadow-indigo-500/20 transition-all active:scale-95 flex items-center space-x-2"
        >
          <span>+ Create Organization Default</span>
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {loading ? (
          <div className="text-slate-400">Loading configurations...</div>
        ) : configs.length === 0 ? (
          <div className="col-span-full p-8 border border-slate-700/50 rounded-xl bg-slate-800/30 text-center text-slate-400">
            No configurations found. Click above to create the Organization Default config.
          </div>
        ) : (
          configs.map((c) => (
            <div key={c.id} className="p-5 bg-slate-800/50 border border-slate-700/50 rounded-xl hover:border-indigo-500/30 transition-colors group relative overflow-hidden">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <Bot className="w-16 h-16 text-indigo-400" />
              </div>
              <div className="relative z-10">
                <div className="flex justify-between items-start mb-4">
                  <h3 className="font-bold text-white text-lg">
                    {c.name}
                  </h3>
                  <span className={`px-2 py-0.5 text-[10px] font-bold tracking-wide uppercase rounded-full ${c.is_active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-slate-500/10 text-slate-400 border border-slate-500/20'}`}>
                    {c.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
                
                <div className="space-y-3 text-sm text-slate-300 mb-6">
                  <div className="flex items-center space-x-2">
                    <Cpu className="w-4 h-4 text-slate-500" />
                    <span><span className="text-slate-500 mr-1">AI Model:</span> <span className="font-medium text-indigo-300">{c.ai_model}</span></span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <MessageSquare className="w-4 h-4 text-slate-500" />
                    <span><span className="text-slate-500 mr-1">AI Name:</span> {c.ai_name}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Clock className="w-4 h-4 text-slate-500" />
                    <span><span className="text-slate-500 mr-1">Version:</span> v{c.config_version}</span>
                  </div>
                </div>

                <div className="flex items-center space-x-2 pt-4 border-t border-slate-700/50">
                  <button 
                    onClick={() => openEditModal(c.id)}
                    className="flex-1 px-3 py-2 bg-indigo-600/20 hover:bg-indigo-600/40 text-indigo-300 hover:text-white text-xs font-bold rounded-lg transition-colors flex items-center justify-center space-x-1.5"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    <span>Configure AI</span>
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Full Edit Modal */}
      {isEditing && editForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
          <div className="absolute inset-0 bg-slate-950/80 backdrop-blur-sm" onClick={() => setIsEditing(false)}></div>
          <div className="relative w-full max-w-4xl max-h-[90vh] bg-slate-900 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            
            <div className="p-5 border-b border-slate-800 flex items-center justify-between bg-slate-800/50 shrink-0">
              <div className="flex items-center space-x-3">
                <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center border border-indigo-500/30">
                  <Bot className="w-5 h-5 text-indigo-400" />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-white">Configure: {editForm.name}</h2>
                  <p className="text-xs text-indigo-400 font-mono">v{editForm.config_version} • {editForm.id}</p>
                </div>
              </div>
              <button onClick={() => setIsEditing(false)} className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-700 transition-colors">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto flex-1 space-y-8">
              
              {/* Section 1: Core AI Identity */}
              <section className="space-y-4">
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider border-b border-slate-800 pb-2 flex items-center space-x-2">
                  <Bot className="w-4 h-4 text-emerald-400" />
                  <span>1. AI Voice & Identity</span>
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">AI Model Engine</label>
                    <select name="ai_model" value={editForm.ai_model || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none">
                      <option value="gpt-4o">GPT-4 Omni (Fastest)</option>
                      <option value="claude-3-haiku">Claude 3 Haiku (Conversational)</option>
                      <option value="qwen/qwen3.8-27b">Qwen 27B (Groq/Fast)</option>
                      <option value="crestina-v2">Crestina v2 (Custom Tuning)</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">AI Name</label>
                    <input type="text" name="ai_name" value={editForm.ai_name || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none" placeholder="e.g. Ananya" />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Voice Provider</label>
                    <select name="voice_provider" value={editForm.voice_provider || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none">
                      <option value="cartesia">Cartesia Sonic</option>
                      <option value="elevenlabs">ElevenLabs</option>
                      <option value="deepgram">Deepgram Aura</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Voice ID / Accent</label>
                    <input type="text" name="voice_id" value={editForm.voice_id || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none" placeholder="e.g. cartesia_hi_sonic (Hindi/Indian Accent)" />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Primary Language</label>
                    <select name="primary_language" value={editForm.primary_language || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none">
                      <option value="en">English (US/UK)</option>
                      <option value="en-IN">English (Indian)</option>
                      <option value="hi">Hindi</option>
                      <option value="hinglish">Hinglish</option>
                      <option value="marwadi">Marwadi (मारवाड़ी)</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Speaking Style</label>
                    <select name="speaking_style" value={editForm.speaking_style || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none">
                      <option value="Friendly">Friendly & Welcoming</option>
                      <option value="Professional">Professional & Corporate</option>
                      <option value="Empathetic">Empathetic & Supportive</option>
                    </select>
                  </div>
                </div>
              </section>

              {/* Section 2: Instructions & Prompt */}
              <section className="space-y-4">
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider border-b border-slate-800 pb-2 flex items-center space-x-2">
                  <MessageSquare className="w-4 h-4 text-blue-400" />
                  <span>2. Prompting & Behavior</span>
                </h3>
                <div className="space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Role Description</label>
                    <input type="text" name="role_description" value={editForm.role_description || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none" placeholder="e.g. Senior Sales Representative for XYZ Corp" />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Primary Objective</label>
                    <input type="text" name="primary_objective" value={editForm.primary_objective || ''} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none" placeholder="e.g. Qualify the lead and book a meeting on the calendar." />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">System Instructions (Custom Prompt Tuning)</label>
                    <textarea 
                      name="system_instructions" 
                      value={editForm.system_instructions || ''} 
                      onChange={handleFormChange} 
                      rows={5}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none font-mono text-xs" 
                      placeholder="Enter specific behaviors, rules, or exact phrasing the AI must follow..."
                    ></textarea>
                    <p className="text-[10px] text-slate-500">This overrides the base model behaviors to tightly fit your organization's specific needs.</p>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">FAQ / Knowledge Base</label>
                    <textarea 
                      name="faq_knowledge_base" 
                      value={editForm.faq_knowledge_base || ''} 
                      onChange={handleFormChange} 
                      rows={4}
                      className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none font-mono text-xs" 
                      placeholder="Q: What are your hours? A: We are open 9am to 5pm..."
                    ></textarea>
                  </div>
                </div>
              </section>

              {/* Section 3: Telephony & Call Flow */}
              <section className="space-y-4">
                <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider border-b border-slate-800 pb-2 flex items-center space-x-2">
                  <PhoneForwarded className="w-4 h-4 text-orange-400" />
                  <span>3. Telephony & Routing Rules</span>
                </h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Outside Hours Action</label>
                    <select name="outside_hours_action" value={editForm.outside_hours_action || 'continue_ai'} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none">
                      <option value="continue_ai">Let AI Handle Call</option>
                      <option value="voicemail">Send to Voicemail</option>
                      <option value="schedule_callback">Schedule Callback</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Ring Strategy (Agent Handoff)</label>
                    <select name="ring_strategy" value={editForm.ring_strategy || 'first_available'} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none">
                      <option value="first_available">First Available Agent</option>
                      <option value="round_robin">Round Robin</option>
                      <option value="team_parallel">Ring All Parallel</option>
                    </select>
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-400">Temperature (Creativity)</label>
                    <input type="number" step="0.1" min="0" max="1" name="temperature" value={editForm.temperature !== undefined ? editForm.temperature : 0.3} onChange={handleFormChange} className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white focus:border-indigo-500 outline-none" />
                  </div>
                </div>
              </section>

            </div>

            <div className="p-4 border-t border-slate-800 bg-slate-900 flex justify-end space-x-3 shrink-0">
              <button 
                onClick={() => setIsEditing(false)}
                className="px-4 py-2 text-sm font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button 
                onClick={handleSaveConfig}
                className="px-6 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-500/20 rounded-lg transition-all active:scale-95 flex items-center space-x-2"
              >
                <Save className="w-4 h-4" />
                <span>Save Configuration</span>
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
};
