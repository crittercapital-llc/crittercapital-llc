/* ── Goggins Fitness Agent — App JS ─────────────────────────────────────── */

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  tab: 'today',
  chatHistory: [],
  authStatus: { whoop: false, strava: false },
  todayData: null,
  plan: null,
};

// ── Helpers ────────────────────────────────────────────────────────────────
function qs(sel, parent = document) { return parent.querySelector(sel); }
function qsa(sel, parent = document) { return [...parent.querySelectorAll(sel)]; }

function showToast(msg, duration = 2500) {
  const t = qs('#toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), duration);
}

function scoreColor(score) {
  if (score === null || score === undefined) return '';
  if (score >= 67) return 'score-green';
  if (score >= 34) return 'score-yellow';
  if (score >= 20) return 'score-orange';
  return 'score-red';
}

function intensityClass(intensity) {
  return `intensity-${(intensity || 'moderate').toLowerCase()}`;
}

function dotColor(intensity) {
  const map = { rest: '#555', easy: '#44ff88', moderate: '#e8ff00', hard: '#ff8c00', peak: '#ff4444' };
  return map[(intensity || 'moderate').toLowerCase()] || '#555';
}

function fmtDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr + 'T00:00:00');
  return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

// Simple markdown-ish to HTML (bold, bullets)
function renderMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>')
    .replace(/\n\n/g, '<br><br>')
    .replace(/\n/g, '<br>');
}

// ── Tab Navigation ─────────────────────────────────────────────────────────
function switchTab(tab) {
  state.tab = tab;
  qsa('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
  qsa('.screen').forEach(s => s.classList.toggle('active', s.id === `screen-${tab}`));

  if (tab === 'today') loadToday();
  if (tab === 'plan') loadPlan();
  if (tab === 'settings') loadSettings();
}

// ── Auth Status ────────────────────────────────────────────────────────────
async function fetchAuthStatus() {
  try {
    const res = await fetch('/auth/status');
    state.authStatus = await res.json();
  } catch (e) { /* offline */ }
}

// ── TODAY SCREEN ───────────────────────────────────────────────────────────
async function loadToday() {
  const screen = qs('#screen-today');
  screen.innerHTML = '<div class="loading">Loading your data...</div>';

  try {
    const res = await fetch('/today');
    const data = await res.json();
    state.todayData = data;
    renderToday(data);
  } catch (e) {
    screen.innerHTML = `<div class="empty-state"><div class="big-icon">⚡</div><p>Couldn't load data. Check your connection.</p></div>`;
  }
}

function renderToday(data) {
  const recovery = data.recovery || {};
  const sleep = data.sleep || {};
  const workout = data.scheduled_workout || {};
  const score = recovery.score;
  const intensity = data.recommended_intensity;

  let workoutHTML = '';
  if (workout.error) {
    workoutHTML = `
      <div class="card" id="today-workout-card">
        <div class="card-title">Today's Mission</div>
        <div class="empty-state" style="padding:16px 0">
          <p>No plan set yet. Go to Settings to set your goals, then generate your plan.</p>
          <br>
          <button class="btn btn-primary btn-sm" onclick="switchTab('settings')">Set Goals</button>
        </div>
      </div>`;
  } else {
    workoutHTML = `
      <div class="card" id="today-workout-card">
        <div class="card-title">Today's Mission</div>
        <span class="workout-intensity ${intensityClass(intensity || workout.intensity)}">${(intensity || workout.intensity || 'moderate').toUpperCase()}</span>
        <div class="workout-description">${workout.description || 'Rest Day'}</div>
        <div class="workout-meta">
          ${workout.distance_km ? `${workout.distance_km} km · ` : ''}${workout.duration_min ? `${workout.duration_min} min` : ''}
          ${data.intensity_rationale ? `<br><em style="color:var(--text2)">${data.intensity_rationale}</em>` : ''}
        </div>
        <button class="btn btn-primary" onclick="openLogWorkout()">Log Workout</button>
      </div>`;
  }

  let recoveryHTML = '';
  if (recovery.error) {
    recoveryHTML = `
      <div class="card" id="recovery-card">
        <div class="card-title">Recovery</div>
        <div style="color:var(--text2);font-size:14px">
          ${recovery.error === 'not_connected'
            ? 'Connect Whoop in <a href="#" onclick="switchTab(\'settings\')" style="color:var(--accent)">Settings</a> to see your recovery data.'
            : 'No recovery data yet today.'}
        </div>
      </div>`;
  } else {
    recoveryHTML = `
      <div class="card" id="recovery-card">
        <div class="card-title">Recovery Score</div>
        <div class="recovery-score ${scoreColor(score)}">${score !== null && score !== undefined ? Math.round(score) : '—'}</div>
        <div style="font-size:13px;color:var(--text2);margin-bottom:8px">${fmtDate(recovery.date) || 'Today'}</div>
        <div class="recovery-stats">
          <div class="stat-box">
            <div class="stat-val">${recovery.hrv_rmssd ? Math.round(recovery.hrv_rmssd) : '—'}</div>
            <div class="stat-lbl">HRV ms</div>
          </div>
          <div class="stat-box">
            <div class="stat-val">${recovery.resting_hr ? Math.round(recovery.resting_hr) : '—'}</div>
            <div class="stat-lbl">RHR bpm</div>
          </div>
          <div class="stat-box">
            <div class="stat-val">${sleep.hours !== null && sleep.hours !== undefined ? sleep.hours : '—'}</div>
            <div class="stat-lbl">Sleep hrs</div>
          </div>
        </div>
      </div>`;
  }

  qs('#screen-today').innerHTML = recoveryHTML + workoutHTML;
}

// ── LOG WORKOUT MODAL ──────────────────────────────────────────────────────
function openLogWorkout() {
  // Pre-fill chat with log workout prompt
  switchTab('chat');
  qs('#chat-input').value = "I just finished my workout. Here's how it went: ";
  qs('#chat-input').focus();
}

// ── PLAN SCREEN ────────────────────────────────────────────────────────────
async function loadPlan() {
  const screen = qs('#screen-plan');
  screen.innerHTML = '<div class="loading">Loading plan...</div>';

  try {
    const res = await fetch('/plan');
    const data = await res.json();

    if (data.error) {
      screen.innerHTML = `
        <div class="empty-state">
          <div class="big-icon">📋</div>
          <p>No training plan yet.</p>
          <br>
          <button class="btn btn-primary" onclick="generatePlan()">Generate My Plan</button>
          <br><br>
          <p style="font-size:13px">Set your goals in Settings first.</p>
        </div>`;
      return;
    }

    state.plan = data;
    renderPlan(data);
  } catch (e) {
    screen.innerHTML = `<div class="empty-state"><p>Couldn't load plan.</p></div>`;
  }
}

function renderPlan(data) {
  const today = todayISO();
  const weeks = data.weeks || {};
  let html = `<button class="btn btn-secondary" style="margin-bottom:16px" onclick="generatePlan()">↻ Regenerate Plan</button>`;

  for (const [weekNum, days] of Object.entries(weeks)) {
    html += `<div class="week-header">Week ${weekNum}</div>`;
    for (const day of days) {
      const isToday = day.date === today;
      const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
      const dayName = dayNames[(day.day || 1) - 1] || '';
      const dateShort = day.date ? day.date.slice(5) : ''; // MM-DD

      html += `
        <div class="plan-day ${day.completed ? 'completed' : ''} ${isToday ? 'today' : ''}">
          <div class="plan-day-date">
            <div class="day-name">${dayName}</div>
            <div>${dateShort}</div>
          </div>
          <div class="plan-day-body">
            <div class="plan-day-desc">${day.description || 'Rest'}</div>
            <div class="plan-day-meta">
              ${day.distance_km ? `${day.distance_km}km · ` : ''}${day.duration_min ? `${day.duration_min}min · ` : ''}${(day.intensity || '').toUpperCase()}
            </div>
          </div>
          <div class="plan-day-dot" style="background:${dotColor(day.intensity)}"></div>
        </div>`;
    }
  }

  qs('#screen-plan').innerHTML = html;
}

async function generatePlan() {
  showToast('Goggins is building your plan...', 5000);
  try {
    const res = await fetch('/plan/generate', { method: 'POST' });
    const data = await res.json();
    if (data.message) {
      showToast('Plan generated!');
      loadPlan();
      // Show coaching message in chat
      state.chatHistory.push({ role: 'assistant', content: data.message });
      renderChatHistory();
      switchTab('chat');
    }
  } catch (e) {
    showToast('Error generating plan. Make sure your profile is set.');
  }
}

// ── CHAT SCREEN ────────────────────────────────────────────────────────────
function renderChatHistory() {
  const container = qs('#chat-messages');
  if (state.chatHistory.length === 0) {
    container.innerHTML = `
      <div class="msg msg-agent">
        What's up. I'm Goggins — your coach. Tell me your goal and let's get to work. Or ask me anything about your training.
      </div>`;
    return;
  }
  container.innerHTML = state.chatHistory
    .filter(m => m.role !== 'system')
    .map(m => `<div class="msg msg-${m.role === 'user' ? 'user' : 'agent'}">${
      m.role === 'user' ? escapeHtml(m.content) : renderMarkdown(m.content)
    }</div>`)
    .join('');
  container.scrollTop = container.scrollHeight;
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function sendChat() {
  const input = qs('#chat-input');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.style.height = 'auto';

  state.chatHistory.push({ role: 'user', content: msg });
  renderChatHistory();

  // Show typing indicator
  const container = qs('#chat-messages');
  const typingEl = document.createElement('div');
  typingEl.className = 'msg msg-typing';
  typingEl.textContent = 'Goggins is thinking...';
  container.appendChild(typingEl);
  container.scrollTop = container.scrollHeight;

  qs('#chat-send').disabled = true;

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        history: state.chatHistory.slice(0, -1), // exclude the just-added user msg
      }),
    });

    typingEl.remove();

    // Read SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let agentMsg = '';

    // Add agent message bubble
    const agentEl = document.createElement('div');
    agentEl.className = 'msg msg-agent';
    container.appendChild(agentEl);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      const lines = chunk.split('\n');

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') break;

        try {
          const json = JSON.parse(payload);
          if (json.text) {
            agentMsg += json.text;
            agentEl.innerHTML = renderMarkdown(agentMsg);
            container.scrollTop = container.scrollHeight;
          }
          if (json.error) {
            agentEl.textContent = `Error: ${json.error}`;
          }
        } catch (_) { /* ignore parse errors */ }
      }
    }

    state.chatHistory.push({ role: 'assistant', content: agentMsg });

  } catch (e) {
    typingEl.remove();
    const errEl = document.createElement('div');
    errEl.className = 'msg msg-agent';
    errEl.textContent = 'Something went wrong. Try again.';
    container.appendChild(errEl);
  }

  qs('#chat-send').disabled = false;
  qs('#chat-input').focus();
}

// ── SETTINGS SCREEN ────────────────────────────────────────────────────────
async function loadSettings() {
  await fetchAuthStatus();
  const { whoop, strava } = state.authStatus;

  let profile = {};
  try {
    const res = await fetch('/profile');
    const data = await res.json();
    if (!data.error) profile = data;
  } catch (_) {}

  const screen = qs('#screen-settings');
  screen.innerHTML = `
    <div class="settings-section">
      <span class="settings-label">Connected Accounts</span>

      <div class="connect-row">
        <div>
          <div class="connect-name">Whoop</div>
          <div class="connect-status ${whoop ? 'status-connected' : 'status-disconnected'}">
            <span class="status-dot"></span>${whoop ? 'Connected' : 'Not connected'}
          </div>
        </div>
        <a href="/auth/whoop/start" class="btn btn-sm ${whoop ? 'btn-secondary' : 'btn-primary'}">
          ${whoop ? 'Reconnect' : 'Connect'}
        </a>
      </div>

      <div class="connect-row">
        <div>
          <div class="connect-name">Strava</div>
          <div class="connect-status ${strava ? 'status-connected' : 'status-disconnected'}">
            <span class="status-dot"></span>${strava ? 'Connected' : 'Not connected'}
          </div>
        </div>
        <a href="/auth/strava/start" class="btn btn-sm ${strava ? 'btn-secondary' : 'btn-primary'}">
          ${strava ? 'Reconnect' : 'Connect'}
        </a>
      </div>
    </div>

    <div class="settings-section">
      <span class="settings-label">Your Goals</span>
      <form id="profile-form">
        <label>Primary Goal</label>
        <input type="text" id="f-goals" placeholder="e.g. Run a marathon under 4 hours by July" value="${escapeHtml(profile.goals || '')}">

        <label>Timeline (weeks)</label>
        <input type="number" id="f-timeline" min="4" max="52" value="${profile.timeline_weeks || 12}">

        <label>Fitness Level</label>
        <select id="f-level">
          <option value="beginner"     ${profile.fitness_level === 'beginner'     ? 'selected' : ''}>Beginner</option>
          <option value="intermediate" ${profile.fitness_level === 'intermediate' ? 'selected' : ''}>Intermediate</option>
          <option value="advanced"     ${profile.fitness_level === 'advanced'     ? 'selected' : ''}>Advanced</option>
        </select>

        <label>Days Available per Week</label>
        <input type="number" id="f-days" min="2" max="7" value="${profile.days_per_week || 5}">

        <label>Preferred Sports (comma separated)</label>
        <input type="text" id="f-sports" placeholder="e.g. running, cycling, strength" value="${escapeHtml((profile.preferred_sports || []).join(', '))}">

        <label>Injuries / Restrictions</label>
        <input type="text" id="f-restrictions" placeholder="e.g. left knee pain" value="${escapeHtml(profile.restrictions || '')}">

        <button type="submit" class="btn btn-primary">Save & Generate Plan</button>
      </form>
    </div>`;

  qs('#profile-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
      goals: qs('#f-goals').value.trim(),
      timeline_weeks: parseInt(qs('#f-timeline').value) || 12,
      fitness_level: qs('#f-level').value,
      days_per_week: parseInt(qs('#f-days').value) || 5,
      preferred_sports: qs('#f-sports').value.split(',').map(s => s.trim()).filter(Boolean),
      restrictions: qs('#f-restrictions').value.trim(),
    };

    if (!body.goals) { showToast('Please enter your goal.'); return; }

    try {
      await fetch('/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      showToast('Profile saved!');
      // Kick off plan generation
      await generatePlan();
    } catch (e) {
      showToast('Error saving profile.');
    }
  });
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', async () => {
  // Tab buttons
  qsa('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Chat send button
  qs('#chat-send').addEventListener('click', sendChat);

  // Chat input — send on Enter (not Shift+Enter), auto-resize
  qs('#chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });

  qs('#chat-input').addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  });

  // Handle OAuth redirect query param
  const params = new URLSearchParams(window.location.search);
  if (params.get('connected')) {
    showToast(`${params.get('connected').charAt(0).toUpperCase() + params.get('connected').slice(1)} connected!`);
    window.history.replaceState({}, '', '/');
  }

  // Initial render
  renderChatHistory();
  await fetchAuthStatus();
  switchTab('today');
});
