import React, { useState, useEffect } from 'react';
import { Bell, Activity, Server, PhoneCall, Sun, Moon, Menu, Clock, XCircle, UserCheck, LogOut } from 'lucide-react';
import { SystemOverview, AgentSession } from '../types';

interface HeaderProps {
  overview: SystemOverview | null;
  theme: 'dark' | 'light';
  onToggleTheme: () => void;
  onToggleMobileMenu?: () => void;
  agentSession?: AgentSession | null;
  onOpenAgentLogin?: () => void;
  onLogoutAgent?: () => void;
}

export const Header: React.FC<HeaderProps> = React.memo(({
  overview,
  theme,
  onToggleTheme,
  onToggleMobileMenu,
  agentSession,
  onOpenAgentLogin,
  onLogoutAgent
}) => {
  const [activeAlert, setActiveAlert] = useState<{ id: string; note: string; contact_name: string; contact_phone: string } | null>(null);

  const healthyCount = overview?.services.filter(s => s.status === 'healthy').length || 0;
  const totalServices = overview?.services.length || 5;

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    let ws: WebSocket | null = null;

    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (evt) => {
        try {
          const data = JSON.parse(evt.data);
          if (data.type === 'REMINDER_ALERT') {
            setActiveAlert({
              id: data.reminder_id,
              note: data.note,
              contact_name: data.contact_name,
              contact_phone: data.contact_phone
            });
          }
        } catch (ex) {}
      };
    } catch (ex) {}

    return () => {
      if (ws) ws.close();
    };
  }, []);

  return (
    <>
      {activeAlert && (
        <div className="bg-amber-500/90 text-slate-950 px-4 py-2.5 flex items-center justify-between shadow-lg z-50 animate-in slide-in-from-top duration-200">
          <div className="flex items-center space-x-3 text-xs md:text-sm font-semibold">
            <Clock className="w-5 h-5 text-slate-950 animate-bounce" />
            <span>
              <strong>REMINDER ALERT:</strong> {activeAlert.note} (Lead: {activeAlert.contact_name} {activeAlert.contact_phone})
            </span>
          </div>
          <button
            onClick={() => setActiveAlert(null)}
            className="p-1 hover:bg-black/10 rounded-full transition-colors"
            aria-label="Dismiss reminder alert"
          >
            <XCircle className="w-5 h-5" />
          </button>
        </div>
      )}

      <header className="h-16 glass-panel border-b border-slate-800 px-3 md:px-6 flex items-center justify-between shrink-0 z-30 overflow-hidden">
        <div className="flex items-center space-x-2.5 min-w-0 overflow-hidden">
          {onToggleMobileMenu && (
            <button
              onClick={onToggleMobileMenu}
              className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors shrink-0"
              aria-label="Open sidebar menu"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}

          <div className="flex items-center space-x-2.5 min-w-0 overflow-hidden">
            <h2 className="text-xs sm:text-sm md:text-base lg:text-lg font-bold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-indigo-300 whitespace-nowrap truncate min-w-0">
              <span className="hidden sm:inline">Superfone AI Telephony Hub</span>
              <span className="sm:hidden">Superfone Hub</span>
            </h2>
            <span className="hidden xl:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-gradient-to-r from-indigo-500/15 via-purple-500/15 to-pink-500/15 text-indigo-300 border border-indigo-500/30 shrink-0 whitespace-nowrap shadow-sm">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
              Live Telephony Cluster
            </span>
          </div>
        </div>

        <div className="flex items-center space-x-3 md:space-x-4 shrink-0">
          <div className="hidden md:flex items-center space-x-2 text-xs bg-slate-800/40 px-3 py-1.5 rounded-full border border-slate-700/50 shadow-inner">
            <Server className="w-4 h-4 text-indigo-400" />
            <span className="text-slate-400 hidden lg:inline font-medium">Services:</span>
            <span className={`font-bold ${healthyCount === totalServices ? 'text-emerald-400' : 'text-amber-400'}`}>
              {healthyCount}/{totalServices} <span className="hidden lg:inline">Online</span>
            </span>
          </div>

          <div className="flex items-center space-x-2 text-xs bg-indigo-500/10 px-3 py-1.5 rounded-full border border-indigo-500/30 shadow-sm">
            <PhoneCall className="w-4 h-4 text-indigo-400 animate-pulse" />
            <span className="text-slate-300 hidden sm:inline font-semibold">Active Calls:</span>
            <span className="font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-purple-400">
              {overview?.active_calls || 0}
            </span>
          </div>

          {/* Agent Session Header Status / Login / Logout Button */}
          {agentSession ? (
            <div className="flex items-center space-x-2 bg-indigo-950/60 border border-indigo-500/40 px-3 py-1 rounded-2xl">
              <div className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
              <div className="hidden sm:block text-left text-xs">
                <div className="font-bold text-white leading-tight">{agentSession.agent.name}</div>
                <div className="text-[10px] text-indigo-300 font-mono">Ext {agentSession.agent.sip_extension || '101'}</div>
              </div>
              {onLogoutAgent && (
                <button
                  onClick={onLogoutAgent}
                  className="ml-1.5 px-2.5 py-1 rounded-xl bg-red-500/15 hover:bg-red-500/30 border border-red-500/40 text-red-300 hover:text-white text-xs font-bold transition-all flex items-center space-x-1 shadow-sm active:scale-95"
                  title="Logout Agent"
                >
                  <LogOut className="w-3.5 h-3.5 text-red-400" />
                  <span>Logout</span>
                </button>
              )}
            </div>
          ) : (
            <div className="flex items-center space-x-2">
              {onOpenAgentLogin && (
                <button
                  onClick={onOpenAgentLogin}
                  className="px-3.5 py-1.5 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-extrabold shadow-md flex items-center space-x-1.5 transition-all"
                >
                  <UserCheck className="w-4 h-4 text-white" />
                  <span className="hidden sm:inline">Agent Portal</span>
                </button>
              )}
              {onLogoutAgent && (
                <button
                  onClick={onLogoutAgent}
                  className="px-2.5 py-1.5 rounded-xl bg-slate-800/80 hover:bg-red-500/20 border border-slate-700 hover:border-red-500/40 text-slate-300 hover:text-red-300 text-xs font-bold transition-all flex items-center space-x-1.5 active:scale-95"
                  title="Logout to Login Screen"
                >
                  <LogOut className="w-3.5 h-3.5 text-red-400" />
                  <span className="hidden sm:inline">Logout</span>
                </button>
              )}
            </div>
          )}

          <button
            onClick={onToggleTheme}
            className="p-2 rounded-xl bg-slate-800/60 border border-slate-700/60 text-slate-300 hover:text-white hover:border-indigo-500/50 transition-all shadow-md active:scale-95"
            title="Toggle theme"
          >
            {theme === 'dark' ? <Sun className="w-4.5 h-4.5 text-amber-400" /> : <Moon className="w-4.5 h-4.5 text-indigo-400" />}
          </button>
        </div>
      </header>
    </>
  );
});
