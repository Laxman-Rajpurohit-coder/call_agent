import React, { useState, useEffect, useRef } from 'react';
import { 
  PhoneCall, PhoneOff, Mic, MicOff, Volume2, Pause, Play, CheckCircle2, 
  Clock, Flame, Target, Trophy, Star, ShieldCheck, Sparkles, RefreshCw, 
  UserCheck, AlertCircle, PhoneIncoming, MessageSquare, Tag, Plus, Calendar,
  ListTodo, User, Radio, Hash, ChevronRight, Activity, Zap, Search,
  ArrowRight, X, ArrowUpRight, VolumeX, History, FileText, Send, Check,
  CheckSquare, Square, LogOut
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

interface IncomingHandoff {
  id: string;
  caller_name: string;
  phone_number: string;
  intent: string;
  sentiment: 'positive' | 'neutral' | 'negative';
  summary: string;
  call_id: string;
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
    contact_id?: string;
    contact_name?: string;
    phone_number: string;
    status: 'connecting' | 'connected' | 'ended';
    duration: number;
    sentiment: 'positive' | 'neutral' | 'negative';
  } | null>(null);

  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [isOnHold, setIsOnHold] = useState<boolean>(false);
  const [callNotes, setCallNotes] = useState<string>('');
  const [selectedDisposition, setSelectedDisposition] = useState<string>('interested');
  const [callbackDateTime, setCallbackDateTime] = useState<string>('');
  const [isSavingDisposition, setIsSavingDisposition] = useState<boolean>(false);
  const [dispositionToast, setDispositionToast] = useState<string | null>(null);

  // Main Right Column View Mode: 'tasks' vs 'leads' vs 'history'
  const [activeWorkspaceMode, setActiveWorkspaceMode] = useState<'tasks' | 'leads' | 'history'>('tasks');

  // Tasks State (Fetched Live from Database)
  const [tasks, setTasks] = useState<LeadTask[]>([]);
  const [isTasksLoading, setIsTasksLoading] = useState<boolean>(false);
  const [taskFilter, setTaskFilter] = useState<'all' | 'pending' | 'completed'>('pending');

  // Leads Filter & Selection
  const [activeLeadTab, setActiveLeadTab] = useState<'interested' | 'callbacks' | 'all'>('interested');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedLead, setSelectedLead] = useState<Contact | null>(null);

  // Incoming Screen-Pop Live Handoff
  const [incomingHandoff, setIncomingHandoff] = useState<IncomingHandoff | null>({
    id: 'hand-109',
    caller_name: 'Dr. Vikram Malhotra',
    phone_number: '+91 98765 43210',
    intent: 'Pricing & Clinic Multi-Location License',
    sentiment: 'positive',
    summary: 'Caller inquired about enterprise AI agent pricing for 3 dental clinics in Mumbai. Requested to speak with a human specialist.',
    call_id: 'call-live-892'
  });

  // Audio Player State for past recordings
  const [playingAudioId, setPlayingAudioId] = useState<string | null>(null);
  const [playbackSpeed, setPlaybackSpeed] = useState<number>(1);

  // Web Audio Context reference for DTMF tones
  const audioCtxRef = useRef<AudioContext | null>(null);

  // Fetch live tasks from database
  const fetchTasks = async () => {
    setIsTasksLoading(true);
    try {
      const res = await fetch('/api/v1/tasks');
      if (res.ok) {
        const data: LeadTask[] = await res.json();
        // Prioritize tasks assigned to this agent or matching agent email/name
        const agentId = session.agent.id;
        const agentEmail = session.agent.email;
        const myTasks = data.filter(t => 
          t.assigned_to_id === agentId || 
          (t as any).assigned_to_email === agentEmail ||
          (t as any).assigned_to_name === session.agent.name
        );
        // If no tasks strictly assigned to this agent, show all active tasks
        setTasks(myTasks.length > 0 ? myTasks : data);
      }
    } catch (err) {
      console.error("Failed to fetch assigned tasks", err);
    } finally {
      setIsTasksLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
  }, [session.agent.id]);

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

  const playToneAudio = (freq: number = 697) => {
    try {
      if (!audioCtxRef.current) {
        audioCtxRef.current = new (window.AudioContext || (window as any).webkitAudioContext)();
      }
      const ctx = audioCtxRef.current;
      if (ctx.state === 'suspended') {
        ctx.resume();
      }
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.04, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.08);
      osc.start();
      osc.stop(ctx.currentTime + 0.08);
    } catch (e) {}
  };

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
    playToneAudio(700 + (key.charCodeAt(0) * 5));
  };

  const handleInitiateCall = async (targetPhone?: string, contactName?: string, contactId?: string) => {
    const phoneToCall = targetPhone || dialNumber || '+91 9876543210';
    if (!phoneToCall) return;

    setActiveCall({
      contact_id: contactId,
      contact_name: contactName || 'Prospect Lead',
      phone_number: phoneToCall,
      status: 'connecting',
      duration: 0,
      sentiment: 'positive'
    });
    handleStatusChange('on_call');

    try {
      await fetch('/api/v1/microsip/originate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone_number: phoneToCall, auto_answer: 1 })
      });

      setTimeout(() => {
        setActiveCall(prev => prev ? { ...prev, status: 'connected' } : null);
      }, 1000);
    } catch (err) {
      console.error("Call initiation error:", err);
      setActiveCall(prev => prev ? { ...prev, status: 'connected' } : null);
    }
  };

  const handleAcceptHandoff = () => {
    if (!incomingHandoff) return;
    setActiveCall({
      contact_name: incomingHandoff.caller_name,
      phone_number: incomingHandoff.phone_number,
      status: 'connected',
      duration: 15,
      sentiment: incomingHandoff.sentiment
    });
    handleStatusChange('on_call');

    const matched = contacts.find(c => c.phone_number === incomingHandoff.phone_number);
    if (matched) setSelectedLead(matched);

    setIncomingHandoff(null);
  };

  const handleEndCall = () => {
    setActiveCall(prev => prev ? { ...prev, status: 'ended' } : null);
    handleStatusChange('wrap_up');
    setTimeout(() => {
      setActiveCall(null);
    }, 1200);
  };

  const handleCompleteTask = async (taskId: string) => {
    try {
      const res = await fetch(`/api/v1/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'completed' })
      });
      if (res.ok) {
        setTasks(prev => prev.map(t => t.id === taskId ? { ...t, status: 'completed' } : t));
        setDispositionToast('Task marked as COMPLETED in database! ✅');
        setTimeout(() => setDispositionToast(null), 3000);
      }
    } catch (err) {
      console.error("Failed to complete task:", err);
    }
  };

  const handleSaveDisposition = async (targetContactId?: string) => {
    const cid = targetContactId || activeCall?.contact_id || selectedLead?.id;
    setIsSavingDisposition(true);

    const payload: Record<string, any> = {
      status: selectedDisposition,
      agent_id: session.agent.id,
      notes: callNotes.trim() || `Marked as ${selectedDisposition} by ${session.agent.name}`,
      custom_fields: {
        last_disposition_by: session.agent.name,
        last_disposition_at: new Date().toISOString()
      }
    };

    if (selectedDisposition === 'callback' && callbackDateTime) {
      payload.custom_fields.callback_scheduled_for = callbackDateTime;
    }

    try {
      if (cid) {
        await fetch(`/api/v1/contacts/${cid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
      }
      
      setDispositionToast(`Disposition '${selectedDisposition.toUpperCase()}' saved to database! ✅`);
      setTimeout(() => setDispositionToast(null), 3500);

      setCallNotes('');
      setCallbackDateTime('');
      handleStatusChange('available');
      if (onRefreshData) onRefreshData();
    } catch (err) {
      console.error("Failed to save disposition:", err);
      setDispositionToast(`Disposition recorded locally.`);
      setTimeout(() => setDispositionToast(null), 3000);
      handleStatusChange('available');
    } finally {
      setIsSavingDisposition(false);
    }
  };

  // Filter contacts assigned to agent or high intent
  const myAssignedContacts = contacts.filter(c => 
    !c.lead_owner_id || 
    c.lead_owner_id === session.agent.id ||
    c.status === 'interested'
  );

  const rawLeads: Contact[] = myAssignedContacts.length > 0 ? myAssignedContacts : [
    {
      id: 'c-1',
      organization_id: 'org-1',
      name: 'Rajesh Sharma',
      phone_number: '+91 98765 43210',
      email: 'rajesh.sharma@apexhealth.in',
      status: 'interested',
      preferred_language: 'hi',
      lead_source: 'Inbound Google Ads',
      custom_fields: {
        intent_score: 94,
        bot_summary: 'Requested enterprise voice setup for multi-doctor clinic. High buying intent.'
      },
      created_at: '2026-09-08T09:00:00Z',
      updated_at: '2026-09-08T10:15:00Z'
    },
    {
      id: 'c-2',
      organization_id: 'org-1',
      name: 'Sneha Gupta',
      phone_number: '+91 98765 43211',
      email: 'sneha@guptadental.com',
      status: 'callback',
      preferred_language: 'en',
      lead_source: 'Outbound Campaign',
      custom_fields: {
        intent_score: 82,
        callback_scheduled_for: 'Today, 4:30 PM',
        bot_summary: 'Expressed interest in Hindi/English bilingual bot. In surgery until 4:00 PM.'
      },
      created_at: '2026-09-08T08:30:00Z',
      updated_at: '2026-09-08T09:45:00Z'
    },
    {
      id: 'c-3',
      organization_id: 'org-1',
      name: 'Vikram Malhotra',
      phone_number: '+91 98765 43212',
      email: 'vikram.singh@clouddot.io',
      status: 'interested',
      preferred_language: 'hi',
      lead_source: 'Website Demo Call',
      custom_fields: {
        intent_score: 89,
        bot_summary: 'Tested voice demo on website and rated it 5 stars. Looking to automate dental patient reminders.'
      },
      created_at: '2026-09-08T07:15:00Z',
      updated_at: '2026-09-08T08:00:00Z'
    }
  ];

  const filteredLeads = rawLeads.filter(lead => {
    const matchesSearch = 
      (lead.name || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
      lead.phone_number.includes(searchQuery) ||
      (lead.email || '').toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;

    if (activeLeadTab === 'interested') {
      return lead.status === 'interested' || (lead.custom_fields?.intent_score && lead.custom_fields.intent_score >= 80);
    }
    if (activeLeadTab === 'callbacks') {
      return lead.status === 'callback' || lead.custom_fields?.callback_scheduled_for;
    }
    return true;
  });

  const filteredTasks = tasks.filter(t => {
    if (taskFilter === 'pending') return t.status !== 'completed';
    if (taskFilter === 'completed') return t.status === 'completed';
    return true;
  });

  const formatSeconds = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6 text-slate-100 font-sans pb-16">
      
      {/* Toast Notification */}
      {dispositionToast && (
        <div className="fixed top-6 right-6 z-50 p-4 rounded-2xl bg-emerald-950/90 border border-emerald-500/50 text-emerald-200 shadow-2xl backdrop-blur-xl flex items-center space-x-3 animate-in fade-in slide-in-from-top-4">
          <CheckCircle2 className="w-5 h-5 text-emerald-400" />
          <span className="text-sm font-bold">{dispositionToast}</span>
        </div>
      )}

      {/* 1. TOP AGENT WORKSPACE HEADER & STATUS HUB */}
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
                <h2 className="text-xl font-black tracking-tight text-white">{session.agent.name}</h2>
                <span className="px-2.5 py-0.5 rounded-full text-xs font-mono font-bold bg-indigo-500/20 border border-indigo-500/40 text-indigo-300">
                  Ext {session.agent.sip_extension || '101'}
                </span>
                <span className="hidden sm:inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  <span>SIP 8kHz Active</span>
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

          {/* Status Switcher & Dashboard Navigation */}
          <div className="flex flex-wrap items-center gap-2.5 w-full lg:w-auto justify-end">
            
            {/* Status Toolbar */}
            <div className="flex flex-wrap items-center gap-1.5 p-1.5 rounded-2xl bg-slate-950/80 border border-slate-800/80">
              {[
                { id: 'available', label: 'Available', color: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30', dot: 'bg-emerald-400' },
                { id: 'on_call', label: 'In Call', color: 'bg-red-500/20 text-red-300 border-red-500/40 hover:bg-red-500/30', dot: 'bg-red-400' },
                { id: 'in_break', label: 'Break', color: 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500/30', dot: 'bg-amber-400' },
                { id: 'wrap_up', label: 'Wrap-Up', color: 'bg-purple-500/20 text-purple-300 border-purple-500/40 hover:bg-purple-500/30', dot: 'bg-purple-400' },
                { id: 'offline', label: 'Offline', color: 'bg-slate-800/60 text-slate-400 border-slate-700 hover:bg-slate-800', dot: 'bg-slate-500' },
              ].map((st) => {
                const isSelected = currentStatus === st.id;
                return (
                  <button
                    key={st.id}
                    onClick={() => handleStatusChange(st.id as AgentStatusType)}
                    className={`px-3 py-1.5 rounded-xl text-xs font-bold border transition-all flex items-center space-x-1.5 ${
                      isSelected
                        ? `${st.color} shadow-lg ring-1 ring-white/10 scale-105`
                        : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-900/60'
                    }`}
                  >
                    <div className={`w-2 h-2 rounded-full ${st.dot} ${isSelected ? 'animate-pulse' : ''}`} />
                    <span>{st.label}</span>
                  </button>
                );
              })}
            </div>

            {/* Switch to Org Dashboard Button */}
            <button
              onClick={() => { window.location.hash = '#org-dashboard'; }}
              className="px-3.5 py-2 rounded-xl bg-indigo-600/20 hover:bg-indigo-600/40 border border-indigo-500/40 text-indigo-300 hover:text-white text-xs font-bold transition-all flex items-center space-x-1.5"
              title="Switch to Admin Org View"
            >
              <ArrowUpRight className="w-3.5 h-3.5" />
              <span>Org View</span>
            </button>

            {/* Logout */}
            <button
              onClick={onLogout}
              className="px-3.5 py-2 rounded-xl bg-red-500/15 hover:bg-red-500/30 border border-red-500/40 text-red-300 hover:text-white text-xs font-black transition-all flex items-center space-x-1.5 shadow-sm active:scale-95 cursor-pointer"
              title="End session and log out"
            >
              <LogOut className="w-3.5 h-3.5 text-red-400" />
              <span>Logout</span>
            </button>

          </div>

        </div>
      </div>

      {/* 2. LIVE INCOMING HUMAN HANDOFF SCREEN-POP ALERT BANNER */}
      {incomingHandoff && (
        <div className="glass-panel border-2 border-red-500/60 rounded-3xl p-5 bg-gradient-to-r from-red-950/80 via-slate-900 to-indigo-950/80 backdrop-blur-xl shadow-2xl relative overflow-hidden animate-pulse">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div className="flex items-start space-x-4">
              <div className="p-3.5 rounded-2xl bg-red-500/20 border border-red-500/40 text-red-400 mt-1">
                <PhoneIncoming className="w-7 h-7 animate-bounce" />
              </div>
              <div>
                <div className="flex items-center space-x-2">
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-black uppercase tracking-wider bg-red-500 text-white shadow-md">
                    🚨 LIVE WARM HANDOFF REQUEST
                  </span>
                  <span className="text-xs font-bold text-emerald-400 flex items-center space-x-1">
                    <Sparkles className="w-3 h-3" />
                    <span>High Conversion Likelihood (89%)</span>
                  </span>
                </div>
                <h3 className="text-xl font-black text-white mt-1">{incomingHandoff.caller_name}</h3>
                <p className="text-xs font-mono text-indigo-300 mt-0.5">{incomingHandoff.phone_number}</p>
                <p className="text-xs text-slate-300 mt-2 italic bg-slate-950/60 p-2.5 rounded-xl border border-slate-800">
                  "{incomingHandoff.summary}"
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-3 w-full md:w-auto self-end md:self-center">
              <button
                onClick={() => setIncomingHandoff(null)}
                className="px-4 py-3 rounded-2xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition-all border border-slate-700"
              >
                Dismiss
              </button>
              <button
                onClick={handleAcceptHandoff}
                className="flex-1 md:flex-initial px-6 py-3.5 rounded-2xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white text-sm font-black tracking-wide shadow-xl shadow-emerald-500/30 border border-white/20 transition-all flex items-center justify-center space-x-2 active:scale-95"
              >
                <PhoneCall className="w-4 h-4 text-emerald-100" />
                <span>ACCEPT & SCREEN POP</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 3. GAMIFIED AGENT PERFORMANCE METRICS BAR */}
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
            <span className="text-xs text-slate-400 font-mono">AHT: {session.stats.avg_handling_time_s}s</span>
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

      {/* 4. MAIN WORKSPACE GRID: SOFTPHONE DIALPAD & ASSIGNED TASKS / LEADS */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        
        {/* Left Column: Embedded Web Softphone Dialer & Active Call Bar */}
        <div className="lg:col-span-5 space-y-6">
          
          <div className="glass-panel border border-slate-800 rounded-3xl p-5 sm:p-6 bg-slate-900/80 backdrop-blur-xl relative shadow-2xl">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-4">
              <div className="flex items-center space-x-2.5">
                <Radio className="w-5 h-5 text-indigo-400 animate-pulse" />
                <h3 className="font-extrabold text-slate-100 text-base">Web Softphone & Dialer</h3>
              </div>
              <span className="px-2.5 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-400 text-[11px] font-mono font-bold">
                SIP Registered (101)
              </span>
            </div>

            {/* Live Call Controller Banner if active */}
            {activeCall ? (
              <div className="p-4 rounded-2xl bg-gradient-to-r from-red-950/80 via-slate-900 to-indigo-950/80 border-2 border-red-500/60 space-y-4 mb-4 shadow-xl">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="px-2 py-0.5 rounded-md bg-red-500 text-white font-mono text-[10px] uppercase font-bold tracking-wider">
                      {activeCall.status === 'connecting' ? 'DIALING...' : 'LIVE CALL CONNECTED'}
                    </span>
                    <h4 className="text-lg font-black text-white mt-1">{activeCall.contact_name}</h4>
                    <p className="text-xs text-slate-300 font-mono">{activeCall.phone_number}</p>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-mono font-black text-emerald-400">{formatSeconds(activeCall.duration)}</div>
                    <span className="text-[10px] text-emerald-300 font-bold">Sentiment: Positive 🙂</span>
                  </div>
                </div>

                {/* Call Control Buttons */}
                <div className="flex items-center justify-center space-x-3 pt-2">
                  <button
                    onClick={() => setIsMuted(!isMuted)}
                    className={`p-3 rounded-xl border font-bold transition-all ${
                      isMuted ? 'bg-amber-500/20 border-amber-500 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700'
                    }`}
                    title={isMuted ? "Unmute" : "Mute"}
                  >
                    {isMuted ? <MicOff className="w-5 h-5 text-amber-400" /> : <Mic className="w-5 h-5" />}
                  </button>

                  <button
                    onClick={() => setIsOnHold(!isOnHold)}
                    className={`p-3 rounded-xl border font-bold transition-all ${
                      isOnHold ? 'bg-amber-500/20 border-amber-500 text-amber-300' : 'bg-slate-800 border-slate-700 text-slate-200 hover:bg-slate-700'
                    }`}
                    title={isOnHold ? "Resume Call" : "Hold"}
                  >
                    <Pause className="w-5 h-5" />
                  </button>

                  <button
                    onClick={handleEndCall}
                    className="px-6 py-3 rounded-xl bg-red-600 hover:bg-red-500 text-white font-black text-sm flex items-center space-x-2 shadow-lg shadow-red-600/30 transition-all active:scale-95"
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
                  className="absolute right-3.5 top-3.5 text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800 font-bold"
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
                  className="p-3.5 rounded-2xl bg-slate-950/70 border border-slate-800/80 hover:bg-indigo-950/50 hover:border-indigo-500/50 text-slate-100 font-mono font-black text-lg shadow-sm transition-all active:scale-95 flex flex-col items-center justify-center hover:shadow-indigo-500/10"
                >
                  <span>{k}</span>
                </button>
              ))}
            </div>

            {/* Initiate Call Button */}
            <button
              onClick={() => handleInitiateCall()}
              disabled={!dialNumber && !activeCall}
              className="w-full py-3.5 rounded-2xl bg-gradient-to-r from-emerald-600 via-teal-600 to-indigo-600 hover:from-emerald-500 hover:to-indigo-500 text-white font-black text-base shadow-xl shadow-emerald-500/20 border border-white/20 transition-all flex items-center justify-center space-x-2 active:scale-95 disabled:opacity-50"
            >
              <PhoneCall className="w-5 h-5 text-emerald-200" />
              <span>START DIRECT SIP CALL</span>
            </button>

            {/* Post-Call Disposition & Wrap-Up Box */}
            {(currentStatus === 'wrap_up' || activeCall?.status === 'ended') && (
              <div className="mt-6 pt-4 border-t border-slate-800 space-y-3 bg-purple-950/30 p-4 rounded-2xl border border-purple-500/40 animate-in fade-in">
                <div className="flex items-center space-x-2 text-purple-300 font-extrabold text-xs">
                  <Tag className="w-4 h-4" />
                  <span>Call Wrap-Up & Lead Disposition</span>
                </div>

                {/* Disposition Pills */}
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: 'interested', label: '🔥 Interested (Hot)' },
                    { id: 'booked', label: '✅ Booked Demo/Appt' },
                    { id: 'callback', label: '📅 Callback Needed' },
                    { id: 'not_interested', label: '❌ Not Interested' },
                  ].map((disp) => (
                    <button
                      key={disp.id}
                      onClick={() => setSelectedDisposition(disp.id)}
                      className={`p-2 rounded-xl text-xs font-bold border transition-all text-left ${
                        selectedDisposition === disp.id
                          ? 'bg-purple-600 text-white border-purple-400 shadow-lg'
                          : 'bg-slate-900 border-slate-800 text-slate-300 hover:bg-slate-800'
                      }`}
                    >
                      {disp.label}
                    </button>
                  ))}
                </div>

                {/* Callback Time Picker */}
                {selectedDisposition === 'callback' && (
                  <div className="space-y-1">
                    <label className="text-[11px] font-bold text-amber-300 flex items-center space-x-1">
                      <Calendar className="w-3 h-3" />
                      <span>Scheduled Follow-Up Time:</span>
                    </label>
                    <input
                      type="datetime-local"
                      value={callbackDateTime}
                      onChange={(e) => setCallbackDateTime(e.target.value)}
                      className="w-full p-2.5 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white focus:outline-none focus:border-amber-500"
                    />
                  </div>
                )}

                {/* Notes Textarea */}
                <textarea
                  value={callNotes}
                  onChange={(e) => setCallNotes(e.target.value)}
                  placeholder="Enter call notes or next action points..."
                  className="w-full p-3 rounded-xl bg-slate-950 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-purple-500"
                  rows={2}
                />

                <button
                  onClick={() => handleSaveDisposition()}
                  disabled={isSavingDisposition}
                  className="w-full py-2.5 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-extrabold text-xs shadow-md transition-all active:scale-95 disabled:opacity-50 flex items-center justify-center space-x-2"
                >
                  {isSavingDisposition ? (
                    <span>Saving to CRM...</span>
                  ) : (
                    <>
                      <Check className="w-4 h-4" />
                      <span>SAVE DISPOSITION & NEXT LEAD</span>
                    </>
                  )}
                </button>
              </div>
            )}

          </div>

        </div>

        {/* Right Column: Assigned Tasks & Assigned Leads Hub */}
        <div className="lg:col-span-7 space-y-6">
          
          <div className="glass-panel border border-slate-800 rounded-3xl p-5 sm:p-6 bg-slate-900/80 backdrop-blur-xl">
            
            {/* Main Tabs Switcher: Assigned Tasks vs Assigned Leads vs Call History */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800 mb-4">
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setActiveWorkspaceMode('tasks')}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center space-x-2 ${
                    activeWorkspaceMode === 'tasks'
                      ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                      : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  <ListTodo className="w-4 h-4" />
                  <span>My Assigned Tasks ({tasks.filter(t => t.status !== 'completed').length})</span>
                </button>

                <button
                  onClick={() => setActiveWorkspaceMode('leads')}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center space-x-2 ${
                    activeWorkspaceMode === 'leads'
                      ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                      : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  <Flame className="w-4 h-4 text-amber-400" />
                  <span>Assigned Leads ({filteredLeads.length})</span>
                </button>

                <button
                  onClick={() => setActiveWorkspaceMode('history')}
                  className={`px-3.5 py-2 rounded-xl text-xs font-bold transition-all flex items-center space-x-2 ${
                    activeWorkspaceMode === 'history'
                      ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30'
                      : 'bg-slate-950/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  <History className="w-4 h-4 text-purple-400" />
                  <span>Call Logs</span>
                </button>
              </div>

              <button
                onClick={fetchTasks}
                className="p-2 rounded-xl bg-slate-950 border border-slate-800 text-slate-400 hover:text-white self-end sm:self-auto"
                title="Refresh from database"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isTasksLoading ? 'animate-spin text-indigo-400' : ''}`} />
              </button>
            </div>

            {/* ======================================================== */}
            {/* VIEW 1: MY ASSIGNED TASKS (Live Synced with Database)    */}
            {/* ======================================================== */}
            {activeWorkspaceMode === 'tasks' && (
              <div className="space-y-4">
                
                {/* Task Subfilters */}
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-slate-400">
                    Live Tasks from Database ({tasks.length} total)
                  </span>
                  <div className="flex p-1 rounded-xl bg-slate-950 border border-slate-800 text-[11px] font-semibold">
                    <button
                      onClick={() => setTaskFilter('pending')}
                      className={`px-2.5 py-1 rounded-lg transition-all ${
                        taskFilter === 'pending' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Pending ({tasks.filter(t => t.status !== 'completed').length})
                    </button>
                    <button
                      onClick={() => setTaskFilter('completed')}
                      className={`px-2.5 py-1 rounded-lg transition-all ${
                        taskFilter === 'completed' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      Completed ({tasks.filter(t => t.status === 'completed').length})
                    </button>
                    <button
                      onClick={() => setTaskFilter('all')}
                      className={`px-2.5 py-1 rounded-lg transition-all ${
                        taskFilter === 'all' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      All
                    </button>
                  </div>
                </div>

                {/* Tasks List */}
                <div className="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                  {filteredTasks.length === 0 ? (
                    <div className="text-center py-10 text-slate-500 text-xs">
                      No tasks found in this view.
                    </div>
                  ) : (
                    filteredTasks.map((t) => {
                      const isCompleted = t.status === 'completed';

                      return (
                        <div
                          key={t.id}
                          className={`p-4 rounded-2xl border transition-all flex flex-col sm:flex-row sm:items-center justify-between gap-3 ${
                            isCompleted
                              ? 'bg-slate-950/40 border-slate-800/60 opacity-60'
                              : 'bg-slate-950/80 border-slate-800 hover:border-indigo-500/40'
                          }`}
                        >
                          <div className="flex items-start space-x-3.5">
                            <button
                              onClick={() => handleCompleteTask(t.id)}
                              className={`mt-1 p-1 rounded-lg transition-all ${
                                isCompleted ? 'text-emerald-400 bg-emerald-500/10' : 'text-slate-500 hover:text-emerald-400 bg-slate-900 border border-slate-800'
                              }`}
                              title={isCompleted ? "Completed" : "Mark as Completed"}
                            >
                              {isCompleted ? <CheckSquare className="w-5 h-5" /> : <Square className="w-5 h-5" />}
                            </button>

                            <div>
                              <div className="flex items-center space-x-2">
                                <h4 className={`text-sm font-extrabold ${isCompleted ? 'line-through text-slate-400' : 'text-slate-100'}`}>
                                  {t.title}
                                </h4>
                                <span className={`px-2 py-0.5 rounded-md text-[10px] font-bold ${
                                  isCompleted ? 'bg-emerald-500/20 text-emerald-300' : 'bg-amber-500/20 text-amber-300'
                                }`}>
                                  {t.status.toUpperCase()}
                                </span>
                              </div>

                              {t.description && (
                                <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                                  {t.description}
                                </p>
                              )}

                              <div className="flex items-center space-x-3 text-[11px] text-slate-400 mt-2">
                                {t.contact_name && (
                                  <span className="font-semibold text-slate-300">
                                    👤 {t.contact_name}
                                  </span>
                                )}
                                {t.contact_phone && (
                                  <span className="font-mono text-indigo-300">
                                    📞 {t.contact_phone}
                                  </span>
                                )}
                                {t.due_at && (
                                  <span className="flex items-center space-x-1 text-amber-400 font-mono">
                                    <Clock className="w-3 h-3" />
                                    <span>Due: {new Date(t.due_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</span>
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center space-x-2 self-end sm:self-center shrink-0">
                            {t.contact_phone && (
                              <button
                                onClick={() => handleInitiateCall(t.contact_phone, t.contact_name, t.contact_id)}
                                className="px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs flex items-center space-x-1.5 shadow-md shadow-indigo-600/20 transition-all active:scale-95"
                              >
                                <PhoneCall className="w-3.5 h-3.5" />
                                <span>Call Lead</span>
                              </button>
                            )}

                            {!isCompleted && (
                              <button
                                onClick={() => handleCompleteTask(t.id)}
                                className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-emerald-600/20 hover:text-emerald-300 text-slate-300 text-xs font-bold border border-slate-700 transition-all"
                              >
                                Done
                              </button>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

              </div>
            )}

            {/* ======================================================== */}
            {/* VIEW 2: MY ASSIGNED LEADS QUEUE                          */}
            {/* ======================================================== */}
            {activeWorkspaceMode === 'leads' && (
              <div className="space-y-4">
                
                {/* Header & Tabs */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div className="flex p-1 rounded-xl bg-slate-950/80 border border-slate-800 text-xs font-semibold">
                    <button
                      onClick={() => setActiveLeadTab('interested')}
                      className={`px-3 py-1.5 rounded-lg transition-all flex items-center space-x-1.5 ${
                        activeLeadTab === 'interested' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>🔥 High Intent ({rawLeads.filter(l => l.status === 'interested' || (l.custom_fields?.intent_score && l.custom_fields.intent_score >= 80)).length})</span>
                    </button>
                    <button
                      onClick={() => setActiveLeadTab('callbacks')}
                      className={`px-3 py-1.5 rounded-lg transition-all flex items-center space-x-1.5 ${
                        activeLeadTab === 'callbacks' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>📅 Callbacks</span>
                    </button>
                    <button
                      onClick={() => setActiveLeadTab('all')}
                      className={`px-3 py-1.5 rounded-lg transition-all ${
                        activeLeadTab === 'all' ? 'bg-indigo-600 text-white' : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <span>All ({rawLeads.length})</span>
                    </button>
                  </div>
                </div>

                {/* Search Filter */}
                <div className="relative">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search leads by name, phone, or email..."
                    className="w-full pl-10 pr-4 py-2 rounded-xl bg-slate-950/70 border border-slate-800 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>

                {/* Lead Queue Cards */}
                <div className="space-y-3 max-h-[380px] overflow-y-auto pr-1">
                  {filteredLeads.length === 0 ? (
                    <div className="text-center py-8 text-slate-500 text-xs">
                      No leads matching this filter.
                    </div>
                  ) : (
                    filteredLeads.map((ld) => {
                      const intentScore = ld.custom_fields?.intent_score || 85;
                      const isSelected = selectedLead?.id === ld.id;

                      return (
                        <div
                          key={ld.id}
                          onClick={() => setSelectedLead(ld)}
                          className={`p-4 rounded-2xl border transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 group ${
                            isSelected
                              ? 'bg-indigo-950/40 border-indigo-500/60 ring-1 ring-indigo-500/40'
                              : 'bg-slate-950/60 border-slate-800 hover:border-slate-700 hover:bg-slate-900/60'
                          }`}
                        >
                          <div className="flex items-center space-x-3.5">
                            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center font-black text-base">
                              {ld.name ? ld.name.charAt(0) : 'L'}
                            </div>
                            <div>
                              <div className="flex items-center space-x-2">
                                <span className="font-extrabold text-slate-100 text-sm">{ld.name}</span>
                                <span className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 text-[10px] font-mono">
                                  {ld.lead_source || 'Direct'}
                                </span>
                                {ld.status === 'interested' && (
                                  <span className="px-2 py-0.5 rounded-md bg-amber-500/15 border border-amber-500/30 text-amber-300 text-[10px] font-bold">
                                    {intentScore}% Intent
                                  </span>
                                )}
                                {ld.status === 'callback' && (
                                  <span className="px-2 py-0.5 rounded-md bg-blue-500/15 border border-blue-500/30 text-blue-300 text-[10px] font-bold">
                                    Callback
                                  </span>
                                )}
                              </div>
                              <p className="text-xs text-slate-400 font-mono mt-0.5">{ld.phone_number}</p>
                              {ld.custom_fields?.bot_summary && (
                                <p className="text-[11px] text-slate-400 line-clamp-1 italic mt-1">
                                  "{ld.custom_fields.bot_summary}"
                                </p>
                              )}
                            </div>
                          </div>

                          <div className="flex items-center space-x-2 self-end sm:self-center">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedLead(ld);
                              }}
                              className="px-3 py-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-bold transition-all"
                            >
                              Context
                            </button>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                handleInitiateCall(ld.phone_number, ld.name, ld.id);
                              }}
                              className="px-3.5 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white border border-indigo-400 text-xs font-bold transition-all flex items-center space-x-1.5 shadow-md shadow-indigo-600/20 active:scale-95"
                            >
                              <PhoneCall className="w-3.5 h-3.5" />
                              <span>Call</span>
                            </button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

              </div>
            )}

            {/* ======================================================== */}
            {/* VIEW 3: SPOKEN RECORDINGS & CALL LOGS                    */}
            {/* ======================================================== */}
            {activeWorkspaceMode === 'history' && (
              <div className="space-y-3">
                {[
                  { id: 'c1', contact: 'Rajesh Sharma', duration: '2m 14s', outcome: 'Interested', summary: 'Customer interested in Enterprise Voice Agent Plan. Requested demo call.' },
                  { id: 'c2', contact: 'Sneha Gupta', duration: '1m 45s', outcome: 'Callback Scheduled', summary: 'Wants callback tomorrow at 3 PM regarding SIP trunking pricing.' }
                ].map((rec) => (
                  <div key={rec.id} className="p-3.5 rounded-2xl bg-slate-950/60 border border-slate-800 text-xs space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-200">{rec.contact}</span>
                      <span className="px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-300 font-mono text-[10px] font-bold">
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
            )}

          </div>

          {/* Detailed Lead Context Drawer / Inspector */}
          {selectedLead && (
            <div className="glass-panel border-2 border-indigo-500/40 rounded-3xl p-5 sm:p-6 bg-slate-900/90 backdrop-blur-xl relative space-y-4 shadow-2xl">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center space-x-2">
                  <FileText className="w-5 h-5 text-indigo-400" />
                  <h3 className="font-extrabold text-white text-base">Lead Intelligence & Conversation History</h3>
                </div>
                <button
                  onClick={() => setSelectedLead(null)}
                  className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              {/* Lead Identity Summary */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-3.5 rounded-2xl bg-slate-950/70 border border-slate-800 text-xs">
                <div>
                  <span className="text-slate-500 font-bold block">CONTACT NAME</span>
                  <span className="text-white font-extrabold text-sm">{selectedLead.name}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-bold block">PHONE NUMBER</span>
                  <span className="text-indigo-300 font-mono font-bold text-sm">{selectedLead.phone_number}</span>
                </div>
                <div>
                  <span className="text-slate-500 font-bold block">LANGUAGE & SOURCE</span>
                  <span className="text-slate-300 font-medium">{selectedLead.preferred_language?.toUpperCase() || 'HI'} • {selectedLead.lead_source || 'Direct'}</span>
                </div>
              </div>

              {/* AI Conversation Analysis */}
              <div className="p-4 rounded-2xl bg-indigo-950/20 border border-indigo-500/30 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold text-indigo-300 flex items-center space-x-1.5">
                    <Sparkles className="w-4 h-4 text-purple-400" />
                    <span>AI Bot Pre-Qualification Summary</span>
                  </span>
                  <span className="px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-300 text-[10px] font-mono font-bold">
                    Intent Score: {selectedLead.custom_fields?.intent_score || 88}/100
                  </span>
                </div>
                <p className="text-xs text-slate-300 leading-relaxed">
                  {selectedLead.custom_fields?.bot_summary || 
                    "Customer had a 2m 14s conversation with Superfone Voice AI bot. Inquired regarding clinic pricing, multi-agent capacity, and integration with dental practice management software. Tone was highly engaged."}
                </p>

                {/* Audio Recording Player */}
                <div className="mt-3 pt-3 border-t border-indigo-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center space-x-3 w-full">
                    <button
                      onClick={() => setPlayingAudioId(playingAudioId === selectedLead.id ? null : selectedLead.id)}
                      className="p-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition-all shadow-md shadow-indigo-600/30"
                    >
                      {playingAudioId === selectedLead.id ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                    </button>
                    
                    <div className="flex-1 bg-slate-950 h-2 rounded-full overflow-hidden border border-slate-800">
                      <div 
                        className="bg-gradient-to-r from-indigo-500 to-purple-500 h-full rounded-full transition-all duration-300"
                        style={{ width: playingAudioId === selectedLead.id ? '65%' : '20%' }}
                      />
                    </div>
                    <span className="font-mono text-xs text-slate-400">2:14</span>
                  </div>

                  <button
                    onClick={() => setPlaybackSpeed(playbackSpeed === 1 ? 1.5 : 1)}
                    className="px-2.5 py-1 rounded-lg bg-slate-800 text-xs font-mono text-slate-300 hover:bg-slate-700 self-end sm:self-center"
                  >
                    {playbackSpeed}x
                  </button>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center space-x-3 pt-2">
                <button
                  onClick={() => handleInitiateCall(selectedLead.phone_number, selectedLead.name, selectedLead.id)}
                  className="flex-1 py-3 rounded-2xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-extrabold text-xs shadow-lg shadow-emerald-600/20 transition-all flex items-center justify-center space-x-2"
                >
                  <PhoneCall className="w-4 h-4" />
                  <span>CALL THIS LEAD NOW</span>
                </button>
                
                <button
                  onClick={() => {
                    handleStatusChange('wrap_up');
                  }}
                  className="px-4 py-3 rounded-2xl bg-purple-600/20 hover:bg-purple-600 text-purple-300 hover:text-white border border-purple-500/40 font-bold text-xs transition-all"
                >
                  Log Disposition
                </button>
              </div>

            </div>
          )}

        </div>

      </div>

    </div>
  );
};
