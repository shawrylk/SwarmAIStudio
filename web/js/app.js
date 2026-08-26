/**
 * Swarm AI Studio Frontend Controller
 * Multi-Chat, GitHub Desktop, Swarm Topology & Artifact Vault
 */

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
let currentModalContent = "";
let currentModalFilename = "";

function switchTab(tabId) {
  document.getElementById('tabChatBtn').className = (tabId === 'chat') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabGitBtn').className = (tabId === 'git') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabTopoBtn').className = (tabId === 'topo') ? 'tab-btn active' : 'tab-btn';
  document.getElementById('tabVaultBtn').className = (tabId === 'vault') ? 'tab-btn active' : 'tab-btn';
  
  document.getElementById('tabChat').className = (tabId === 'chat') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabGit').className = (tabId === 'git') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabTopo').className = (tabId === 'topo') ? 'tab-content active' : 'tab-content';
  document.getElementById('tabVault').className = (tabId === 'vault') ? 'tab-content active' : 'tab-content';

  const sidebar = document.getElementById('chatSidebar');
  sidebar.style.display = (tabId === 'chat') ? 'flex' : 'none';

  if (tabId === 'git') loadGitHubDesktopState();
  if (tabId === 'vault') loadArtifactsVault();
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
// FULL GITHUB DESKTOP CLIENT LOGIC
// ─────────────────────────────────────────────────────────────
async function loadGitHubDesktopState() {
  try {
    const res = await fetch(`/api/git/overview?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const data = await res.json();
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

    allBranches = data.branches || [];
    renderBranchModalList(allBranches, data.branch);

    renderChangesList(data.changed_files || []);
    renderHistoryList(data.history || []);

  } catch(e) {}
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

  files.forEach((f, idx) => {
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
  } catch(e) {}
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
  if (confirm(`Are you sure you want to discard changes to ${selectedGhdFile}? This cannot be undone.`)) {
    try {
      const res = await fetch('/api/git/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: currentRepoPath, file: selectedGhdFile })
      });
      const data = await res.json();
      if (data.success) {
        selectedGhdFile = "";
        await loadGitHubDesktopState();
      } else {
        alert("Discard error: " + data.stderr);
      }
    } catch(e) { alert("Error: " + e.message); }
  }
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
      document.getElementById('commitSummaryInput').value = '';
      document.getElementById('commitDescInput').value = '';
      selectedGhdFile = "";
      await loadGitHubDesktopState();
    } else {
      alert("Commit error: " + (data.stderr || data.error));
    }
  } catch(e) { alert("Error: " + e.message); }
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
    if (data.success) alert("✓ Pushed to remote successfully!");
    else alert("Push info: " + (data.stderr || data.stdout));
  } catch(e) { alert("Push error: " + e.message); }
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
    alert("Pull result: " + (data.stdout || data.stderr));
  } catch(e) { alert("Pull error: " + e.message); }
}

async function ghdFetch() {
  try {
    const res = await fetch('/api/git/fetch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath })
    });
    await loadGitHubDesktopState();
    alert("✓ Remote repository fetched!");
  } catch(e) { alert("Fetch error: " + e.message); }
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
  if (m && !m.contains(e.target) && !document.getElementById('ghdBranchBtn').contains(e.target)) {
    m.className = 'branch-modal';
  }
});

function renderBranchModalList(branches, currentBranch) {
  const scroll = document.getElementById('branchListScroll');
  scroll.innerHTML = '';
  
  branches.forEach(b => {
    const row = document.createElement('div');
    row.className = `branch-item-row ${b === currentBranch ? 'current' : ''}`;
    row.onclick = () => ghdCheckoutBranch(b, false);
    row.innerHTML = `<span>🌿 ${escapeHtml(b)}</span> ${b === currentBranch ? '<span>✓</span>' : ''}`;
    scroll.appendChild(row);
  });
}

function filterBranches(val) {
  const query = val.toLowerCase();
  const filtered = allBranches.filter(b => b.toLowerCase().includes(query));
  renderBranchModalList(filtered, currentGhdState ? currentGhdState.branch : "");
}

async function ghdCheckoutBranch(branchName, create) {
  try {
    const res = await fetch('/api/git/branch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, branch: branchName, create: create })
    });
    const data = await res.json();
    document.getElementById('branchModal').className = 'branch-modal';
    if (data.success) {
      await loadGitHubDesktopState();
    } else {
      alert("Branch error: " + (data.stderr || data.error));
    }
  } catch(e) { alert("Error: " + e.message); }
}

async function createAndCheckoutBranch() {
  const input = document.getElementById('branchSearchInput').value.trim();
  if (!input) {
    alert("Type a new branch name in the search box first.");
    return;
  }
  await ghdCheckoutBranch(input, true);
}

async function openStashModal() {
  const msg = prompt("Enter stash message (or leave blank for default):");
  if (msg !== null) {
    try {
      const res = await fetch('/api/git/stash/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: currentRepoPath, message: msg })
      });
      await loadGitHubDesktopState();
      alert("✓ Stash created!");
    } catch(e) { alert("Error: " + e.message); }
  }
}

async function openWorktreeModal() {
  const path = prompt("Enter worktree directory path (e.g. ../worktree-feature):");
  if (path) {
    const branch = prompt("Enter branch name for worktree (optional):") || "";
    try {
      const res = await fetch('/api/git/worktree/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repo_path: currentRepoPath, path: path, branch: branch })
      });
      const data = await res.json();
      if (data.success) {
        alert("✓ Worktree created successfully!");
        await loadGitHubDesktopState();
      } else {
        alert("Worktree error: " + data.stderr);
      }
    } catch(e) { alert("Error: " + e.message); }
  }
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
  } catch(e) {}
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
  } catch(e) {}
}

async function switchSession(id) {
  activeSessionId = id;
  await loadSessionsList();
}

async function deleteSession(id) {
  if (confirm("Delete this chat session?")) {
    await fetch('/api/sessions/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    });
    if (activeSessionId === id) activeSessionId = "";
    await loadSessionsList();
  }
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

        assistRow.innerHTML = `
          <div class="msg-assistant" id="${msgId}">
            <div class="msg-header">
              <div class="msg-author">🤖 Direct Lead Advisor (Dynamic GPU Swarm)</div>
              <span style="font-size:12px; color:var(--green); font-weight:700;">✓ ${turn.duration || 1.5}s</span>
            </div>
            <div class="status-timeline">
              ${(turn.status_steps || []).map(s => `<div>${escapeHtml(s)}</div>`).join('')}
            </div>
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
  } catch(e) {}
}

// ─────────────────────────────────────────────────────────────
// Repos & Artifact Vault
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
    document.getElementById('repoSelect').innerHTML = '<option value="">(Repos loaded)</option>';
  }
}

async function loadArtifactsVault() {
  try {
    const res = await fetch(`/api/artifacts?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const list = await res.json();
    const tbody = document.getElementById('vaultTableBody');
    tbody.innerHTML = '';

    if (!list || list.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center; color:var(--text-muted); padding:16px;">No artifacts generated yet.</td></tr>';
      return;
    }

    list.forEach(art => {
      const tr = document.createElement('tr');
      const sizeKb = (art.size / 1024).toFixed(1) + ' KB';
      tr.innerHTML = `
        <td style="font-weight:700; color:#ffffff; padding:12px 16px;">📄 ${escapeHtml(art.name)}</td>
        <td style="padding:12px 16px;"><span class="file-status-badge status-u">${escapeHtml(art.type)}</span></td>
        <td style="font-family:monospace; color:var(--text-muted); padding:12px 16px;">${sizeKb}</td>
        <td style="font-family:monospace; color:var(--text-muted); font-size:12px; padding:12px 16px;">${escapeHtml(art.modified)}</td>
        <td style="padding:12px 16px;">
          <div style="display:flex; gap:6px;">
            <button class="action-btn" onclick="openRemoteArtifact('${escapeJs(art.path)}', '${escapeJs(art.name)}')">👁️ Read</button>
            <button class="action-btn" onclick="downloadArtifactFile('${escapeJs(art.path)}', '${escapeJs(art.name)}')">⬇️ Download</button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  } catch(e) {}
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
      alert("✓ Document copied to clipboard!");
    };
    document.getElementById('modalDownloadBtn').onclick = () => {
      downloadBlob(currentModalContent, currentModalFilename);
    };

    document.getElementById('artifactModal').className = 'modal-overlay active';
  } catch(e) {
    alert("Error reading remote document: " + e.message);
  }
}

function closeArtifactModal(e) {
  document.getElementById('artifactModal').className = 'modal-overlay';
}

async function downloadArtifactFile(filepath, filename) {
  try {
    const res = await fetch(`/api/artifacts/read?path=${encodeURIComponent(filepath)}`, { cache: 'no-store' });
    const data = await res.json();
    downloadBlob(data.content || "", filename);
  } catch(e) {
    alert("Error downloading file: " + e.message);
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
    setTimeout(() => { btn.innerText = '🔄 Rescout Models'; }, 1500);
  } catch(e) {
    btn.innerText = 'Error';
  }
}

async function updateModelAssignment(targetKey, modelId) {
  await fetch('/api/models/assign', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target: targetKey, model_id: modelId })
  });
}

// ─────────────────────────────────────────────────────────────
// Dynamic Sub-Agent Topology Synchronizer
// ─────────────────────────────────────────────────────────────
async function updateTelemetryAndTopology() {
  try {
    const res = await fetch('/api/metrics', { cache: 'no-store' });
    const data = await res.json();
    
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
    }

    if (data.topology) {
      renderDynamicTopology(data.topology);
    }
  } catch(e) {}
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
  badge.className = `status-badge ${status === 'running' ? 'badge-running' : (status === 'online' || status === 'ready' ? 'badge-online' : 'badge-idle')}`;
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
}

const promptEl = document.getElementById('promptInput');
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
    alert("Use Ctrl+V to paste.");
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

function copyArtifact(content) {
  navigator.clipboard.writeText(content);
  alert("✓ Artifact copied to clipboard!");
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function escapeJs(str) {
  if (!str) return '';
  return String(str).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"').replace(/\n/g, '\\n');
}
