/* ── Goggins Fitness Agent — App JS (v2, no OAuth) ──────────────────────── */

// ── State ──────────────────────────────────────────────────────────────────
const state = {
  tab: 'today',
  chatHistory: [],
  todayData: null,
  showLogForm: false,
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

function intensityClass(intensity) {
  return `intensity-${(intensity || 'moderate').toLowerCase()}`;
}

function dotColor(intensity) {
  const map = { rest: '#555', easy: '#44ff88', moderate: '#e8ff00', hard: '#ff8c00', peak: '#ff4444' };
  return map[(intensity || 'moderate').toLowerCase()] || '#555';
}

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function renderMarkdown(text) {
  if (!text) return '';
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^[-•] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>')
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

// ── TODAY SCREEN ───────────────────────────────────────────────────────────
async function loadToday() {
  const screen = qs('#screen-today');
  screen.innerHTML = '<div class="loading">Loading...</div>';
  try {
    const res = await fetch('/today');
    const data = await res.json();
    state.todayData = data;
    renderToday(data);
  } catch (e) {
    screen.innerHTML = `<div class="empty-state"><p>Couldn't load. Check your connection.</p></div>`;
  }
}

function renderToday(data) {
  const workout = data.scheduled_workout || {};
  const hasWorkout = !workout.error;

  const workoutCard = hasWorkout ? `
    <div class="card" id="today-workout-card">
      <div class="card-title">Today's Mission</div>
      <span class="workout-intensity ${intensityClass(workout.intensity)}">${(workout.intensity || 'moderate').toUpperCase()}</span>
      <div class="workout-description">${escapeHtml(workout.description || 'Rest Day')}</div>
      <div class="workout-meta">
        ${workout.target_distance_km ? `${workout.target_distance_km} km · ` : ''}${workout.target_duration_min ? `${workout.target_duration_min} min` : ''}
      </div>
    </div>` : `
    <div class="card">
      <div class="card-title">Today's Mission</div>
      <div class="empty-state" style="padding:12px 0">
        <p>No plan yet. Set your goals in Settings to get started.</p>
        <br>
        <button class="btn btn-primary btn-sm" onclick="switchTab('settings')">Set Goals</button>
      </div>
    </div>`;

  const checkinCard = `
    <div class="card" id="checkin-card">
      <div class="card-title">Pre-Workout Check-In</div>
      <p class="checkin-hint">Enter your Whoop recovery score before you start.</p>
      <div class="checkin-row">
        <div class="checkin-field">
          <label for="recovery-input">Recovery Score</label>
          <input type="number" id="recovery-input" min="0" max="100" placeholder="0–100">
        </div>
      </div>
      <label for="pain-input" style="margin-top:10px">Pain / Notes (optional)</label>
      <input type="text" id="pain-input" placeholder="e.g. left knee sore, feeling tired">
      <button class="btn btn-primary" id="checkin-btn" onclick="submitCheckin()">Check In with Goggins</button>
      <div id="checkin-response" class="checkin-response" style="display:none"></div>
    </div>`;

  const logBtn = `
    <button class="btn btn-secondary" onclick="showLogForm()" style="margin-bottom:4px">
      Log Completed Workout
    </button>`;

  const logFormHTML = `
    <div class="card" id="log-form-card" style="display:none">
      <div class="card-title">Log Workout</div>

      <label>What did you do?</label>
      <textarea id="log-recap" rows="3" placeholder="e.g. Ran 8km easy pace, felt good throughout"></textarea>

      <div id="exercises-list"></div>
      <button class="btn btn-secondary btn-sm" onclick="addExerciseRow()" style="margin-bottom:12px">+ Add Exercise</button>

      <div style="display:flex;gap:10px">
        <div style="flex:1">
          <label>Perceived Effort (1–10)</label>
          <input type="number" id="log-effort" min="1" max="10" placeholder="7">
        </div>
        <div style="flex:1">
          <label>Recovery Score</label>
          <input type="number" id="log-recovery" min="0" max="100" placeholder="65">
        </div>
      </div>

      <label>How did you feel after?</label>
      <input type="text" id="log-post-notes" placeholder="e.g. legs heavy, lungs felt great">

      <button class="btn btn-primary" onclick="submitLog()">Submit to Goggins</button>
      <div id="log-response" class="checkin-response" style="display:none"></div>
    </div>`;

  qs('#screen-today').innerHTML = workoutCard + checkinCard + logBtn + logFormHTML;
}

function showLogForm() {
  const card = qs('#log-form-card');
  if (card) {
    card.style.display = 'block';
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ── Exercise rows ──────────────────────────────────────────────────────────
function addExerciseRow() {
  const list = qs('#exercises-list');
  if (!list) return;
  const idx = list.children.length;
  const row = document.createElement('div');
  row.className = 'exercise-row';
  row.innerHTML = `
    <input type="text"   class="ex-name"   placeholder="Exercise name" style="flex:2">
    <input type="number" class="ex-sets"   placeholder="Sets"   min="1" style="flex:1">
    <input type="number" class="ex-reps"   placeholder="Reps"   min="1" style="flex:1">
    <input type="number" class="ex-weight" placeholder="lbs"    min="0" step="2.5" style="flex:1">
    <button class="btn btn-sm" style="width:36px;padding:0;background:var(--bg3);color:var(--red);border:1px solid var(--border)"
      onclick="this.parentElement.remove()">✕</button>`;
  list.appendChild(row);
}

function collectExercises() {
  const rows = qsa('.exercise-row');
  const exercises = [];
  for (const row of rows) {
    const name = row.querySelector('.ex-name').value.trim();
    if (!name) continue;
    const ex = { name };
    const sets = parseInt(row.querySelector('.ex-sets').value);
    const reps = parseInt(row.querySelector('.ex-reps').value);
    const weight = parseFloat(row.querySelector('.ex-weight').value);
    if (!isNaN(sets)) ex.sets = sets;
    if (!isNaN(reps)) ex.reps = reps;
    if (!isNaN(weight)) ex.weight_lbs = weight;
    exercises.push(ex);
  }
  return exercises;
}

// ── Pre-workout check-in ───────────────────────────────────────────────────
async function submitCheckin() {
  const scoreEl = qs('#recovery-input');
  const notesEl = qs('#pain-input');
  const score = parseInt(scoreEl.value);

  if (isNaN(score) || score < 0 || score > 100) {
    showToast('Enter a valid recovery score (0–100)');
    return;
  }

  const btn = qs('#checkin-btn');
  const responseEl = qs('#checkin-response');
  btn.disabled = true;
  btn.textContent = 'Goggins is reading your data...';
  responseEl.style.display = 'none';
  responseEl.innerHTML = '';

  try {
    const res = await fetch('/checkin', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ recovery_score: score, notes: notesEl.value.trim() }),
    });

    responseEl.style.display = 'block';
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let text = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') break;
        try {
          const j = JSON.parse(payload);
          if (j.text) { text += j.text; responseEl.innerHTML = renderMarkdown(text); }
          if (j.error) responseEl.textContent = `Error: ${j.error}`;
        } catch (_) {}
      }
    }

    // Add to chat history so it's accessible there too
    state.chatHistory.push(
      { role: 'user', content: `Recovery check-in: ${score}/100. Notes: ${notesEl.value || 'None'}` },
      { role: 'assistant', content: text }
    );

  } catch (e) {
    responseEl.style.display = 'block';
    responseEl.textContent = 'Something went wrong. Try again.';
  }

  btn.disabled = false;
  btn.textContent = 'Check In with Goggins';
}

// ── Post-workout log ───────────────────────────────────────────────────────
async function submitLog() {
  const recap = qs('#log-recap')?.value.trim();
  if (!recap) { showToast('Describe what you did first.'); return; }

  const exercises = collectExercises();
  const effort = parseInt(qs('#log-effort')?.value) || null;
  const recovery = parseInt(qs('#log-recovery')?.value) || null;
  const postNotes = qs('#log-post-notes')?.value.trim() || '';

  const responseEl = qs('#log-response');
  responseEl.style.display = 'block';
  responseEl.innerHTML = '<em style="color:var(--text2)">Goggins is reviewing your session...</em>';

  const btn = qs('#log-form-card .btn-primary');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_recap: recap,
        exercises,
        perceived_effort: effort,
        recovery_score: recovery,
        post_notes: postNotes,
      }),
    });
    const data = await res.json();
    responseEl.innerHTML = renderMarkdown(data.feedback || 'Logged.');

    // Add to chat history
    state.chatHistory.push(
      { role: 'user', content: `Post-workout log: ${recap}` },
      { role: 'assistant', content: data.feedback || '' }
    );

    showToast('Workout logged!');
  } catch (e) {
    responseEl.innerHTML = 'Error saving log. Try again.';
  }

  if (btn) btn.disabled = false;
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
          <p>No training plan yet.</p><br>
          <button class="btn btn-primary" onclick="generatePlan()">Generate My Plan</button>
          <br><br><p style="font-size:13px">Set your goals in Settings first.</p>
        </div>`;
      return;
    }
    renderPlan(data);
  } catch (e) {
    screen.innerHTML = `<div class="empty-state"><p>Couldn't load plan.</p></div>`;
  }
}

function renderPlan(data) {
  const today = todayISO();
  const weeks = data.weeks || {};
  let html = `<button class="btn btn-secondary" style="margin-bottom:16px" onclick="generatePlan()">↻ Regenerate Plan</button>`;

  const dayNames = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

  for (const [weekNum, days] of Object.entries(weeks)) {
    html += `<div class="week-header">Week ${weekNum}</div>`;
    for (const day of days) {
      const isToday = day.date === today;
      const dayName = dayNames[(day.day || 1) - 1] || '';
      const dateShort = day.date ? day.date.slice(5) : '';

      html += `
        <div class="plan-day ${day.completed ? 'completed' : ''} ${isToday ? 'today' : ''}">
          <div class="plan-day-date">
            <div class="day-name">${dayName}</div>
            <div>${dateShort}</div>
          </div>
          <div class="plan-day-body">
            <div class="plan-day-desc">${escapeHtml(day.description || 'Rest')}</div>
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
  showToast('Goggins is building your plan...', 6000);
  try {
    const res = await fetch('/plan/generate', { method: 'POST' });
    const data = await res.json();
    if (data.message) {
      showToast('Plan generated!');
      loadPlan();
      state.chatHistory.push({ role: 'assistant', content: data.message });
      renderChatHistory();
    }
  } catch (e) {
    showToast('Error generating plan. Set your profile in Settings first.');
  }
}

// ── CHAT SCREEN ────────────────────────────────────────────────────────────
function renderChatHistory() {
  const container = qs('#chat-messages');
  if (!container) return;

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

async function sendChat() {
  const input = qs('#chat-input');
  const msg = input.value.trim();
  if (!msg) return;

  input.value = '';
  input.style.height = 'auto';

  state.chatHistory.push({ role: 'user', content: msg });
  renderChatHistory();

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
        history: state.chatHistory.slice(0, -1),
      }),
    });

    typingEl.remove();

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let agentMsg = '';

    const agentEl = document.createElement('div');
    agentEl.className = 'msg msg-agent';
    container.appendChild(agentEl);

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value, { stream: true });
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') break;
        try {
          const j = JSON.parse(payload);
          if (j.text) { agentMsg += j.text; agentEl.innerHTML = renderMarkdown(agentMsg); container.scrollTop = container.scrollHeight; }
          if (j.error) agentEl.textContent = `Error: ${j.error}`;
        } catch (_) {}
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
  let profile = {};
  try {
    const res = await fetch('/profile');
    const data = await res.json();
    if (!data.error) profile = data;
  } catch (_) {}

  qs('#screen-settings').innerHTML = `
    <div class="settings-section">
      <span class="settings-label">Your Goals & Profile</span>
      <form id="profile-form">
        <label>Primary Goal</label>
        <input type="text" id="f-goals" placeholder="e.g. Run a marathon under 4 hours by July" value="${escapeHtml(profile.goals || '')}">

        <label>Current Fitness Level</label>
        <textarea id="f-fitness" rows="2" placeholder="e.g. Run 3x/week doing 5km, no strength training, played college soccer">${escapeHtml(profile.current_fitness || '')}</textarea>

        <label>Timeline (weeks)</label>
        <input type="number" id="f-timeline" min="4" max="52" value="${profile.timeline_weeks || 12}">

        <label>Days Available per Week</label>
        <input type="number" id="f-days" min="2" max="7" value="${profile.days_per_week || 5}">

        <label>Preferred Sports (comma separated)</label>
        <input type="text" id="f-sports" placeholder="e.g. running, cycling, strength" value="${escapeHtml((profile.preferred_sports || []).join(', '))}">

        <label>Injuries / Restrictions</label>
        <input type="text" id="f-restrictions" placeholder="e.g. left knee pain, no overhead pressing" value="${escapeHtml(profile.restrictions || '')}">

        <button type="submit" class="btn btn-primary">Save & Generate Plan</button>
      </form>
    </div>`;

  qs('#profile-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const body = {
      goals: qs('#f-goals').value.trim(),
      current_fitness: qs('#f-fitness').value.trim(),
      timeline_weeks: parseInt(qs('#f-timeline').value) || 12,
      days_per_week: parseInt(qs('#f-days').value) || 5,
      preferred_sports: qs('#f-sports').value.split(',').map(s => s.trim()).filter(Boolean),
      restrictions: qs('#f-restrictions').value.trim(),
    };

    if (!body.goals) { showToast('Enter your goal first.'); return; }
    if (!body.current_fitness) { showToast('Describe your current fitness level.'); return; }

    try {
      await fetch('/profile', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      showToast('Saved! Building your plan...');
      await generatePlan();
    } catch (e) {
      showToast('Error saving profile.');
    }
  });
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  qsa('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  qs('#chat-send').addEventListener('click', sendChat);

  qs('#chat-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });

  qs('#chat-input').addEventListener('input', function () {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 120) + 'px';
  });

  renderChatHistory();
  switchTab('today');
});
