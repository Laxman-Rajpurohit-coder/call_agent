const API_BASE = window.location.origin + '/api';
let socket = null;

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
  const token = localStorage.getItem('crm_token');
  if (token) {
    showDashboard();
  } else {
    showAuth();
  }

  // Setup Login Form Handler
  document.getElementById('loginForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();

      if (data.success) {
        localStorage.setItem('crm_token', data.token);
        localStorage.setItem('crm_user', JSON.stringify(data.user));
        showDashboard();
      } else {
        alert(data.error || 'Login failed');
      }
    } catch (err) {
      alert('Error connecting to backend server');
    }
  });

  // Connect Socket.io for Live Screen Pops
  try {
    socket = io();
    socket.on('screen-pop-handoff', (payload) => {
      showScreenPop(payload);
    });
    socket.on('call-ended', () => {
      dismissPop();
    });
  } catch (err) {
    console.log('Socket initialization error:', err);
  }
});

function showAuth() {
  document.getElementById('authContainer').classList.remove('hidden');
  document.getElementById('dashboardContainer').classList.add('hidden');
}

function showDashboard() {
  document.getElementById('authContainer').classList.add('hidden');
  document.getElementById('dashboardContainer').classList.remove('hidden');
  
  const user = JSON.parse(localStorage.getItem('crm_user') || '{}');
  if (user.name) {
    document.getElementById('userName').innerText = user.name;
    const roleElem = document.querySelector('.user-info small');
    if (roleElem) {
      roleElem.innerText = user.role === 'AGENT' ? 'Telecaller / Sales Agent' : 'Clinic Owner (Admin)';
    }
  }

  // If agent, default to tasksTab
  if (user.role === 'AGENT') {
    switchTab('tasksTab');
  } else {
    switchTab('leadsTab');
  }

  fetchDashboardData();
}

function logout() {
  localStorage.removeItem('crm_token');
  localStorage.removeItem('crm_user');
  showAuth();
}

function switchTab(tabId) {
  document.querySelectorAll('.tab-content').forEach(tab => tab.classList.add('hidden'));
  document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));

  const activeContent = document.getElementById(tabId);
  if (activeContent) activeContent.classList.remove('hidden');

  const navMap = {
    'tasksTab': 'navTasksBtn',
    'campaignsTab': 'navCampaignsBtn',
    'leadsTab': 'navLeadsBtn',
    'callsTab': 'navCallsBtn',
    'simulatorTab': 'navSimBtn'
  };
  const activeBtn = document.getElementById(navMap[tabId]);
  if (activeBtn) activeBtn.classList.add('active');

  const titles = {
    'tasksTab': 'My Assigned Tasks & Follow-ups',
    'campaignsTab': 'My Assigned Outreach Campaigns',
    'leadsTab': 'Leads & Appointments',
    'callsTab': 'AI Call Logs & Transcripts',
    'simulatorTab': 'Live AI Call Simulator'
  };
  document.getElementById('pageTitle').innerText = titles[tabId] || 'Dashboard';
}

async function fetchDashboardData() {
  await Promise.all([fetchTasks(), fetchCampaigns(), fetchLeads(), fetchActivities()]);
}

async function fetchTasks() {
  try {
    const res = await fetch(`${API_BASE}/tasks`);
    const data = await res.json();
    if (data.success && data.tasks) {
      renderTasks(data.tasks);
      const pendingCount = data.tasks.filter(t => t.status !== 'completed').length;
      const badge = document.getElementById('pendingTasksBadge');
      if (badge) badge.innerText = `${pendingCount} Pending`;
    }
  } catch (err) {
    console.error('Error fetching tasks:', err);
  }
}

function renderTasks(tasks) {
  const tbody = document.getElementById('tasksTableBody');
  if (!tbody) return;
  if (!tasks || tasks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="empty-state">No assigned tasks found.</td></tr>`;
    return;
  }

  tbody.innerHTML = tasks.map(t => {
    const isDone = t.status === 'completed';
    return `
      <tr style="${isDone ? 'opacity: 0.6;' : ''}">
        <td>
          <strong style="${isDone ? 'text-decoration: line-through;' : ''}">${escapeHtml(t.title)}</strong>
          ${t.description ? `<br><small style="color: #94a3b8;">${escapeHtml(t.description)}</small>` : ''}
        </td>
        <td>${escapeHtml(t.contact_name || 'Lead')}</td>
        <td><strong style="color: #6366f1;">${escapeHtml(t.contact_phone || '-')}</strong></td>
        <td>📅 ${t.due_at ? new Date(t.due_at).toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : 'Flexible'}</td>
        <td><span class="status-pill ${isDone ? 'CONTACTED' : 'NEW'}">${t.status.toUpperCase()}</span></td>
        <td>
          ${t.contact_phone ? `<button class="action-btn" style="background:#4f46e5; margin-right:4px;" onclick="initiatePhoneCall('${t.contact_phone}')">📞 Call</button>` : ''}
          ${!isDone ? `<button class="action-btn" onclick="completeTaskItem('${t.id}')">✅ Done</button>` : '<span style="color:#10b981; font-weight:bold;">Completed</span>'}
        </td>
      </tr>
    `;
  }).join('');
}

async function completeTaskItem(taskId) {
  try {
    const res = await fetch(`${API_BASE}/tasks/${taskId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: 'completed' })
    });
    if (res.ok) {
      await fetchTasks();
    }
  } catch (err) {
    console.error('Failed to complete task:', err);
  }
}

async function initiatePhoneCall(phone) {
  try {
    const res = await fetch(`${API_BASE}/telephony/originate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone_number: phone, auto_answer: 1 })
    });
    alert(`Calling ${phone} via MicroSIP Softphone...`);
  } catch (err) {
    alert(`Failed to start call: ${err.message}`);
  }
}

async function fetchCampaigns() {
  try {
    const res = await fetch('/api/v1/campaigns');
    if (res.ok) {
      const campaigns = await res.json();
      renderCampaigns(campaigns);
    }
  } catch (err) {
    console.error('Error fetching campaigns:', err);
  }
}

function renderCampaigns(campaigns) {
  const container = document.getElementById('campaignsGrid');
  if (!container) return;
  if (!campaigns || campaigns.length === 0) {
    container.innerHTML = `<div class="empty-state" style="grid-column: 1/-1; padding: 32px; text-align: center; color: #94a3b8;">No outreach campaigns found. Ask your clinic admin to create one.</div>`;
    return;
  }

  container.innerHTML = campaigns.map(c => {
    const statusColors = {
      'RUNNING': '#10b981',
      'PAUSED': '#f59e0b',
      'DRAFT': '#94a3b8',
      'COMPLETED': '#6366f1'
    };
    const statusColor = statusColors[c.status] || '#94a3b8';
    return `
      <div class="campaign-card" style="background: #182234; border: 1px solid #334155; border-radius: 12px; padding: 18px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.3);">
        <div>
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 11px; font-weight: 700; text-transform: uppercase; background: ${statusColor}20; color: ${statusColor}; border: 1px solid ${statusColor}40; padding: 2px 8px; border-radius: 9999px;">
              ${escapeHtml(c.status)}
            </span>
            <span style="font-size: 11px; color: #94a3b8; font-family: monospace;">${escapeHtml(c.type || 'AI')} MODE</span>
          </div>
          <h4 style="font-size: 16px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">${escapeHtml(c.name)}</h4>
          <p style="font-size: 12px; color: #94a3b8; line-height: 1.4;">${escapeHtml(c.script_content || c.description || 'Automated Outreach Call Flow')}</p>
        </div>

        <div style="border-top: 1px solid #334155; padding-top: 12px; display: flex; justify-content: space-between; align-items: center; font-size: 12px; color: #cbd5e1;">
          <div>
            <span>👥 Contacts: <strong style="color: #6366f1;">${c.contact_count || 1}</strong></span>
          </div>
          <div style="display: flex; gap: 6px;">
            ${c.status === 'RUNNING' 
              ? `<button class="action-btn" style="background: #f59e0b; color:#fff;" onclick="pauseCampaign('${c.id}')">⏸ Pause</button>` 
              : `<button class="action-btn" style="background: #10b981; color:#fff;" onclick="startCampaign('${c.id}')">▶ Start</button>`}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

async function startCampaign(id) {
  try {
    const res = await fetch(`/api/v1/campaigns/${id}/start`, { method: 'POST' });
    if (res.ok) {
      alert('Campaign started! Calls are now being placed.');
      fetchCampaigns();
    } else {
      alert('Failed to start campaign.');
    }
  } catch (err) {
    alert(`Error starting campaign: ${err.message}`);
  }
}

async function pauseCampaign(id) {
  try {
    const res = await fetch(`/api/v1/campaigns/${id}/pause`, { method: 'POST' });
    if (res.ok) {
      alert('Campaign paused.');
      fetchCampaigns();
    } else {
      alert('Failed to pause campaign.');
    }
  } catch (err) {
    alert(`Error pausing campaign: ${err.message}`);
  }
}

async function fetchLeads() {
  try {
    const res = await fetch(`${API_BASE}/leads`);
    const data = await res.json();

    if (data.success) {
      renderLeads(data.leads);
      updateMetrics(data.leads);
    }
  } catch (err) {
    console.error('Error fetching leads:', err);
  }
}

function renderLeads(leads) {
  const tbody = document.getElementById('leadsTableBody');
  if (!leads || leads.length === 0) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">No leads captured yet. Run a call simulation!</td></tr>`;
    return;
  }

  tbody.innerHTML = leads.map(lead => {
    const score = lead.intentScore || (lead.need?.toLowerCase().includes('whitening') || lead.need?.toLowerCase().includes('cleaning') || lead.need?.toLowerCase().includes('root canal') ? 92 : 80);
    const scoreColor = score >= 85 ? '#10b981' : '#f59e0b';
    return `
      <tr>
        <td><strong>${escapeHtml(lead.name)}</strong></td>
        <td><strong style="color:#6366f1;">${escapeHtml(lead.phone)}</strong></td>
        <td>
          <span style="font-weight: 500;">${escapeHtml(lead.need)}</span>
          ${lead.summary ? `<br><small style="color: #94a3b8; font-style: italic;">“${escapeHtml(lead.summary)}”</small>` : ''}
        </td>
        <td>
          <div style="display: flex; align-items: center; gap: 6px;">
            <div style="flex: 1; height: 6px; background: #0f172a; border-radius: 9999px; overflow: hidden; width: 60px;">
              <div style="height: 100%; width: ${score}%; background: ${scoreColor}; border-radius: 9999px;"></div>
            </div>
            <strong style="font-size: 11px; color: ${scoreColor};">${score}%</strong>
          </div>
        </td>
        <td>📅 ${escapeHtml(lead.preferredTime || 'Flexible')}</td>
        <td>${new Date(lead.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
        <td><span class="status-pill ${lead.status}">${lead.status}</span></td>
        <td>
          <button class="action-btn" style="background:#10b981; color:#fff; font-weight:600; margin-right:4px;" onclick="triggerOutboundPhoneCall('${escapeHtml(lead.phone)}')">📞 Call Customer</button>
          <button class="action-btn" onclick="updateLeadStatus('${lead.id}', 'CONTACTED')">Mark Contacted</button>
        </td>
      </tr>
    `;
  }).join('');
}

async function fetchActivities() {
  try {
    const res = await fetch(`${API_BASE}/activities`);
    const data = await res.json();

    if (data.success) {
      renderActivities(data.activities);
      document.getElementById('statTotalCalls').innerText = data.activities.length;
    }
  } catch (err) {
    console.error('Error fetching activities:', err);
  }
}

function renderActivities(activities) {
  const tbody = document.getElementById('callsTableBody');
  if (!activities || activities.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No call logs recorded yet.</td></tr>`;
    return;
  }

  tbody.innerHTML = activities.map(act => `
    <tr>
      <td>${new Date(act.createdAt).toLocaleString()}</td>
      <td><strong>${escapeHtml(act.phone)}</strong></td>
      <td>⏱️ ${act.durationSec}s</td>
      <td><span class="status-pill NEW">${escapeHtml(act.intent || 'general_query')}</span></td>
      <td>${escapeHtml(act.summary || 'AI call handled.')}</td>
      <td>
        ${act.recordingUrl 
          ? `<audio controls style="height:30px; width:150px;" src="${act.recordingUrl}"></audio>` 
          : '<small style="color:#94a3b8">No audio</small>'}
      </td>
      <td>
        <button class="action-btn" onclick="viewTranscript('${escapeHtml(act.transcript || 'No transcript available.')}')">View Transcript</button>
      </td>
    </tr>
  `).join('');
}

function updateMetrics(leads) {
  document.getElementById('statTotalLeads').innerText = leads.length;
  const bookedCount = leads.filter(l => l.status === 'BOOKED' || l.need.toLowerCase().includes('appointment')).length;
  document.getElementById('statBooked').innerText = bookedCount;
}

async function updateLeadStatus(id, newStatus) {
  try {
    const res = await fetch(`${API_BASE}/leads/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus })
    });
    if (res.ok) fetchLeads();
  } catch (err) {
    console.error('Error updating status:', err);
  }
}

async function simulateAiCall() {
  const name = document.getElementById('simName').value;
  const phone = document.getElementById('simPhone').value;
  const need = document.getElementById('simNeed').value;
  const preferredTime = document.getElementById('simTime').value;

  const mockTranscript = `
AI: Thank you for calling Smile Dental Clinic! I'm Riya. How can I assist you?
Caller: Hi, my name is ${name}. I need to get ${need}.
AI: Sure ${name}, we can schedule that for you. What date or time works best?
Caller: ${preferredTime} would be great.
AI: Perfect, I have noted down your request for ${need} at ${preferredTime}. Our clinic manager will confirm shortly.
  `.trim();

  try {
    const leadRes = await fetch(`${API_BASE}/leads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, phone, need, preferredTime })
    });
    const leadData = await leadRes.json();

    if (leadData.success) {
      await fetch(`${API_BASE}/activities`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          leadId: leadData.lead.id,
          phone,
          type: 'CALL',
          durationSec: 42,
          transcript: mockTranscript,
          summary: `Call received from ${name} requesting ${need} at ${preferredTime}.`,
          intent: 'book_appointment'
        })
      });

      alert('✅ Simulated Inbound Call processed! New Lead and Call Log added to database.');
      fetchDashboardData();
      switchTab('leadsTab');
    }
  } catch (err) {
    alert('Error running AI call simulation: ' + err.message);
  }
}

function showScreenPop(payload) {
  document.getElementById('popCallerName').innerText = `${payload.name || 'Caller'} (${payload.phone})`;
  document.getElementById('popIntent').innerText = `Need: ${payload.need || 'Consultation'} • Preferred: ${payload.preferredTime || 'Flexible'}`;
  document.getElementById('screenPopBanner').classList.remove('hidden');
}

function dismissPop() {
  document.getElementById('screenPopBanner').classList.add('hidden');
}

function viewTranscript(text) {
  document.getElementById('modalTranscriptBody').innerText = text;
  document.getElementById('transcriptModal').classList.remove('hidden');
}

function closeModal() {
  document.getElementById('transcriptModal').classList.add('hidden');
}

function escapeHtml(str) {
  return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function triggerOutboundPhoneCall(targetPhone) {
  const phoneInput = document.getElementById('outboundPhoneInput');
  const phone = targetPhone || (phoneInput ? phoneInput.value.trim() : '');
  if (!phone) {
    alert('Please enter a valid phone number.');
    return;
  }

  try {
    const res = await fetch(`${API_BASE}/telephony/outbound-call`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ to: phone })
    });
    const data = await res.json();
    if (data.success) {
      alert(`📞 Outbound Call Triggered! Exotel is dialing ${phone} now. Answer your phone to speak with Riya (AI Receptionist).`);
    } else {
      alert(`Outbound call error: ${data.error || 'Failed to connect Exotel API'}`);
    }
  } catch (err) {
    alert('Error connecting to backend API: ' + err.message);
  }
}
