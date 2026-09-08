import React from 'react';
import { LayoutDashboard, Radio, Users, Megaphone, Mic, TestTube2, Cpu, Settings, X, CheckSquare, MessageSquare, UserCheck } from 'lucide-react';

interface SidebarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isOpen?: boolean;
  onClose?: () => void;
}

export const Sidebar: React.FC<SidebarProps> = React.memo(({ activeTab, setActiveTab, isOpen = false, onClose }) => {
  const navItems = [
    { id: 'org-dashboard', label: 'Organization Dashboard', icon: LayoutDashboard },
    { id: 'agent-panel', label: 'Agent Panel', icon: UserCheck },
    { id: 'live-monitor', label: 'Live Call Monitor', icon: Radio },
    { id: 'crm', label: 'Voice CRM & Calls', icon: Users },
    { id: 'tasks', label: 'To-Do & Tasks', icon: CheckSquare },
    { id: 'team', label: 'Team Activity', icon: UserCheck },
    { id: 'campaigns', label: 'Campaign Engine', icon: Megaphone },
    { id: 'voice-studio', label: 'Voice Studio', icon: Mic },
    { id: 'evaluations', label: 'Evaluation & QA', icon: TestTube2 },
    { id: 'load-testing', label: 'Load & Capacity', icon: Cpu },
    { id: 'settings', label: 'System Settings', icon: Settings },
  ];

  const handleNavClick = (id: string) => {
    setActiveTab(id);
    if (onClose) onClose();
  };

  return (
    <>
      {/* Mobile Backdrop Overlay */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-40 lg:hidden transition-opacity"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Drawer Container */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 glass-panel border-r border-slate-800 flex flex-col h-screen shrink-0 transform transition-transform duration-300 ease-in-out lg:static lg:translate-x-0 ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        {/* Brand Header */}
        <div className="p-4 md:p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center text-white font-extrabold text-lg shadow-md shadow-indigo-500/20">
              S
            </div>
            <div>
              <span className="font-bold text-slate-100 dark:text-white tracking-tight text-base leading-none block">SUPERFONE</span>
              <span className="text-[11px] text-indigo-400 font-semibold tracking-wide uppercase mt-0.5 block">AI Voice Platform</span>
            </div>
          </div>

          {/* Close Button for Mobile Drawer */}
          {onClose && (
            <button
              onClick={onClose}
              className="lg:hidden p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
              aria-label="Close sidebar"
            >
              <X className="w-5 h-5" />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav className="p-3 space-y-1 flex-1 overflow-y-auto">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleNavClick(item.id)}
                className={`w-full flex items-center space-x-3 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all duration-150 ${
                  isActive
                    ? 'bg-indigo-600/15 text-indigo-400 border border-indigo-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                }`}
              >
                <Icon className={`w-4.5 h-4.5 ${isActive ? 'text-indigo-400' : 'text-slate-400'}`} />
                <span className="tracking-wide">{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Footer Info */}
        <div className="p-4 border-t border-slate-800 text-xs text-slate-400 bg-slate-950/30">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <span className="text-slate-300 font-medium text-[11px]">FastAPI Engine v2.0</span>
            </div>
            <span className="px-2 py-0.5 rounded-full bg-emerald-500/15 text-emerald-400 text-[10px] font-mono border border-emerald-500/30">ONLINE</span>
          </div>
          <div className="mt-1.5 text-[10px] text-slate-500 font-mono">AudioSocket :9092 | SQLite</div>
        </div>
      </aside>
    </>
  );
});

