import React, { useState, useEffect } from 'react';
import { CheckCircle2, Circle, Clock, Calendar, User, Search, ExternalLink, Building, XCircle, Plus, RefreshCw, Sparkles, UserCheck } from 'lucide-react';
import { LeadTask } from '../types';

const DEFAULT_AGENTS = [
  { id: 'agent-alex', name: 'Agent Alex', role: 'Senior Sales Representative', assigned_leads_count: 5 },
  { id: 'agent-priya', name: 'Agent Priya', role: 'Key Account Manager', assigned_leads_count: 4 },
  { id: 'agent-rahul', name: 'Agent Rahul', role: 'Real Estate Lead Specialist', assigned_leads_count: 3 },
  { id: 'agent-swati', name: 'Agent Swati (AI Bot)', role: 'AI Telephony Voice Agent', assigned_leads_count: 0 },
  { id: 'agent-kabir', name: 'Agent Kabir (AI Bot)', role: 'Automated Lead Qualification', assigned_leads_count: 0 },
];

export const TasksPage: React.FC = () => {
  const [tasks, setTasks] = useState<LeadTask[]>([]);
  const [teamMembers, setTeamMembers] = useState<any[]>(DEFAULT_AGENTS);
  const [filter, setFilter] = useState<'pending' | 'completed' | 'all'>('pending');
  const [search, setSearch] = useState('');
  const [selectedTask, setSelectedTask] = useState<LeadTask | null>(null);
  const [loading, setLoading] = useState(true);

  // Modal State for Task Creation
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newAssignee, setNewAssignee] = useState('auto');
  const [newDueHours, setNewDueHours] = useState(24);
  const [submitting, setSubmitting] = useState(false);

  const fetchTasks = async () => {
    try {
      const res = await fetch('/api/v1/tasks');
      if (res.ok) {
        const data = await res.json();
        setTasks(data);
      }
    } catch (ex) {
      console.error('Failed to fetch tasks', ex);
    } finally {
      setLoading(false);
    }
  };

  const fetchTeam = async () => {
    try {
      const res = await fetch('/api/v1/team/members');
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data) && data.length > 0) {
          setTeamMembers(data);
          return;
        }
      }
      const res2 = await fetch('/api/v1/team/stats');
      if (res2.ok) {
        const data = await res2.json();
        if (Array.isArray(data) && data.length > 0) {
          setTeamMembers(data);
          return;
        }
      }
    } catch (ex) {
      console.error('Failed to fetch team members', ex);
    }
  };

  useEffect(() => {
    fetchTasks();
    fetchTeam();
    const interval = setInterval(fetchTasks, 5000);
    return () => clearInterval(interval);
  }, []);

  const toggleTaskStatus = async (taskId: string, currentStatus: string) => {
    const newStatus = currentStatus === 'pending' ? 'completed' : 'pending';
    try {
      await fetch(`/api/v1/tasks/${taskId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
      });
      fetchTasks();
      if (selectedTask && selectedTask.id === taskId) {
        setSelectedTask(prev => prev ? { ...prev, status: newStatus as any } : null);
      }
    } catch (ex) {
      console.error('Failed to update task', ex);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;

    setSubmitting(true);
    try {
      if (newAssignee === 'auto') {
        // Use Round-Robin Tool Endpoint
        await fetch('/api/v1/tasks/llm-create-task', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: newTitle,
            description: newDescription,
            contact_name: newName || 'Valued Customer',
            phone_number: newPhone || '9999999999',
            due_in_hours: newDueHours
          })
        });
      } else {
        // Manual Assignment
        await fetch('/api/v1/tasks', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: newTitle,
            description: newDescription,
            assigned_to_id: newAssignee,
            due_at: new Date(Date.now() + newDueHours * 3600 * 1000).toISOString()
          })
        });
      }

      setIsCreateOpen(false);
      setNewTitle('');
      setNewDescription('');
      setNewName('');
      setNewPhone('');
      setNewAssignee('auto');
      fetchTasks();
      fetchTeam();
    } catch (ex) {
      console.error('Failed to create task', ex);
    } finally {
      setSubmitting(false);
    }
  };

  const filteredTasks = tasks.filter(t => {
    const matchesFilter = filter === 'all' || t.status === filter;
    const matchesSearch = !search ||
      t.title.toLowerCase().includes(search.toLowerCase()) ||
      (t.contact_name && t.contact_name.toLowerCase().includes(search.toLowerCase())) ||
      (t.contact_phone && t.contact_phone.includes(search));
    return matchesFilter && matchesSearch;
  });

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-100 to-indigo-200 tracking-tight flex items-center gap-2.5">
            <span>To-Do & Lead Tasks</span>
            <span className="text-xs px-3 py-1 rounded-full bg-gradient-to-r from-cyan-500/20 to-indigo-500/20 text-cyan-300 border border-cyan-500/40 font-mono font-extrabold shadow-sm">
              Round-Robin Enabled
            </span>
          </h1>
          <p className="text-xs md:text-sm text-slate-400 font-medium mt-1">Manage assigned lead follow-ups, auto-captured inquiries, and sales action items</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="px-3.5 py-1.5 bg-slate-900/60 border border-slate-800 rounded-full text-xs font-bold text-slate-300 shadow-inner">
            Pending: <span className="text-emerald-400 font-extrabold ml-1">{tasks.filter(t => t.status === 'pending').length}</span>
          </span>
          <button
            onClick={() => setIsCreateOpen(true)}
            className="px-4 py-2.5 bg-gradient-to-r from-emerald-500 via-teal-500 to-cyan-600 hover:from-emerald-400 hover:to-cyan-500 text-white font-extrabold rounded-xl text-xs shadow-lg shadow-emerald-500/25 flex items-center gap-2 transition-all transform hover:-translate-y-0.5 active:translate-y-0"
          >
            <Plus className="w-4 h-4 stroke-[3]" />
            Create Task
          </button>
        </div>
      </div>

      <div className="flex items-center justify-between gap-4 glass-panel p-4 rounded-xl border border-slate-800 shadow-md">
        <div className="flex items-center gap-3 flex-1">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              type="text"
              placeholder="Search tasks, customers, or phone..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              className="w-full pl-10 pr-4 py-2 bg-slate-950/80 border border-slate-800 rounded-lg text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(['pending', 'completed', 'all'] as const).map(s => (
            <button
              key={s}
              onClick={() => setFilter(s)}
              className={`px-3.5 py-1.5 rounded-lg text-xs font-bold capitalize transition-all ${filter === s ? 'bg-gradient-to-r from-emerald-500/25 to-teal-500/25 text-emerald-300 border border-emerald-500/40 shadow-sm' : 'bg-slate-800/40 text-slate-400 hover:text-white hover:bg-slate-800'}`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-xl">
        {loading ? (
          <div className="p-12 text-center text-slate-400 font-medium">Loading tasks...</div>
        ) : filteredTasks.length === 0 ? (
          <div className="p-12 text-center text-slate-400 font-medium">No tasks found matching your filter.</div>
        ) : (
          <div className="divide-y divide-slate-800/60">
            {filteredTasks.map(task => (
              <div
                key={task.id}
                className="p-4 hover:bg-slate-800/40 transition-all flex items-center justify-between gap-4 group"
              >
                <div className="flex items-center gap-3.5 flex-1 min-w-0">
                  <button
                    onClick={() => toggleTaskStatus(task.id, task.status)}
                    className="text-slate-500 hover:text-emerald-400 transition-colors"
                  >
                    {task.status === 'completed' ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                    ) : (
                      <Circle className="w-5 h-5" />
                    )}
                  </button>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2.5">
                      <h3 className={`font-bold text-sm ${task.status === 'completed' ? 'line-through text-slate-500' : 'text-slate-100 group-hover:text-indigo-300 transition-colors'}`}>
                        {task.title}
                      </h3>
                      {task.lead_source && (
                        <span className="px-2.5 py-0.5 bg-amber-500/15 text-amber-300 border border-amber-500/30 rounded-md text-[10px] font-extrabold tracking-wider uppercase shadow-sm">
                          {task.lead_source}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-400 font-medium truncate mt-0.5">
                      {task.description || 'No description'} {task.contact_name ? `• ${task.contact_name} (${task.contact_phone})` : ''}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-4 shrink-0">
                  <div className="text-right">
                    <div className="text-xs text-slate-200 flex items-center gap-1.5 justify-end font-extrabold">
                      <User className="w-3.5 h-3.5 text-emerald-400" />
                      {task.assigned_to_name || 'Agent Alex'}
                    </div>
                    <div className="text-[11px] text-slate-400 flex items-center gap-1 justify-end mt-0.5 font-medium">
                      <Calendar className="w-3 h-3 text-slate-500" />
                      {task.due_at ? new Date(task.due_at).toLocaleDateString() : 'Due: Today'}
                    </div>
                  </div>

                  <button
                    onClick={() => setSelectedTask(task)}
                    className="px-3.5 py-1.5 bg-gradient-to-r from-indigo-600 via-purple-600 to-indigo-500 hover:from-indigo-500 hover:to-purple-500 text-white rounded-xl text-xs font-extrabold flex items-center gap-1.5 shadow-md shadow-indigo-500/20 transition-all transform hover:scale-105 active:scale-95"
                  >
                    View Task
                    <ExternalLink className="w-3 h-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* CREATE TASK MODAL */}
      {isCreateOpen && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950/50">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-xl">
                  <Plus className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 dark:text-white text-lg">Create New To-Do Task</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Manual creation or AI Round-Robin Load Balance</p>
                </div>
              </div>
              <button onClick={() => setIsCreateOpen(false)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white" aria-label="Close task creation modal">
                <XCircle className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleCreateTask} className="p-6 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Task Title *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Schedule 3 BHK site visit"
                  value={newTitle}
                  onChange={e => setNewTitle(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                  Description / Action Items
                </label>
                <textarea
                  rows={2}
                  placeholder="Details about customer requirement, budget, or inquiry notes..."
                  value={newDescription}
                  onChange={e => setNewDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    Customer Name
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Rahul Sharma"
                    value={newName}
                    onChange={e => setNewName(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    Phone Number
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 9876543210"
                    value={newPhone}
                    onChange={e => setNewPhone(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    Assignee Routing
                  </label>
                  <select
                    value={newAssignee}
                    onChange={e => setNewAssignee(e.target.value)}
                    className="w-full px-3 py-2 bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500 font-semibold shadow-sm"
                  >
                    <option value="auto">🔄 Auto (Round-Robin Load Balance)</option>
                    <optgroup label="🟢 Choice of Available Agents">
                      {(teamMembers.length > 0 ? teamMembers : DEFAULT_AGENTS).map(m => (
                        <option key={m.id || m.name} value={m.id || m.name}>
                          👤 {m.name} ({m.role || 'Sales Agent'}) — {m.assigned_leads_count || 0} active leads
                        </option>
                      ))}
                    </optgroup>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider mb-1">
                    Due In
                  </label>
                  <select
                    value={newDueHours}
                    onChange={e => setNewDueHours(Number(e.target.value))}
                    className="w-full px-3 py-2 bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-800 rounded-lg text-sm text-slate-900 dark:text-white focus:outline-none focus:border-emerald-500 font-medium"
                  >
                    <option value={1}>1 Hour</option>
                    <option value={4}>4 Hours</option>
                    <option value={24}>24 Hours (1 Day)</option>
                    <option value={48}>48 Hours (2 Days)</option>
                  </select>
                </div>
              </div>

              {newAssignee === 'auto' && (
                <div className="p-3 bg-cyan-500/10 border border-cyan-500/30 rounded-xl flex items-center gap-2 text-xs text-cyan-700 dark:text-cyan-400 font-semibold">
                  <Sparkles className="w-4 h-4 text-cyan-500 shrink-0" />
                  <span>Task will be automatically routed to the sales agent with the fewest assigned tasks.</span>
                </div>
              )}

              <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsCreateOpen(false)}
                  className="px-4 py-2 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white text-sm font-medium"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg text-sm shadow-md transition-colors flex items-center gap-2"
                >
                  {submitting ? 'Creating...' : 'Create & Assign Task'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* VIEW TASK MODAL */}
      {selectedTask && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl w-full max-w-lg shadow-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950/50">
              <div className="flex items-center gap-2.5">
                <div className="p-2 bg-emerald-100 dark:bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 rounded-xl">
                  <CheckCircle2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 dark:text-white text-lg">Lead Task Details</h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">Customer Inquiry & Lead Owner Assignment</p>
                </div>
              </div>
              <button onClick={() => setSelectedTask(null)} className="text-slate-400 hover:text-slate-600 dark:hover:text-white" aria-label="Close task details modal">
                <XCircle className="w-6 h-6" />
              </button>
            </div>

            <div className="p-6 space-y-5">
              <div className="p-3.5 bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 rounded-xl">
                <div className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider mb-1">Task Title</div>
                <div className="text-sm font-semibold text-slate-900 dark:text-white">{selectedTask.title}</div>
                <div className="text-xs text-slate-600 dark:text-slate-400 mt-1">{selectedTask.description}</div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="p-3 bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 rounded-lg">
                  <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase">Customer Name</div>
                  <div className="text-sm font-semibold text-slate-900 dark:text-white mt-0.5">{selectedTask.contact_name || 'Anonymous'}</div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 rounded-lg">
                  <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase">Contact Number</div>
                  <div className="text-sm font-semibold text-emerald-600 dark:text-emerald-400 mt-0.5">{selectedTask.contact_phone || 'N/A'}</div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 rounded-lg">
                  <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase">Lead Source</div>
                  <div className="text-sm font-semibold text-amber-700 dark:text-amber-300 mt-0.5">{selectedTask.lead_source || 'Google Ads'}</div>
                </div>
                <div className="p-3 bg-slate-50 dark:bg-slate-950/50 border border-slate-200 dark:border-slate-800 rounded-lg">
                  <div className="text-[11px] font-semibold text-slate-500 dark:text-slate-400 uppercase">Lead Owner (Round Robin)</div>
                  <div className="text-sm font-semibold text-cyan-600 dark:text-cyan-400 mt-0.5">{selectedTask.assigned_to_name || 'Agent Alex'}</div>
                </div>
              </div>

              <div className="p-4 bg-slate-50 dark:bg-slate-950/90 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2">
                <h4 className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Building className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /> Customer Inquiry Fields
                </h4>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-2.5 bg-white dark:bg-slate-900/80 rounded-lg border border-slate-200 dark:border-slate-800">
                    <span className="text-slate-500 dark:text-slate-400">Requirement: </span>
                    <span className="text-slate-900 dark:text-white font-semibold">{selectedTask.custom_inquiry_data?.property_type || '2 BHK Apartment'}</span>
                  </div>
                  <div className="p-2.5 bg-white dark:bg-slate-900/80 rounded-lg border border-slate-200 dark:border-slate-800">
                    <span className="text-slate-500 dark:text-slate-400">Location: </span>
                    <span className="text-slate-900 dark:text-white font-semibold">{selectedTask.custom_inquiry_data?.location || 'Bangalore'}</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="p-5 bg-slate-50 dark:bg-slate-950/50 border-t border-slate-200 dark:border-slate-800 flex items-center justify-end gap-3">
              <button
                onClick={() => toggleTaskStatus(selectedTask.id, selectedTask.status)}
                className="px-4 py-2 bg-emerald-100 dark:bg-emerald-500/20 hover:bg-emerald-200 dark:hover:bg-emerald-500/30 text-emerald-800 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-500/50 rounded-lg text-sm font-semibold flex items-center gap-2 transition-colors"
              >
                {selectedTask.status === 'pending' ? 'Mark as Completed' : 'Mark as Pending'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

