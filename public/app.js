const API_BASE = 'http://localhost:8080/api';
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
    'leadsTab': 'navLeadsBtn',
    'simulatorTab': 'navSimBtn'
  };
  const activeBtn = document.getElementById(navMap[tabId]);
  if (activeBtn) activeBtn.classList.add('active');

  const titles = {
    'tasksTab': 'My Assigned Tasks & Follow-ups',
    'leadsTab': 'Leads & Appointments',
    'callsTab': 'AI Call Logs & Transcripts',
    'simulatorTab': 'Live AI Call Simulator'
  };
  document.getElementById('pageTitle').innerText = titles[tabId] || 'Dashboard';
}

async function fetchDashboardData() {
  await Promise.all([fetchTasks(), fetchLeads(), fetchActivities()]);
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
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">No leads captured yet. Run a call simulation!</td></tr>`;
    return;
  }

  tbody.innerHTML = leads.map(lead => `
    <tr>
      <td><strong>${escapeHtml(lead.name)}</strong></td>
      <td>${escapeHtml(lead.phone)}</td>
      <td>${escapeHtml(lead.need)}</td>
      <td>📅 ${escapeHtml(lead.preferredTime || 'Flexible')}</td>
      <td>${new Date(lead.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</td>
      <td><span class="status-pill ${lead.status}">${lead.status}</span></td>
      <td>
        <button class="action-btn" onclick="updateLeadStatus('${lead.id}', 'CONTACTED')">Mark Contacted</button>
      </td>
    </tr>
  `).join('');
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

async function triggerOutboundPhoneCall() {
  const phone = document.getElementById('outboundPhoneInput').value.trim();
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
