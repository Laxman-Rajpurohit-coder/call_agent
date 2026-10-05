import React, { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import { Sidebar } from './components/Sidebar';
import { Header } from './components/Header';
import { SEOHead } from './components/SEOHead';
import { SystemOverview, CallSession, Contact, Campaign, LogEvent, AgentSession, AgentStatusType } from './types';

// Dynamic lazy loading for code splitting and fast FCP/LCP
const OverviewPage = lazy(() => import('./pages/OverviewPage').then(m => ({ default: m.OverviewPage })));
const LiveMonitorPage = lazy(() => import('./pages/LiveMonitorPage').then(m => ({ default: m.LiveMonitorPage })));
const CRMPage = lazy(() => import('./pages/CRMPage').then(m => ({ default: m.CRMPage })));
const CampaignsPage = lazy(() => import('./pages/CampaignsPage').then(m => ({ default: m.CampaignsPage })));
const TasksPage = lazy(() => import('./pages/TasksPage').then(m => ({ default: m.TasksPage })));
const TeamPage = lazy(() => import('./pages/TeamPage').then(m => ({ default: m.TeamPage })));
const IncomingCallConfigPage = lazy(() => import('./pages/IncomingCallConfigPage').then(m => ({ default: m.IncomingCallConfigPage })));
const OrgDashboardPage = lazy(() => import('./pages/OverviewPage').then(m => ({ default: m.OverviewPage })));

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
  'org-dashboard', 'live-monitor', 'crm', 'tasks',
  'team', 'campaigns', 'incoming-config'
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
  const safeJson = async (res: Response | null | undefined) => {
    if (!res || !res.ok) return null;
    try {
      const text = await res.text();
      return text ? JSON.parse(text) : null;
    } catch {
      return null;
    }
  };

  const fetchData = async (isInitial = false) => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);
    const fetchOpts = { signal: controller.signal };

    try {
      if (isInitial) {
        const [ovRes, callRes, ctRes, cmpRes] = await Promise.all([
          fetch('/api/v1/overview', fetchOpts).catch(() => null),
          fetch('/api/v1/calls', fetchOpts).catch(() => null),
          fetch('/api/v1/contacts', fetchOpts).catch(() => null),
          fetch('/api/v1/campaigns', fetchOpts).catch(() => null),
        ]);

        const [ovData, callData, ctData, cmpData] = await Promise.all([
          safeJson(ovRes),
          safeJson(callRes),
          safeJson(ctRes),
          safeJson(cmpRes),
        ]);

        if (ovData) setSelectiveState('overview', ovData, setOverview);
        if (callData) setSelectiveState('calls', callData, setCalls);
        if (ctData) setSelectiveState('contacts', ctData, setContacts);
        if (cmpData) setSelectiveState('campaigns', cmpData, setCampaigns);
      } else {
        const currentTab = activeTabRef.current;
        const promises: Promise<Response | null>[] = [fetch('/api/v1/overview', fetchOpts).catch(() => null)];
        const keys: string[] = ['overview'];

        if (currentTab === 'crm' || currentTab === 'team') {
          promises.push(fetch('/api/v1/calls', fetchOpts).catch(() => null), fetch('/api/v1/contacts', fetchOpts).catch(() => null));
          keys.push('calls', 'contacts');
        } else if (currentTab === 'live-monitor' || currentTab === 'org-dashboard') {
          promises.push(fetch('/api/v1/calls', fetchOpts).catch(() => null));
          keys.push('calls');
        } else if (currentTab === 'campaigns') {
          promises.push(fetch('/api/v1/campaigns', fetchOpts).catch(() => null));
          keys.push('campaigns');
        }

        const responses = await Promise.all(promises);
        for (let i = 0; i < responses.length; i++) {
          const res = responses[i];
          const key = keys[i];
          if (res?.ok) {
            const data = await safeJson(res);
            if (data) {
              if (key === 'overview') setSelectiveState('overview', data, setOverview);
              else if (key === 'calls') setSelectiveState('calls', data, setCalls);
              else if (key === 'contacts') setSelectiveState('contacts', data, setContacts);
              else if (key === 'campaigns') setSelectiveState('campaigns', data, setCampaigns);
            }
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
      if (callRes?.ok) {
        const data = await safeJson(callRes);
        if (data) setSelectiveState('calls', data, setCalls);
      }
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

  const handlePauseCampaign = async (id: string) => {
    try {
      const resp = await fetch(`/api/v1/campaigns/${id}/pause`, { method: 'POST' });
      if (resp.ok) {
        fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to pause campaign: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to pause campaign: ${ex.message}`);
    }
  };

  const handleResumeCampaign = async (id: string) => {
    try {
      const resp = await fetch(`/api/v1/campaigns/${id}/resume`, { method: 'POST' });
      if (resp.ok) {
        fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to resume campaign: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to resume campaign: ${ex.message}`);
    }
  };

  const handleStopCampaign = async (id: string) => {
    try {
      const resp = await fetch(`/api/v1/campaigns/${id}/stop`, { method: 'POST' });
      if (resp.ok) {
        fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to stop campaign: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to stop campaign: ${ex.message}`);
    }
  };

  const handleDeleteCampaign = async (id: string) => {
    try {
      const resp = await fetch(`/api/v1/campaigns/${id}`, { method: 'DELETE' });
      if (resp.ok) {
        await fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to delete campaign: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to delete campaign: ${ex.message}`);
    }
  };

  const handleBulkDeleteCampaigns = async (ids: string[]) => {
    try {
      const resp = await fetch(`/api/v1/campaigns/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ campaign_ids: ids })
      });
      if (resp.ok) {
        await fetchData();
      } else {
        const errJson = await resp.json().catch(() => ({}));
        alert(`Failed to delete campaigns: ${resp.status} ${errJson.detail || resp.statusText || 'Server error'}`);
      }
    } catch (ex: any) {
      alert(`Failed to delete campaigns: ${ex.message}`);
    }
  };

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const toggleMobileMenu = useCallback(() => {
    setIsMobileMenuOpen(prev => !prev);
  }, []);

  const closeMobileMenu = useCallback(() => {
    setIsMobileMenuOpen(false);
  }, []);

    return (
      <div className="flex h-screen bg-slate-950 text-slate-100 antialiased overflow-hidden">
        <SEOHead activeTab={activeTab} />
        {/* Sidebar with Mobile Drawer */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        isOpen={isMobileMenuOpen}
        onClose={closeMobileMenu}
        agentSession={agentSession}
        onLogoutAgent={handleLogoutAgent}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 h-screen overflow-hidden">
        <Header
          overview={overview}
          theme={theme}
          onToggleTheme={toggleTheme}
          onToggleMobileMenu={toggleMobileMenu}
          agentSession={agentSession}
          onLogoutAgent={handleLogoutAgent}
        />

        <main className="flex-1 overflow-y-auto p-3 sm:p-4 md:p-6 space-y-4 md:space-y-6">
          <Suspense fallback={<PageLoader />}>
            {activeTab === 'org-dashboard' && <OrgDashboardPage overview={overview} logs={logs} />}
            {activeTab === 'live-monitor' && (
              <LiveMonitorPage
                logs={logs}
                activeCalls={calls.filter(c => ['in_progress', 'in-progress', 'active', 'connected', 'CONNECTED', 'RINGING', 'HUMAN_CONNECTED', 'BRIDGING'].includes(c.status))}
                allCalls={calls}
                onRefreshData={fetchCallsOnly}
              />
            )}

            {activeTab === 'crm' && <CRMPage calls={calls} contacts={contacts} onImportCSV={handleImportCSV} onRefreshData={fetchData} />}
            {activeTab === 'tasks' && <TasksPage />}
            {activeTab === 'campaigns' && (
              <CampaignsPage
                campaigns={campaigns}
                contacts={contacts}
                onCreateCampaign={handleCreateCampaign}
                onStartCampaign={handleStartCampaign}
                onPauseCampaign={handlePauseCampaign}
                onResumeCampaign={handleResumeCampaign}
                onStopCampaign={handleStopCampaign}
                onDeleteCampaign={handleDeleteCampaign}
                onBulkDeleteCampaigns={handleBulkDeleteCampaigns}
              />
            )}
            {activeTab === 'team' && <TeamPage />}
            {activeTab === 'incoming-config' && <IncomingCallConfigPage agentSession={agentSession} />}
          </Suspense>
        </main>
      </div>
    </div>
  );
};

export default App;
