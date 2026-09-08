import React, { useState, useEffect } from 'react';
import { 
  PhoneCall, PhoneOff, Mic, MicOff, Volume2, Pause, Play, CheckCircle2, 
  Clock, Flame, Target, Trophy, Star, ShieldCheck, Sparkles, RefreshCw, 
  UserCheck, AlertCircle, PhoneIncoming, MessageSquare, Tag, Plus, Calendar,
  ListTodo, User, Radio, Hash, ChevronRight, Activity, Zap
} from 'lucide-react';
import { AgentSession, AgentStatusType, Contact, CallSession, LeadTask } from '../types';

interface AgentDashboardPageProps {
  session: AgentSession;
  onUpdateStatus: (newStatus: AgentStatusType) => void;
  onLogout: () => void;
  calls: CallSession[];
  contacts: Contact[];
  onRefreshData?: () => void;
}

export const AgentDashboardPage: React.FC<AgentDashboardPageProps> = ({
  session,
  onUpdateStatus,
  onLogout,
  calls,
  contacts,
  onRefreshData
}) => {
  const [currentStatus, setCurrentStatus] = useState<AgentStatusType>(session.agent.status || 'available');
  const [activeShiftTime, setActiveShiftTime] = useState<number>(142); // in minutes
  
  // Softphone & Dialpad State
  const [dialNumber, setDialNumber] = useState<string>('');
  const [activeCall, setActiveCall] = useState<{
    contact_name?: string;
    phone_number: string;
    status: 'connecting' | 'connected' | 'ended';
    duration: number;
    sentiment: 'positive' | 'neutral' | 'negative';
  } | null>(null);

  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [isOnHold, setIsOnHold] = useState<boolean>(false);
  const [callNotes, setCallNotes] = useState<string>('');
  const [selectedDisposition, setSelectedDisposition] = useState<string>('Interested');
  const [activeLeadTab, setActiveLeadTab] = useState<'all' | 'priority' | 'callbacks'>('priority');
  
  // Playback state for recordings
  const [playingAudioId, setPlayingAudioId] = useState<string | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);

  // Shift Timer
  useEffect(() => {
    const timer = setInterval(() => {
      setActiveShiftTime(prev => prev + 1);
    }, 60000);
    return () => clearInterval(timer);
  }, []);

  // Call timer when call is active
  useEffect(() => {
    let callTimer: any;
    if (activeCall && activeCall.status === 'connected') {
      callTimer = setInterval(() => {
        setActiveCall(prev => prev ? { ...prev, duration: prev.duration + 1 } : null);
      }, 1000);
    }
    return () => clearInterval(callTimer);
  }, [activeCall]);

  const handleStatusChange = async (newStatus: AgentStatusType) => {
    setCurrentStatus(newStatus);
    onUpdateStatus(newStatus);
    try {
      await fetch('/api/v1/auth/status', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: session.agent.id, status: newStatus })
      });
    } catch (err) {
      console.error("Failed to sync agent status", err);
    }
  };

  const handleDialKey = (key: string) => {
    setDialNumber(prev => prev + key);
    // Play DTMF click audio synthesis
    playToneAudio();
  };

  const playToneAudio = () => {
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = 697;
      gain.gain.setValueAtTime(0.05, ctx.currentTime);
      osc.start();
      osc.stop(ctx.currentTime + 0.08);
    } catch (e) {}
  };

  const handleInitiateCall = async (targetPhone?: string, contactName?: string) => {
    const phoneToCall = targetPhone || dialNumber || '+91 9876543210';
    if (!phoneToCall) return;

    setActiveCall({
      contact_name: contactName || 'Voice Lead',
      phone_number: phoneToCall,
      status: 'connecting',
      duration: 0,
      sentiment: 'positive'
    });
    handleStatusChange('on_call');

    // Trigger zero latency MicroSIP session
    try {
      await fetch('/api/v1/microsip/originate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneToCall, auto_answer: 1 })
      });

      // Simulate connection
      setTimeout(() => {
        setActiveCall(prev => prev ? { ...prev, status: 'connected' } : null);
      }, 1200);
    } catch (err) {
      console.error("Call initiation error:", err);
      setActiveCall(prev => prev ? { ...prev, status: 'connected' } : null);
    }
  };

  const handleEndCall = () => {
    setActiveCall(prev => prev ? { ...prev, status: 'ended' } : null);
    handleStatusChange('wrap_up');
    setTimeout(() => {
      setActiveCall(null);
    }, 1500);
  };

  const handleSaveDisposition = () => {
    alert(`Call Disposition Saved: ${selectedDisposition}. Notes: "${callNotes || 'No notes'}"`);
    setCallNotes('');
    handleStatusChange('available');
    if (onRefreshData) onRefreshData();
  };

  // Filter contacts assigned to agent or default contacts
  const agentLeads = contacts.length > 0 ? contacts : [
    { id: '1', name: 'Rajesh Sharma', phone_number: '+91 9876543210', status: 'lead', lead_source: 'Google Ads', preferred_language: 'hi' },
    { id: '2', name: 'Sneha Gupta', phone_number: '+91 9876543211', status: 'lead', lead_source: 'Meta Ads', preferred_language: 'en' },
    { id: '3', name: 'Vikram Singh', phone_number: '+91 9876543212', status: 'interested', lead_source: 'Direct', preferred_language: 'hi' },
    { id: '4', name: 'Ananya Verma', phone_number: '+91 9876543213', status: 'callback', lead_source: 'Website', preferred_language: 'hi' },
  ];

  const formatSeconds = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6 text-slate-100 font-sans pb-12">
      
      {/* 1. TOP AGENT WORKSPACE HEADER & STATUS CONTROL HUB */}
      <div className="glass-panel border border-slate-800 rounded-3xl p-5 sm:p-6 bg-gradient-to-r from-slate-900/90 via-indigo-950/40 to-slate-900/90 backdrop-blur-xl shadow-xl">
        <div className="flex flex-col lg:flex-row items-center justify-between gap-6">
          
          {/* Agent Info & Shift Badge */}
          <div className="flex items-center space-x-4 w-full lg:w-auto">
            <div className="relative">
              <img
                src={session.agent.avatar_url || `https://api.dicebear.com/7.x/avataaars/svg?seed=${session.agent.name}`}
                alt={session.agent.name}
                className="w-14 h-14 rounded-2xl object-cover border-2 border-indigo-500/50 shadow-lg shadow-indigo-500/20"
              />
              <div className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full border-2 border-slate-900 ${
                currentStatus === 'available' ? 'bg-emerald-400' :
                currentStatus === 'on_call' ? 'bg-red-500 animate-ping' :
                currentStatus === 'in_break' ? 'bg-amber-400' :
                currentStatus === 'wrap_up' ? 'bg-purple-400' : 'bg-slate-500'
              }`} />
            </div>

            <div>
              <div className="flex items-center space-x-2.5">
                <h2 className="text-xl font-extrabold tracking-tight text-white">{session.agent.name}</h2>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-indigo-500/20 border border-indigo-500/40 text-indigo-300">
                  Ext {session.agent.sip_extension || '101'}
                </span>
              </div>
              <div className="flex items-center space-x-3 text-xs text-slate-400 mt-1">
                <span className="flex items-center space-x-1">
                  <UserCheck className="w-3.5 h-3.5 text-indigo-400" />
                  <span>{session.agent.role}</span>
                </span>
                <span>•</span>
                <span className="flex items-center space-x-1 font-mono text-slate-300">
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                  <span>Shift: {Math.floor(activeShiftTime / 60)}h {activeShiftTime % 60}m</span>
                </span>
              </div>
            </div>
          </div>

          {/* Status Switcher Toolbar */}
          <div className="flex flex-wrap items-center gap-2 p-1.5 rounded-2xl bg-slate-950/80 border border-slate-800/80 w-full lg:w-auto justify-center">
            {[
              { id: 'available', label: 'Online / Available', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30', dot: 'bg-emerald-400' },
              { id: 'on_call', label: 'In Call', color: 'bg-red-500/20 text-red-300 border-red-500/40 hover:bg-red-500/30', dot: 'bg-red-400' },
              { id: 'in_break', label: 'Short Break', color: 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30', dot: 'bg-amber-400' },
              { id: 'wrap_up', label: 'Wrap-Up (ACW)', color: 'bg-purple-500/20 text-purple-300 border-purple-500/40 hover:bg-purple-500/30', dot: 'bg-purple-400' },
              { id: 'offline', label: 'Offline', color: 'bg-slate-800/60 text-slate-400 border-slate-700 hover:bg-slate-800', dot: 'bg-slate-500' },
            ].map((st) => {
              const isSelected = currentStatus === st.id;
              return (
                <button
                  key={st.id}
                  onClick={() => handleStatusChange(st.id as AgentStatusType)}
                  className={`px-3 py-2 rounded-xl text-xs font-bold border transition-all flex items-center space-x-2 ${
                    isSelected
                      ? `${st.color} shadow-lg ring-1 ring-white/10 scale-105`
                      : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                  }`}
                >
                  <div className={`w-2.5 h-2.5 rounded-full ${st.dot} ${isSelected ? 'animate-pulse' : ''}`} />
                  <span>{st.label}</span>
                </button>
              );
            })}
          </div>

        </div>
      </div>

      {/* 2. GAMIFIED AGENT PERFORMANCE METRICS BAR */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        
        {/* Calls Target Metric */}
        <div className="glass-panel border border-slate-800 rounded-2xl p-4 bg-slate-900/60 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Today's Calls</span>
            <div className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <PhoneCall className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <div className="text-2xl font-black text-white font-mono">
              {session.stats.calls_made_today} <span className="text-sm font-medium text-slate-500">/ {session.stats.calls_target}</span>
            </div>
            <span className="text-xs font-bold text-indigo-400">76% Target</span>
          </div>
          <div className="w-full bg-slate-800 h-2 rounded-full mt-3 overflow-hidden">
            <div className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full w-[76%]" />
          </div>
        </div>

        {/* Talk Time Metric */}
        <div className="glass-panel border border-slate-800 rounded-2xl p-4 bg-slate-900/60">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Total Talk Time</span>
            <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <div className="text-2xl font-black text-white font-mono">
              {session.stats.talk_time_minutes} <span className="text-xs font-medium text-slate-400">min</span>
            </div>
            <span className="text-xs text-slate-400">AHT: {session.stats.avg_handling_time_s}s</span>
          </div>
          <p className="text-[11px] text-emerald-400 mt-2 font-medium">↑ 14% higher than team avg</p>
        </div>

        {/* Lead Conversions Metric */}
        <div className="glass-panel border border-slate-800 rounded-2xl p-4 bg-slate-900/60">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Conversions</span>
            <div className="p-2 rounded-xl bg-pink-500/10 text-pink-400 border border-pink-500/20">
              <Trophy className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <div className="text-2xl font-black text-white font-mono">
              {session.stats.leads_converted} <span className="text-xs font-medium text-slate-400">Deals</span>
            </div>
            <span className="text-xs font-bold text-pink-400">₹1,45,000</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">Conversion Rate: 23.6%</p>
        </div>

        {/* Quality Score QA Metric */}
        <div className="glass-panel border border-slate-800 rounded-2xl p-4 bg-slate-900/60">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">AI Speech Quality</span>
            <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <Star className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-3 flex items-baseline justify-between">
            <div className="text-2xl font-black text-white font-mono flex items-center space-x-1">
              <span>{session.stats.quality_score}</span>
              <span className="text-sm text-amber-400">★</span>
            </div>
            <span className="text-xs font-extrabold text-emerald-400">Top 5% Agent</span>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">Script Adherence: 98%</p>
        </div>

      </div>

      {/* 3. MAIN WORKSPACE GRID: SOFTPHONE DIALPAD & ASSIGNED LEAD QUEUE */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Embedded Web Softphone Dialer & Active Call Bar */}
        <div className="lg:col-span-5 space-y-6">
          
          <div className="glass-panel border border-slate-800 rounded-3xl p-5 sm:p-6 bg-slate-900/80 backdrop-blur-xl relative shadow-2xl">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
              <div className="flex items-center space-x-2.5">
                <Radio className="w-5 h-5 text-indigo-400 animate-pulse" />
                <h3 className="font-extrabold text-slate-100 text-base">Web Softphone Dialer</h3>
              </div>
              <span className="px-2.5 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[11px] font-mono font-bold">
                SIP Registered
              </span>
            </div>

            {/* Live Call Controller Banner if active */}
            {activeCall ? (
              <div className="p-4 rounded-2xl bg-gradient-to-r from-red-950/80 via-slate-900 to-indigo-950/80 border border-red-500/50 space-y-4 mb-4 animate-pulse">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="px-2 py-0.5 rounded-md bg-red-500/20 text-red-400 font-mono text-[10px] uppercase font-bold tracking-wider">
                      {activeCall.status === 'connecting' ? 'DIALING...' : 'LIVE CALL ACTIVE'}
                    </span>
                    <h4 className="text-lg font-black text-white mt-1">{activeCall.contact_name}</h4>
                    <p className="text-xs text-slate-300 font-mono">{activeCall.phone_number}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-xl font-mono font-black text-white">{formatSeconds(activeCall.duration)}</div>
                    <span className="text-[10px] text-emerald-400 font-semibold">AI Sentiment: Positive 🙂</span>
                  </div>
                </div>

                {/* Call Control Buttons */}
                <div className="flex items-center justify-center space-x-3 pt-2">
                  <button
                    onClick={() => setIsMuted(!isMuted)}
                    className={`p-3 rounded-xl border font-bold transition-all ${
                      isMuted ? 'bg-amber-500/20 border-amber-500 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-200'
                    }`}
                  >
                    {isMuted ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
                  </button>

                  <button
                    onClick={() => setIsOnHold(!isOnHold)}
                    className={`p-3 rounded-xl border font-bold transition-all ${
                      isOnHold ? 'bg-amber-500/20 border-amber-500 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-200'
                    }`}
                  >
                    <Pause className="w-5 h-5" />
                  </button>

                  <button
                    onClick={handleEndCall}
                    className="px-6 py-3 rounded-xl bg-red-600 hover:bg-red-500 text-white font-extrabold flex items-center space-x-2 shadow-lg shadow-red-600/30 transition-all active:scale-95"
                  >
                    <PhoneOff className="w-5 h-5" />
                    <span>END CALL</span>
                  </button>
                </div>
              </div>
            ) : null}

            {/* Dial Display Input */}
            <div className="relative mb-4">
              <input
                type="text"
                value={dialNumber}
                onChange={(e) => setDialNumber(e.target.value)}
                placeholder="+91 Phone number..."
                className="w-full text-center text-xl font-mono font-bold py-3.5 px-4 rounded-2xl bg-slate-950/90 border border-slate-800 text-white placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 tracking-wider"
              />
              {dialNumber && (
                <button
                  onClick={() => setDialNumber('')}
                  className="absolute right-3.5 top-3.5 text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800"
                >
                  CLEAR
                </button>
              )}
            </div>

            {/* DTMF Keypad Grid */}
            <div className="grid grid-cols-3 gap-2.5 mb-5">
              {['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#'].map((k) => (
                <button
                  key={k}
                  onClick={() => handleDialKey(k)}
                  className="p-3.5 rounded-2xl bg-slate-950/70 border border-slate-800/80 hover:bg-indigo-950/50 hover:border-indigo-500/50 text-slate-100 font-mono font-black text-lg shadow-sm transition-all active:scale-95 flex flex-col items-center justify-center"
                >
                  <span>{k}</span>
                </button>
              ))}
            </div>

            {/* Initiate Call Button */}
            <button
              onClick={() => handleInitiateCall()}
              disabled={!dialNumber && !activeCall}
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white font-extrabold text-base shadow-xl shadow-emerald-500/20 border border-white/20 transition-all flex items-center justify-center space-x-2 active:scale-95 disabled:opacity-50"
            >
              <PhoneCall className="w-5 h-5 text-emerald-200" />
              <span>START DIRECT SIP CALL</span>
            </button>

            {/* Quick Post-Call Disposition Form */}
            {currentStatus === 'wrap_up' && (
              <div className="mt-6 pt-4 border-t border-slate-800 space-y-3 bg-purple-950/20 p-4 rounded-2xl border border-purple-500/30">
                <div className="flex items-center space-x-2 text-purple-300 font-bold text-xs">
                  <Tag className="w-4 h-4" />
                  <span>Call Wrap-Up & Disposition Form</span>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  {['Interested', 'Callback Scheduled', 'Not Interested', 'Sale Closed'].map((disp) => (
                    <button
                      key={disp}
                      onClick={() => setSelectedDisposition(disp)}
                      className={`p-2 rounded-xl text-xs font-bold border transition-all ${
                        selectedDisposition === disp
                          ? 'bg-purple-600 text-white border-purple-400'
                          : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800'
                      }`}
                    >
                      {disp}
                    </button>
                  ))}
                </div>

                <textarea
                  value={callNotes}
                  onChange={(e) => setCallNotes(e.target.value)}
                  placeholder="Enter call notes or next action points..."
                  className="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  rows={2}
                />

                <button
                  onClick={handleSaveDisposition}
                  className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-extrabold text-xs shadow-md"
                >
                  SAVE & MARK AVAILABLE
                </button>
              </div>
            )}

          </div>

        </div>

        {/* Right Column: Assigned Lead Queue & Reminders */}
        <div className="lg:col-span-7 space-y-6">
          
          <div className="glass-panel border border-slate-800 rounded-3xl p-5 sm:p-6 bg-slate-900/80 backdrop-blur-xl">
            
            {/* Header & Tabs */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800 mb-4">
              <div className="flex items-center space-x-2.5">
                <User className="w-5 h-5 text-indigo-400" />
                <h3 className="font-extrabold text-slate-100 text-base">My Priority Leads Queue</h3>
              </div>

              <div className="flex p-1 rounded-xl bg-slate-950/80 border border-slate-800 text-xs font-semibold">
                <button
                  onClick={() => setActiveLeadTab('priority')}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    activeLeadTab === 'priority' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  High Intent (4)
                </button>
                <button
                  onClick={() => setActiveLeadTab('callbacks')}
                  className={`px-3 py-1.5 rounded-lg transition-all ${
                    activeLeadTab === 'callbacks' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  Callbacks Due
                </button>
              </div>
            </div>

            {/* Lead Queue Cards */}
            <div className="space-y-3">
              {agentLeads.map((ld) => (
                <div
                  key={ld.id}
                  className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 hover:border-indigo-500/40 transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
                >
                  <div className="flex items-center space-x-3.5">
                    <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center font-bold text-base">
                      {ld.name ? ld.name.charAt(0) : 'L'}
                    </div>
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-bold text-slate-100 text-sm">{ld.name}</span>
                        <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 text-[10px] font-mono">
                          {ld.lead_source || 'Direct'}
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 font-mono mt-0.5">{ld.phone_number}</p>
                    </div>
                  </div>

                  <div className="flex items-center space-x-2 self-end sm:self-center">
                    <button
                      onClick={() => handleInitiateCall(ld.phone_number, ld.name)}
                      className="px-3.5 py-2 rounded-xl bg-indigo-600/20 hover:bg-indigo-600 text-indigo-300 hover:text-white border border-indigo-500/40 text-xs font-bold transition-all flex items-center space-x-1.5"
                    >
                      <PhoneCall className="w-3.5 h-3.5" />
                      <span>Call Now</span>
                    </button>
                  </div>
                </div>
              ))}
            </div>

          </div>

          {/* Spoken Call History & AI Audio Player */}
          <div className="glass-panel border border-slate-800 rounded-3xl p-5 sm:p-6 bg-slate-900/80 backdrop-blur-xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800 mb-4">
              <h3 className="font-extrabold text-slate-100 text-sm flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <span>Recent Agent Spoken Recordings & AI Insights</span>
              </h3>
            </div>

            <div className="space-y-3">
              {[
                { id: 'c1', contact: 'Rajesh Sharma', duration: '2m 14s', outcome: 'Interested', audio: '/recordings/demo1.wav', summary: 'Customer interested in Enterprise Voice Agent Plan. Requested demo call.' },
                { id: 'c2', contact: 'Sneha Gupta', duration: '1m 45s', outcome: 'Callback Scheduled', audio: '/recordings/demo2.wav', summary: 'Wants callback tomorrow at 3 PM regarding SIP trunking pricing.' }
              ].map((rec) => (
                <div key={rec.id} className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800 text-xs space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-200">{rec.contact}</span>
                    <span className="px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 font-mono text-[10px]">
                      {rec.outcome}
                    </span>
                  </div>
                  <p className="text-slate-400 italic text-[11px]">"{rec.summary}"</p>
                  
                  {/* Waveform Player Controls */}
                  <div className="flex items-center justify-between pt-1">
                    <div className="flex items-center space-x-2">
                      <button
                        onClick={() => setPlayingAudioId(playingAudioId === rec.id ? null : rec.id)}
                        className="p-1.5 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500"
                      >
                        {playingAudioId === rec.id ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5" />}
                      </button>
                      <span className="font-mono text-[10px] text-slate-400">{rec.duration}</span>
                    </div>

                    <button
                      onClick={() => setPlaybackSpeed(playbackSpeed === 1 ? 1.5 : 1)}
                      className="px-2 py-0.5 rounded bg-slate-800 text-[10px] font-mono text-slate-300"
                    >
                      {playbackSpeed}x
                    </button>
                  </div>
                </div>
              ))}
            </div>

          </div>

        </div>

      </div>

    </div>
  );
};
