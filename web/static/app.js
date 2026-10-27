/**
 * BotMother Admin Dashboard — JavaScript
 * Handles all API calls, live data, and UI interactions.
 */

const API = {
  token: localStorage.getItem('admin_token'),

  async get(url) {
    const res = await fetch(url, { headers: { 'X-Admin-Token': this.token } });
    if (res.status === 401) { logout(); return null; }
    return res.json();
  },

  async post(url, data) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Admin-Token': this.token },
      body: JSON.stringify(data)
    });
    if (res.status === 401) { logout(); return null; }
    return res.json();
  }
};

// ==================== GLOBAL STATE ====================

let statsCache = null;
let usersCache = [];
let currentSection = 'dashboard';
let autoRefreshInterval = null;

// ==================== AUTH ====================

function logout() {
  API.post('/api/logout', {});
  localStorage.removeItem('admin_token');
  window.location.href = '/';
}

// Check auth on load
if (!API.token) {
  window.location.href = '/';
}

// ==================== NAVIGATION ====================

function showSection(name) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const section = document.getElementById(`section-${name}`);
  if (section) section.classList.add('active');

  const navItems = document.querySelectorAll('.nav-item');
  navItems.forEach(item => {
    if (item.getAttribute('onclick') && item.getAttribute('onclick').includes(`'${name}'`)) {
      item.classList.add('active');
    }
  });

  const titles = {
    dashboard: '📊 Dashboard',
    scripts: '🟢 Running Scripts',
    users: '👥 Users',
    pending: '📋 Pending Files',
    subscriptions: '⭐ Subscriptions',
    referrals: '🏆 Referrals',
    bans: '🚫 Banned Users',
    broadcast: '📢 Broadcast',
    settings: '⚙️ Settings',
  };
  document.getElementById('page-title').textContent = titles[name] || name;
  currentSection = name;

  // Section-specific loads
  if (name === 'users') loadUsers();
  if (name === 'pending') loadPending();
  if (name === 'bans') loadBans();
  if (name === 'subscriptions') loadSubscriptions();
  if (name === 'referrals') loadReferrals();
}

// ==================== DATA LOADING ====================

async function loadStats() {
  const data = await API.get('/api/stats');
  if (!data) return;
  statsCache = data;

  // Stat cards
  document.getElementById('stat-users').textContent = fmt(data.total_users);
  document.getElementById('stat-running').textContent = fmt(data.running_scripts);
  document.getElementById('stat-pending').textContent = fmt(data.pending_approvals);
  document.getElementById('stat-trials').textContent = fmt(data.active_trials);
  document.getElementById('stat-banned').textContent = fmt(data.banned_users);
  document.getElementById('stat-files').textContent = fmt(data.total_files);

  // Pending badge
  const badge = document.getElementById('pending-badge');
  if (data.pending_approvals > 0) {
    badge.textContent = data.pending_approvals;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }

  // Resources
  const sys = data.system;
  if (sys) {
    document.getElementById('cpu-val').textContent = `${sys.cpu_percent}%`;
    document.getElementById('cpu-bar').style.width = `${sys.cpu_percent}%`;
    document.getElementById('ram-val').textContent = `${sys.memory_used_gb}/${sys.memory_total_gb} GB (${sys.memory_percent}%)`;
    document.getElementById('ram-bar').style.width = `${sys.memory_percent}%`;
    document.getElementById('disk-val').textContent = `${sys.disk_used_gb}/${sys.disk_total_gb} GB (${sys.disk_percent}%)`;
    document.getElementById('disk-bar').style.width = `${sys.disk_percent}%`;
  }

  // Status toggles
  const locked = data.bot_locked;
  document.getElementById('toggle-lock').checked = locked;
  document.getElementById('settings-lock').checked = locked;
  document.getElementById('bot-lock-badge').textContent = locked ? '🔒 Locked' : '🔓 Unlocked';
  document.getElementById('bot-lock-badge').className = `badge ${locked ? 'badge-danger' : 'badge-success'}`;

  const maint = data.maintenance;
  document.getElementById('toggle-maintenance').checked = maint.enabled;
  document.getElementById('settings-maintenance').checked = maint.enabled;
  document.getElementById('maint-msg-text').textContent = maint.message || '—';
  document.getElementById('maint-msg-input').value = maint.message || '';

  // Uptime
  document.getElementById('uptime-text').textContent = data.uptime || '—';
  document.getElementById('uptime-badge').textContent = data.uptime || '';

  // Running scripts table
  const tbody = document.getElementById('scripts-tbody');
  const allTbody = document.getElementById('all-scripts-tbody');
  const list = data.running_list || [];
  document.getElementById('running-count-badge').textContent = `${list.length} running`;

  if (list.length === 0) {
    const row = '<tr><td colspan="5"><div class="empty-state"><div class="icon">💤</div><h3>No scripts running</h3><p>Scripts appear here when users start them</p></div></td></tr>';
    tbody.innerHTML = row;
    allTbody.innerHTML = row;
  } else {
    const rows = list.map(r => `
      <tr>
        <td><code style="font-size:12px;color:var(--accent-light)">${esc(r.file_name)}</code></td>
        <td><span class="badge badge-accent">${esc(r.file_type || '?')}</span></td>
        <td><code>${esc(String(r.user_id))}</code></td>
        <td><code>${r.pid || '—'}</code></td>
        <td><span class="badge badge-success">🟢 Running</span></td>
      </tr>`).join('');
    tbody.innerHTML = rows;
    allTbody.innerHTML = rows;
  }

  // Last updated
  document.getElementById('last-updated').textContent = `Updated ${new Date().toLocaleTimeString()}`;
}

async function loadUsers() {
  document.getElementById('users-tbody').innerHTML = '<tr><td colspan="7" class="loader">⏳ Loading users...</td></tr>';
  const data = await API.get('/api/users');
  if (!data) return;
  usersCache = data.users;
  renderUsers(data.users);
}

function renderUsers(users) {
  const tbody = document.getElementById('users-tbody');
  if (!users || users.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7"><div class="empty-state"><div class="icon">👥</div><h3>No users yet</h3></div></td></tr>';
    return;
  }
  tbody.innerHTML = users.map(u => `
    <tr>
      <td><code>${u.user_id}</code></td>
      <td>
        ${u.user_id == ${getOwnerId()} ? '<span class="badge badge-accent">👑 Owner</span>' :
          u.is_admin ? '<span class="badge badge-info">🛡 Admin</span>' :
          u.is_subscribed ? '<span class="badge badge-success">⭐ Premium</span>' :
          u.trial_active ? '<span class="badge badge-warning">🆓 Trial</span>' :
          u.is_banned ? '<span class="badge badge-danger">🚫 Banned</span>' :
          '<span class="badge badge-muted">👤 Free</span>'}
      </td>
      <td>${u.file_count}</td>
      <td>${u.trial_active ? `✅ Expires ${u.trial_expires ? u.trial_expires.slice(0,10) : '?'}` : '—'}</td>
      <td>${u.referral_count}</td>
      <td>${u.extra_slots > 0 ? `<span class="badge badge-success">+${u.extra_slots}</span>` : '—'}</td>
      <td style="display:flex;gap:6px;flex-wrap:wrap">
        <button class="btn btn-sm btn-success" onclick="openSubModal(${u.user_id})">⭐ Sub</button>
        ${u.is_banned
          ? `<button class="btn btn-sm btn-success" onclick="unbanUser(${u.user_id})">✅ Unban</button>`
          : `<button class="btn btn-sm btn-danger" onclick="quickBan(${u.user_id})">🚫 Ban</button>`}
      </td>
    </tr>`).join('');
}

function filterUsers() {
  const q = document.getElementById('user-search').value.trim();
  if (!q) { renderUsers(usersCache); return; }
  const filtered = usersCache.filter(u => String(u.user_id).includes(q));
  renderUsers(filtered);
}

async function loadPending() {
  document.getElementById('pending-list').innerHTML = '<div class="loader">⏳ Loading...</div>';
  const data = await API.get('/api/pending');
  if (!data) return;
  const list = document.getElementById('pending-list');

  if (!data.pending || data.pending.length === 0) {
    list.innerHTML = '<div class="empty-state"><div class="icon">✅</div><h3>No pending files</h3><p>All files have been reviewed</p></div>';
    return;
  }

  list.innerHTML = data.pending.map(p => `
    <div style="border:1px solid var(--border);border-radius:var(--radius);padding:18px;margin-bottom:12px;background:var(--bg-card)">
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:12px">
        <span class="badge badge-warning">📋 #${p.id}</span>
        <code style="color:var(--accent-light)">${esc(p.file_name)}</code>
        <span class="badge badge-accent">${esc(p.file_type)}</span>
        <span style="margin-left:auto;font-size:12px;color:var(--text-muted)">${p.submitted_at ? p.submitted_at.slice(0,16) : '—'}</span>
      </div>
      <div style="font-size:13px;color:var(--text-secondary);margin-bottom:12px">
        👤 User ID: <code>${p.user_id}</code>
      </div>
      <div style="display:flex;gap:10px">
        <button class="btn btn-sm btn-success" onclick="approveFile(${p.id})">✅ Approve</button>
        <button class="btn btn-sm btn-danger" onclick="rejectFile(${p.id})">❌ Reject</button>
      </div>
    </div>`).join('');
}

async function loadBans() {
  const data = await API.get('/api/users');
  if (!data) return;
  const banned = data.users.filter(u => u.is_banned);
  const tbody = document.getElementById('bans-tbody');
  if (banned.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">✅</div><h3>No banned users</h3></div></td></tr>';
    return;
  }
  tbody.innerHTML = banned.map(u => `
    <tr>
      <td><code>${u.user_id}</code></td>
      <td>—</td>
      <td>—</td>
      <td><button class="btn btn-sm btn-success" onclick="unbanUser(${u.user_id})">✅ Unban</button></td>
    </tr>`).join('');
}

async function loadSubscriptions() {
  const data = await API.get('/api/users');
  if (!data) return;
  const subs = data.users.filter(u => u.is_subscribed);
  const tbody = document.getElementById('subs-tbody');
  if (subs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4"><div class="empty-state"><div class="icon">⭐</div><h3>No active subscriptions</h3></div></td></tr>';
    return;
  }
  tbody.innerHTML = subs.map(u => {
    const exp = u.subscription_expiry ? new Date(u.subscription_expiry) : null;
    const daysLeft = exp ? Math.max(0, Math.ceil((exp - Date.now()) / 86400000)) : 0;
    return `<tr>
      <td><code>${u.user_id}</code></td>
      <td>${exp ? exp.toLocaleDateString() : '—'}</td>
      <td><span class="badge ${daysLeft > 7 ? 'badge-success' : 'badge-warning'}">${daysLeft} days</span></td>
      <td>${u.extra_slots > 0 ? `<span class="badge badge-success">+${u.extra_slots}</span>` : '—'}</td>
    </tr>`;
  }).join('');
}

async function loadReferrals() {
  const data = await API.get('/api/referrals/leaderboard');
  if (!data) return;
  const tbody = document.getElementById('referrals-tbody');
  const medals = ['🥇','🥈','🥉'];
  if (!data.leaderboard || data.leaderboard.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3"><div class="empty-state"><div class="icon">🏆</div><h3>No referrals yet</h3></div></td></tr>';
    return;
  }
  tbody.innerHTML = data.leaderboard.map((r, i) => `
    <tr>
      <td>${medals[i] || `${i+1}.`}</td>
      <td><code>${r.user_id}</code></td>
      <td><span class="badge badge-accent">${r.referral_count}</span></td>
    </tr>`).join('');
}

// ==================== ACTIONS ====================

async function toggleLock() {
  const locked = document.getElementById('toggle-lock').checked ||
                 document.getElementById('settings-lock').checked;
  await API.post('/api/settings', { bot_locked: locked });
  // Sync both toggles
  document.getElementById('toggle-lock').checked = locked;
  document.getElementById('settings-lock').checked = locked;
  toast(locked ? '🔒 Bot locked' : '🔓 Bot unlocked', 'info');
  await loadStats();
}

async function toggleMaintenance() {
  const enabled = document.getElementById('toggle-maintenance').checked ||
                  document.getElementById('settings-maintenance').checked;
  const msg = document.getElementById('maint-msg-input').value || null;
  await API.post('/api/settings', { maintenance: { enabled, message: msg } });
  document.getElementById('toggle-maintenance').checked = enabled;
  document.getElementById('settings-maintenance').checked = enabled;
  toast(enabled ? '🛠 Maintenance enabled' : '✅ Maintenance disabled', 'info');
}

async function saveMaintMsg() {
  const msg = document.getElementById('maint-msg-input').value;
  const enabled = document.getElementById('settings-maintenance').checked;
  await API.post('/api/settings', { maintenance: { enabled, message: msg } });
  toast('💾 Message saved', 'success');
}

async function approveFile(id) {
  const res = await API.post('/api/approve', { approval_id: id });
  toast(res?.success ? '✅ File approved' : '❌ Failed to approve', res?.success ? 'success' : 'error');
  loadPending();
  await loadStats();
}

async function rejectFile(id) {
  const reason = prompt('Rejection reason (optional):') || 'Rejected via web panel';
  const res = await API.post('/api/reject', { approval_id: id, reason });
  toast(res?.success ? '❌ File rejected' : '❌ Failed', res?.success ? 'info' : 'error');
  loadPending();
  await loadStats();
}

function openBanModal() {
  document.getElementById('ban-modal').classList.add('open');
}

function openSubModal(userId) {
  document.getElementById('sub-user-id').value = userId;
  document.getElementById('sub-modal').classList.add('open');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('open');
}

async function banUser() {
  const userId = document.getElementById('ban-user-id').value;
  const reason = document.getElementById('ban-reason').value || 'Violation of terms';
  if (!userId) { toast('❌ User ID required', 'error'); return; }
  const res = await API.post('/api/ban', { user_id: parseInt(userId), reason });
  toast(res?.success ? `🚫 User ${userId} banned` : '❌ Failed to ban', res?.success ? 'success' : 'error');
  closeModal('ban-modal');
  loadBans();
  loadUsers();
}

async function quickBan(userId) {
  if (!confirm(`Ban user ${userId}?`)) return;
  const res = await API.post('/api/ban', { user_id: userId, reason: 'Banned by admin' });
  toast(res?.success ? `🚫 User ${userId} banned` : '❌ Failed to ban', res?.success ? 'success' : 'error');
  loadUsers();
  await loadStats();
}

async function unbanUser(userId) {
  if (!confirm(`Unban user ${userId}?`)) return;
  const res = await API.post('/api/unban', { user_id: userId });
  toast(res?.success ? `✅ User ${userId} unbanned` : '❌ Not found', res?.success ? 'success' : 'error');
  loadUsers();
  loadBans();
}

async function giveSubscription() {
  const userId = parseInt(document.getElementById('sub-user-id').value);
  const days = parseInt(document.getElementById('sub-days').value);
  if (!userId || !days) { toast('❌ Fill all fields', 'error'); return; }
  const res = await API.post('/api/subscription/add', { user_id: userId, days });
  toast(res?.success ? `⭐ ${days}-day subscription given to ${userId}` : '❌ Failed', res?.success ? 'success' : 'error');
  closeModal('sub-modal');
  loadUsers();
}

async function sendBroadcast() {
  const msg = document.getElementById('broadcast-msg').value.trim();
  if (!msg) { toast('❌ Message cannot be empty', 'error'); return; }
  const btn = document.getElementById('broadcast-btn');
  const status = document.getElementById('broadcast-status');
  btn.disabled = true;
  btn.textContent = '⏳ Sending...';
  const res = await API.post('/api/broadcast', { message: msg });
  btn.disabled = false;
  btn.textContent = '📢 Send Broadcast';
  if (res?.success) {
    toast(`✅ Sent to ${res.sent} users (${res.failed} failed)`, 'success');
    status.textContent = `✅ Sent: ${res.sent} | Failed: ${res.failed} | Total: ${res.total}`;
  } else {
    toast('❌ Broadcast failed', 'error');
  }
}

// ==================== UTILS ====================

function fmt(n) { return n !== undefined && n !== null ? n.toLocaleString() : '—'; }

function esc(str) {
  if (!str) return '';
  return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function getOwnerId() {
  // Fallback — can't know owner ID on frontend unless returned by API
  return null;
}

function toast(msg, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  const icons = { success: '✅', error: '❌', info: 'ℹ️' };
  el.innerHTML = `<span>${icons[type] || 'ℹ️'}</span><span>${esc(msg)}</span>`;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; setTimeout(() => el.remove(), 300); }, 3500);
}

function openModal(id) {
  document.getElementById(id).classList.add('open');
}

// Close modal on backdrop click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.remove('open');
  });
});

// ==================== AUTO REFRESH ====================

async function refreshData() {
  const btn = document.getElementById('refresh-btn');
  btn.textContent = '⏳ Refreshing...';
  btn.disabled = true;
  await loadStats();
  btn.textContent = '🔄 Refresh';
  btn.disabled = false;
}

// Auto-refresh every 15 seconds
autoRefreshInterval = setInterval(() => {
  if (document.visibilityState === 'visible') {
    loadStats();
  }
}, 15000);

// ==================== INIT ====================

// Initial load
loadStats();
