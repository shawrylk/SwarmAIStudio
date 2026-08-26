/**
 * Swarm AI Studio Frontend Controller
 * Multi-Chat, Full GitHub Desktop, Stash Local Changes, Worktree Manager, Autonomous Loop Agent,
 * Cost-Based Optimizer (CBO) & SQL Explain DAG, and Auto-Dismissing Toast Notification System.
 */

let isServerConnected = true;
let consecutiveFailures = 0;
let activeSessionId = "";
let promptHistory = [];
let historyIndex = -1;
let tempDraft = "";
let currentRepoPath = "";
let currentGhdState = null;
let selectedGhdFile = "";
let selectedGhdCommit = "";
let checkedFiles = new Set();
let allBranches = [];
let pollInterval = null;
let loopPollInterval = null;
let debugPollInterval = null;
let currentModalContent = "";
let currentModalFilename = "";
let pendingBranchSwitch = null;

// ─────────────────────────────────────────────────────────────
// TOAST NOTIFICATION SYSTEM (AUTO-DISMISS, NON-INTRUSIVE)
// ─────────────────────────────────────────────────────────────
function showToast(message, type = 'info', duration = 3400) {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast-item ${type}`;

  const iconMap = {
    success: '✓',
    error: '⚠️',
    warn: '⚡',
    info: 'ℹ️'
  };
  const icon = iconMap[type] || 'ℹ️';

  toast.innerHTML = `
    <span class="toast-icon">${icon}</span>
    <div class="toast-msg">${escapeHtml(message)}</div>
    <button class="toast-close" onclick="event.stopPropagation(); dismissToast(this.parentElement)">✕</button>
    <div class="toast-progress" style="animation-duration: ${duration}ms;"></div>
  `;

  toast.onclick = () => dismissToast(toast);
  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  const timer = setTimeout(() => {
    dismissToast(toast);
  }, duration);

  toast._dismissTimer = timer;
}

function dismissToast(toast) {
  if (!toast || toast._isDismissing) return;
  toast._isDismissing = true;
  if (toast._dismissTimer) clearTimeout(toast._dismissTimer);
  
  toast.classList.remove('show');
  toast.classList.add('hide');

  setTimeout(() => {
    if (toast.parentElement) toast.parentElement.removeChild(toast);
  }, 260);
}

// ─────────────────────────────────────────────────────────────
// SERVER DISCONNECTION & RECOVERY HANDLING
// ─────────────────────────────────────────────────────────────
function handleServerDisconnected() {
  consecutiveFailures++;
  isServerConnected = false;

  const banner = document.getElementById('serverOfflineBanner');
  if (banner) banner.style.display = 'flex';

  const dot = document.getElementById('serverStatusDot');
  if (dot) dot.className = 'dot offline';

  const vramEl = document.getElementById('vramVal');
  if (vramEl) vramEl.innerText = 'VRAM: Offline';

  const gpuEl = document.getElementById('gpuVal');
  if (gpuEl) gpuEl.innerText = 'GPU: Offline';

  const ramEl = document.getElementById('ramVal');
  if (ramEl) ramEl.innerText = 'RAM: Offline';

  const modelEl = document.getElementById('modelVal');
  if (modelEl) {
    modelEl.innerText = '⚠️ SERVER KILLED / DISCONNECTED';
    modelEl.style.color = 'var(--rose)';
  }

  ['gemini', 'lfm', 'qwen'].forEach(id => {
    updateStaticNodeView(id, 'offline', 'Backend server killed or unreachable');
  });

  const countBadge = document.getElementById('agentCountBadge');
  if (countBadge) {
    countBadge.innerText = '🔴 Server Offline (Reconnecting...)';
    countBadge.style.borderColor = 'var(--rose)';
    countBadge.style.color = 'var(--rose)';
  }

  const loopBadge = document.getElementById('loopStatusBadge');
  if (loopBadge && loopBadge.innerText !== 'COMPLETED') {
    loopBadge.innerText = 'OFFLINE';
    loopBadge.className = 'status-badge badge-offline';
  }
}

function handleServerConnected() {
  if (!isServerConnected) {
    isServerConnected = true;
    consecutiveFailures = 0;

    const banner = document.getElementById('serverOfflineBanner');
    if (banner) banner.style.display = 'none';

    const dot = document.getElementById('serverStatusDot');
    if (dot) dot.className = 'dot';

    showToast("✓ Connected back to Swarm backend!", "success", 2500);
  }
}

function switchTab(tabId) {
  document.getElementById('tabChatBtn').className = (tabId === 'chat') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabLoopBtn').className = (tabId === 'loop') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabGitBtn').className = (tabId === 'git') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabTopoBtn').className = (tabId === 'topo') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabVaultBtn').className = (tabId === 'vault') ? 'tab-btn active' : 'tab-btn';
  
  document.getElementById('tabChat').className = (tabId === 'chat') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabLoop').className = (tabId === 'loop') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabGit').className = (tabId === 'git') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabTopo').className = (tabId === 'topo') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabVault').className = (tabId === 'vault') ? 'tab-content active' : 'tab-content';

  const sidebar = document.getElementById('chatSidebar');
  sidebar.style.display = (tabId === 'chat') ? 'flex' : 'none';

  if (tabId === 'git') loadGitHubDesktopState();
  if (tabId === 'vault') loadArtifactsVault();
  if (tabId === 'loop') {
    pollLoopState();
    if (!loopPollInterval) loopPollInterval = setInterval(pollLoopState, 1200);
  } else {
    if (loopPollInterval) { clearInterval(loopPollInterval); loopPollInterval = null; }
  }
}

function parseMarkdown(md) {
  if (!md) return '';
  let html = md;
  html = html.replace(/```([a-zA-Z0-9_]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre><code class="language-${lang}">${escapeHtml(code)}</code></pre>`;
  });
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  html = html.replace(/\*([^*]+)\*/g, '<i>$1</i>');
  html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>');
  html = html.replace(/(<li>[\s\S]*?<\/li>)/gim, '<ul>$1</ul>');
  html = html.replace(/\n\n/g, '<br><br>');
  return html;
}

// ─────────────────────────────────────────────────────────────
// AUTONOMOUS LOOP AGENT CONTROLLER (AUTO-DEV SWARM)
// ─────────────────────────────────────────────────────────────
async function startAutonomousLoop() {
  const goal = document.getElementById('loopGoalInput').value.trim();
  if (!goal) {
    showToast("Please enter a goal or feature description.", "warn");
    return;
  }

  try {
    const res = await fetch('/api/loop/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal: goal, repo_path: currentRepoPath })
    });
    const data = await res.json();
    if (data.success) {
      showToast("🚀 Autonomous Swarm Loop started!", "success");
      pollLoopState();
    } else {
      showToast("Loop Error: " + data.error, "error", 4500);
    }
  } catch(e) {
    handleServerDisconnected();
    showToast("Error: " + e.message, "error");
  }
}

async function pauseAutonomousLoop() {
  try {
    await fetch('/api/loop/pause', { method: 'POST' });
    showToast("⏸️ Swarm loop paused", "info");
    pollLoopState();
  } catch(e) { handleServerDisconnected(); }
}

async function resumeAutonomousLoop() {
  try {
    await fetch('/api/loop/resume', { method: 'POST' });
    showToast("▶️ Swarm loop resumed", "info");
    pollLoopState();
  } catch(e) { handleServerDisconnected(); }
}

async function stopAutonomousLoop() {
  try {
    await fetch('/api/loop/stop', { method: 'POST' });
    showToast("⏹️ Swarm loop stopped", "warn");
    pollLoopState();
  } catch(e) { handleServerDisconnected(); }
}

async function pollLoopState() {
  try {
    const controller = new AbortController();
    const tId = setTimeout(() => controller.abort(), 2000);
    const res = await fetch('/api/loop/status', { cache: 'no-store', signal: controller.signal });
    clearTimeout(tId);

    if (!res.ok) {
      handleServerDisconnected();
      return;
    }
    const state = await res.json();
    handleServerConnected();
    renderLoopDashboard(state);
  } catch(e) {
    handleServerDisconnected();
  }
}

function renderLoopDashboard(state) {
  const statusBadge = document.getElementById('loopStatusBadge');
  const startBtn = document.getElementById('loopStartBtn');
  const pauseBtn = document.getElementById('loopPauseBtn');
  const stopBtn = document.getElementById('loopStopBtn');

  if (statusBadge) {
    const s = (state.status || 'idle').toUpperCase();
    statusBadge.innerText = s;
    statusBadge.className = `status-badge ${s === 'RUNNING' ? 'badge-running' : (s === 'COMPLETED' ? 'badge-online' : 'badge-idle')}`;
  }

  if (startBtn && pauseBtn && stopBtn) {
    if (state.status === 'running') {
      startBtn.style.display = 'none';
      pauseBtn.style.display = 'inline-flex';
      pauseBtn.innerText = '⏸️ Pause';
      stopBtn.style.display = 'inline-flex';
    } else if (state.status === 'paused') {
      startBtn.style.display = 'none';
      pauseBtn.style.display = 'inline-flex';
      pauseBtn.innerText = '▶️ Resume';
      stopBtn.style.display = 'inline-flex';
    } else {
      startBtn.style.display = 'inline-flex';
      pauseBtn.style.display = 'none';
      stopBtn.style.display = 'none';
    }
  }

  // Render Active Sub-Agent
  const activeBox = document.getElementById('loopActiveAgentBox');
  if (activeBox) {
    if (state.active_subagent) {
      const sa = state.active_subagent;
      activeBox.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:800; color:#ffffff; font-size:13.5px;">⚡ Active: ${escapeHtml(sa.name)}</span>
          <span class="file-status-badge status-a">${escapeHtml(sa.slot)}</span>
        </div>
        <div style="font-size:12px; color:var(--accent); font-family:monospace; margin-top:2px;">
          Working on: <b>${escapeHtml(sa.task_title)}</b>
        </div>
      `;
      activeBox.style.display = 'block';
    } else {
      activeBox.style.display = 'none';
    }
  }

  // Render Task Pipeline Kanban
  const taskContainer = document.getElementById('loopTaskGrid');
  if (taskContainer) {
    const tasks = state.tasks || [];
    if (tasks.length === 0) {
      taskContainer.innerHTML = '<div style="color:var(--text-muted); padding:16px; text-align:center; grid-column:1/-1;">No tasks scheduled yet. Start a goal to decompose into PM, Dev, QA, and Review stages.</div>';
    } else {
      taskContainer.innerHTML = '';
      tasks.forEach((t) => {
        const card = document.createElement('div');
        const isCurrent = (t.id === state.current_task_id && state.status === 'running');
        card.className = `task-pipeline-card ${isCurrent ? 'in-progress' : (t.status === 'completed' ? 'completed' : '')}`;
        
        const roleColors = {
          pm: 'status-u',
          dev: 'status-m',
          qa: 'status-a',
          review: 'status-d'
        };
        const badgeClass = roleColors[t.role] || 'status-u';

        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span class="file-status-badge ${badgeClass}">${escapeHtml(t.role.toUpperCase())}</span>
            <span style="font-size:11px; font-family:monospace; font-weight:800; color:${t.status === 'completed' ? 'var(--green)' : (isCurrent ? 'var(--accent)' : 'var(--text-muted)')};">
              ${isCurrent ? '⚡ IN PROGRESS' : escapeHtml(t.status.toUpperCase())}
            </span>
          </div>
          <div style="font-weight:700; color:#ffffff; font-size:13px; line-height:1.4;">${escapeHtml(t.title)}</div>
          <div style="font-size:11.5px; color:#cbd5e1;">${escapeHtml(t.description || '')}</div>
          <div style="font-family:monospace; font-size:11px; color:#93c5fd; background:#070a12; padding:4px 8px; border-radius:4px; border:1px solid #1e293b;">
            🤖 Assigned: ${escapeHtml(t.assigned_agent)}
          </div>
        `;
        taskContainer.appendChild(card);
      });
    }
  }

  // Render Advisor Pings & Consultations Feed
  const pingContainer = document.getElementById('loopAdvisorPingsContainer');
  if (pingContainer) {
    const pings = state.advisor_pings || [];
    if (pings.length === 0) {
      pingContainer.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:10px;">Sub-agents will automatically ping the Lead Advisor whenever they need architectural guidance or unblocking.</div>';
    } else {
      pingContainer.innerHTML = '';
      pings.forEach(p => {
        const div = document.createElement('div');
        div.className = 'advisor-ping-card';
        div.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:11.5px; font-weight:800; color:#c084fc;">📡 ${escapeHtml(p.subagent)} ➔ 👑 Lead Advisor</span>
            <span style="font-size:10.5px; font-family:monospace; color:var(--text-muted);">${escapeHtml(p.timestamp)} (${p.duration}s)</span>
          </div>
          <div class="advisor-ping-q">❓ "${escapeHtml(p.question)}"</div>
          <div class="advisor-ping-a markdown-body">${parseMarkdown(p.answer)}</div>
        `;
        pingContainer.appendChild(div);
      });
    }
  }

  // Render Final Summary Artifact if complete
  const finalSummaryDiv = document.getElementById('loopFinalSummaryContainer');
  if (finalSummaryDiv) {
    if (state.final_summary && state.status === 'completed') {
      finalSummaryDiv.style.display = 'block';
      document.getElementById('loopFinalSummaryContent').innerHTML = parseMarkdown(state.final_summary);
    } else {
      finalSummaryDiv.style.display = 'none';
    }
  }
}

function setLoopGoalPrompt(text) {
  document.getElementById('loopGoalInput').value = text;
}

// ─────────────────────────────────────────────────────────────
// FULL GITHUB DESKTOP CLIENT LOGIC
// ─────────────────────────────────────────────────────────────
async function loadGitHubDesktopState() {
  try {
    const controller = new AbortController();
    const tId = setTimeout(() => controller.abort(), 2000);
    const res = await fetch(`/api/git/overview?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store', signal: controller.signal });
    clearTimeout(tId);
    
    if (!res.ok) {
      handleServerDisconnected();
      return;
    }

    const data = await res.json();
    handleServerConnected();
    currentGhdState = data;

    if (!data.active) {
      document.getElementById('ghdRepoName').innerText = "(No Git Repo)";
      return;
    }

    document.getElementById('ghdRepoName').innerText = data.repo_name;
    document.getElementById('ghdCurrentBranch').innerText = data.branch;
    document.getElementById('commitTargetBranch').innerText = data.branch;
    
    document.getElementById('ghdAheadCount').innerText = data.ahead || 0;
    document.getElementById('ghdBehindCount').innerText = data.behind || 0;
    document.getElementById('ghdChangesCount').innerText = data.changed_files ? data.changed_files.length : 0;

    const stashes = data.stashes || [];
    const stashBtn = document.getElementById('ghdStashNavBtn');
    if (stashBtn) {
      stashBtn.innerText = `📦 Stashes (${stashes.length})`;
    }

    renderStashBanner(stashes);

    allBranches = data.branches || [];
    renderBranchModalList(allBranches, data.branch);

    renderChangesList(data.changed_files || []);
    renderHistoryList(data.history || []);

  } catch(e) {
    handleServerDisconnected();
  }
}

function renderStashBanner(stashes) {
  const banner = document.getElementById('ghdStashBanner');
  if (!banner) return;

  if (!stashes || stashes.length === 0) {
    banner.style.display = 'none';
    return;
  }

  const latest = stashes[0];
  banner.style.display = 'flex';
  banner.innerHTML = `
    <div class="stash-banner-title">
      <span>📦 Stashed changes on <b>${escapeHtml(latest.branch)}</b></span>
      <span style="font-size:11px; color:var(--text-muted);">${escapeHtml(latest.date || '')}</span>
    </div>
    <div style="font-family:monospace; font-size:11.5px; color:#cbd5e1; text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">
      ${escapeHtml(latest.message)}
    </div>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:4px;">
      <button class="action-btn" onclick="popStash(0)" style="background:#1d4ed8; color:#ffffff; border:none; padding:3px 10px; font-size:11.5px;">
        ↩️ Restore
      </button>
      <button class="action-btn danger" onclick="dropStash(0)" style="padding:3px 8px; font-size:11.5px;">
        🗑️ Discard
      </button>
      <button class="action-btn" onclick="openStashesModal()" style="padding:3px 8px; font-size:11.5px;">
        View All (${stashes.length})
      </button>
    </div>
  `;
}

function renderChangesList(files) {
  const container = document.getElementById('ghdChangesList');
  container.innerHTML = '';
  
  if (files.length === 0) {
    container.innerHTML = '<div style="color:var(--green); text-align:center; padding:30px; font-weight:700;">✓ No local changes<br><span style="font-size:12px; color:var(--text-muted); font-weight:400;">Working tree is completely clean.</span></div>';
    document.getElementById('ghdDiffTitle').innerText = "Working tree clean";
    document.getElementById('ghdDiffContent').innerHTML = '<div style="color:var(--text-muted); padding:20px;">No uncommitted changes in working directory.</div>';
    document.getElementById('ghdDiscardFileBtn').style.display = 'none';
    updateCommitBtnState();
    return;
  }

  checkedFiles.clear();
  files.forEach(f => checkedFiles.add(f.path));
  updateSelectedCount();

  files.forEach((f) => {
    const row = document.createElement('div');
    row.className = `ghd-file-row ${f.path === selectedGhdFile ? 'selected' : ''}`;
    row.onclick = () => selectFileForDiff(f.path, f.staged);

    const statusClass = `status-${f.status.toLowerCase()}`;
    row.innerHTML = `
      <div style="display:flex; align-items:center; gap:8px; overflow:hidden;">
        <input type="checkbox" ${checkedFiles.has(f.path) ? 'checked' : ''} onclick="event.stopPropagation(); toggleFileCheck('${escapeJs(f.path)}', this.checked)">
        <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${escapeHtml(f.path)}</span>
      </div>
      <span class="file-status-badge ${statusClass}">${escapeHtml(f.status)}</span>
    `;
    container.appendChild(row);
  });

  if (!selectedGhdFile || !files.find(f => f.path === selectedGhdFile)) {
    selectFileForDiff(files[0].path, files[0].staged);
  }
}

function toggleFileCheck(path, isChecked) {
  if (isChecked) checkedFiles.add(path);
  else checkedFiles.delete(path);
  updateSelectedCount();
}

function toggleSelectAllFiles(isChecked) {
  if (!currentGhdState || !currentGhdState.changed_files) return;
  checkedFiles.clear();
  if (isChecked) {
    currentGhdState.changed_files.forEach(f => checkedFiles.add(f.path));
  }
  const checkboxes = document.querySelectorAll('#ghdChangesList input[type="checkbox"]');
  checkboxes.forEach(cb => cb.checked = isChecked);
  updateSelectedCount();
}

function updateSelectedCount() {
  const el = document.getElementById('ghdSelectedCount');
  if (el) el.innerText = `${checkedFiles.size} files selected`;
  updateCommitBtnState();
}

function updateCommitBtnState() {
  const summary = document.getElementById('commitSummaryInput').value.trim();
  const btn = document.getElementById('commitActionBtn');
  btn.disabled = (checkedFiles.size === 0 || !summary);
}

async function selectFileForDiff(filePath, isStaged) {
  selectedGhdFile = filePath;
  
  const rows = document.querySelectorAll('.ghd-file-row');
  rows.forEach(r => {
    if (r.innerText.includes(filePath)) r.className = 'ghd-file-row selected';
    else r.className = 'ghd-file-row';
  });

  document.getElementById('ghdDiffTitle').innerText = `📄 ${filePath}`;
  const discardBtn = document.getElementById('ghdDiscardFileBtn');
  discardBtn.style.display = 'inline-block';
  discardBtn.innerText = `🗑️ Discard Changes`;

  try {
    const res = await fetch(`/api/git/diff?repo_path=${encodeURIComponent(currentRepoPath)}&file=${encodeURIComponent(filePath)}&staged=${isStaged ? 'true' : 'false'}`);
    const data = await res.json();
    renderColoredDiff(data.diff || "No diff available.");
  } catch(e) { handleServerDisconnected(); }
}

function renderColoredDiff(rawDiff) {
  const container = document.getElementById('ghdDiffContent');
  container.innerHTML = '';
  
  const lines = rawDiff.split("\n");
  lines.forEach(line => {
    const div = document.createElement('div');
    div.className = 'diff-line';
    
    if (line.startsWith('@@')) {
      div.className += ' chunk-header';
    } else if (line.startsWith('+') && !line.startsWith('+++')) {
      div.className += ' added';
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      div.className += ' deleted';
    } else {
      div.className += ' neutral';
    }
    
    div.innerText = line;
    container.appendChild(div);
  });
}

async function discardSelectedFile() {
  if (!selectedGhdFile) return;
  try {
    const res = await fetch('/api/git/discard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, file: selectedGhdFile })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Discarded changes to ${selectedGhdFile}`, "info");
      selectedGhdFile = "";
      await loadGitHubDesktopState();
    } else {
      showToast("Discard error: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function ghdCommit() {
  const summary = document.getElementById('commitSummaryInput').value.trim();
  const desc = document.getElementById('commitDescInput').value.trim();
  if (!summary) return;

  const fullMessage = desc ? `${summary}\n\n${desc}` : summary;
  const fileList = Array.from(checkedFiles);

  try {
    const res = await fetch('/api/git/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, message: fullMessage, files: fileList })
    });
    const data = await res.json();
    if (data.success) {
      showToast("✓ Committed changes successfully!", "success");
      document.getElementById('commitSummaryInput').value = '';
      document.getElementById('commitDescInput').value = '';
      selectedGhdFile = "";
      await loadGitHubDesktopState();
    } else {
      showToast("Commit error: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function ghdPush() {
  try {
    const btn = document.getElementById('ghdPushBtn');
    btn.innerText = "Pushing...";
    const res = await fetch('/api/git/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath })
    });
    const data = await res.json();
    await loadGitHubDesktopState();
    btn.innerText = `⬆️ Push ${currentGhdState ? currentGhdState.ahead : 0}`;
    if (data.success) showToast("✓ Pushed to remote repository!", "success");
    else showToast("Push failed: " + (data.stderr || data.stdout || data.error), "error", 4500);
  } catch(e) { showToast("Push error: " + e.message, "error"); }
}

async function ghdPull() {
  try {
    const res = await fetch('/api/git/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath })
    });
    const data = await res.json();
    await loadGitHubDesktopState();
    if (data.success) showToast("✓ Pull complete: " + (data.stdout || "Already up to date."), "success");
    else showToast("Pull failed: " + (data.stderr || data.error), "error", 4500);
  } catch(e) { showToast("Pull error: " + e.message, "error"); }
}

async function ghdFetch() {
  try {
    const res = await fetch('/api/git/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath })
    });
    await loadGitHubDesktopState();
    showToast("✓ Remote repository fetched successfully!", "success");
  } catch(e) { showToast("Fetch error: " + e.message, "error"); }
}

function renderHistoryList(commits) {
  const container = document.getElementById('ghdHistoryList');
  container.innerHTML = '';

  if (commits.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:20px;">No commits found.</div>';
    return;
  }

  commits.forEach(c => {
    const div = document.createElement('div');
    div.className = `ghd-commit-item ${c.hash === selectedGhdCommit ? 'selected' : ''}`;
    div.onclick = () => selectCommitForInspection(c);
    div.innerHTML = `
      <div class="ghd-commit-msg">${escapeHtml(c.subject)}</div>
      <div class="ghd-commit-meta">
        <span>👤 ${escapeHtml(c.author)}</span>
        <span>🕒 ${escapeHtml(c.date)}</span>
        <span style="color:var(--accent);">${escapeHtml(c.short_hash)}</span>
      </div>
    `;
    container.appendChild(div);
  });
}

async function selectCommitForInspection(commit) {
  selectedGhdCommit = commit.hash;
  
  const items = document.querySelectorAll('.ghd-commit-item');
  items.forEach(i => {
    if (i.innerHTML.includes(commit.short_hash)) i.className = 'ghd-commit-item selected';
    else i.className = 'ghd-commit-item';
  });

  document.getElementById('ghdDiffTitle').innerText = `📜 Commit: ${commit.subject} (${commit.short_hash})`;
  document.getElementById('ghdDiscardFileBtn').style.display = 'none';

  try {
    const res = await fetch(`/api/git/commit_detail?repo_path=${encodeURIComponent(currentRepoPath)}&hash=${encodeURIComponent(commit.hash)}`);
    const data = await res.json();
    renderColoredDiff(data.diff || "No diff recorded for this commit.");
  } catch(e) {}
}

function switchGhdTab(tab) {
  document.getElementById('ghdTabChangesBtn').className = (tab === 'changes') ? 'ghd-nav-tab active' : 'ghd-nav-tab';
  document.getElementById('ghdTabHistoryBtn').className = (tab === 'history') ? 'ghd-nav-tab active' : 'ghd-nav-tab';

  document.getElementById('ghdChangesTab').style.display = (tab === 'changes') ? 'flex' : 'none';
  document.getElementById('ghdHistoryTab').style.display = (tab === 'history') ? 'flex' : 'none';
}

function toggleBranchModal() {
  const m = document.getElementById('branchModal');
  m.className = (m.className.includes('active')) ? 'branch-modal' : 'branch-modal active';
}

document.addEventListener('click', (e) => {
  const m = document.getElementById('branchModal');
  const btn = document.getElementById('ghdBranchBtn');
  if (m && btn && !m.contains(e.target) && !btn.contains(e.target)) {
    m.className = 'branch-modal';
  }
});

function renderBranchModalList(branches, currentBranch) {
  const scroll = document.getElementById('branchListScroll');
  scroll.innerHTML = '';
  
  branches.forEach(b => {
    const bName = typeof b === 'string' ? b : b.name;
    const isCurrent = (bName === currentBranch);
    const row = document.createElement('div');
    row.className = `branch-item-row ${isCurrent ? 'current' : ''}`;
    row.onclick = () => ghdCheckoutBranch(bName, false);
    row.innerHTML = `<span>🌿 ${escapeHtml(bName)}</span> ${isCurrent ? '<span style="color:var(--green); font-weight:800;">✓ Current</span>' : ''}`;
    scroll.appendChild(row);
  });
}

function filterBranches(val) {
  const query = val.toLowerCase();
  const filtered = allBranches.filter(b => {
    const name = typeof b === 'string' ? b : b.name;
    return name.toLowerCase().includes(query);
  });
  renderBranchModalList(filtered, currentGhdState ? currentGhdState.branch : "");
}

// ─────────────────────────────────────────────────────────────
// BRANCH SWITCHING & STASH INTERACTION (GITHUB DESKTOP STYLE)
// ─────────────────────────────────────────────────────────────
async function ghdCheckoutBranch(branchName, create) {
  document.getElementById('branchModal').className = 'branch-modal';

  const cleanName = branchName.trim().replace(/^origin\//, '').replace(/^remotes\/origin\//, '');
  if (currentGhdState && currentGhdState.branch === cleanName && !create) {
    return;
  }

  // If local uncommitted changes exist, open the Stash & Switch dialog
  if (currentGhdState && currentGhdState.changed_files && currentGhdState.changed_files.length > 0) {
    pendingBranchSwitch = { branch: cleanName, create: create };
    openBranchSwitchPrompt(cleanName, currentGhdState.changed_files.length);
    return;
  }

  await executeDirectBranchCheckout(cleanName, create);
}

function openBranchSwitchPrompt(targetBranch, changeCount) {
  document.getElementById('switchTargetBranchName').innerText = targetBranch;
  document.getElementById('switchChangeCount').innerText = changeCount;
  document.getElementById('branchSwitchModal').className = 'modal-overlay active';
}

function closeBranchSwitchModal() {
  document.getElementById('branchSwitchModal').className = 'modal-overlay';
  pendingBranchSwitch = null;
}

async function confirmStashAndSwitch() {
  if (!pendingBranchSwitch) return;
  const { branch, create } = pendingBranchSwitch;
  closeBranchSwitchModal();

  try {
    const res = await fetch('/api/git/stash_and_switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, branch: branch, create: create })
    });
    const data = await res.json();
    await loadGitHubDesktopState();
    if (data.success) {
      showToast(`✓ Changes stashed! Switched to '${branch}'`, "success");
    } else {
      showToast("Stash & Switch failed: " + (data.error || data.stderr), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function confirmBringChanges() {
  if (!pendingBranchSwitch) return;
  const { branch, create } = pendingBranchSwitch;
  closeBranchSwitchModal();
  await executeDirectBranchCheckout(branch, create);
}

async function executeDirectBranchCheckout(branchName, create) {
  try {
    const res = await fetch('/api/git/branch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, branch: branchName, create: create })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Switched to branch '${branchName}'`, "success");
      await loadGitHubDesktopState();
    } else {
      showToast("Branch switch failed: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function createAndCheckoutBranch() {
  const input = document.getElementById('branchSearchInput').value.trim();
  if (!input) {
    showToast("Type a branch name in the search box first.", "warn");
    return;
  }
  await ghdCheckoutBranch(input, true);
}

// ─────────────────────────────────────────────────────────────
// STASH MANAGEMENT (SAVE, POP, DROP, VIEW ALL)
// ─────────────────────────────────────────────────────────────
async function quickStash() {
  const msg = prompt("Enter stash message (or leave blank for automatic timestamped message):");
  if (msg === null) return;

  try {
    const res = await fetch('/api/git/stash/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, message: msg })
    });
    const data = await res.json();
    if (data.success) {
      await loadGitHubDesktopState();
      showToast("✓ Local changes stashed! Working tree is clean.", "success");
    } else {
      showToast("Stash error: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function popStash(index = 0) {
  try {
    const res = await fetch('/api/git/stash/pop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, index: index })
    });
    const data = await res.json();
    if (data.success) {
      await loadGitHubDesktopState();
      showToast("✓ Stash restored onto current branch!", "success");
    } else {
      showToast("Error restoring stash: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function dropStash(index = 0) {
  try {
    const res = await fetch('/api/git/stash/drop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, index: index })
    });
    const data = await res.json();
    if (data.success) {
      showToast("✓ Stash discarded", "info");
      await loadGitHubDesktopState();
      if (document.getElementById('stashModal').className.includes('active')) {
        await loadStashesList();
      }
    } else {
      showToast("Error discarding stash: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function openStashesModal() {
  document.getElementById('stashModal').className = 'modal-overlay active';
  await loadStashesList();
}

function closeStashesModal() {
  document.getElementById('stashModal').className = 'modal-overlay';
}

async function loadStashesList() {
  const container = document.getElementById('stashesTableBody');
  container.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:16px; color:var(--text-muted);">Loading stashes...</td></tr>';
  
  try {
    const res = await fetch(`/api/git/stashes?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const data = await res.json();
    const stashes = data.stashes || [];

    container.innerHTML = '';
    if (stashes.length === 0) {
      container.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:16px; color:var(--text-muted);">No saved stashes found.</td></tr>';
      return;
    }

    stashes.forEach(s => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="padding:10px 14px; font-family:monospace; color:#ffffff; font-weight:700;">
          📦 ${escapeHtml(s.ref)}
        </td>
        <td style="padding:10px 14px; font-family:monospace; color:var(--accent);">🌿 ${escapeHtml(s.branch)}</td>
        <td style="padding:10px 14px; font-family:monospace; color:#cbd5e1; font-size:12px;">
          ${escapeHtml(s.message)}<br><span style="color:var(--text-muted); font-size:11px;">🕒 ${escapeHtml(s.date)}</span>
        </td>
        <td style="padding:10px 14px; text-align:right;">
          <div style="display:inline-flex; gap:6px;">
            <button class="action-btn" onclick="popStash(${s.index}); closeStashesModal();" style="background:#1d4ed8; color:#ffffff; border:none;">
              ↩️ Restore
            </button>
            <button class="action-btn danger" onclick="dropStash(${s.index})">
              🗑️ Discard
            </button>
          </div>
        </td>
      `;
      container.appendChild(tr);
    });

  } catch(e) {
    container.innerHTML = `<tr><td colspan="4" style="color:var(--rose); padding:16px;">Error loading stashes: ${escapeHtml(e.message)}</td></tr>`;
  }
}

// ─────────────────────────────────────────────────────────────
// WORKTREE MANAGER (LIST, CREATE, REMOVE LIKE GITHUB DESKTOP)
// ─────────────────────────────────────────────────────────────
async function openWorktreeModal() {
  document.getElementById('worktreeModal').className = 'modal-overlay active';
  await loadWorktreesList();
}

function closeWorktreeModal() {
  document.getElementById('worktreeModal').className = 'modal-overlay';
}

async function loadWorktreesList() {
  const container = document.getElementById('worktreesTableBody');
  container.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:16px; color:var(--text-muted);">Loading active worktrees...</td></tr>';
  
  try {
    const res = await fetch(`/api/git/worktrees?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const data = await res.json();
    const wts = data.worktrees || [];

    container.innerHTML = '';
    if (wts.length === 0) {
      container.innerHTML = '<tr><td colspan="4" style="text-align:center; padding:16px; color:var(--text-muted);">No isolated worktrees found.</td></tr>';
      return;
    }

    wts.forEach(wt => {
      const tr = document.createElement('tr');
      const isMain = wt.is_main;
      tr.innerHTML = `
        <td style="padding:10px 14px; font-family:monospace; color:#ffffff; font-weight:700;">
          ${isMain ? '👑 Main Repository' : '🌳 ' + escapeHtml(wt.display_path || wt.path)}
          ${isMain ? '<span class="file-status-badge status-a" style="margin-left:6px;">MAIN</span>' : ''}
        </td>
        <td style="padding:10px 14px; font-family:monospace; color:var(--accent);">🌿 ${escapeHtml(wt.branch || 'detached')}</td>
        <td style="padding:10px 14px; font-family:monospace; color:var(--text-muted); font-size:12px;">${escapeHtml(wt.commit || '')}</td>
        <td style="padding:10px 14px; text-align:right;">
          ${isMain ? '<span style="color:var(--text-muted); font-size:11px;">Primary</span>' : `
            <button class="action-btn danger" onclick="removeWorktreeAction('${escapeJs(wt.path)}')">🗑️ Remove</button>
          `}
        </td>
      `;
      container.appendChild(tr);
    });

    const branchSel = document.getElementById('wtBranchSelect');
    if (branchSel) {
      branchSel.innerHTML = '<option value="">Current HEAD</option>';
      allBranches.forEach(b => {
        const bName = typeof b === 'string' ? b : b.name;
        const opt = document.createElement('option');
        opt.value = bName;
        opt.innerText = `🌿 ${bName}`;
        branchSel.appendChild(opt);
      });
    }

  } catch(e) {
    container.innerHTML = `<tr><td colspan="4" style="color:var(--rose); padding:16px;">Error loading worktrees: ${escapeHtml(e.message)}</td></tr>`;
  }
}

async function addWorktreeFromModal() {
  const dirPath = document.getElementById('wtPathInput').value.trim();
  const branchName = document.getElementById('wtBranchSelect').value;
  const newBranchName = document.getElementById('wtNewBranchInput').value.trim();
  const isNewBranch = Boolean(newBranchName);

  if (!dirPath) {
    showToast("Specify a directory path for the worktree.", "warn");
    return;
  }

  const targetBranch = isNewBranch ? newBranchName : branchName;

  try {
    const res = await fetch('/api/git/worktree/add', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_path: currentRepoPath,
        path: dirPath,
        branch: targetBranch,
        new_branch: isNewBranch
      })
    });
    const data = await res.json();
    if (data.success) {
      document.getElementById('wtPathInput').value = '';
      document.getElementById('wtNewBranchInput').value = '';
      await loadWorktreesList();
      await loadGitHubDesktopState();
      showToast("✓ Worktree created successfully!", "success");
    } else {
      showToast("Worktree creation failed: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function removeWorktreeAction(wtPath) {
  try {
    const res = await fetch('/api/git/worktree/remove', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, path: wtPath, force: false })
    });
    const data = await res.json();
    if (data.success) {
      showToast("✓ Worktree removed", "info");
      await loadWorktreesList();
      await loadGitHubDesktopState();
    } else {
      const resForce = await fetch('/api/git/worktree/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: currentRepoPath, path: wtPath, force: true })
      });
      await loadWorktreesList();
      await loadGitHubDesktopState();
      showToast("✓ Force removed worktree", "info");
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

// ─────────────────────────────────────────────────────────────
// Multi-Chat Session Logic
// ─────────────────────────────────────────────────────────────
async function loadSessionsList() {
  try {
    const res = await fetch('/api/sessions', { cache: 'no-store' });
    const list = await res.json();
    const container = document.getElementById('sessionListContainer');
    container.innerHTML = '';

    if (!list || list.length === 0) {
      await startNewChat();
      return;
    }

    if (!activeSessionId) activeSessionId = list[0].id;

    list.forEach(sess => {
      const div = document.createElement('div');
      div.className = `session-item ${sess.id === activeSessionId ? 'active' : ''}`;
      div.onclick = () => switchSession(sess.id);
      div.innerHTML = `
        <span class="session-title-span">💬 ${escapeHtml(sess.title)}</span>
        <button class="session-del-btn" onclick="event.stopPropagation(); deleteSession('${sess.id}')">✕</button>
      `;
      container.appendChild(div);
    });

    await loadActiveSessionMessages();
  } catch(e) { handleServerDisconnected(); }
}

async function startNewChat() {
  try {
    const res = await fetch('/api/sessions/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New Chat', repo_path: currentRepoPath })
    });
    const sess = await res.json();
    activeSessionId = sess.id;
    await loadSessionsList();
  } catch(e) { handleServerDisconnected(); }
}

async function switchSession(id) {
  activeSessionId = id;
  await loadSessionsList();
}

async function deleteSession(id) {
  await fetch('/api/sessions/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: id })
  });
  if (activeSessionId === id) activeSessionId = "";
  showToast("Chat session deleted", "info");
  await loadSessionsList();
}

async function confirmClearCurrentSession() {
  if (activeSessionId) await deleteSession(activeSessionId);
}

async function loadActiveSessionMessages() {
  if (!activeSessionId) return;
  try {
    const res = await fetch(`/api/sessions/get?id=${encodeURIComponent(activeSessionId)}`, { cache: 'no-store' });
    const sess = await res.json();
    if (!sess) return;

    const container = document.getElementById('chatContainer');
    container.innerHTML = '';

    const welcome = document.createElement('div');
    welcome.className = 'msg-row';
    welcome.innerHTML = `
      <div class="msg-assistant">
        <div class="msg-header">
          <div class="msg-author">🤖 Direct Lead Advisor (Session: ${escapeHtml(sess.title)})</div>
          <span style="font-size:12px; color:var(--green); font-weight:700;">Ready</span>
        </div>
        <div class="markdown-body">
          <p>Active session loaded. All tasks dynamically allocate sub-agent slots with tailored skills.</p>
        </div>
      </div>
    `;
    container.appendChild(welcome);

    promptHistory = [];
    (sess.messages || []).forEach(turn => {
      if (turn.prompt) {
        promptHistory.push(turn.prompt);
        const userRow = document.createElement('div');
        userRow.className = 'msg-row';
        userRow.innerHTML = `<div class="msg-user">${escapeHtml(turn.prompt)}</div>`;
        container.appendChild(userRow);
      }

      if (turn.answer) {
        const assistRow = document.createElement('div');
        assistRow.className = 'msg-row';
        const msgId = 'hist-' + (turn.timestamp || Date.now() + Math.random());
        
        let artHtml = '';
        if (turn.artifact) {
          const art = turn.artifact;
          artHtml = `
            <div class="artifact-card">
              <div class="artifact-header">
                <span>📄 ARTIFACT: ${escapeHtml(art.title)} (${escapeHtml(art.filename)})</span>
                <div class="artifact-actions">
                  <button class="action-btn" onclick="openRemoteArtifact('${escapeJs(art.path || '')}', '${escapeJs(art.filename)}')">👁️ Read Live</button>
                  <button class="action-btn" onclick="downloadBlob('${escapeJs(art.content)}', '${escapeJs(art.filename)}')">⬇️ Download</button>
                  <button class="action-btn" onclick="copyArtifact('${escapeJs(art.content)}')">📋 Copy</button>
                </div>
              </div>
              <div class="artifact-content markdown-body">
                ${parseMarkdown(art.content)}
              </div>
            </div>
          `;
        }

        const planHtml = turn.plan ? renderCboPlanHtml(turn.plan, msgId) : '';

        assistRow.innerHTML = `
          <div class="msg-assistant" id="${msgId}">
            <div class="msg-header">
              <div class="msg-author">🤖 Direct Lead Advisor (Dynamic GPU Swarm)</div>
              <span style="font-size:12px; color:var(--green); font-weight:700;">✓ ${turn.duration || 1.5}s</span>
            </div>
            <div class="status-timeline">
              ${(turn.status_steps || []).map(s => `<div>${escapeHtml(s)}</div>`).join('')}
            </div>
            ${planHtml}
            <div class="markdown-body">
              ${parseMarkdown(turn.answer)}
            </div>
            ${artHtml}
          </div>
        `;
        container.appendChild(assistRow);
      }
    });

    historyIndex = promptHistory.length;
    container.scrollTop = container.scrollHeight;
  } catch(e) { handleServerDisconnected(); }
}

// ─────────────────────────────────────────────────────────────
// GROUPED ARTIFACTS VAULT
// ─────────────────────────────────────────────────────────────
async function loadArtifactsVault() {
  try {
    const res = await fetch(`/api/artifacts?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const data = await res.json();
    const container = document.getElementById('groupedArtifactsContainer');
    container.innerHTML = '';

    const groups = data.groups || [];
    if (groups.length === 0) {
      container.innerHTML = '<div style="text-align:center; color:var(--text-muted); padding:30px;">No artifacts generated yet.</div>';
      return;
    }

    groups.forEach(grp => {
      const card = document.createElement('div');
      card.className = 'repo-artifact-group';

      let rowsHtml = '';
      grp.artifacts.forEach(art => {
        const sizeKb = (art.size / 1024).toFixed(1) + ' KB';
        rowsHtml += `
          <tr style="border-bottom:1px solid #1a2538;">
            <td style="padding:10px 16px; font-weight:700; color:#ffffff;">📄 ${escapeHtml(art.name)}</td>
            <td style="padding:10px 16px;"><span class="file-status-badge status-u">${escapeHtml(art.type)}</span></td>
            <td style="padding:10px 16px; font-family:monospace; color:var(--text-muted); font-size:12px;">${sizeKb}</td>
            <td style="padding:10px 16px; font-family:monospace; color:var(--text-muted); font-size:12px;">${escapeHtml(art.modified)}</td>
            <td style="padding:10px 16px; text-align:right;">
              <div style="display:inline-flex; gap:6px;">
                <button class="action-btn" onclick="openRemoteArtifact('${escapeJs(art.path)}', '${escapeJs(art.name)}')">👁️ Read</button>
                <button class="action-btn" onclick="downloadArtifactFile('${escapeJs(art.path)}', '${escapeJs(art.name)}')">⬇️ Download</button>
              </div>
            </td>
          </tr>
        `;
      });

      card.innerHTML = `
        <div class="repo-group-header" onclick="toggleArtifactGroup('${escapeJs(grp.repo_name)}')">
          <div class="repo-group-title">
            <span>📁 Repository: <b>${escapeHtml(grp.repo_name)}</b></span>
            <span class="file-status-badge status-a">${grp.count} Document${grp.count === 1 ? '' : 's'}</span>
          </div>
          <span id="group-icon-${escapeJs(grp.repo_name)}" style="color:var(--accent); font-weight:800;">▾</span>
        </div>
        <div id="group-body-${escapeJs(grp.repo_name)}" style="display:block;">
          <table style="width:100%; border-collapse:collapse; background:#070a12;">
            <thead>
              <tr style="background:#090d16; border-bottom:1px solid #1e293b; color:#93c5fd; font-size:11.5px; text-align:left;">
                <th style="padding:8px 16px;">Document Name</th>
                <th style="padding:8px 16px;">Type</th>
                <th style="padding:8px 16px;">Size</th>
                <th style="padding:8px 16px;">Modified</th>
                <th style="padding:8px 16px; text-align:right;">Actions</th>
              </tr>
            </thead>
            <tbody>
              ${rowsHtml}
            </tbody>
          </table>
        </div>
      `;
      container.appendChild(card);
    });

  } catch(e) { handleServerDisconnected(); }
}

function toggleArtifactGroup(groupName) {
  const body = document.getElementById(`group-body-${groupName}`);
  const icon = document.getElementById(`group-icon-${groupName}`);
  if (body) {
    const isHidden = (body.style.display === 'none');
    body.style.display = isHidden ? 'block' : 'none';
    if (icon) icon.innerText = isHidden ? '▾' : '▸';
  }
}

async function openRemoteArtifact(filepath, filename) {
  try {
    const res = await fetch(`/api/artifacts/read?path=${encodeURIComponent(filepath)}`, { cache: 'no-store' });
    const data = await res.json();
    
    currentModalContent = data.content || "Empty document.";
    currentModalFilename = filename || "document.md";

    document.getElementById('modalDocTitle').innerText = `📄 ${currentModalFilename}`;
    document.getElementById('modalDocContent').innerHTML = parseMarkdown(currentModalContent);
    
    document.getElementById('modalCopyBtn').onclick = () => {
      navigator.clipboard.writeText(currentModalContent);
      showToast("✓ Document copied to clipboard!", "success");
    };
    document.getElementById('modalDownloadBtn').onclick = () => {
      downloadBlob(currentModalContent, currentModalFilename);
    };

    document.getElementById('artifactModal').className = 'modal-overlay active';
  } catch(e) {
    showToast("Error reading remote document: " + e.message, "error");
  }
}

function closeArtifactModal() {
  document.getElementById('artifactModal').className = 'modal-overlay';
}

async function downloadArtifactFile(filepath, filename) {
  try {
    const res = await fetch(`/api/artifacts/read?path=${encodeURIComponent(filepath)}`, { cache: 'no-store' });
    const data = await res.json();
    downloadBlob(data.content || "", filename);
  } catch(e) {
    showToast("Error downloading file: " + e.message, "error");
  }
}

function downloadBlob(text, filename) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast(`⬇️ Downloaded ${filename}`, "info");
}

// ─────────────────────────────────────────────────────────────
// LIVE DEBUG LOGS DRAWER
// ─────────────────────────────────────────────────────────────
function toggleDebugDrawer() {
  const drawer = document.getElementById('debugDrawer');
  const isActive = drawer.className.includes('active');
  drawer.className = isActive ? 'debug-drawer' : 'debug-drawer active';
  if (!isActive) {
    fetchLiveDebugLogs();
    if (!debugPollInterval) debugPollInterval = setInterval(fetchLiveDebugLogs, 1500);
  } else {
    if (debugPollInterval) { clearInterval(debugPollInterval); debugPollInterval = null; }
  }
}

async function fetchLiveDebugLogs() {
  try {
    const res = await fetch('/api/debug/logs?limit=40', { cache: 'no-store' });
    const data = await res.json();
    const list = document.getElementById('debugLogList');
    list.innerHTML = '';

    (data.logs || []).forEach(log => {
      const div = document.createElement('div');
      const lvl = (log.level || 'INFO').toLowerCase();
      div.className = `debug-log-entry ${lvl === 'error' ? 'error' : (lvl === 'warn' ? 'warn' : '')}`;
      div.innerHTML = `
        <div><span style="color:var(--text-muted);">[${escapeHtml(log.timestamp)}]</span> <b style="color:var(--accent);">[${escapeHtml(log.category)}]</b> ${escapeHtml(log.action)}</div>
        ${log.error ? `<div style="color:#fca5a5; font-size:11px; margin-top:2px;">↳ ${escapeHtml(log.error)}</div>` : ''}
      `;
      list.appendChild(div);
    });

    list.scrollTop = list.scrollHeight;
  } catch(e) {}
}

async function clearDebugLogs() {
  document.getElementById('debugLogList').innerHTML = '<div style="color:var(--text-muted); padding:10px;">Logs cleared in viewer.</div>';
  showToast("Debug logs cleared in viewer", "info");
}

// ─────────────────────────────────────────────────────────────
// Initial Load & Repos
// ─────────────────────────────────────────────────────────────
async function loadRepos() {
  try {
    const res = await fetch('/api/repos', { cache: 'no-store' });
    const repos = await res.json();
    const sel = document.getElementById('repoSelect');
    sel.innerHTML = '';
    
    if (!repos || repos.length === 0) {
      sel.innerHTML = '<option value="">No Git repos found</option>';
      return;
    }

    repos.forEach(r => {
      const opt = document.createElement('option');
      opt.value = r.path;
      opt.innerText = `${r.name}`;
      sel.appendChild(opt);
    });

    currentRepoPath = repos[0].path;
  } catch(e) {
    handleServerDisconnected();
  }
}

async function loadModelCatalogAndAssignments() {
  try {
    const [catRes, assignRes] = await Promise.all([
      fetch('/api/models/catalog', { cache: 'no-store' }),
      fetch('/api/models/assignments', { cache: 'no-store' })
    ]);
    const catalog = await catRes.json();
    const assignments = await assignRes.json();

    const geminiSel = document.getElementById('select-gemini');
    if (geminiSel && catalog.gemini) {
      geminiSel.innerHTML = '';
      catalog.gemini.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.innerText = m.name;
        geminiSel.appendChild(opt);
      });
      if (assignments.gemini) geminiSel.value = assignments.gemini;
    }

    const qwenSel = document.getElementById('select-qwen');
    if (qwenSel && catalog.qwen) {
      qwenSel.innerHTML = '';
      catalog.qwen.forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.innerText = m.name;
        qwenSel.appendChild(opt);
      });
      if (assignments.qwen) qwenSel.value = assignments.qwen;
    }
  } catch(e) {}
}

async function rescoutModels() {
  const btn = document.getElementById('rescoutBtn');
  btn.innerText = '🔄 Scouting...';
  try {
    await fetch('/api/models/rescout', { method: 'POST' });
    await loadModelCatalogAndAssignments();
    btn.innerText = '✓ Scouted!';
    showToast("✓ Model catalog refreshed!", "success");
    setTimeout(() => { btn.innerText = '🔄 Rescout Models'; }, 1500);
  } catch(e) {
    btn.innerText = 'Error';
    showToast("Model rescout failed", "error");
  }
}

async function updateModelAssignment(targetKey, modelId) {
  await fetch('/api/models/assign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target: targetKey, model_id: modelId })
  });
  showToast(`Updated model: ${targetKey} ➔ ${modelId}`, "info");
}

// ─────────────────────────────────────────────────────────────
// Dynamic Sub-Agent Topology Synchronizer & Disconnection Handler
// ─────────────────────────────────────────────────────────────
async function updateTelemetryAndTopology() {
  try {
    const controller = new AbortController();
    const tId = setTimeout(() => controller.abort(), 2000);
    const res = await fetch('/api/metrics', { cache: 'no-store', signal: controller.signal });
    clearTimeout(tId);
    
    if (!res.ok) {
      handleServerDisconnected();
      return;
    }

    const data = await res.json();
    handleServerConnected();

    if (data && data.metrics && data.metrics.gpu) {
      const gpu = data.metrics.gpu;
      const vramGb = (gpu.mem_used / 1024).toFixed(1);
      document.getElementById('vramVal').innerText = `VRAM: ${vramGb}/16GB (${gpu.mem_percent}%)`;
      document.getElementById('gpuVal').innerText = `GPU: ${gpu.util}% (${gpu.temp}°C)`;
      document.getElementById('ramVal').innerText = `RAM: ${data.metrics.ram_used_gb}/${data.metrics.ram_total_gb}GB`;
    }
    
    const mVal = document.getElementById('modelVal');
    if (data && data.status && data.status.lfm) {
      mVal.innerText = 'LFM 2.5: 8 SLOTS READY';
      mVal.style.color = 'var(--green)';
    } else {
      mVal.innerText = 'LFM 2.5: HOST OFFLINE';
      mVal.style.color = 'var(--orange)';
    }

    if (data.topology) {
      renderDynamicTopology(data.topology);
    }
  } catch(e) {
    handleServerDisconnected();
  }
}

function renderDynamicTopology(topo) {
  let totalNodes = 0;
  let runningCount = 0;

  if (topo.orchestrator) {
    totalNodes++;
    if (topo.orchestrator.status === 'running') runningCount++;
    updateStaticNodeView('gemini', topo.orchestrator.status, topo.orchestrator.task);
  }

  if (topo.consensus_nodes) {
    topo.consensus_nodes.forEach(n => {
      totalNodes++;
      if (n.status === 'running') runningCount++;
      updateStaticNodeView(n.id, n.status, n.task);
    });
  }

  const subContainer = document.getElementById('dynamicSubagentsContainer');
  const subList = topo.sub_agents || [];
  
  subContainer.innerHTML = '';
  if (subList.length === 0) {
    subContainer.innerHTML = '<div style="color:var(--text-muted); font-size:13px; padding:10px;">No active task. Sub-agents dynamically instantiate (1 to 8) upon next prompt.</div>';
  } else {
    subList.forEach(s => {
      totalNodes++;
      if (s.status === 'running') runningCount++;
      
      const card = document.createElement('div');
      const isRunning = (s.status === 'running');
      card.style.cssText = `background:var(--card-bg); border:1.5px solid ${isRunning ? 'var(--green)' : 'var(--card-border)'}; border-radius:12px; padding:12px; width:280px; display:flex; flex-direction:column; gap:6px; box-shadow:0 8px 24px rgba(0,0,0,0.5);`;
      
      const toolsHtml = (s.tools || []).map(t => `<span style="font-family:monospace; font-size:9.5px; background:#1e293b; color:#93c5fd; padding:2px 6px; border-radius:4px; border:1px solid #334155;">${escapeHtml(t)}</span>`).join(' ');

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:800; color:#ffffff; font-size:13px;">${escapeHtml(s.name)}</span>
          <span class="status-badge ${isRunning ? 'badge-running' : (s.status === 'online' ? 'badge-online' : 'badge-idle')}">${escapeHtml(s.status.toUpperCase())}</span>
        </div>
        <div style="font-size:10.5px; color:#94a3b8; font-weight:800;">${escapeHtml(s.role || 'Level 3 Sub-Agent')}</div>
        <div style="font-family:monospace; font-size:11px; background:#070a12; color:var(--accent); border:1px solid #1e293b; padding:3px 7px; border-radius:6px; font-weight:700;">🎯 Skill: ${escapeHtml(s.skill || 'Specialist')}</div>
        <div class="agent-task" style="font-family:monospace; font-size:11px; background:#070a12; padding:6px 10px; border-radius:8px; border:1px solid #1e293b; color:#ffffff;">${escapeHtml(s.task || 'Idle')}</div>
        <div style="display:flex; flex-wrap:wrap; gap:4px;">${toolsHtml}</div>
      `;
      subContainer.appendChild(card);
    });
  }

  const badge = document.getElementById('agentCountBadge');
  if (badge) {
    if (runningCount > 0) {
      badge.innerText = `🟢 ${runningCount} / ${totalNodes} Agents Active (Running)`;
      badge.style.borderColor = 'var(--green)';
      badge.style.color = 'var(--green)';
    } else {
      badge.innerText = `🤖 ${totalNodes} Nodes Registered (0 Running / Idle)`;
      badge.style.borderColor = 'var(--accent)';
      badge.style.color = 'var(--accent)';
    }
  }
}

function updateStaticNodeView(id, status, task) {
  const card = document.getElementById(`node-${id}`);
  const badge = document.getElementById(`badge-${id}`);
  const taskEl = document.getElementById(`task-${id}`);
  if (!card || !badge || !taskEl) return;

  taskEl.innerText = task || 'Idle';
  badge.innerText = status.toUpperCase();
  badge.className = `status-badge ${status === 'running' ? 'badge-running' : (status === 'online' || status === 'ready' ? 'badge-online' : (status === 'offline' ? 'badge-offline' : 'badge-idle'))}`;
}

function filterLegendCards(val) {
  const q = (val || '').toLowerCase().trim();
  const cards = document.querySelectorAll('.legend-card');
  cards.forEach(card => {
    const text = (card.innerText + ' ' + (card.getAttribute('data-keywords') || '')).toLowerCase();
    if (!q || text.includes(q)) {
      card.classList.remove('hidden');
    } else {
      card.classList.add('hidden');
    }
  });
}

function setPollingSpeed(fast) {
  if (pollInterval) clearInterval(pollInterval);
  pollInterval = setInterval(updateTelemetryAndTopology, fast ? 300 : 1200);
}

window.addEventListener('DOMContentLoaded', async () => {
  await loadRepos();
  await loadSessionsList();
  await loadModelCatalogAndAssignments();
  updateTelemetryAndTopology();
  setPollingSpeed(false);
});

function onRepoChanged() {
  const sel = document.getElementById('repoSelect');
  currentRepoPath = sel.value;
  selectedGhdFile = "";
  selectedGhdCommit = "";
  loadGitHubDesktopState();
  loadArtifactsVault();
  pollLoopState();
  showToast(`Switched repository: ${sel.options[sel.selectedIndex]?.text || ''}`, "info", 2000);
}

const promptEl = document.getElementById('promptInput');
if (promptEl) {
  promptEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitMessage();
      return;
    }
    if (promptHistory.length === 0) return;
    if (e.key === 'ArrowUp' && (promptEl.selectionStart === 0 || promptEl.value === '')) {
      e.preventDefault();
      if (historyIndex === promptHistory.length) tempDraft = promptEl.value;
      if (historyIndex > 0) { historyIndex--; promptEl.value = promptHistory[historyIndex]; }
    } else if (e.key === 'ArrowDown') {
      if (historyIndex < promptHistory.length - 1) {
        e.preventDefault();
        historyIndex++;
        promptEl.value = promptHistory[historyIndex];
      } else if (historyIndex === promptHistory.length - 1) {
        e.preventDefault();
        historyIndex = promptHistory.length;
        promptEl.value = tempDraft;
      }
    }
  });
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

function sendQuickPrompt(text) {
  document.getElementById('promptInput').value = text;
  submitMessage();
}

async function pasteFromClipboard() {
  try {
    const text = await navigator.clipboard.readText();
    if (text) {
      document.getElementById('promptInput').value = text;
      autoResize(document.getElementById('promptInput'));
    }
  } catch(e) {
    showToast("Use Ctrl+V to paste into input.", "info");
  }
}

async function submitMessage() {
  const prompt = promptEl.value.trim();
  if (!prompt) return;

  promptHistory.push(prompt);
  historyIndex = promptHistory.length;
  promptEl.value = '';
  promptEl.style.height = '52px';

  const container = document.getElementById('chatContainer');

  const userRow = document.createElement('div');
  userRow.className = 'msg-row';
  userRow.innerHTML = `<div class="msg-user">${escapeHtml(prompt)}</div>`;
  container.appendChild(userRow);

  const assistRow = document.createElement('div');
  assistRow.className = 'msg-row';
  const msgId = 'msg-' + Date.now();
  assistRow.innerHTML = `
    <div class="msg-assistant" id="${msgId}">
      <div class="msg-header">
        <div class="msg-author">🤖 Direct Lead Advisor (Task-Aware GPU Swarm Active)</div>
        <span style="font-size:12px; color:var(--accent); font-weight:700;"><span class="spinner"></span> Planning Swarm...</span>
      </div>
      <div class="status-timeline" id="status-${msgId}">
        <div class="step-active">➔ Decomposing task & determining dynamic sub-agent slot allocation...</div>
      </div>
      <div class="markdown-body" id="body-${msgId}">
        <span style="color:var(--text-muted);">Analyzing intent and allocating GPU continuous batching slots...</span>
      </div>
    </div>
  `;
  container.appendChild(assistRow);
  container.scrollTop = container.scrollHeight;

  const btn = document.getElementById('sendBtn');
  btn.disabled = true;
  
  setPollingSpeed(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: prompt, repo_path: currentRepoPath, session_id: activeSessionId })
    });
    const data = await res.json();

    const statusEl = document.getElementById(`status-${msgId}`);
    statusEl.innerHTML = (data.status_steps || []).map(s => `<div>${escapeHtml(s)}</div>`).join('');

    if (data.plan) {
      const planDiv = document.createElement('div');
      planDiv.innerHTML = renderCboPlanHtml(data.plan, msgId);
      statusEl.parentNode.insertBefore(planDiv, document.getElementById(`body-${msgId}`));
    }

    const bodyEl = document.getElementById(`body-${msgId}`);
    bodyEl.innerHTML = parseMarkdown(data.answer || "No response received.");

    if (data.artifact) {
      const art = data.artifact;
      const artDiv = document.createElement('div');
      artDiv.className = 'artifact-card';
      artDiv.innerHTML = `
        <div class="artifact-header">
          <span>📄 ARTIFACT: ${escapeHtml(art.title)} (${escapeHtml(art.filename)})</span>
          <div class="artifact-actions">
            <button class="action-btn" onclick="openRemoteArtifact('${escapeJs(art.path || '')}', '${escapeJs(art.filename)}')">👁️ Read Live</button>
            <button class="action-btn" onclick="downloadBlob('${escapeJs(art.content)}', '${escapeJs(art.filename)}')">⬇️ Download</button>
            <button class="action-btn" onclick="copyArtifact('${escapeJs(art.content)}')">📋 Copy</button>
          </div>
        </div>
        <div class="artifact-content markdown-body">
          ${parseMarkdown(art.content)}
        </div>
      `;
      document.getElementById(msgId).appendChild(artDiv);
    }

    const headSpan = document.getElementById(msgId).querySelector('.msg-header span');
    headSpan.innerText = `✓ ${data.duration}s (Dynamic Swarm)`;
    headSpan.style.color = 'var(--green)';

    await loadSessionsList();

  } catch (err) {
    document.getElementById(`body-${msgId}`).innerHTML = `<span style="color:#f87171; font-weight:700;">Error: ${escapeHtml(err.message || err)}</span>`;
  } finally {
    btn.disabled = false;
    setPollingSpeed(false);
    updateTelemetryAndTopology();
    container.scrollTop = container.scrollHeight;
  }
}

function renderCboPlanHtml(plan, msgId) {
  if (!plan) return '';
  const opClassMap = {
    'INDEX_SCAN': 'op-index',
    'DOC_FETCH': 'op-doc',
    'CODE_DRAFT': 'op-draft',
    'SYNTAX_VERIFY': 'op-verify',
    'THREAT_AUDIT': 'op-audit',
    'CONSENSUS_MERGE': 'op-doc',
    'SYNTHESIZE': 'op-synth'
  };

  const nodesHtml = (plan.nodes || []).map((n, i) => {
    const opClass = opClassMap[n.operator] || 'op-index';
    return `
      <div class="cbo-dag-node">
        <div style="display:flex; align-items:center; gap:8px;">
          <span class="cbo-op-tag ${opClass}">${escapeHtml(n.operator)}</span>
          <span style="font-weight:700; color:#ffffff;">${escapeHtml(n.name)}</span>
          <span style="color:var(--text-muted); font-size:11px;">(${escapeHtml(n.assigned_agent)})</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="color:#94a3b8; font-size:11px;">${escapeHtml(n.slot)}</span>
          <span style="color:var(--accent); font-weight:700;">${n.estimated_cost_ms}ms</span>
        </div>
      </div>
    `;
  }).join('');

  const pId = `cbo-plan-${msgId}`;
  return `
    <div class="cbo-plan-wrapper">
      <div class="cbo-plan-toggle" onclick="toggleCboPlan('${pId}')">
        <span>⚡ EXPLAIN SWARM QUERY PLAN: ${escapeHtml(plan.strategy_name)}</span>
        <span>Cost: ${plan.cost_score} · Conf: ${Math.round(plan.confidence_score*100)}% ▾</span>
      </div>
      <div class="cbo-plan-content" id="${pId}" style="display:block;">
        <div class="cbo-metrics-strip">
          <div class="cbo-metric-tag">Cost Score: <b>${plan.cost_score}</b></div>
          <div class="cbo-metric-tag">Confidence: <b>${Math.round(plan.confidence_score*100)}%</b></div>
          <div class="cbo-metric-tag">Parallel Width: <b>${plan.parallelism_width}x</b></div>
          <div class="cbo-metric-tag">Critical Path: <b>${Math.round(plan.critical_path_cost_ms)}ms</b></div>
          <div class="cbo-metric-tag">Est. Tokens: <b>${plan.total_estimated_tokens}</b></div>
        </div>
        <div style="font-size:12px; color:#cbd5e1; font-style:italic;">
          Rationale: ${escapeHtml(plan.strategy_rationale || '')}
        </div>
        <div class="cbo-dag-list">
          <div style="font-weight:800; color:#93c5fd; font-size:11px; margin-bottom:2px;">OPTIMIZED EXECUTION DAG:</div>
          ${nodesHtml}
        </div>
      </div>
    </div>
  `;
}

function toggleCboPlan(pId) {
  const el = document.getElementById(pId);
  if (el) {
    el.style.display = (el.style.display === 'none') ? 'block' : 'none';
  }
}

function copyArtifact(content) {
  navigator.clipboard.writeText(content);
  showToast("✓ Artifact copied to clipboard!", "success");
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeJs(str) {
  if (!str) return '';
  return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n');
}
