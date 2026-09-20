import React, { useState, useEffect } from 'react';
import { Users, PhoneCall, Search, FileText, ChevronRight, Upload, Phone, Clock, Play, X, CheckCircle, AlertCircle, RefreshCw, Copy, Download, Check, ShieldCheck, Activity } from 'lucide-react';
import { CallSession, Contact } from '../types';
import { IncomingCallCard, HandoffOffer } from '../components/IncomingCallCard';

interface CRMPageProps {
  calls: CallSession[];
  contacts: Contact[];
  onImportCSV: (file: File) => void;
  onRefreshData?: () => void;
}

export const CRMPage: React.FC<CRMPageProps> = ({ calls, contacts, onImportCSV, onRefreshData }) => {
  const [selectedCall, setSelectedCall] = useState<CallSession | null>(null);
  const [selectedContact, setSelectedContact] = useState<Contact | null>(null);
  const [contactHistory, setContactHistory] = useState<CallSession[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [transcriptSearch, setTranscriptSearch] = useState('');
  const [copySuccess, setCopySuccess] = useState(false);
  const [activeTab, setActiveTab] = useState<'calls' | 'contacts'>('calls');

  // Agent Presence & Real-Time Call Handoff States
  const [agentId, setAgentId] = useState<string>('agent-101');
  const [presenceStatus, setPresenceStatus] = useState<string>('AVAILABLE');
  const [incomingOffer, setIncomingOffer] = useState<HandoffOffer | null>(null);
  const [handoffToast, setHandoffToast] = useState<string | null>(null);

  // 10s Heartbeat Loop
  useEffect(() => {
    const sendHeartbeat = async () => {
      try {
        await fetch('/api/v1/team/heartbeat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ agent_id: agentId, device_status: 'REGISTERED' })
        });
      } catch (err) {
        console.warn('Agent heartbeat failed:', err);
      }
    };
    sendHeartbeat();
    const interval = setInterval(sendHeartbeat, 10000);
    return () => clearInterval(interval);
  }, [agentId]);

  // Presence Change Handler
  const handlePresenceChange = async (newStatus: string) => {
    setPresenceStatus(newStatus);
    try {
      await fetch('/api/v1/team/presence', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentId, presence_status: newStatus })
      });
    } catch (err) {
      console.error('Failed to update presence:', err);
    }
  };

  // Accept Handoff
  const handleAcceptHandoff = async (callId: string) => {
    try {
      const res = await fetch('/api/v1/calls/handoff/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ call_session_id: callId, agent_id: agentId, idempotency_key: `accept_${callId}_${agentId}` })
      });
      const data = await res.json();
      if (res.ok) {
        setIncomingOffer(null);
        setPresenceStatus('BUSY');
        setHandoffToast(`Connected to Call #${callId}! Customer profile loading...`);
        setTimeout(() => setHandoffToast(null), 4000);
        if (onRefreshData) onRefreshData();
      } else if (res.status === 409) {
        setIncomingOffer(null);
        setHandoffToast('Call was answered by another agent.');
        setTimeout(() => setHandoffToast(null), 4000);
      }
    } catch (err) {
      console.error('Accept handoff failed:', err);
    }
  };

  // Reject Handoff
  const handleRejectHandoff = async (callId: string) => {
    try {
      await fetch('/api/v1/calls/handoff/reject', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ call_session_id: callId, agent_id: agentId })
      });
      setIncomingOffer(null);
    } catch (err) {
      console.error('Reject handoff failed:', err);
    }
  };

  const handleCopyTranscript = (transcript: any[]) => {
    if (!transcript || transcript.length === 0) return;
    const formatted = transcript
      .map(t => `${t.role === 'user' ? 'User' : 'Assistant'}: ${t.content}`)
      .join('\n');
    navigator.clipboard.writeText(formatted);
    setCopySuccess(true);
    setTimeout(() => setCopySuccess(false), 2000);
  };

  const handleDownloadTranscript = (callId: string, transcript: any[]) => {
    if (!transcript || transcript.length === 0) return;
    const formatted = transcript
      .map(t => `[${t.role === 'user' ? 'USER' : 'ASSISTANT'}]: ${t.content}`)
      .join('\n');
    const blob = new Blob([formatted], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `transcript_${callId}.txt`;
    link.click();
  };


  // Manual Dial Modal States
  const [isDialerOpen, setIsDialerOpen] = useState(false);
  const [dialPhone, setDialPhone] = useState('');
  const [dialName, setDialName] = useState('');
  const [dialVoice, setDialVoice] = useState('cartesia_hi_sonic');
  const [dialMode, setDialMode] = useState<'INTERACTIVE_AI' | 'SCRIPT'>('INTERACTIVE_AI');
  const [dialRoute, setDialRoute] = useState<'app' | 'sim'>('app');
  const [reminderNote, setReminderNote] = useState('');
  const [reminderMins, setReminderMins] = useState(15);
  const [reminderSuccess, setReminderSuccess] = useState(false);
  const [dialScript, setDialScript] = useState(() => localStorage.getItem('superfone_manual_script') || '');
  const DEFAULT_AI_PROMPT = `You are a warm, polite, and professional AI phone representative.
FLUENCY & CONVERSATIONAL VARIETY:
- Vary your opening phrases naturally for every response. Avoid repeating generic opening lines.
- Speak smoothly and naturally in conversational Hindi/Hinglish or English.
- Keep sentences short, concise, and expressive (max 15-20 words per response).
STRICT TELEPHONY RULE: Output ONLY 1-2 spoken response sentences. Never output internal thinking text, markdown, or bullet points.`;

  const [dialPrompt, setDialPrompt] = useState(() => localStorage.getItem('superfone_manual_prompt') || DEFAULT_AI_PROMPT);
  const [dialStatus, setDialStatus] = useState<string | null>(null);
  const [isDialing, setIsDialing] = useState(false);

  const handleScriptChange = (val: string) => {
    setDialScript(val);
    localStorage.setItem('superfone_manual_script', val);
  };

  const handlePromptChange = (val: string) => {
    setDialPrompt(val);
    localStorage.setItem('superfone_manual_prompt', val);
  };

  const filteredCalls = calls.filter(c => 
    c.from_number.includes(searchTerm) || 
    c.to_number.includes(searchTerm) ||
    c.status.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const filteredContacts = contacts.filter(c =>
    c.phone_number.includes(searchTerm) ||
    (c.name && c.name.toLowerCase().includes(searchTerm.toLowerCase()))
  );

  // Fetch full calling records for a selected contact
  const handleSelectContact = async (contact: Contact) => {
    setSelectedContact(contact);
    setLoadingHistory(true);
    try {
      const res = await fetch(`/api/v1/contacts/${contact.id}/history`);
      if (res.ok) {
        const data = await res.json();
        setContactHistory(data.calls || []);
      } else {
        const localHistory = calls.filter(
          c => c.from_number === contact.phone_number || c.to_number === contact.phone_number
        );
        setContactHistory(localHistory);
      }
    } catch (err) {
      const localHistory = calls.filter(
        c => c.from_number === contact.phone_number || c.to_number === contact.phone_number
      );
      setContactHistory(localHistory);
    } finally {
      setLoadingHistory(false);
    }
  };

  // Trigger Quick Manual Call for any contact/number
  const openManualDialer = (phone: string = '', name: string = '') => {
    setDialPhone(phone);
    setDialName(name);
    setDialStatus(null);
    setIsDialerOpen(true);
  };

  // Submit Manual Call to API
  const handleExecuteManualCall = async () => {
    if (!dialPhone.trim()) {
      alert("Please enter a phone number to call.");
      return;
    }
    setIsDialing(true);
    setDialStatus("Initiating direct softphone call...");
    try {
      if (dialRoute === 'sim') {
        setDialStatus("📞 EXOTEL DIALING... Calling phone via Exotel API!");
        const resp = await fetch('/api/telephony/outbound-call', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            to: dialPhone.trim(),
            contact_name: dialName.trim() || undefined,
            script_content: dialMode === 'SCRIPT' ? dialScript : '',
            system_prompt: dialMode === 'INTERACTIVE_AI' ? dialPrompt : ''
          })
        });

        if (resp.ok) {
          setDialStatus(`📞 EXOTEL DIALING! Ringing ${dialPhone.trim()} on cellular SIM network...`);
          if (onRefreshData) onRefreshData();
          setTimeout(() => { if (onRefreshData) onRefreshData(); }, 1500);
        } else {
          const err = await resp.json().catch(() => ({}));
          setDialStatus(`❌ Exotel Call Failed: ${err.error || err.detail || 'Server error'}`);
        }
      } else {
        const resp = await fetch('/api/v1/calls/manual-dial', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            phone_number: dialPhone.trim(),
            contact_name: dialName.trim() || undefined,
            voice_model: dialVoice,
            call_mode: dialMode,
            dial_mode: dialRoute,
            script_content: dialMode === 'SCRIPT' ? dialScript : '',
            system_prompt: dialMode === 'INTERACTIVE_AI' ? dialPrompt : ''
          })
        });

        if (resp.ok) {
          const data = await resp.json();
          setDialStatus(`📲 CALLING MICROSIP! ${data.message || 'Ringing on desktop...'}`);
          if (onRefreshData) onRefreshData();
          setTimeout(() => { if (onRefreshData) onRefreshData(); }, 1500);
          setTimeout(() => { if (onRefreshData) onRefreshData(); }, 3500);
        } else {
          const err = await resp.json().catch(() => ({}));
          setDialStatus(`❌ Call Failed: ${err.detail || 'Server error'}`);
        }
      }
    } catch (ex: any) {
      setDialStatus(`❌ Error initiating call: ${ex.message}`);
    } finally {
      setIsDialing(false);
    }
  };

  const handleScheduleReminder = async () => {
    if (!reminderNote.trim()) return;
    try {
      const remindAt = new Date(Date.now() + reminderMins * 60000).toISOString();
      await fetch('/api/v1/reminders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_id: selectedContact?.id,
          note: reminderNote.trim(),
          remind_at: remindAt
        })
      });
      setReminderSuccess(true);
      setReminderNote('');
      setTimeout(() => setReminderSuccess(false), 3000);
    } catch (ex) {
      console.error('Failed to schedule reminder', ex);
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header & Search Bar */}
      <div className="glass-panel p-6 rounded-2xl border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-100 flex items-center space-x-2">
            <Users className="w-5 h-5 text-brand-500" />
            <span>Voice CRM & Call History</span>
          </h2>
          <p className="text-sm text-slate-400 mt-1">
            Manual dialing, complete contact calling records, conversation transcripts, and AI intent tagging.
          </p>
        </div>

        <div className="flex items-center space-x-3 w-full md:w-auto">
          {/* Agent Presence Status Dropdown */}
          <div className="flex items-center space-x-2 bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-xs">
            <span className="relative flex h-2.5 w-2.5">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                presenceStatus === 'AVAILABLE' ? 'bg-emerald-400' : presenceStatus === 'BUSY' ? 'bg-rose-400' : 'bg-amber-400'
              }`}></span>
              <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${
                presenceStatus === 'AVAILABLE' ? 'bg-emerald-500' : presenceStatus === 'BUSY' ? 'bg-rose-500' : 'bg-amber-500'
              }`}></span>
            </span>
            <select
              value={presenceStatus}
              onChange={(e) => handlePresenceChange(e.target.value)}
              className="bg-transparent text-slate-200 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="AVAILABLE" className="bg-slate-900 text-emerald-400">🟢 AVAILABLE</option>
              <option value="AWAY" className="bg-slate-900 text-amber-400">🌙 AWAY / BREAK</option>
              <option value="BUSY" className="bg-slate-900 text-rose-400">🔴 BUSY (ON CALL)</option>
              <option value="WRAP_UP" className="bg-slate-900 text-indigo-400">📝 WRAP UP</option>
              <option value="OFFLINE" className="bg-slate-900 text-slate-500">⚪ OFFLINE</option>
            </select>
          </div>

          <div className="relative flex-1 md:w-64">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
            <input
              type="text"
              placeholder="Search phone, name, status..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-full bg-slate-900/80 border border-slate-800 rounded-xl pl-9 pr-4 py-2 text-sm text-slate-200 focus:outline-none focus:border-brand-500"
            />
          </div>

          <button
            onClick={() => openManualDialer('')}
            className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-xs transition-all shadow-lg shadow-emerald-600/20 active:scale-95"
          >
            <PhoneCall className="w-4 h-4" />
            <span>⚡ Manual Dial</span>
          </button>

          <label className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium text-xs cursor-pointer transition-colors border border-slate-700">
            <Upload className="w-4 h-4" />
            <span>Import CSV</span>
            <input
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  onImportCSV(e.target.files[0]);
                }
              }}
            />
          </label>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex space-x-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('calls')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'calls' ? 'bg-brand-600/20 text-brand-500 border border-brand-500/30' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Call History ({calls.length})
        </button>
        <button
          onClick={() => setActiveTab('contacts')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            activeTab === 'contacts' ? 'bg-brand-600/20 text-brand-500 border border-brand-500/30' : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Contacts Directory ({contacts.length})
        </button>
      </div>

      {/* Main Content View */}
      {activeTab === 'calls' ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Calls Table */}
          <div className="lg:col-span-2 glass-panel p-4 md:p-5 rounded-2xl border border-slate-800 overflow-hidden space-y-3">
            <div className="sm:hidden flex items-center justify-between text-[11px] text-slate-400 bg-slate-900/60 px-3 py-1.5 rounded-lg border border-slate-800/80">
              <span>↔ Swipe table horizontally for full record</span>
              <span className="font-semibold text-brand-400">{filteredCalls.length} calls</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-sm text-slate-300">
                <thead className="text-xs text-slate-400 uppercase bg-slate-900/50 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3 whitespace-nowrap">Phone Number</th>
                    <th className="px-4 py-3 whitespace-nowrap">Status</th>
                    <th className="px-4 py-3 whitespace-nowrap">Duration</th>
                    <th className="px-4 py-3 whitespace-nowrap">Intent</th>
                    <th className="px-4 py-3 whitespace-nowrap">Actions</th>
                    <th className="px-4 py-3 whitespace-nowrap"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredCalls.map((call) => {
                    const interaction = call.interactions && call.interactions[0];
                    const targetPhone = (call.to_number && call.to_number !== '+918000000700')
                      ? call.to_number
                      : (call.from_number !== '+918000000700' ? call.from_number : (call.to_number || call.from_number));
                    return (
                      <tr
                        key={call.id}
                        onClick={() => setSelectedCall(call)}
                        className={`hover:bg-slate-800/40 cursor-pointer transition-colors ${selectedCall?.id === call.id ? 'bg-brand-600/10' : ''}`}
                      >
                        <td className="px-4 py-3.5 font-medium text-slate-100 whitespace-nowrap">
                          <span className="text-[10px] uppercase font-bold text-slate-400 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700 mr-2">
                            {call.direction === 'inbound' ? 'Inbound' : 'Outbound'}
                          </span>
                          <span className="font-mono text-slate-200">{targetPhone}</span>
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                            {call.status}
                          </span>
                        </td>
                        <td className="px-4 py-3.5 font-mono text-slate-400 whitespace-nowrap">{call.duration_s}s</td>
                        <td className="px-4 py-3.5 text-xs text-brand-400 font-medium whitespace-nowrap">
                          {interaction?.intent_detected || 'general_info'}
                        </td>
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              openManualDialer(targetPhone);
                            }}
                            className="px-2.5 py-1 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 border border-emerald-500/30 text-xs font-semibold flex items-center space-x-1 transition-all"
                          >
                            <PhoneCall className="w-3 h-3" />
                            <span>Call</span>
                          </button>
                        </td>
                        <td className="px-4 py-3.5 text-right whitespace-nowrap">
                          <ChevronRight className="w-4 h-4 text-slate-500 inline-block" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Call Detail & Transcript Drawer */}
          <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center justify-between border-b border-slate-800 pb-3">
              <span className="flex items-center space-x-2">
                <FileText className="w-4 h-4 text-brand-500" />
                <span>Call Session Detail</span>
              </span>
              {selectedCall && selectedCall.transcript && selectedCall.transcript.length > 0 && (
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => handleCopyTranscript(selectedCall.transcript)}
                    className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium flex items-center space-x-1 border border-slate-700"
                    title="Copy full transcript to clipboard"
                  >
                    {copySuccess ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                    <span>{copySuccess ? 'Copied' : 'Copy'}</span>
                  </button>
                  <button
                    onClick={() => handleDownloadTranscript(selectedCall.id, selectedCall.transcript)}
                    className="px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] font-medium flex items-center space-x-1 border border-slate-700"
                    title="Download transcript as text file"
                  >
                    <Download className="w-3 h-3" />
                    <span>Export</span>
                  </button>
                </div>
              )}
            </h3>

            {selectedCall ? (
              <div className="space-y-4 text-xs">
                <div className="glass-card p-3 rounded-xl border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="text-slate-400">Target Phone: <span className="font-semibold text-slate-200 font-mono">{
                        (selectedCall.to_number && selectedCall.to_number !== '+918000000700')
                          ? selectedCall.to_number
                          : (selectedCall.from_number !== '+918000000700' ? selectedCall.from_number : (selectedCall.to_number || selectedCall.from_number))
                      }</span></div>
                      <div className="text-slate-400">System Agent: <span className="font-semibold text-slate-200 font-mono">{selectedCall.from_number}</span></div>
                      <div className="text-slate-400">Duration: <span className="font-semibold text-slate-200">{selectedCall.duration_s}s</span></div>
                      <div className="text-slate-400">Date: <span className="font-semibold text-slate-200">{selectedCall.created_at}</span></div>
                    </div>
                    <button
                      onClick={() => openManualDialer(
                        (selectedCall.to_number && selectedCall.to_number !== '+918000000700')
                          ? selectedCall.to_number
                          : (selectedCall.from_number !== '+918000000700' ? selectedCall.from_number : selectedCall.to_number)
                      )}
                      className="px-3 py-1.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center space-x-1 shadow-md shadow-emerald-600/20"
                    >
                      <PhoneCall className="w-3.5 h-3.5" />
                      <span>Call Now</span>
                    </button>
                  </div>

                  {/* Audio Call Recording Player - Full Featured */}
                  <div className="pt-3 border-t border-slate-800/80 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="flex items-center space-x-1.5 text-emerald-400 text-[11px] font-bold">
                        <Play className="w-3.5 h-3.5 fill-emerald-400" />
                        <span>CALL RECORDING</span>
                      </span>
                      <div className="flex items-center space-x-1 text-[10px]">
                        {['1x','1.25x','1.5x','2x'].map(rate => (
                          <button
                            key={rate}
                            onClick={(e) => {
                              const audio = (e.currentTarget.closest('.audio-player-block') as HTMLElement)?.querySelector('audio') as HTMLAudioElement;
                              if (audio) audio.playbackRate = parseFloat(rate);
                            }}
                            className="px-1.5 py-0.5 rounded bg-slate-800 hover:bg-brand-600 text-slate-400 hover:text-white border border-slate-700 font-mono transition-colors"
                          >{rate}</button>
                        ))}
                      </div>
                    </div>
                    <div className="audio-player-block glass-card p-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5">
                      <audio
                        controls
                        src={selectedCall.recording_url || `/recordings/${selectedCall.id}.wav`}
                        className="w-full"
                        onError={(e) => {
                          const el = e.currentTarget.parentElement;
                          if (el) el.innerHTML = '<div class="text-slate-500 text-[11px] py-2 text-center italic">⚠️ Recording file not available for this call session</div>';
                        }}
                      />
                      <div className="flex items-center justify-between mt-1.5 text-[10px] text-slate-500 font-mono">
                        <span>📁 {selectedCall.recording_url || `/recordings/${selectedCall.id}.wav`}</span>
                        <span>{selectedCall.duration_s}s</span>
                      </div>
                    </div>
                  </div>
                </div>

                {selectedCall.interactions && selectedCall.interactions[0] && (
                  <div className="glass-card p-3 rounded-xl border border-brand-500/20 bg-brand-500/5 space-y-1">
                    <div className="text-brand-400 font-semibold">AI Summary & Intent</div>
                    <p className="text-slate-300 leading-relaxed">{selectedCall.interactions[0].ai_summary || 'Intent: ' + (selectedCall.interactions[0].intent_detected || 'General Enquiry')}</p>
                  </div>
                )}

                <div>
                  <div className="flex items-center justify-between mb-2">
                    <h4 className="font-semibold text-slate-300">
                      Utterance Transcript ({selectedCall.transcript ? selectedCall.transcript.length : 0} turns)
                    </h4>

                    {/* Filter transcript search */}
                    {selectedCall.transcript && selectedCall.transcript.length > 3 && (
                      <div className="relative w-36">
                        <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
                        <input
                          type="text"
                          placeholder="Filter turns..."
                          value={transcriptSearch}
                          onChange={(e) => setTranscriptSearch(e.target.value)}
                          className="w-full bg-slate-900 border border-slate-800 rounded-lg pl-7 pr-2 py-1 text-[11px] text-slate-200 focus:outline-none focus:border-brand-500"
                        />
                      </div>
                    )}
                  </div>

                  <div className="space-y-2.5 max-h-[320px] overflow-y-auto pr-1">
                    {selectedCall.transcript && selectedCall.transcript.length > 0 ? (
                      selectedCall.transcript
                        .filter((t: any) => !transcriptSearch || t.content.toLowerCase().includes(transcriptSearch.toLowerCase()))
                        .map((t: any, i: number) => (
                          <div
                            key={i}
                            className={`p-3 rounded-xl border text-xs ${
                              t.role === 'user'
                                ? 'bg-slate-800/80 border-slate-700 text-slate-200 ml-2 shadow-sm'
                                : 'bg-brand-600/10 border-brand-500/20 text-brand-300 mr-2'
                            }`}
                          >
                            <div className="font-bold text-[10px] uppercase mb-1.5 flex items-center justify-between opacity-90">
                              <span className="flex items-center space-x-1">
                                <span>{t.role === 'user' ? '👤 USER' : '🤖 ASSISTANT'}</span>
                              </span>
                              {t.role === 'user' ? (
                                <span className="flex items-center space-x-1 text-[9px] bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded border border-emerald-500/30 font-mono">
                                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
                                  <span>LIVE MIC {t.audio_dur_s ? `(${t.audio_dur_s}s)` : ''}</span>
                                </span>
                              ) : (
                                <span className="text-[9px] text-brand-400 font-mono bg-brand-500/10 px-1.5 py-0.5 rounded border border-brand-500/20">
                                  NEURAL TTS
                                </span>
                              )}
                            </div>
                            <p className="leading-snug font-sans text-slate-100">{t.content}</p>
                            {t.wav_file && (
                              <div className="mt-2 pt-1.5 text-[10px] text-emerald-400 font-mono flex items-center justify-between border-t border-slate-700/50">
                                <span>WAV: {t.wav_file}</span>
                                <audio controls src={`/recordings/${t.wav_file}`} className="h-5 w-28" />
                              </div>
                            )}
                          </div>
                        ))
                    ) : (
                      <div className="text-slate-500 italic text-xs py-6 text-center border border-dashed border-slate-800 rounded-xl">
                        No transcript turns captured for this call session
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-slate-500 text-xs italic">Select a call record to view full transcript & AI analysis</div>
            )}
          </div>

        </div>
      ) : (
        /* Contacts Directory & Full Call History Inspector */
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Contacts Table */}
          <div className="lg:col-span-2 glass-panel p-4 md:p-5 rounded-2xl border border-slate-800 overflow-hidden space-y-3">
            <div className="sm:hidden flex items-center justify-between text-[11px] text-slate-400 bg-slate-900/60 px-3 py-1.5 rounded-lg border border-slate-800/80">
              <span>↔ Swipe table horizontally for full directory</span>
              <span className="font-semibold text-brand-400">{filteredContacts.length} contacts</span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[620px] text-left text-sm text-slate-300">
                <thead className="text-xs text-slate-400 uppercase bg-slate-900/50 border-b border-slate-800">
                  <tr>
                    <th className="px-4 py-3 whitespace-nowrap">Name</th>
                    <th className="px-4 py-3 whitespace-nowrap">Phone Number</th>
                    <th className="px-4 py-3 whitespace-nowrap">Status</th>
                    <th className="px-4 py-3 whitespace-nowrap">Language</th>
                    <th className="px-4 py-3 whitespace-nowrap">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredContacts.map((contact) => (
                    <tr
                      key={contact.id}
                      onClick={() => handleSelectContact(contact)}
                      className={`hover:bg-slate-800/40 cursor-pointer transition-colors ${selectedContact?.id === contact.id ? 'bg-brand-600/10' : ''}`}
                    >
                      <td className="px-4 py-3.5 font-medium text-slate-100 whitespace-nowrap">{contact.name || 'Unnamed Lead'}</td>
                      <td className="px-4 py-3.5 font-mono text-slate-300 whitespace-nowrap">{contact.phone_number}</td>
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-brand-500/10 text-brand-400 border border-brand-500/20">
                          {contact.status}
                        </span>
                      </td>
                      <td className="px-4 py-3.5 text-xs text-slate-400 uppercase whitespace-nowrap">{contact.preferred_language}</td>
                      <td className="px-4 py-3.5 whitespace-nowrap">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            openManualDialer(contact.phone_number, contact.name || '');
                          }}
                          className="px-2.5 py-1 rounded-lg bg-emerald-600/20 hover:bg-emerald-600/40 text-emerald-400 border border-emerald-500/30 text-xs font-semibold flex items-center space-x-1 transition-all"
                        >
                          <PhoneCall className="w-3 h-3" />
                          <span>Call</span>
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Contact Complete Call History Inspector Panel */}
          <div className="glass-panel p-5 rounded-2xl border border-slate-800 space-y-4">
            <h3 className="text-sm font-semibold text-slate-200 flex items-center justify-between border-b border-slate-800 pb-3">
              <span className="flex items-center space-x-2">
                <Clock className="w-4 h-4 text-emerald-400" />
                <span>Contact Call Records</span>
              </span>
              {selectedContact && (
                <button
                  onClick={() => openManualDialer(selectedContact.phone_number, selectedContact.name || '')}
                  className="px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-xs flex items-center space-x-1"
                >
                  <PhoneCall className="w-3 h-3" />
                  <span>Call Manually</span>
                </button>
              )}
            </h3>

            {selectedContact ? (
              <div className="space-y-4 text-xs">
                <div className="glass-card p-3 rounded-xl border border-slate-800 space-y-1">
                  <div className="font-bold text-sm text-slate-100">{selectedContact.name || 'Unnamed Lead'}</div>
                  <div className="text-slate-400 font-mono">{selectedContact.phone_number}</div>
                  <div className="flex items-center space-x-2 text-[11px] text-slate-500 mt-1">
                    <span>Language: {selectedContact.preferred_language.toUpperCase()}</span>
                    <span>•</span>
                    <span>Status: {selectedContact.status}</span>
                  </div>
                  {selectedContact.lead_source && (
                    <div className="mt-2 flex items-center gap-2">
                      <span className="px-2 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/30 rounded text-[10px] font-semibold">
                        Source: {selectedContact.lead_source}
                      </span>
                      <span className="px-2 py-0.5 bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 rounded text-[10px] font-semibold">
                        Owner: {selectedContact.lead_owner_name || 'Round Robin'}
                      </span>
                    </div>
                  )}
                </div>

                {/* Schedule Follow-up Reminder Box (Demoed in Superfone Video) */}
                <div className="p-3 bg-slate-950/70 border border-slate-800 rounded-xl space-y-2">
                  <div className="text-[11px] font-semibold text-slate-300 uppercase tracking-wider flex items-center justify-between">
                    <span className="flex items-center gap-1.5"><Clock className="w-3.5 h-3.5 text-amber-400" /> Schedule Follow-up Alert</span>
                    {reminderSuccess && <span className="text-emerald-400 text-[10px]">Saved!</span>}
                  </div>
                  <input
                    type="text"
                    placeholder="e.g. Call back after 2 hours regarding property details..."
                    value={reminderNote}
                    onChange={e => setReminderNote(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-750 rounded-lg px-2.5 py-1.5 text-xs text-white placeholder:text-slate-500 focus:outline-none focus:border-amber-500/50"
                  />
                  <div className="flex items-center gap-2">
                    {[15, 60, 120, 240].map(mins => (
                      <button
                        key={mins}
                        onClick={() => setReminderMins(mins)}
                        className={`px-2 py-1 rounded text-[10px] font-semibold transition-colors ${reminderMins === mins ? 'bg-amber-500/30 text-amber-300 border border-amber-500/40' : 'bg-slate-800 text-slate-400'}`}
                      >
                        +{mins >= 60 ? `${mins/60}h` : `${mins}m`}
                      </button>
                    ))}
                    <button
                      onClick={handleScheduleReminder}
                      className="ml-auto px-3 py-1 bg-amber-500 hover:bg-amber-400 text-slate-950 rounded text-xs font-bold transition-colors"
                    >
                      Set Alert
                    </button>
                  </div>
                </div>

                <div>
                  <h4 className="font-semibold text-slate-300 mb-2 flex items-center justify-between">
                    <span>Calling Records ({contactHistory.length})</span>
                    {loadingHistory && <RefreshCw className="w-3 h-3 animate-spin text-brand-400" />}
                  </h4>

                  {contactHistory.length > 0 ? (
                    <div className="space-y-3 max-h-[400px] overflow-y-auto pr-1">
                      {contactHistory.map((call, idx) => (
                        <div key={call.id || idx} className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 space-y-2">
                          <div className="flex items-center justify-between text-slate-300 font-medium">
                            <span className="text-emerald-400 font-semibold">{call.status}</span>
                            <span className="font-mono text-[11px] text-slate-400">{call.duration_s}s</span>
                          </div>
                          <div className="text-[11px] text-slate-500">{call.created_at}</div>

                          {call.transcript && call.transcript.length > 0 && (
                            <div className="mt-2 space-y-1 border-t border-slate-800/80 pt-2">
                              <div className="text-[10px] text-slate-400 font-semibold">Transcript Turns:</div>
                              {call.transcript.map((t, ti) => (
                                <div key={ti} className="text-[11px] text-slate-300">
                                  <span className="font-bold text-brand-400">{t.role}:</span> {t.content}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="p-6 text-center text-slate-500 italic border border-dashed border-slate-800 rounded-xl">
                      No call records found for this contact yet.
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="p-8 text-center text-slate-500 text-xs italic">
                Select a contact from directory to view complete calling history & transcripts
              </div>
            )}
          </div>
        </div>
      )}

      {/* Manual Dialer Modal */}
      {isDialerOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md">
          <div className="glass-panel w-full max-w-lg p-6 rounded-2xl border border-slate-800 space-y-5 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center space-x-2 text-slate-100 font-bold text-lg">
                <PhoneCall className="w-5 h-5 text-emerald-400" />
                <span>Manual Call Dialer</span>
              </div>
              <button
                onClick={() => setIsDialerOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                aria-label="Close dialer modal"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4 text-xs">
              <div>
                <label className="block text-slate-400 mb-1 font-medium">Target Phone Number</label>
                <div className="space-y-2">
                  <input
                    type="text"
                    value={dialPhone}
                    onChange={(e) => setDialPhone(e.target.value)}
                    placeholder="Enter 10-digit phone number (e.g. 8830718466) or SIP extension"
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100 font-mono focus:outline-none focus:border-brand-500"
                  />
                  <div className="flex items-center space-x-2 text-[11px]">
                    <span className="text-slate-500 font-medium">Quick Presets:</span>
                    <button
                      type="button"
                      onClick={() => { setDialPhone('8830718466'); setDialRoute('sim'); }}
                      className="px-2.5 py-1 rounded-lg bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/30 font-mono transition-colors flex items-center space-x-1"
                    >
                      <span>📱 SIM (8830718466)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => { setDialPhone('test1000'); setDialRoute('app'); }}
                      className="px-2.5 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono transition-colors flex items-center space-x-1"
                    >
                      <span>💻 Softphone (test1000)</span>
                    </button>
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Contact Name (Optional)</label>
                <input
                  type="text"
                  value={dialName}
                  onChange={(e) => setDialName(e.target.value)}
                  placeholder="e.g. Rahul Sharma"
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-brand-500"
                />
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Agent Interaction Mode</label>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <button
                    type="button"
                    onClick={() => setDialMode('INTERACTIVE_AI')}
                    className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all ${
                      dialMode === 'INTERACTIVE_AI'
                        ? 'bg-brand-600/20 border-brand-500 text-brand-300 shadow-md shadow-brand-500/10'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>🤖 Interactive AI Agent</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setDialMode('SCRIPT')}
                    className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all ${
                      dialMode === 'SCRIPT'
                        ? 'bg-brand-600/20 border-brand-500 text-brand-300 shadow-md shadow-brand-500/10'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>📜 Pre-written Script</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Outgoing Dialing Route (Superfone Feature)</label>
                <div className="grid grid-cols-2 gap-2 mb-3">
                  <button
                    type="button"
                    onClick={() => setDialRoute('app')}
                    className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all ${
                      dialRoute === 'app'
                        ? 'bg-emerald-500/20 border-emerald-500 text-emerald-300 shadow-md shadow-emerald-500/10'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>🌐 Application (Wi-Fi/VoIP)</span>
                  </button>
                  <button
                    type="button"
                    onClick={() => setDialRoute('sim')}
                    className={`py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center space-x-1.5 transition-all ${
                      dialRoute === 'sim'
                        ? 'bg-amber-500/20 border-amber-500 text-amber-300 shadow-md shadow-amber-500/10'
                        : 'bg-slate-900 border-slate-800 text-slate-400 hover:bg-slate-800'
                    }`}
                  >
                    <span>📱 SIM Card (Cellular GSM)</span>
                  </button>
                </div>
              </div>

              <div>
                <label className="block text-slate-400 mb-1 font-medium">Neural Voice Model</label>
                <select
                  value={dialVoice}
                  onChange={(e) => setDialVoice(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-800 rounded-xl px-3 py-2 text-sm text-slate-100 focus:outline-none focus:border-brand-500"
                >
                  <option value="deepgram_aura_asteria">Deepgram Aura Asteria (Cloud Neural - Recommended)</option>
                  <option value="cartesia_hi_sonic">Cartesia Hindi Sonic (Cloud Neural)</option>
                  <option value="openai_alloy">OpenAI Alloy (Cloud Neural)</option>
                  <option value="elevenlabs_rachel">ElevenLabs Rachel (Cloud Neural)</option>
                  <option value="hi_pratham">Piper Hindi Pratham (On-Premise Local)</option>
                  <option value="af_sarah">Kokoro Female Sarah (Local ONNX)</option>
                  <option value="am_adam">Kokoro Male Adam (Local ONNX)</option>
                </select>
              </div>

              {dialMode === 'INTERACTIVE_AI' ? (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-slate-400 font-medium">AI Agent Persona & Instructions</label>
                    <span className="text-[10px] text-slate-500 font-mono">{dialPrompt.length} chars</span>
                  </div>
                  <textarea
                    rows={4}
                    value={dialPrompt}
                    onChange={(e) => handlePromptChange(e.target.value)}
                    placeholder="Enter system prompt instructions for the AI agent..."
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 focus:outline-none focus:border-brand-500 font-mono text-[11px]"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">
                    💡 In Interactive AI mode, the agent speaks dynamically based on your instructions without reciting a rigid script.
                  </p>
                </div>
              ) : (
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-slate-400 font-medium">Fixed Speech Script (Text to Recite)</label>
                    <span className="text-[10px] text-slate-500 font-mono">{dialScript.length} chars | {dialScript.trim().split(/\s+/).filter(Boolean).length} words</span>
                  </div>
                  <textarea
                    rows={4}
                    value={dialScript}
                    onChange={(e) => handleScriptChange(e.target.value)}
                    placeholder="Type your fixed script text to recite..."
                    className="w-full bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs text-slate-200 focus:outline-none focus:border-brand-500"
                  />
                  <p className="text-[10px] text-slate-500 mt-1">
                    📜 In Script Recitation mode, the agent reads your exact typed text line-by-line.
                  </p>
                </div>
              )}

              {dialStatus && (
                <div className={`p-3 rounded-xl border text-xs font-semibold flex items-center space-x-2 ${
                  dialStatus.includes('❌') 
                    ? 'bg-rose-500/10 border-rose-500/30 text-rose-400' 
                    : 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 animate-pulse'
                }`}>
                  {dialStatus.includes('❌') ? <AlertCircle className="w-4 h-4" /> : <PhoneCall className="w-4 h-4 animate-bounce" />}
                  <span>{dialStatus}</span>
                </div>
              )}
            </div>

            <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-800">
              <button
                onClick={() => setIsDialerOpen(false)}
                className="px-4 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium text-xs"
              >
                Close
              </button>

              <button
                onClick={handleExecuteManualCall}
                disabled={isDialing}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs flex items-center space-x-2 shadow-lg shadow-emerald-600/25 active:scale-95 disabled:opacity-50"
              >
                {isDialing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Dialing...</span>
                  </>
                ) : (
                  <>
                    <PhoneCall className="w-4 h-4" />
                    <span>📞 Start Call Now</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Real-Time Incoming Handoff Call Modal Card */}
      <IncomingCallCard
        offer={incomingOffer}
        agentId={agentId}
        onAccept={handleAcceptHandoff}
        onReject={handleRejectHandoff}
        onClose={() => setIncomingOffer(null)}
        statusMessage={handoffToast}
      />
    </div>
  );
};
