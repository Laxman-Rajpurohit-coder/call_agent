import React, { useState, useEffect } from 'react';
import { 
  ShieldCheck, PhoneCall, KeyRound, Sparkles, User, Sun, Sunset, Moon, 
  CheckCircle2, AlertCircle, ArrowRight, Activity, Cpu, Lock, Radio
} from 'lucide-react';
import { AgentSession, AgentProfile } from '../types';

interface AgentLoginPageProps {
  onLoginSuccess: (session: AgentSession) => void;
}

export const AgentLoginPage: React.FC<AgentLoginPageProps> = ({ onLoginSuccess }) => {
  const [agents, setAgents] = useState<AgentProfile[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>('');
  const [emailInput, setEmailInput] = useState<string>('');
  const [pinInput, setPinInput] = useState<string>('1234');
  const [selectedShift, setSelectedShift] = useState<string>('Morning Shift');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [loginMode, setLoginMode] = useState<'quick' | 'manual'>('quick');

  useEffect(() => {
    fetchAgents();
  }, []);

  const fetchAgents = async () => {
    try {
      const res = await fetch('/api/v1/auth/agents');
      if (res.ok) {
        const data: AgentProfile[] = await res.json();
        setAgents(data);
        if (data.length > 0) {
          setSelectedAgentId(data[0].id);
          setEmailInput(data[0].email || '');
        }
      }
    } catch (err) {
      console.error("Failed to fetch available agents", err);
    }
  };

  const handleSelectAgent = (agent: AgentProfile) => {
    setSelectedAgentId(agent.id);
    setEmailInput(agent.email || '');
    setErrorMsg('');
  };

  const handlePinKeyPress = (val: string) => {
    if (val === 'C') {
      setPinInput('');
    } else if (val === 'DEL') {
      setPinInput(prev => prev.slice(0, -1));
    } else if (pinInput.length < 6) {
      setPinInput(prev => prev + val);
    }
  };

  const handleLoginSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsLoading(true);
    setErrorMsg('');

    try {
      const payload = {
        agent_id: loginMode === 'quick' ? selectedAgentId : undefined,
        email: loginMode === 'manual' ? emailInput : undefined,
        pin: pinInput || '1234',
        shift_name: selectedShift
      };

      const res = await fetch('/api/v1/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (res.ok && data.success) {
        onLoginSuccess(data);
      } else {
        setErrorMsg(data.detail || 'Authentication failed. Please check credentials.');
      }
    } catch (err: any) {
      setErrorMsg(`Connection error: ${err.message || 'Server unreachable'}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-center items-center p-4 relative overflow-hidden font-sans">
      {/* Dynamic Glowing Ambient Background Grid & Orbs */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-600/20 rounded-full blur-3xl animate-pulse pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-pink-600/15 rounded-full blur-3xl animate-pulse pointer-events-none" style={{ animationDelay: '1s' }} />
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-cyan-600/10 rounded-full blur-3xl pointer-events-none" />

      {/* Main Glassmorphism Card */}
      <div className="w-full max-w-4xl glass-panel border border-slate-800/80 rounded-3xl p-6 sm:p-8 shadow-2xl relative z-10 backdrop-blur-2xl bg-slate-900/80">
        
        {/* Header Section */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 pb-6 mb-6 border-b border-slate-800">
          <div className="flex items-center space-x-3.5">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-pink-500 flex items-center justify-center text-white font-black text-2xl shadow-xl shadow-indigo-500/30 border border-white/20">
              S
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h1 className="text-2xl font-black tracking-tight text-white">SUPERFONE AI</h1>
                <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold uppercase tracking-widest bg-gradient-to-r from-indigo-500/20 to-purple-500/20 border border-indigo-500/40 text-indigo-300">
                  Agent Workspace
                </span>
              </div>
              <p className="text-xs text-slate-400 font-medium">Telecaller Portal & Voice Operations Gateway</p>
            </div>
          </div>

          {/* Header Action & Diagnostic Badge */}
          <div className="flex items-center space-x-2">
            <button
              onClick={() => { window.location.hash = '#org-dashboard'; window.location.reload(); }}
              className="px-3 py-1.5 rounded-xl bg-slate-800/80 hover:bg-indigo-600/30 border border-slate-700 hover:border-indigo-500/40 text-slate-300 hover:text-white text-xs font-bold transition-all flex items-center space-x-1.5 cursor-pointer shadow-sm"
              title="Return to Main Organization Platform"
            >
              <span>← Org Dashboard</span>
            </button>
            <div className="flex items-center space-x-2 px-3 py-1.5 rounded-xl bg-slate-950/60 border border-emerald-500/30 text-emerald-400 text-xs font-mono">
              <Radio className="w-3.5 h-3.5 animate-pulse text-emerald-400" />
              <span className="hidden sm:inline">MicroSIP 8kHz</span>
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {errorMsg && (
          <div className="mb-6 p-4 rounded-2xl bg-red-950/60 border border-red-500/50 text-red-300 text-xs flex items-center space-x-3 animate-shake">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Column: Quick Agent Selector / Auth Modes */}
          <div className="lg:col-span-7 space-y-6">
            
            {/* Mode Switcher */}
            <div className="flex p-1 rounded-xl bg-slate-950/80 border border-slate-800 text-xs font-semibold">
              <button
                onClick={() => setLoginMode('quick')}
                className={`flex-1 py-2 rounded-lg transition-all flex items-center justify-center space-x-2 ${
                  loginMode === 'quick'
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Sparkles className="w-3.5 h-3.5" />
                <span>Quick Agent Select</span>
              </button>
              <button
                onClick={() => setLoginMode('manual')}
                className={`flex-1 py-2 rounded-lg transition-all flex items-center justify-center space-x-2 ${
                  loginMode === 'manual'
                    ? 'bg-gradient-to-r from-indigo-600 to-purple-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <KeyRound className="w-3.5 h-3.5" />
                <span>Manual Credentials</span>
              </button>
            </div>

            {loginMode === 'quick' ? (
              <div>
                <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block mb-3">
                  Select Active Telecaller Agent
                </label>
                <div className="space-y-3">
                  {agents.map((agent) => {
                    const isSelected = selectedAgentId === agent.id;
                    return (
                      <div
                        key={agent.id}
                        onClick={() => handleSelectAgent(agent)}
                        className={`p-4 rounded-2xl border transition-all cursor-pointer flex items-center justify-between ${
                          isSelected
                            ? 'bg-gradient-to-r from-indigo-950/70 via-purple-950/40 to-slate-900 border-indigo-500/70 shadow-lg shadow-indigo-500/10 ring-1 ring-indigo-500/30'
                            : 'bg-slate-950/40 border-slate-800/90 hover:border-slate-700 hover:bg-slate-900/60'
                        }`}
                      >
                        <div className="flex items-center space-x-3.5">
                          <img
                            src={agent.avatar_url || `https://api.dicebear.com/7.x/avataaars/svg?seed=${agent.name}`}
                            alt={agent.name}
                            className="w-12 h-12 rounded-xl object-cover border border-slate-700 shadow-md"
                          />
                          <div>
                            <div className="flex items-center space-x-2">
                              <span className="font-bold text-slate-100 text-sm">{agent.name}</span>
                              <span className="px-2 py-0.5 rounded-md bg-indigo-500/15 border border-indigo-500/30 text-indigo-300 text-[10px] font-mono">
                                Ext {agent.sip_extension || '101'}
                              </span>
                            </div>
                            <p className="text-xs text-slate-400">{agent.role} • {agent.assigned_leads_count || 8} Active Leads</p>
                          </div>
                        </div>

                        <div className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                          isSelected ? 'bg-indigo-600 border-indigo-400 text-white' : 'border-slate-700'
                        }`}>
                          {isSelected && <CheckCircle2 className="w-3.5 h-3.5" />}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block mb-1.5">
                    Agent Email / SIP Extension
                  </label>
                  <div className="relative">
                    <User className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
                    <input
                      type="text"
                      value={emailInput}
                      onChange={(e) => setEmailInput(e.target.value)}
                      placeholder="alex@superfone.ai or Ext 101"
                      className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                    />
                  </div>
                </div>
              </div>
            )}

            {/* Shift Selector */}
            <div>
              <label className="text-xs font-bold text-slate-300 uppercase tracking-wider block mb-2">
                Shift Assignment
              </label>
              <div className="grid grid-cols-3 gap-2.5">
                {[
                  { name: 'Morning Shift', icon: Sun, time: '09:00 - 17:00' },
                  { name: 'Afternoon Shift', icon: Sunset, time: '13:00 - 21:00' },
                  { name: 'Evening Shift', icon: Moon, time: '17:00 - 01:00' }
                ].map((shift) => {
                  const Icon = shift.icon;
                  const isShiftSel = selectedShift === shift.name;
                  return (
                    <button
                      key={shift.name}
                      type="button"
                      onClick={() => setSelectedShift(shift.name)}
                      className={`p-2.5 rounded-xl border text-left transition-all ${
                        isShiftSel
                          ? 'bg-indigo-950/60 border-indigo-500/60 text-white'
                          : 'bg-slate-950/40 border-slate-800 text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      <Icon className="w-4 h-4 text-indigo-400 mb-1" />
                      <div className="text-xs font-bold">{shift.name}</div>
                      <div className="text-[10px] text-slate-400">{shift.time}</div>
                    </button>
                  );
                })}
              </div>
            </div>

          </div>

          {/* Right Column: PIN Keypad & Launch Button */}
          <div className="lg:col-span-5 flex flex-col justify-between space-y-6">
            
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                  Security PIN Code
                </label>
                <span className="text-[10px] text-slate-500 font-mono">Default: 1234</span>
              </div>

              {/* PIN Indicator Dots */}
              <div className="flex justify-center items-center space-x-3 p-3.5 rounded-2xl bg-slate-950/90 border border-slate-800 mb-4 shadow-inner">
                {[0, 1, 2, 3].map((idx) => {
                  const filled = pinInput.length > idx;
                  return (
                    <div
                      key={idx}
                      className={`w-3.5 h-3.5 rounded-full transition-all duration-200 ${
                        filled
                          ? 'bg-gradient-to-tr from-indigo-500 to-purple-500 shadow-md shadow-indigo-500/50 scale-110'
                          : 'bg-slate-800 border border-slate-700'
                      }`}
                    />
                  );
                })}
              </div>

              {/* Interactive Keypad */}
              <div className="grid grid-cols-3 gap-2">
                {['1', '2', '3', '4', '5', '6', '7', '8', '9', 'C', '0', 'DEL'].map((keyVal) => (
                  <button
                    key={keyVal}
                    type="button"
                    onClick={() => handlePinKeyPress(keyVal)}
                    className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 hover:bg-indigo-950/40 hover:border-indigo-500/50 text-slate-100 font-mono font-bold text-base transition-all active:scale-95 shadow-sm"
                  >
                    {keyVal}
                  </button>
                ))}
              </div>
            </div>

            {/* Launch Workspace Button */}
            <button
              onClick={() => handleLoginSubmit()}
              disabled={isLoading}
              className="w-full py-4 rounded-2xl bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 text-white font-extrabold text-base shadow-xl shadow-indigo-500/25 hover:shadow-indigo-500/40 border border-white/20 transition-all flex items-center justify-center space-x-3 active:scale-[0.99] disabled:opacity-50"
            >
              {isLoading ? (
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <>
                  <ShieldCheck className="w-5 h-5 text-indigo-200" />
                  <span>START AGENT SHIFT</span>
                  <ArrowRight className="w-5 h-5 text-white" />
                </>
              )}
            </button>

          </div>

        </div>

        {/* Footer info */}
        <div className="mt-8 pt-4 border-t border-slate-800/60 flex flex-col sm:flex-row items-center justify-between text-xs text-slate-400 gap-2">
          <div className="flex items-center space-x-2">
            <Lock className="w-3.5 h-3.5 text-indigo-400" />
            <span>Encrypted Telephony Session • Zero Latency MicroSIP</span>
          </div>
          <div className="font-mono text-[11px]">
            Superfone AI Telephony v2.0
          </div>
        </div>

      </div>
    </div>
  );
};
