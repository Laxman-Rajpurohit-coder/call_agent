import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { SEOHead } from './components/SEOHead';
import { SystemOverview, CallSession, Contact, Campaign, EvaluationReport, LoadTestSummary, LogEvent, AgentSession, AgentStatusType } from './types';

// Dynamic lazy loading for code splitting and fast FCP/LCP
const OverviewPage = lazy(() => import('./pages/OverviewPage').then(m => ({ default: m.OverviewPage })));
const LiveMonitorPage = lazy(() => import('./pages/LiveMonitorPage').then(m => ({ default: m.LiveMonitorPage })));
const CRMPage = lazy(() => import('./pages/CRMPage').then(m => ({ default: m.CRMPage })));
const CampaignsPage = lazy(() => import('./pages/CampaignsPage').then(m => ({ default: m.CampaignsPage })));
const VoiceStudioPage = lazy(() => import('./pages/VoiceStudioPage').then(m => ({ default: m.VoiceStudioPage })));
const EvaluationsPage = lazy(() => import('./pages/EvaluationsPage').then(m => ({ default: m.EvaluationsPage })));
const LoadTestingPage = lazy(() => import('./pages/LoadTestingPage').then(m => ({ default: m.LoadTestingPage })));
const SettingsPage = lazy(() => import('./pages/SettingsPage').then(m => ({ default: m.SettingsPage })));
const TasksPage = lazy(() => import('./pages/TasksPage').then(m => ({ default: m.TasksPage })));
const TeamPage = lazy(() => import('./pages/TeamPage').then(m => ({ default: m.TeamPage })));
const AgentLoginPage = lazy(() => import('./pages/AgentLoginPage').then(m => ({ default: m.AgentLoginPage })));
const AgentDashboardPage = lazy(() => import('./pages/AgentDashboardPage').then(m => ({ default: m.AgentDashboardPage })));
// New alias pages for distinct routes
const OrgDashboardPage = lazy(() => import('./pages/OverviewPage').then(m => ({ default: m.OverviewPage })));
const AgentPanelPage = lazy(() => import('./pages/AgentDashboardPage').then(m => ({ default: m.AgentDashboardPage })));

const PageLoader: React.FC = () => (
  <div className="flex flex-col items-center justify-center min-h-[350px] p-8 space-y-4">
    <div className="relative w-10 h-10">
      <div className="absolute inset-0 rounded-full border-4 border-brand-500/20"></div>
      <div className="absolute inset-0 rounded-full border-4 border-brand-500 border-t-transparent animate-spin"></div>
    </div>
    <div className="text-xs font-mono text-slate-400 tracking-wider uppercase animate-pulse">
      Loading Module...
    </div>
  </div>
);

const VALID_TABS = [
  'org-dashboard', 'agent-panel', 'agent-login', 'live-monitor', 'crm', 'tasks',
  'team', 'campaigns', 'voice-studio', 'evaluations', 'load-testing', 'settings'
];

const getInitialTab = (): string => {
  if (typeof window !== 'undefined') {
    const hash = window.location.hash.replace('#', '').trim();
    if (hash && VALID_TABS.includes(hash)) return hash;
    const saved = localStorage.getItem('superfone_active_tab');
    if (saved && VALID_TABS.includes(saved)) return saved;
  }
  return 'org-dashboard';
};

const getInitialTheme = (): 'dark' | 'light' => {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem('superfone_theme');
    if (saved === 'light' || saved === 'dark') return saved;
  }
  return 'dark';
};

export const App: React.FC = () => {
  const [theme, setTheme] = useState<'dark' | 'light'>(getInitialTheme);
  const [activeTab, setActiveTabState] = useState<string>(getInitialTab);
  
  // Agent Auth Session State
  const [agentSession, setAgentSession] = useState<AgentSession | null>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem('superfone_agent_session');
      if (saved) {
        try {
          return JSON.parse(saved);
        } catch (e) {}
      }
    }
    return null;
  });

  const setActiveTab = useCallback((tab: string) => {
    setActiveTabState(tab);
    if (typeof window !== 'undefined') {
      window.location.hash = tab;
      localStorage.setItem('superfone_active_tab', tab);
    }
  }, []);

  const handleAgentLoginSuccess = useCallback((session: AgentSession) => {
    setAgentSession(session);
    if (typeof window !== 'undefined') {
      localStorage.setItem('superfone_agent_session', JSON.stringify(session));
    }
    setActiveTab('agent-panel');
  }, [setActiveTab]);

  const handleLogoutAgent = useCallback(() => {
    if (agentSession) {
      fetch('/api/v1/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_id: agentSession.agent.id })
      }).catch(() => {});
    }
    setAgentSession(null);
    if (typeof window !== 'undefined') {
      localStorage.removeItem('superfone_agent_session');
    }
    setActiveTab('org-dashboard');
  }, [agentSession, setActiveTab]);

  const handleUpdateAgentStatus = useCallback((newStatus: AgentStatusType) => {
    setAgentSession(prev => {
      if (!prev) return null;
      const updated = {
        ...prev,
        agent: {
          ...prev.agent,
          status: newStatus
        }
      };
      if (typeof window !== 'undefined') {
        localStorage.setItem('superfone_agent_session', JSON.stringify(updated));
      }
      return updated;
    });
  }, []);

  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '').trim();
      if (hash && VALID_TABS.includes(hash)) {
        setActiveTabState(hash);
        localStorage.setItem('superfone_active_tab', hash);
      }
    };
    window.addEventListener('hashchange', handleHashChange);
    window.addEventListener('popstate', handleHashChange);
    return () => {
      window.removeEventListener('hashchange', handleHashChange);
      window.removeEventListener('popstate', handleHashChange);
    };
  }, []);

  useEffect(() => {
    if (typeof document !== 'undefined') {
      const root = document.documentElement;
      const body = document.body;
      if (theme === 'dark') {
        root.classList.add('dark');
        root.classList.remove('light');
        body.classList.add('bg-dark-900', 'text-slate-100');
        body.classList.remove('bg-slate-50', 'text-slate-900');
      } else {
        root.classList.remove('dark');
        root.classList.add('light');
        body.classList.remove('bg-dark-900', 'text-slate-100');
        body.classList.add('bg-slate-50', 'text-slate-900');
      }
    }
  }, [theme]);

  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [calls, setCalls] = useState<CallSession[]>([]);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [evaluations, setEvaluations] = useState<EvaluationReport[]>([]);
  const [loadTests, setLoadTests] = useState<LoadTestSummary[]>([]);
  const [logs, setLogs] = useState<LogEvent[]>([]);

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      if (typeof window !== 'undefined') {
        localStorage.setItem('superfone_theme', next);
      }
      return next;
    });
  }, []);

  // Algorithmic optimization: Selective State Update (Hash/Equality Check)
  // Prevents React Virtual DOM re-renders if polled data hasn't changed.
  const prevDataHashes = React.useRef<Record<string, string>>({});

  const setSelectiveState = <T,>(key: string, data: T, setter: (val: T) => void) => {
    const hash = JSON.stringify(data);
    if (prevDataHashes.current[key] !== hash) {
      prevDataHashes.current[key] = hash;
      setter(data);
    }
  };

  const isFetchingRef = React.useRef(false);
  const isFetchingCallsRef = React.useRef(false);
  const activeTabRef = React.useRef(activeTab);

  useEffect(() => {
    activeTabRef.current = activeTab;
  }, [activeTab]);

  // Fast background data fetcher with AbortController timeout & Selective Diffing Algorithm
  const fetchData = async (isInitial = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    const fetchOpts = { signal: controller.signal };

    try {
      if (isInitial) {
        const [ovRes, callRes, ctRes, cmpRes, evRes, ltRes] = await Promise.all([
          fetch('/api/v1/overview', fetchOpts).catch(() => null),
          fetch('/api/v1/calls', fetchOpts).catch(() => null),
          fetch('/api/v1/contacts', fetchOpts).catch(() => null),
          fetch('/api/v1/campaigns', fetchOpts).catch(() => null),
          fetch('/api/v1/evaluations', fetchOpts).catch(() => null),
          fetch('/api/v1/load-tests', fetchOpts).catch(() => null),
        ]);

        if (ovRes?.ok) setSelectiveState('overview', await ovRes.json(), setOverview);
        if (callRes?.ok) setSelectiveState('calls', await callRes.json(), setCalls);
        if (ctRes?.ok) setSelectiveState('contacts', await ctRes.json(), setContacts);
        if (cmpRes?.ok) setSelectiveState('campaigns', await cmpRes.json(), setCampaigns);
        if (evRes?.ok) setSelectiveState('evaluations', await evRes.json(), setEvaluations);
        if (ltRes?.ok) setSelectiveState('loadTests', await ltRes.json(), setLoadTests);
      } else {
        const currentTab = activeTabRef.current;
        const promises: Promise<Response | null>[] = [fetch('/api/v1/overview', fetchOpts).catch(() => null)];
        const keys: string[] = ['overview'];

        if (currentTab === 'crm' || currentTab === 'team' || currentTab === 'agent-panel') {
          promises.push(fetch('/api/v1/calls', fetchOpts).catch(() => null), fetch('/api/v1/contacts', fetchOpts).catch(() => null));
          keys.push('calls', 'contacts');
        } else if (currentTab === 'live-monitor' || currentTab === 'org-dashboard') {
          promises.push(fetch('/api/v1/calls', fetchOpts).catch(() => null));
          keys.push('calls');
        } else if (currentTab === 'campaigns') {
          promises.push(fetch('/api/v1/campaigns', fetchOpts).catch(() => null));
          keys.push('campaigns');
        } else if (currentTab === 'evaluations') {
          promises.push(fetch('/api/v1/evaluations', fetchOpts).catch(() => null));
          keys.push('evaluations');
        } else if (currentTab === 'load-testing') {
          promises.push(fetch('/api/v1/load-tests', fetchOpts).catch(() => null));
          keys.push('load-tests');
        }

        const responses = await Promise.all(promises);
        for (let i = 0; i < responses.length; i++) {
          const res = responses[i];
          const key = keys[i];
          if (res?.ok) {
            const data = await res.json();
            if (key === 'overview') setSelectiveState('overview', data, setOverview);
            else if (key === 'calls') setSelectiveState('calls', data, setCalls);
            else if (key === 'contacts') setSelectiveState('contacts', data, setContacts);
            else if (key === 'campaigns') setSelectiveState('campaigns', data, setCampaigns);
            else if (key === 'evaluations') setSelectiveState('evaluations', data, setEvaluations);
            else if (key === 'load-tests') setSelectiveState('loadTests', data, setLoadTests);
          }
        }
      }
    } catch (ex) {
    } finally {
      clearTimeout(timeoutId);
      isFetchingRef.current = false;
    }
  };

  const fetchCallsOnly = async () => {
    if (isFetchingCallsRef.current) return;
    isFetchingCallsRef.current = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2500);
    try {
      const callRes = await fetch('/api/v1/calls', { signal: controller.signal }).catch(() => null);
      if (callRes?.ok) setSelectiveState('calls', await callRes.json(), setCalls);
    } catch (ex) {}
    finally {
      clearTimeout(timeoutId);
      isFetchingCallsRef.current = false;
    }
  };

  useEffect(() => {
    fetchData(true);
    const interval = setInterval(() => fetchData(false), 8000);
    return () => clearInterval(interval);
  }, []);

  // Algorithmic optimization: Throttled Ring Buffer for WebSocket events
  // Batches incoming WebSocket messages every 300ms to eliminate high-frequency UI repaints
  const pendingLogsRef = React.useRef<LogEvent[]>([]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    let ws: WebSocket | null = null;

    const flushInterval = setInterval(() => {
      if (pendingLogsRef.current.length > 0) {
        const batch = pendingLogsRef.current;
        pendingLogsRef.current = [];
        setLogs(prev => [...batch, ...prev].slice(0, 100));
      }
    }, 300);

    try {
      ws = new WebSocket(wsUrl);
      ws.onmessage = (event) => {
        try {
          const parsed: LogEvent = JSON.parse(event.data);
          pendingLogsRef.current.unshift(parsed);
        } catch (err) {}
      };
    } catch (e) {}

    return () => {
      clearInterval(flushInterval);
      if (ws) ws.close();
    };
  }, []);

  const handleImportCSV = async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    try {
      const resp = await fetch('/api/v1/contacts/import-csv', {
        method: 'POST',
        body: formData
      });
      const data = await resp.json();
      alert(`CSV Imported: ${data.imported} contacts added, ${data.skipped} skipped.`);
      fetchData();
    } catch (ex: any) {
      alert(`Import Failed: ${ex.message}`);
    }
  };

  const handleCreateCampaign = async (campaignData: any) => {
    try {
      const resp = await fetch('/api/v1/campaigns', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(campaignData)
      });
      if (resp.ok) {
        fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to create campaign: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to create campaign: ${ex.message}`);
    }
  };

  const handleStartCampaign = async (id: string) => {
    try {
      const resp = await fetch(`/api/v1/campaigns/${id}/start`, { method: 'POST' });
      if (resp.ok) {
        fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to start campaign: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to start campaign: ${ex.message}`);
    }
  };

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const toggleMobileMenu = useCallback(() => {
    setIsMobileMenuOpen(prev => !prev);
  }, []);

  const closeMobileMenu = useCallback(() => {
    setIsMobileMenuOpen(false);
  }, []);

  // If tab is agent-login, show standalone Agent Login Page
  if (activeTab === 'agent-login') {
    return (
      <Suspense fallback={<PageLoader />}>
        <AgentLoginPage onLoginSuccess={handleAgentLoginSuccess} />
      </Suspense>
    );
  }

    // Separate layout for Agent Panel – no sidebar/header
    if (activeTab === 'agent-panel') {
      return (
        <Suspense fallback={<PageLoader />}>
          {agentSession ? (
            <AgentDashboardPage
              session={agentSession}
              onUpdateStatus={handleUpdateAgentStatus}
              onLogout={handleLogoutAgent}
              calls={calls}
              contacts={contacts}
              onRefreshData={fetchData}
            />
          ) : (
            <AgentLoginPage onLoginSuccess={handleAgentLoginSuccess} />
          )}
        </Suspense>
      );
    }
    return (
      <SEOHead activeTab={activeTab} />
      {/* Sidebar with Mobile Drawer */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isOpen={isMobileMenuOpen}
        onClose={closeMobileMenu}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Header
          overview={overview}
          theme={theme}
          onToggleTheme={toggleTheme}
          onToggleMobileMenu={toggleMobileMenu}
          agentSession={agentSession}
          onOpenAgentLogin={() => setActiveTab('agent-login')}
          onLogoutAgent={handleLogoutAgent}
        />

        <main className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6 space-y-4 md:space-y-6">
          <Suspense fallback={<PageLoader />}>
            {activeTab === 'org-dashboard' && <OrgDashboardPage overview={overview} logs={logs} />}
            {activeTab === 'agent-panel' && (
              agentSession ? (
                <AgentDashboardPage
                  session={agentSession}
                  onUpdateStatus={handleUpdateAgentStatus}
                  onLogout={handleLogoutAgent}
                  calls={calls}
                  contacts={contacts}
                  onRefreshData={fetchData}
                />
              ) : (
                <AgentLoginPage onLoginSuccess={handleAgentLoginSuccess} />
              )
            )}
            {activeTab === 'live-monitor' && <LiveMonitorPage logs={logs} activeCalls={calls.filter(c => c.status === 'in_progress' || c.status === 'in-progress' || c.status === 'active')} allCalls={calls} onRefreshData={fetchCallsOnly} />}

            {activeTab === 'crm' && <CRMPage calls={calls} contacts={contacts} onImportCSV={handleImportCSV} onRefreshData={fetchData} />}
            {activeTab === 'tasks' && <TasksPage />}
            {activeTab === 'team' && <TeamPage />}
            {activeTab === 'campaigns' && <CampaignsPage campaigns={campaigns} onCreateCampaign={handleCreateCampaign} onStartCampaign={handleStartCampaign} />}
            {activeTab === 'voice-studio' && <VoiceStudioPage />}
            {activeTab === 'evaluations' && <EvaluationsPage evaluations={evaluations} />}
            {activeTab === 'load-testing' && <LoadTestingPage loadTests={loadTests} />}
            {activeTab === 'settings' && <SettingsPage />}
          </Suspense>
        </main>
      </div>
    </div>
  );
};

export default App;
