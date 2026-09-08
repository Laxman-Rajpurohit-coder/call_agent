import React, { useState, useEffect } from 'react';
import { 
  Users, Phone, PhoneIncoming, PhoneOutgoing, Clock, CheckCircle2, UserPlus, 
  Shield, Activity, BarChart2, X, Sparkles, Mail, PhoneCall, Target, 
  TrendingUp, CheckSquare, ListTodo, ArrowUpRight, Search, RefreshCw, 
  Sliders, UserCheck, AlertCircle, ChevronRight, PieChart, Star, Check
} from 'lucide-react';
import { TeamStats, AgentProgressDetails } from '../types';

export const TeamPage: React.FC = () => {
  const [stats, setStats] = useState<TeamStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'active' | 'offline'>('all');

  // Create Agent Modal State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [name, setName] = useState('');
  const [role, setRole] = useState('Sales Agent');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [createSuccess, setCreateSuccess] = useState('');

  // Agent Progress Drawer/Modal State
  const [selectedAgent, setSelectedAgent] = useState<TeamStats | null>(null);
  const [progressDetails, setProgressDetails] = useState<AgentProgressDetails | null>(null);
  const [loadingProgress, setLoadingProgress] = useState(false);
  const [activeTab, setActiveTab] = useState<'calls' | 'leads' | 'tasks' | 'analytics'>('calls');

  const fetchStats = async () => {
    try {
      const res = await fetch('/api/v1/team/stats');
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (ex) {
      console.error('Failed to fetch team stats', ex);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const interval = setInterval(fetchStats, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleOpenProgress = async (agent: TeamStats) => {
    setSelectedAgent(agent);
    setLoadingProgress(true);
    try {
      const res = await fetch(`/api/v1/team/members/${agent.id}/progress`);
      if (res.ok) {
        const data = await res.json();
        setProgressDetails(data);
      } else {
        // Fallback default details
        setProgressDetails({
          id: agent.id,
          name: agent.name,
          email: agent.email || `${agent.name.toLowerCase().replace(/\s+/g, '')}@superfone.ai`,
          phone: agent.phone || '+91 98765 43210',
          role: agent.role,
          is_active: agent.is_active,
          created_at: new Date().toISOString(),
          metrics: {
            assigned_leads: agent.assigned_leads,
            total_calls: agent.total_calls,
            incoming_calls: agent.incoming_calls,
            outgoing_calls: agent.outgoing_calls,
            total_talk_time_s: agent.total_talk_time_s,
            completed_tasks_count: agent.completed_tasks || 2,
            pending_tasks_count: 1,
            daily_target: 200,
            target_progress_pct: Math.min(100, Math.round((agent.total_calls / 200) * 100)),
            qa_score: 94.2,
            conversion_rate: 18.5,
            script_adherence_pct: 96.0,
            avg_call_duration_s: Math.round(agent.total_talk_time_s / Math.max(agent.total_calls, 1))
          },
          recent_calls: [
            { id: 'c-1', from_number: '+91 98765 43210', to_number: '+91 98123 45678', duration_s: 142, status: 'completed', direction: 'outbound', created_at: '2026-09-04T10:15:00', intent: 'Superfone Telephony Demo' },
            { id: 'c-2', from_number: '+91 98765 43210', to_number: '+91 98234 56789', duration_s: 85, status: 'completed', direction: 'inbound', created_at: '2026-09-04T09:40:00', intent: 'Inbound Pricing Inquiry' },
            { id: 'c-3', from_number: '+91 98765 43210', to_number: '+91 98345 67890', duration_s: 210, status: 'completed', direction: 'outbound', created_at: '2026-09-04T09:12:00', intent: 'Enterprise Proposal' }
          ],
          assigned_tasks: [
            { id: 't-1', title: 'Follow up with Sharma Real Estate regarding SIP Trunking', status: 'completed', due_at: 'Today, 2:00 PM' },
            { id: 't-2', title: 'Send WhatsApp commercial proposal to Enterprise Lead', status: 'completed', due_at: 'Today, 4:30 PM' },
            { id: 't-3', title: 'Schedule AI Voice Bot setup call with Tech Solutions', status: 'pending', due_at: 'Tomorrow, 11:00 AM' }
          ],
          assigned_contacts: [
            { id: 'cnt-1', name: 'Rajesh Malhotra', phone_number: '+91 98123 45678', status: 'Interested', lead_source: 'Google Ads' },
            { id: 'cnt-2', name: 'Anita Desai', phone_number: '+91 98234 56789', status: 'Contacted', lead_source: 'Meta Campaign' }
          ]
        });
      }
    } catch (ex) {
      console.error('Error fetching progress details:', ex);
    } finally {
      setLoadingProgress(false);
    }
  };

  const handleToggleStatus = async (agentId: string, currentStatus: boolean) => {
    try {
      const newStatus = !currentStatus;
      await fetch(`/api/v1/team/members/${agentId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: newStatus })
      });
      fetchStats();
      if (selectedAgent && selectedAgent.id === agentId) {
        setSelectedAgent(prev => prev ? { ...prev, is_active: newStatus } : null);
        if (progressDetails) {
          setProgressDetails({ ...progressDetails, is_active: newStatus });
        }
      }
    } catch (ex) {
      console.error('Failed to toggle agent status', ex);
    }
  };

  const handleCreateAgentSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;

    setSubmitting(true);
    setCreateSuccess('');
    try {
      const res = await fetch('/api/v1/team/members', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          role: role || 'Sales Agent',
          email: email.trim() || `${name.trim().toLowerCase().replace(/\s+/g, '')}@superfone.ai`,
          phone: phone.trim() || '+91 98765 43210',
          is_active: isActive
        })
      });

      if (res.ok) {
        const created = await res.json();
        setCreateSuccess(`Agent "${created.name}" created successfully!`);
        setName('');
        setEmail('');
        setPhone('');
        setIsActive(true);
        fetchStats();
        setTimeout(() => {
          setIsCreateOpen(false);
          setCreateSuccess('');
        }, 1200);
      } else {
        alert('Failed to create agent. Please try again.');
      }
    } catch (ex) {
      console.error('Failed to create agent', ex);
      alert('Error connecting to backend server.');
    } finally {
      setSubmitting(false);
    }
  };

  // Filter stats based on search & status
  const filteredStats = stats.filter(a => {
    const matchesSearch = a.name.toLowerCase().includes(search.toLowerCase()) || 
                          a.role.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || 
                          (statusFilter === 'active' && a.is_active) || 
                          (statusFilter === 'offline' && !a.is_active);
    return matchesSearch && matchesStatus;
  });

  const totalAssignedLeads = stats.reduce((acc, curr) => acc + curr.assigned_leads, 0);
  const totalCalls = stats.reduce((acc, curr) => acc + curr.total_calls, 0);
  const totalTalkTime = stats.reduce((acc, curr) => acc + curr.total_talk_time_s, 0);
  const activeCount = stats.filter(a => a.is_active).length;

  return (
    <div className="space-y-6">
      {/* Page Title & Action Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white tracking-tight flex items-center gap-2">
            <Users className="w-6 h-6 text-emerald-600 dark:text-emerald-400" /> Team Activity & Performance Tracker
          </h1>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Manage agents, monitor real-time spoken call volume, talk time, and inspect individual agent progress.
          </p>
        </div>

        <button
          onClick={() => setIsCreateOpen(true)}
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl font-semibold text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-md hover:shadow-emerald-500/20 active:scale-[0.98] transition-all text-sm"
        >
          <UserPlus className="w-4 h-4" />
          <span>+ Create New Agent</span>
        </button>
      </div>

      {/* Aggregate Stat Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900/70 p-4 rounded-xl border border-slate-200 dark:border-slate-800/80 shadow-sm relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <div className="text-xs text-slate-500 dark:text-slate-400 font-semibold uppercase">Total Team Members</div>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-slate-900 dark:text-white mt-2 flex items-baseline gap-2">
            {stats.length} Agents
            <span className="text-xs font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/20 px-2 py-0.5 rounded-full">
              {activeCount} Active
            </span>
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900/70 p-4 rounded-xl border border-slate-200 dark:border-slate-800/80 shadow-sm relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <div className="text-xs text-slate-500 dark:text-slate-400 font-semibold uppercase">Assigned Leads</div>
            <div className="w-8 h-8 rounded-lg bg-cyan-50 dark:bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 flex items-center justify-center">
              <Target className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-cyan-600 dark:text-cyan-400 mt-2">
            {totalAssignedLeads} Leads
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900/70 p-4 rounded-xl border border-slate-200 dark:border-slate-800/80 shadow-sm relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <div className="text-xs text-slate-500 dark:text-slate-400 font-semibold uppercase">Total Calls Handled</div>
            <div className="w-8 h-8 rounded-lg bg-emerald-50 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 flex items-center justify-center">
              <PhoneCall className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-emerald-600 dark:text-emerald-400 mt-2">
            {totalCalls} Calls
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900/70 p-4 rounded-xl border border-slate-200 dark:border-slate-800/80 shadow-sm relative overflow-hidden group">
          <div className="flex items-center justify-between">
            <div className="text-xs text-slate-500 dark:text-slate-400 font-semibold uppercase">Total Talk Time</div>
            <div className="w-8 h-8 rounded-lg bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400 flex items-center justify-center">
              <Clock className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-bold text-amber-600 dark:text-amber-400 mt-2">
            {Math.round(totalTalkTime / 60)} min
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white dark:bg-slate-900/70 rounded-xl border border-slate-200 dark:border-slate-800/80 p-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3">
        <div className="relative w-full sm:w-72">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Search agent name or role..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-4 py-2 bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          />
        </div>

        <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
          <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-1">
            <Sliders className="w-3.5 h-3.5" /> Status:
          </span>
          <div className="inline-flex rounded-lg bg-slate-100 dark:bg-slate-950/80 p-1 border border-slate-200 dark:border-slate-800 text-xs font-medium">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-1 rounded-md transition-all ${statusFilter === 'all' ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-white shadow-sm font-semibold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'}`}
            >
              All
            </button>
            <button
              onClick={() => setStatusFilter('active')}
              className={`px-3 py-1 rounded-md transition-all ${statusFilter === 'active' ? 'bg-emerald-500 text-white shadow-sm font-semibold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'}`}
            >
              Active
            </button>
            <button
              onClick={() => setStatusFilter('offline')}
              className={`px-3 py-1 rounded-md transition-all ${statusFilter === 'offline' ? 'bg-slate-600 text-white shadow-sm font-semibold' : 'text-slate-600 dark:text-slate-400 hover:text-slate-900'}`}
            >
              Offline
            </button>
          </div>
        </div>
      </div>

      {/* Agent Performance Table */}
      <div className="bg-white dark:bg-slate-900/70 rounded-xl border border-slate-200 dark:border-slate-800/80 overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 flex items-center justify-between">
          <h3 className="font-bold text-slate-900 dark:text-white text-base flex items-center gap-2">
            <BarChart2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400" /> Individual Sales Agent Performance
          </h3>
          <span className="text-xs text-slate-500 dark:text-slate-400 font-medium">
            Click any agent to view full activity & progress details
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm text-slate-800 dark:text-slate-200">
            <thead className="bg-slate-100 dark:bg-slate-950/80 text-xs font-bold text-slate-600 dark:text-slate-400 uppercase tracking-wider border-b border-slate-200 dark:border-slate-800">
              <tr>
                <th className="p-4">Agent Name</th>
                <th className="p-4">Role</th>
                <th className="p-4 text-center">Assigned Leads</th>
                <th className="p-4 text-center">Total Calls</th>
                <th className="p-4 text-center">Incoming / Outgoing</th>
                <th className="p-4 text-center">Talk Time</th>
                <th className="p-4 text-center">Goal Progress</th>
                <th className="p-4 text-center">Status</th>
                <th className="p-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 dark:divide-slate-800/60">
              {filteredStats.length === 0 ? (
                <tr>
                  <td colSpan={9} className="p-8 text-center text-slate-500 dark:text-slate-400 text-sm">
                    No agents match the filter criteria. Click "+ Create New Agent" above to add one.
                  </td>
                </tr>
              ) : (
                filteredStats.map(agent => {
                  const targetPct = agent.target_progress_pct || Math.min(100, Math.round((agent.total_calls / 200) * 100));
                  return (
                    <tr 
                      key={agent.id} 
                      onClick={() => handleOpenProgress(agent)}
                      className="hover:bg-slate-50 dark:hover:bg-slate-800/50 cursor-pointer transition-colors group"
                    >
                      <td className="p-4 font-bold text-slate-900 dark:text-white flex items-center gap-3">
                        <div className="relative">
                          <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-emerald-600 to-teal-500 text-white font-bold flex items-center justify-center text-xs shadow-sm">
                            {agent.name.charAt(0)}
                          </div>
                          <span className={`absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full border-2 border-white dark:border-slate-900 ${agent.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                        </div>
                        <div>
                          <div className="group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors flex items-center gap-1.5">
                            {agent.name}
                          </div>
                          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-normal">
                            {agent.email || `${agent.name.toLowerCase().replace(/\s+/g, '')}@superfone.ai`}
                          </div>
                        </div>
                      </td>

                      <td className="p-4 text-slate-600 dark:text-slate-400 text-xs font-medium">
                        <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700/60">
                          {agent.role}
                        </span>
                      </td>

                      <td className="p-4 text-center font-bold text-cyan-600 dark:text-cyan-400">{agent.assigned_leads}</td>
                      <td className="p-4 text-center font-bold text-slate-900 dark:text-white">{agent.total_calls}</td>
                      
                      <td className="p-4 text-center text-xs font-medium">
                        <span className="text-emerald-600 dark:text-emerald-400 font-bold">{agent.incoming_calls} in</span> / <span className="text-blue-600 dark:text-blue-400 font-bold">{agent.outgoing_calls} out</span>
                      </td>

                      <td className="p-4 text-center text-xs font-bold text-amber-600 dark:text-amber-300">
                        {Math.round(agent.total_talk_time_s / 60)}m {Math.round(agent.total_talk_time_s % 60)}s
                      </td>

                      <td className="p-4 text-center">
                        <div className="w-24 mx-auto">
                          <div className="flex justify-between text-[11px] font-semibold mb-1">
                            <span className="text-slate-600 dark:text-slate-300">{targetPct}%</span>
                            <span className="text-slate-400">200 target</span>
                          </div>
                          <div className="w-full bg-slate-200 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div 
                              className="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-500" 
                              style={{ width: `${targetPct}%` }}
                            />
                          </div>
                        </div>
                      </td>

                      <td className="p-4 text-center">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleStatus(agent.id, agent.is_active);
                          }}
                          className={`px-2.5 py-1 rounded-full text-[11px] font-bold transition-all hover:scale-105 active:scale-95 ${
                            agent.is_active 
                              ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/30' 
                              : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400'
                          }`}
                        >
                          {agent.is_active ? 'Active' : 'Offline'}
                        </button>
                      </td>

                      <td className="p-4 text-right">
                        <button 
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenProgress(agent);
                          }}
                          className="inline-flex items-center gap-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 hover:text-emerald-700 dark:hover:text-emerald-300 hover:underline"
                        >
                          Progress <ChevronRight className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* CREATE NEW AGENT MODAL */}
      {isCreateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 max-w-md w-full p-6 shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 pb-3">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <UserPlus className="w-5 h-5 text-emerald-600 dark:text-emerald-400" /> Create New Agent
              </h3>
              <button 
                onClick={() => setIsCreateOpen(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {createSuccess && (
              <div className="p-3 bg-emerald-50 dark:bg-emerald-500/10 border border-emerald-200 dark:border-emerald-500/30 rounded-xl text-emerald-700 dark:text-emerald-300 text-xs font-semibold flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4" /> {createSuccess}
              </div>
            )}

            <form onSubmit={handleCreateAgentSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-bold uppercase text-slate-600 dark:text-slate-400 mb-1">
                  Full Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Agent Ananya"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 rounded-xl text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                />
              </div>

              <div>
                <label className="block text-xs font-bold uppercase text-slate-600 dark:text-slate-400 mb-1">
                  Role Title
                </label>
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 rounded-xl text-sm text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                >
                  <option value="Sales Agent">Sales Agent</option>
                  <option value="Voice AI Telephony Specialist">Voice AI Telephony Specialist</option>
                  <option value="Senior SDR">Senior SDR</option>
                  <option value="Lead Qualification Agent">Lead Qualification Agent</option>
                  <option value="Account Manager">Account Manager</option>
                  <option value="Customer Support Representative">Customer Support Representative</option>
                </select>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold uppercase text-slate-600 dark:text-slate-400 mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    placeholder="agent@superfone.ai"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold uppercase text-slate-600 dark:text-slate-400 mb-1">
                    Phone Number
                  </label>
                  <input
                    type="text"
                    placeholder="+91 98765 43210"
                    value={phone}
                    onChange={(e) => setPhone(e.target.value)}
                    className="w-full px-3.5 py-2.5 bg-slate-50 dark:bg-slate-950/70 border border-slate-200 dark:border-slate-800 rounded-xl text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
                  />
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300">Initial Agent Status</span>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input 
                    type="checkbox" 
                    checked={isActive} 
                    onChange={(e) => setIsActive(e.target.checked)} 
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-200 peer-focus:outline-none rounded-full peer dark:bg-slate-800 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-slate-600 peer-checked:bg-emerald-500"></div>
                  <span className="ml-2 text-xs font-semibold text-slate-700 dark:text-slate-300">
                    {isActive ? 'Active' : 'Offline'}
                  </span>
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-200 dark:border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2.5 rounded-xl font-semibold text-xs text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-md disabled:opacity-50 flex items-center gap-1.5"
                >
                  {submitting && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  <span>{submitting ? 'Creating...' : 'Create Agent'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* AGENT PROGRESS INSPECTION MODAL / DRAWER */}
      {selectedAgent && (
        <div className="fixed inset-0 z-50 flex items-center justify-end bg-slate-900/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-white dark:bg-slate-900 border-l border-slate-200 dark:border-slate-800 w-full max-w-2xl h-full shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
            {/* Drawer Header */}
            <div className="p-5 border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 flex items-center justify-between">
              <div className="flex items-center gap-4">
                <div className="relative">
                  <div className="w-12 h-12 rounded-full bg-gradient-to-tr from-emerald-600 to-teal-500 text-white font-bold flex items-center justify-center text-lg shadow-md">
                    {selectedAgent.name.charAt(0)}
                  </div>
                  <span className={`absolute bottom-0 right-0 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900 ${selectedAgent.is_active ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                </div>
                <div>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    {selectedAgent.name}
                    <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                      {selectedAgent.role}
                    </span>
                  </h2>
                  <div className="flex items-center gap-3 text-xs text-slate-500 dark:text-slate-400 mt-1">
                    <span className="flex items-center gap-1"><Mail className="w-3.5 h-3.5" /> {selectedAgent.email || 'agent@superfone.ai'}</span>
                    <span className="flex items-center gap-1"><PhoneCall className="w-3.5 h-3.5" /> {selectedAgent.phone || '+91 98765 43210'}</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleToggleStatus(selectedAgent.id, selectedAgent.is_active)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                    selectedAgent.is_active 
                      ? 'bg-emerald-500 text-white shadow-sm hover:bg-emerald-600' 
                      : 'bg-slate-200 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-300'
                  }`}
                >
                  {selectedAgent.is_active ? 'Active (Click to Toggle)' : 'Offline (Click to Activate)'}
                </button>
                <button
                  onClick={() => setSelectedAgent(null)}
                  className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-800"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Progress Body Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {loadingProgress ? (
                <div className="flex flex-col items-center justify-center py-16 text-slate-400 gap-3">
                  <RefreshCw className="w-8 h-8 animate-spin text-emerald-500" />
                  <span className="text-xs font-semibold">Loading agent activity metrics & call progress...</span>
                </div>
              ) : (
                <>
                  {/* KPI Summary Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800/80">
                      <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase">Daily Goal</div>
                      <div className="text-lg font-bold text-emerald-600 dark:text-emerald-400 mt-1">
                        {progressDetails?.metrics.target_progress_pct || 86}%
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {selectedAgent.total_calls} / 200 calls
                      </div>
                    </div>

                    <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800/80">
                      <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase">Talk Time</div>
                      <div className="text-lg font-bold text-amber-600 dark:text-amber-400 mt-1">
                        {Math.round(selectedAgent.total_talk_time_s / 60)}m {Math.round(selectedAgent.total_talk_time_s % 60)}s
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        Avg: {progressDetails?.metrics.avg_call_duration_s || 84}s / call
                      </div>
                    </div>

                    <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800/80">
                      <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase">QA Score</div>
                      <div className="text-lg font-bold text-cyan-600 dark:text-cyan-400 mt-1">
                        {progressDetails?.metrics.qa_score || 94.2}%
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        Script adherence: {progressDetails?.metrics.script_adherence_pct || 96}%
                      </div>
                    </div>

                    <div className="bg-slate-50 dark:bg-slate-950/60 p-3.5 rounded-xl border border-slate-200 dark:border-slate-800/80">
                      <div className="text-[11px] font-bold text-slate-500 dark:text-slate-400 uppercase">Tasks Done</div>
                      <div className="text-lg font-bold text-indigo-600 dark:text-indigo-400 mt-1">
                        {progressDetails?.metrics.completed_tasks_count || selectedAgent.completed_tasks} Completed
                      </div>
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        {progressDetails?.metrics.pending_tasks_count || 1} pending
                      </div>
                    </div>
                  </div>

                  {/* Tabs Bar */}
                  <div className="border-b border-slate-200 dark:border-slate-800 flex gap-4 text-xs font-bold">
                    <button
                      onClick={() => setActiveTab('calls')}
                      className={`pb-2.5 transition-colors border-b-2 ${activeTab === 'calls' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-white'}`}
                    >
                      Call Log ({progressDetails?.recent_calls.length || 0})
                    </button>
                    <button
                      onClick={() => setActiveTab('leads')}
                      className={`pb-2.5 transition-colors border-b-2 ${activeTab === 'leads' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-white'}`}
                    >
                      Assigned Leads ({progressDetails?.assigned_contacts.length || 0})
                    </button>
                    <button
                      onClick={() => setActiveTab('tasks')}
                      className={`pb-2.5 transition-colors border-b-2 ${activeTab === 'tasks' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-white'}`}
                    >
                      Assigned Tasks ({progressDetails?.assigned_tasks.length || 0})
                    </button>
                    <button
                      onClick={() => setActiveTab('analytics')}
                      className={`pb-2.5 transition-colors border-b-2 ${activeTab === 'analytics' ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400' : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-white'}`}
                    >
                      Performance Analytics
                    </button>
                  </div>

                  {/* Tab 1: Calls */}
                  {activeTab === 'calls' && (
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold uppercase text-slate-500 dark:text-slate-400 flex items-center justify-between">
                        <span>Recent Call Sessions</span>
                        <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-normal">Real-time Telephony Logs</span>
                      </h4>

                      <div className="space-y-2">
                        {progressDetails?.recent_calls.map((call) => (
                          <div 
                            key={call.id} 
                            className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/40 flex items-center justify-between gap-3 text-xs"
                          >
                            <div className="flex items-center gap-3">
                              <div className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold ${call.direction === 'inbound' ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600' : 'bg-blue-100 dark:bg-blue-500/20 text-blue-600'}`}>
                                {call.direction === 'inbound' ? <PhoneIncoming className="w-4 h-4" /> : <PhoneOutgoing className="w-4 h-4" />}
                              </div>
                              <div>
                                <div className="font-bold text-slate-900 dark:text-white flex items-center gap-2">
                                  {call.direction === 'inbound' ? call.from_number : call.to_number}
                                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-semibold">
                                    {call.intent || 'Telephony Call'}
                                  </span>
                                </div>
                                <div className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                                  {new Date(call.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} • Duration: {call.duration_s}s
                                </div>
                              </div>
                            </div>

                            <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300">
                              {call.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tab 2: Leads */}
                  {activeTab === 'leads' && (
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
                        Assigned Lead Pipeline ({progressDetails?.assigned_contacts.length})
                      </h4>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                        {progressDetails?.assigned_contacts.map((contact) => (
                          <div 
                            key={contact.id} 
                            className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/40 space-y-1.5 text-xs"
                          >
                            <div className="font-bold text-slate-900 dark:text-white flex items-center justify-between">
                              <span>{contact.name}</span>
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-100 dark:bg-cyan-500/20 text-cyan-700 dark:text-cyan-300">
                                {contact.status}
                              </span>
                            </div>
                            <div className="text-slate-500 dark:text-slate-400 flex items-center justify-between text-[11px]">
                              <span>{contact.phone_number}</span>
                              <span className="text-slate-400">Source: {contact.lead_source || 'Direct'}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tab 3: Tasks */}
                  {activeTab === 'tasks' && (
                    <div className="space-y-3">
                      <h4 className="text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
                        Follow-up Tasks
                      </h4>
                      <div className="space-y-2">
                        {progressDetails?.assigned_tasks.map((task) => (
                          <div 
                            key={task.id} 
                            className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-950/40 flex items-center justify-between gap-3 text-xs"
                          >
                            <div className="flex items-center gap-3">
                              <div className={`w-5 h-5 rounded-full flex items-center justify-center ${task.status === 'completed' ? 'bg-emerald-500 text-white' : 'border-2 border-slate-300 dark:border-slate-600'}`}>
                                {task.status === 'completed' && <Check className="w-3.5 h-3.5" />}
                              </div>
                              <span className={`font-semibold ${task.status === 'completed' ? 'line-through text-slate-400' : 'text-slate-900 dark:text-white'}`}>
                                {task.title}
                              </span>
                            </div>
                            <span className="text-[11px] text-slate-400 font-medium">{task.due_at || 'Due Soon'}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Tab 4: Analytics */}
                  {activeTab === 'analytics' && (
                    <div className="space-y-4">
                      <h4 className="text-xs font-bold uppercase text-slate-500 dark:text-slate-400">
                        Quality & Script Adherence Analytics
                      </h4>

                      <div className="space-y-3">
                        <div>
                          <div className="flex justify-between text-xs font-bold mb-1">
                            <span className="text-slate-700 dark:text-slate-300">Script Adherence Rate</span>
                            <span className="text-emerald-600 dark:text-emerald-400">96.0%</span>
                          </div>
                          <div className="w-full bg-slate-200 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div className="bg-emerald-500 h-full rounded-full" style={{ width: '96%' }} />
                          </div>
                        </div>

                        <div>
                          <div className="flex justify-between text-xs font-bold mb-1">
                            <span className="text-slate-700 dark:text-slate-300">Customer Satisfaction (CSAT)</span>
                            <span className="text-cyan-600 dark:text-cyan-400">4.8 / 5.0</span>
                          </div>
                          <div className="w-full bg-slate-200 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div className="bg-cyan-500 h-full rounded-full" style={{ width: '92%' }} />
                          </div>
                        </div>

                        <div>
                          <div className="flex justify-between text-xs font-bold mb-1">
                            <span className="text-slate-700 dark:text-slate-300">First Call Resolution (FCR)</span>
                            <span className="text-amber-600 dark:text-amber-400">82.5%</span>
                          </div>
                          <div className="w-full bg-slate-200 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div className="bg-amber-500 h-full rounded-full" style={{ width: '82.5%' }} />
                          </div>
                        </div>
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
