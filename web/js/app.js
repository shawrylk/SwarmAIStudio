/**
 * Swarm AI Studio Frontend Controller
 * Multi-Chat, Full GitHub Desktop, Stash Local Changes, Worktree Manager, Autonomous Loop Agent,
 * Cost-Based Optimizer (CBO) & SQL Explain DAG, and Auto-Dismissing Toast Notification System.
 */

let isServerConnected = true;
let consecutiveFailures = 0;
let activeSessionId = "";
let activeLoopSessionId = "";
let allLoopSessions = [];
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
// DRAGGABLE SPLIT PANES & RESIZERS CONTROLLER
// ─────────────────────────────────────────────────────────────
const DEFAULT_PANE_WIDTHS = {
  chatSidebar: 260,
  ghdLeft: 380,
  loopLeft: 600
};

function getSavedPaneWidth(paneKey, defaultVal) {
  try {
    const saved = JSON.parse(localStorage.getItem('swarm_pane_widths') || '{}');
    return (typeof saved[paneKey] === 'number') ? saved[paneKey] : defaultVal;
  } catch (e) {
    return defaultVal;
  }
}

function savePaneWidth(paneKey, width) {
  try {
    const saved = JSON.parse(localStorage.getItem('swarm_pane_widths') || '{}');
    saved[paneKey] = Math.round(width);
    localStorage.setItem('swarm_pane_widths', JSON.stringify(saved));
  } catch (e) {}
}

function initSplitResizers() {
  const configs = [
    {
      resizerId: 'chatSidebarResizer',
      paneId: 'chatSidebar',
      key: 'chatSidebar',
      min: 180,
      max: () => Math.min(window.innerWidth * 0.45, 480),
      defaultWidth: DEFAULT_PANE_WIDTHS.chatSidebar
    },
    {
      resizerId: 'ghdSplitResizer',
      paneId: 'ghdLeftPane',
      key: 'ghdLeft',
      min: 260,
      max: () => {
        const container = document.getElementById('ghdSplitView');
        const cWidth = container ? container.getBoundingClientRect().width : window.innerWidth;
        return Math.min(cWidth * 0.75, cWidth - 280);
      },
      defaultWidth: DEFAULT_PANE_WIDTHS.ghdLeft
    },
    {
      resizerId: 'loopSplitResizer',
      paneId: 'loopLeftPane',
      key: 'loopLeft',
      min: 320,
      max: () => {
        const container = document.getElementById('loopSplitContainer');
        const cWidth = container ? container.getBoundingClientRect().width : window.innerWidth;
        return Math.min(cWidth * 0.75, cWidth - 320);
      },
      defaultWidth: DEFAULT_PANE_WIDTHS.loopLeft
    }
  ];

  configs.forEach(cfg => {
    const resizer = document.getElementById(cfg.resizerId);
    const pane = document.getElementById(cfg.paneId);
    if (!resizer || !pane) return;

    // Apply saved width if desktop
    if (window.innerWidth > 768) {
      const savedWidth = getSavedPaneWidth(cfg.key, cfg.defaultWidth);
      pane.style.width = `${savedWidth}px`;
    }

    // Double click to reset to default width
    resizer.addEventListener('dblclick', () => {
      pane.style.width = `${cfg.defaultWidth}px`;
      savePaneWidth(cfg.key, cfg.defaultWidth);
      showToast(`Reset pane width to ${cfg.defaultWidth}px`, "info", 1500);
    });

    let startX = 0;
    let startWidth = 0;
    let isDragging = false;

    const onPointerDown = (clientX) => {
      if (window.innerWidth <= 768) return;
      isDragging = true;
      startX = clientX;
      startWidth = pane.getBoundingClientRect().width;
      resizer.classList.add('active');
      document.body.classList.add('resizing');
    };

    const onPointerMove = (clientX) => {
      if (!isDragging) return;
      const deltaX = clientX - startX;
      let newWidth = startWidth + deltaX;
      const maxW = typeof cfg.max === 'function' ? cfg.max() : cfg.max;
      if (newWidth < cfg.min) newWidth = cfg.min;
      if (newWidth > maxW) newWidth = maxW;
      pane.style.width = `${newWidth}px`;
    };

    const onPointerUp = () => {
      if (!isDragging) return;
      isDragging = false;
      resizer.classList.remove('active');
      document.body.classList.remove('resizing');
      const finalWidth = pane.getBoundingClientRect().width;
      savePaneWidth(cfg.key, finalWidth);
    };

    // Mouse events
    resizer.addEventListener('mousedown', (e) => {
      e.preventDefault();
      onPointerDown(e.clientX);
    });

    // Touch events
    resizer.addEventListener('touchstart', (e) => {
      if (e.touches && e.touches.length === 1) {
        onPointerDown(e.touches[0].clientX);
      }
    }, { passive: true });

    window.addEventListener('mousemove', (e) => {
      if (isDragging) {
        e.preventDefault();
        onPointerMove(e.clientX);
      }
    });

    window.addEventListener('touchmove', (e) => {
      if (isDragging && e.touches && e.touches.length === 1) {
        onPointerMove(e.touches[0].clientX);
      }
    }, { passive: true });

    window.addEventListener('mouseup', onPointerUp);
    window.addEventListener('touchend', onPointerUp);
    window.addEventListener('touchcancel', onPointerUp);
  });
}

// ─────────────────────────────────────────────────────────────
// MOBILE RESPONSIVE TOGGLES (GHD SINGLE COLUMN & CHAT DRAWER)
// ─────────────────────────────────────────────────────────────
function toggleGhdMobileView(mode) {
  const splitView = document.getElementById('ghdSplitView');
  const backBtn = document.getElementById('ghdMobileBackBtn');
  if (!splitView) return;

  if (mode === 'diff') {
    splitView.classList.add('mobile-diff-active');
    if (backBtn) backBtn.style.display = 'inline-flex';
  } else {
    splitView.classList.remove('mobile-diff-active');
    if (backBtn) backBtn.style.display = 'none';
  }
}

function toggleMobileChatSidebar(forceState) {
  const sidebar = document.getElementById('chatSidebar');
  const backdrop = document.getElementById('chatSidebarBackdrop');
  if (!sidebar) return;

  const shouldOpen = (typeof forceState === 'boolean') ? forceState : !sidebar.classList.contains('open');
  if (shouldOpen) {
    sidebar.classList.add('open');
    if (backdrop) backdrop.classList.add('active');
  } else {
    sidebar.classList.remove('open');
    if (backdrop) backdrop.classList.remove('active');
  }
}

// ─────────────────────────────────────────────────────────────
// AUTO-DEV LOOP LIVE STREAM & ACTION RECORDER
// ─────────────────────────────────────────────────────────────
let loopLiveStreamLogs = [];
let lastLoopTaskStateKey = "";

function appendLoopLiveLog(text, level = 'info', tag = 'LOOP') {
  const stream = document.getElementById('loopLiveLogStream');
  if (!stream) return;

  const now = new Date();
  const timeStr = now.toTimeString().split(' ')[0];
  const entry = { time: timeStr, text, level, tag };
  loopLiveStreamLogs.push(entry);
  if (loopLiveStreamLogs.length > 80) loopLiveStreamLogs.shift();

  renderLoopLiveStream();
}

function clearLoopLiveStream() {
  loopLiveStreamLogs = [];
  const stream = document.getElementById('loopLiveLogStream');
  if (stream) {
    stream.innerHTML = '<div style="color:var(--text-muted); padding:8px 0; font-size:11.5px;">Stream cleared. Awaiting new events...</div>';
  }
  showToast("Live stream log cleared", "info", 1500);
}

function renderLoopLiveStream() {
  const stream = document.getElementById('loopLiveLogStream');
  if (!stream) return;
  if (loopLiveStreamLogs.length === 0) {
    stream.innerHTML = '<div style="color:var(--text-muted); padding:8px 0; font-size:11.5px;">Awaiting Autonomous Swarm execution events...</div>';
    return;
  }

  const isScrolledToBottom = stream.children.length === 0 || (stream.scrollHeight - stream.scrollTop - stream.clientHeight) < 60;

  stream.innerHTML = loopLiveStreamLogs.map(l => {
    const tagColors = {
      LOOP: 'var(--accent)',
      TASK: 'var(--green)',
      JUDGE: 'var(--amber)',
      ADVISOR: 'var(--purple)',
      ERROR: 'var(--rose)',
      WARN: 'var(--orange)'
    };
    const color = tagColors[l.tag] || 'var(--accent)';
    return `
      <div class="loop-log-line">
        <span class="loop-log-time">[${escapeHtml(l.time)}]</span>
        <span class="loop-log-tag" style="color:${color};">[${escapeHtml(l.tag)}]</span>
        <span style="color:var(--text-bright);">${escapeHtml(l.text)}</span>
      </div>
    `;
  }).join('');

  if (isScrolledToBottom) {
    stream.scrollTop = stream.scrollHeight;
  }
}

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
  try { localStorage.setItem('swarm_active_tab', tabId); } catch(_) {}
  const isAgent = (tabId === 'agent' || tabId === 'chat' || tabId === 'loop');
  const agentBtn = document.getElementById('tabAgentBtn') || document.getElementById('tabChatBtn');
  if (agentBtn) agentBtn.className = isAgent ? 'tab-btn active' : 'tab-btn';
  const loopBtn = document.getElementById('tabLoopBtn');
  if (loopBtn) loopBtn.className = 'tab-btn';
  const gitBtn = document.getElementById('tabGitBtn');
  if (gitBtn) gitBtn.className = (tabId === 'git') ? 'tab-btn active' : 'tab-btn';
  const cBtn = document.getElementById('tabContractsBtn');
  if (cBtn) cBtn.className = (tabId === 'contracts') ? 'tab-btn active' : 'tab-btn';
  const topoBtn = document.getElementById('tabTopoBtn');
  if (topoBtn) topoBtn.className = (tabId === 'topo') ? 'tab-btn active' : 'tab-btn';
  const vaultBtn = document.getElementById('tabVaultBtn');
  if (vaultBtn) vaultBtn.className = (tabId === 'vault') ? 'tab-btn active' : 'tab-btn';
  
  const chatTab = document.getElementById('tabChat');
  if (chatTab) chatTab.className = isAgent ? 'tab-content active' : 'tab-content';
  const loopTab = document.getElementById('tabLoop');
  if (loopTab) loopTab.className = 'tab-content';
  const gitTab = document.getElementById('tabGit');
  if (gitTab) gitTab.className = (tabId === 'git') ? 'tab-content active' : 'tab-content';
  const cTab = document.getElementById('tabContracts');
  if (cTab) cTab.className = (tabId === 'contracts') ? 'tab-content active' : 'tab-content';
  const topoTab = document.getElementById('tabTopo');
  if (topoTab) topoTab.className = (tabId === 'topo') ? 'tab-content active' : 'tab-content';
  const vaultTab = document.getElementById('tabVault');
  if (vaultTab) vaultTab.className = (tabId === 'vault') ? 'tab-content active' : 'tab-content';

  const sidebar = document.getElementById('chatSidebar');
  if (sidebar) sidebar.style.display = isAgent ? 'flex' : 'none';

  if (tabId === 'git') loadGitHubDesktopState();
  if (tabId === 'vault') loadArtifactsVault();
  if (tabId === 'contracts') loadContractsCatalog();
  if (isAgent) {
    loadSessionsList();
    updateTelemetryAndTopology();
  }
}

function parseInlineMarkdown(text) {
  if (!text) return '';
  let res = text;
  // Inline code
  res = res.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>');
  // Bold
  res = res.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
  res = res.replace(/__([^_]+)__/g, '<b>$1</b>');
  // Italic
  res = res.replace(/\*([^*]+)\*/g, '<i>$1</i>');
  res = res.replace(/_([^_]+)_/g, '<i>$1</i>');
  // Strikethrough
  res = res.replace(/~~([^~]+)~~/g, '<del>$1</del>');
  // Links: [text](url)
  res = res.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer" class="md-link">$1</a>');
  // Status checkmarks/badges styling
  res = res.replace(/✅\s*Confirmed/gi, '<span class="status-pill status-pill-confirmed">✅ Confirmed</span>');
  res = res.replace(/❌\s*False/gi, '<span class="status-pill status-pill-false">❌ False</span>');
  res = res.replace(/⚠️\s*Partial/gi, '<span class="status-pill status-pill-partial">⚠️ Partial</span>');
  return res;
}

function parseMarkdown(md) {
  if (!md) return '';
  let text = String(md).replace(/\r\n/g, '\n');

  const htmlBlocks = [];
  const saveBlock = (html) => {
    const id = htmlBlocks.length;
    htmlBlocks.push(html);
    return `\n\n%%%HTML_BLOCK_${id}%%%\n\n`;
  };

  // Step 1: Protect Fenced Code Blocks
  text = text.replace(/```([a-zA-Z0-9_\-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
    const l = lang ? lang.trim() : 'text';
    const safeCode = escapeHtml(code);
    const html = `<div class="code-block-wrapper">
      <div class="code-block-header">
        <span class="code-lang-label">${escapeHtml(l)}</span>
        <button class="code-copy-btn" onclick="navigator.clipboard.writeText(this.closest('.code-block-wrapper').querySelector('code').innerText); this.innerText='Copied!'; setTimeout(()=>this.innerText='Copy', 1500)">Copy</button>
      </div>
      <pre><code class="language-${escapeHtml(l)}">${safeCode}</code></pre>
    </div>`;
    return saveBlock(html);
  });

  // Step 2: Handle Claude CLI / Unicode Border Boxes (╭─ ... ─╮ ... ╰─ ... ─╯ or ┌─ ... ─┐ ... └─ ... ─┘)
  text = text.replace(/(?:^[ \t]*[╭┌]─+([^\n─]*?)─+[╮┐][ \t]*\n)([\s\S]*?)(?:^[ \t]*[╰└]─+[╯┘][ \t]*)/gm, (match, title, body) => {
    const cleanTitle = title.trim() || 'Internal Status / Execution';
    const lines = body.split('\n')
      .map(l => l.replace(/^[ \t]*[│|][ \t]?/, '').replace(/[ \t]*[│|][ \t]*$/, '').trim())
      .filter(l => l.length > 0);
    
    let contentHtml = '';
    const listItems = [];
    for (const l of lines) {
      if (l.startsWith('• ') || l.startsWith('- ') || l.startsWith('* ')) {
        listItems.push(`<li>${parseInlineMarkdown(escapeHtml(l.replace(/^[•\-\*]\s*/, '')))}</li>`);
      } else {
        if (listItems.length > 0) {
          contentHtml += `<ul>${listItems.join('')}</ul>`;
          listItems.length = 0;
        }
        contentHtml += `<div class="cli-box-line">${parseInlineMarkdown(escapeHtml(l))}</div>`;
      }
    }
    if (listItems.length > 0) {
      contentHtml += `<ul>${listItems.join('')}</ul>`;
    }

    const html = `<div class="cli-box">
      <div class="cli-box-header">
        <span class="cli-box-icon">⚡</span>
        <span class="cli-box-title">${escapeHtml(cleanTitle)}</span>
      </div>
      <div class="cli-box-body">${contentHtml}</div>
    </div>`;
    return saveBlock(html);
  });

  // Step 3: Handle GitHub Callout Alerts (> [!NOTE], > [!TIP], etc.)
  text = text.replace(/(?:^[ \t]*>[ \t]*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*\n)((?:^[ \t]*>[ \t]?[^\n]*\n?)+)/gim, (match, type, content) => {
    const cleanType = type.toUpperCase();
    const cleanContent = content.split('\n')
      .map(l => l.replace(/^[ \t]*>[ \t]?/, ''))
      .join('\n').trim();
    
    const icons = {
      NOTE: 'ℹ️',
      TIP: '💡',
      IMPORTANT: '❗',
      WARNING: '⚠️',
      CAUTION: '🛑'
    };

    const html = `<div class="callout callout-${cleanType.toLowerCase()}">
      <div class="callout-title"><span class="callout-icon">${icons[cleanType] || 'ℹ️'}</span> ${cleanType}</div>
      <div class="callout-content">${parseInlineMarkdown(escapeHtml(cleanContent))}</div>
    </div>`;
    return saveBlock(html);
  });

  // Step 4: Handle standard blockquotes (> ...)
  text = text.replace(/(?:^[ \t]*>[ \t]?[^\n]+(?:\n[ \t]*>[ \t]?[^\n]+)*)/gm, (match) => {
    const content = match.split('\n')
      .map(l => l.replace(/^[ \t]*>[ \t]?/, ''))
      .join('<br>');
    const html = `<blockquote class="md-blockquote">${parseInlineMarkdown(escapeHtml(content))}</blockquote>`;
    return saveBlock(html);
  });

  // Step 5: Normalize and Parse Markdown Tables
  text = text.replace(/\|\s*\|\s*/g, '|\n| ');

  const lines = text.split('\n');
  const output = [];
  let inTable = false;
  let tableLines = [];
  let inList = false;
  let listType = 'ul';
  let listItems = [];

  const flushTable = () => {
    if (tableLines.length >= 2) {
      let headerCells = [];
      let alignments = [];
      let bodyRows = [];

      let sepIdx = -1;
      for (let i = 0; i < tableLines.length; i++) {
        if (/^[\|\s:\-]+$/.test(tableLines[i]) && tableLines[i].includes('-')) {
          sepIdx = i;
          break;
        }
      }

      if (sepIdx > 0) {
        const rawHeader = tableLines.slice(0, sepIdx).join(' ');
        headerCells = rawHeader.split('|')
          .map(c => c.trim())
          .filter(c => c.length > 0);

        const sepRow = tableLines[sepIdx];
        const sepCols = sepRow.split('|')
          .map(c => c.trim())
          .filter(c => c.length > 0);

        alignments = sepCols.map(s => {
          if (s.startsWith(':') && s.endsWith(':')) return 'center';
          if (s.endsWith(':')) return 'right';
          return 'left';
        });

        for (let i = sepIdx + 1; i < tableLines.length; i++) {
          const rowStr = tableLines[i].trim();
          if (!rowStr) continue;
          const cells = rowStr.split('|')
            .map(c => c.trim());
          
          if (rowStr.startsWith('|') && cells.length > 0 && cells[0] === '') cells.shift();
          if (rowStr.endsWith('|') && cells.length > 0 && cells[cells.length - 1] === '') cells.pop();

          if (cells.length > 0) bodyRows.push(cells);
        }

        let tableHtml = '<div class="table-container"><table class="md-table"><thead><tr>';
        headerCells.forEach((h, idx) => {
          const align = alignments[idx] || 'left';
          tableHtml += `<th style="text-align:${align}">${parseInlineMarkdown(escapeHtml(h))}</th>`;
        });
        tableHtml += '</tr></thead><tbody>';

        bodyRows.forEach(row => {
          tableHtml += '<tr>';
          for (let idx = 0; idx < Math.max(headerCells.length, row.length); idx++) {
            const val = row[idx] || '';
            const align = alignments[idx] || 'left';
            tableHtml += `<td style="text-align:${align}">${parseInlineMarkdown(escapeHtml(val))}</td>`;
          }
          tableHtml += '</tr>';
        });
        tableHtml += '</tbody></table></div>';
        output.push(saveBlock(tableHtml));
      } else {
        output.push(tableLines.map(l => parseInlineMarkdown(escapeHtml(l))).join('<br>'));
      }
    } else {
      output.push(tableLines.map(l => parseInlineMarkdown(escapeHtml(l))).join('<br>'));
    }
    tableLines = [];
    inTable = false;
  };

  const flushList = () => {
    if (listItems.length > 0) {
      const listHtml = `<${listType}>${listItems.map(item => `<li>${parseInlineMarkdown(escapeHtml(item))}</li>`).join('')}</${listType}>`;
      output.push(saveBlock(listHtml));
      listItems = [];
    }
    inList = false;
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Check for Table Row
    if (trimmed.startsWith('|') && trimmed.includes('|', 1)) {
      if (inList) flushList();
      inTable = true;
      tableLines.push(trimmed);
      continue;
    } else if (inTable) {
      flushTable();
    }

    // Check for Headings
    if (/^#{1,6}\s+/.test(trimmed)) {
      if (inList) flushList();
      const level = trimmed.match(/^#+/)[0].length;
      const text = trimmed.replace(/^#+\s*/, '');
      output.push(`<h${level}>${parseInlineMarkdown(escapeHtml(text))}</h${level}>`);
      continue;
    }

    // Check for Horizontal Rule
    if (/^(?:---|\*\*\*|___)$/.test(trimmed)) {
      if (inList) flushList();
      output.push('<hr>');
      continue;
    }

    // Check for Unordered List
    if (/^[•\-\*\+]\s+/.test(trimmed)) {
      if (inList && listType !== 'ul') flushList();
      inList = true;
      listType = 'ul';
      listItems.push(trimmed.replace(/^[•\-\*\+]\s+/, ''));
      continue;
    }

    // Check for Ordered List
    if (/^\d+\.\s+/.test(trimmed)) {
      if (inList && listType !== 'ol') flushList();
      inList = true;
      listType = 'ol';
      listItems.push(trimmed.replace(/^\d+\.\s+/, ''));
      continue;
    }

    // Blank line or regular text
    if (inList) flushList();

    if (!trimmed) {
      output.push('');
    } else if (trimmed.startsWith('%%%HTML_BLOCK_')) {
      output.push(trimmed);
    } else {
      output.push(`<p>${parseInlineMarkdown(escapeHtml(trimmed))}</p>`);
    }
  }

  if (inTable) flushTable();
  if (inList) flushList();

  let finalHtml = output.filter(chunk => chunk.length > 0).join('\n');

  // Step 6: Restore all HTML blocks
  finalHtml = finalHtml.replace(/<p>\s*%%%HTML_BLOCK_(\d+)%%%\s*<\/p>|%%%HTML_BLOCK_(\d+)%%%/g, (match, p1, p2) => {
    const idx = parseInt(p1 || p2, 10);
    return htmlBlocks[idx] || '';
  });

  return finalHtml;
}

// ─────────────────────────────────────────────────────────────
// AUTONOMOUS LOOP AGENT CONTROLLER (AUTO-DEV SWARM & SESSIONS)
// ─────────────────────────────────────────────────────────────
async function loadLoopSessionsList() {
  try {
    const res = await fetch('/api/loop/sessions', { cache: 'no-store' });
    const list = await res.json();
    allLoopSessions = list || [];
    await loadSessionsList();
    const sel = document.getElementById('loopSessionSelect');
    if (!sel) return;
    sel.innerHTML = '';

    if (!allLoopSessions || allLoopSessions.length === 0) {
      sel.innerHTML = '<option value="">No loop sessions</option>';
      return;
    }

    const savedLoopSessionId = localStorage.getItem('swarm_active_loop_session');
    if (savedLoopSessionId && allLoopSessions.some(s => (s.id || s.session_id) === savedLoopSessionId)) {
      activeLoopSessionId = savedLoopSessionId;
    } else if (!activeLoopSessionId) {
      activeLoopSessionId = allLoopSessions[0].id || allLoopSessions[0].session_id;
    }

    allLoopSessions.forEach(s => {
      const opt = document.createElement('option');
      const sId = s.id || s.session_id;
      opt.value = sId;
      const statusIcons = {
        running: '🟢',
        completed: '✅',
        paused: '⏸️',
        interrupted: '⚠️',
        recovering: '🔄',
        failed: '❌',
        idle: '⏹️'
      };
      const statusLabels = {
        interrupted: 'interrupted / recoverable',
        recovering: 'recovering...',
        running: 'running',
        completed: 'completed',
        paused: 'paused',
        failed: 'failed',
        idle: 'idle'
      };
      const icon = statusIcons[s.status] || '🔄';
      const label = statusLabels[s.status] || s.status || 'idle';
      const title = s.title || s.name || s.goal || 'Untitled Loop Run';
      opt.innerText = `${icon} ${title} (${label})`;
      if (sId === activeLoopSessionId) opt.selected = true;
      sel.appendChild(opt);
    });
  } catch(e) { handleServerDisconnected(); }
}

async function onLoopSessionChanged() {
  const sel = document.getElementById('loopSessionSelect');
  if (!sel || !sel.value) return;
  activeLoopSessionId = sel.value;
  try { localStorage.setItem('swarm_active_loop_session', activeLoopSessionId); } catch(_) {}
  try {
    const res = await fetch(`/api/loop/sessions/${encodeURIComponent(activeLoopSessionId)}/select`, { method: 'POST' });
    const data = await res.json();
    if (data.state) {
      renderLoopDashboard(data.state);
    } else {
      await pollLoopState();
    }
    showToast("Switched Auto-Dev Loop session", "info", 1800);
  } catch(e) { handleServerDisconnected(); }
}

async function createNewLoopSessionUI() {
  try {
    const res = await fetch('/api/loop/sessions/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'New Auto-Dev Loop',
        goal: '',
        repo_path: currentRepoPath
      })
    });
    const data = await res.json();
    activeLoopSessionId = data.id || data.session_id;
    const goalInput = document.getElementById('loopGoalInput');
    if (goalInput) goalInput.value = '';
    await loadLoopSessionsList();
    await pollLoopState();
    showToast("✓ Created new Auto-Dev Loop session", "success");
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function deleteCurrentLoopSessionUI() {
  if (!activeLoopSessionId) return;
  if (!confirm("Are you sure you want to delete this Auto-Dev Loop session?")) return;
  try {
    await fetch('/api/loop/sessions/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: activeLoopSessionId })
    });
    activeLoopSessionId = "";
    showToast("Loop session deleted", "info");
    await loadLoopSessionsList();
    await pollLoopState();
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function transferAdvisorChatToLoop(customGoal = null, autoStart = true) {
  showToast("🚀 Synthesizing and transferring Advisor blueprint to Auto-Dev Loop...", "info", 3000);
  try {
    const res = await fetch('/api/advisor/transfer_to_loop', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSessionId,
        custom_goal: customGoal || "",
        auto_start: autoStart,
        repo_path: currentRepoPath
      })
    });
    const data = await res.json();
    if (data.success) {
      activeLoopSessionId = data.loop_session_id || data.session_id;
      switchTab('loop');
      const goalInput = document.getElementById('loopGoalInput');
      if (goalInput && data.goal) {
        goalInput.value = data.goal;
      }
      await loadLoopSessionsList();
      if (data.state) {
        renderLoopDashboard(data.state);
      } else {
        await pollLoopState();
      }
      showToast("🚀 Transferred to Auto-Dev Loop! Autonomous execution started.", "success", 4000);
    } else {
      showToast("Transfer failed: " + (data.error || "Unknown error"), "error", 4500);
    }
  } catch(e) {
    showToast("Transfer error: " + e.message, "error");
  }
}

async function jumpToLinkedAdvisorSession(advId) {
  if (!advId) {
    try {
      const res = await fetch('/api/loop/status', { cache: 'no-store' });
      const state = await res.json();
      advId = state.advisor_session_id;
    } catch(e) {}
  }
  if (advId) {
    activeSessionId = advId;
    switchTab('chat');
    await loadSessionsList();
    showToast(`Loaded linked Advisor Chat session`, "info", 2000);
  }
}

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
      body: JSON.stringify({
        goal: goal,
        repo_path: currentRepoPath,
        session_id: activeLoopSessionId
      })
    });
    const data = await res.json();
    if (data.success) {
      if (data.loop_id || data.session_id) {
        activeLoopSessionId = data.loop_id || data.session_id;
      }
      showToast("🚀 Autonomous Swarm Loop started!", "success");
      await loadLoopSessionsList();
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
    await loadLoopSessionsList();
    pollLoopState();
  } catch(e) { handleServerDisconnected(); }
}

async function resumeAutonomousLoop() {
  try {
    const res = await fetch('/api/loop/resume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeLoopSessionId })
    });
    const data = await res.json();
    if (data.success) {
      showToast("▶️ Swarm loop resumed from checkpoint", "success");
    } else {
      showToast("Resume error: " + (data.error || "Failed"), "error");
    }
    await loadLoopSessionsList();
    pollLoopState();
  } catch(e) { handleServerDisconnected(); }
}

async function stopAutonomousLoop() {
  try {
    await fetch('/api/loop/stop', { method: 'POST' });
    showToast("⏹️ Swarm loop stopped", "warn");
    await loadLoopSessionsList();
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
  if (!state) return;

  const currentId = state.id || state.session_id;
  if (currentId && currentId !== activeLoopSessionId) {
    activeLoopSessionId = currentId;
  }

  // Update session dropdown selection if available
  const sel = document.getElementById('loopSessionSelect');
  if (sel && activeLoopSessionId && sel.value !== activeLoopSessionId) {
    sel.value = activeLoopSessionId;
  }

  // Linked Advisor Badge
  const linkedAdvBadge = document.getElementById('loopLinkedAdvisorBadge');
  if (linkedAdvBadge) {
    if (state.advisor_session_id) {
      linkedAdvBadge.style.display = 'inline-flex';
      linkedAdvBadge.innerText = `💬 Linked Advisor Chat (${state.advisor_session_id.substring(0, 12)}...) ↗`;
      linkedAdvBadge.onclick = () => jumpToLinkedAdvisorSession(state.advisor_session_id);
    } else {
      linkedAdvBadge.style.display = 'none';
    }
  }

  // Auto-populate goal input if empty
  const goalInput = document.getElementById('loopGoalInput');
  if (goalInput && !goalInput.value && state.goal) {
    goalInput.value = state.goal;
  }

  const statusBadge = document.getElementById('loopStatusBadge');
  const startBtn = document.getElementById('loopStartBtn');
  const resumeBtn = document.getElementById('loopResumeBtn');
  const pauseBtn = document.getElementById('loopPauseBtn');
  const stopBtn = document.getElementById('loopStopBtn');

  if (statusBadge) {
    const rawStatus = (state.status || 'idle').toLowerCase();
    if (rawStatus === 'interrupted') {
      statusBadge.innerText = '⚠️ INTERRUPTED / RECOVERABLE';
      statusBadge.className = 'status-badge badge-interrupted';
    } else if (rawStatus === 'recovering') {
      statusBadge.innerText = '🔄 RECOVERING...';
      statusBadge.className = 'status-badge badge-running';
    } else if (rawStatus === 'paused') {
      statusBadge.innerText = '⏸️ PAUSED';
      statusBadge.className = 'status-badge badge-paused';
    } else if (rawStatus === 'running') {
      statusBadge.innerText = '🟢 RUNNING';
      statusBadge.className = 'status-badge badge-running';
    } else if (rawStatus === 'completed') {
      statusBadge.innerText = '✅ COMPLETED';
      statusBadge.className = 'status-badge badge-online';
    } else if (rawStatus === 'failed') {
      statusBadge.innerText = '❌ FAILED';
      statusBadge.className = 'status-badge badge-offline';
    } else {
      statusBadge.innerText = 'IDLE';
      statusBadge.className = 'status-badge badge-idle';
    }
  }

  if (startBtn && pauseBtn && stopBtn) {
    const rawStatus = (state.status || 'idle').toLowerCase();
    if (rawStatus === 'running') {
      startBtn.style.display = 'none';
      if (resumeBtn) resumeBtn.style.display = 'none';
      pauseBtn.style.display = 'inline-flex';
      pauseBtn.innerText = '⏸️ Pause';
      stopBtn.style.display = 'inline-flex';
    } else if (rawStatus === 'paused') {
      startBtn.style.display = 'none';
      pauseBtn.style.display = 'none';
      if (resumeBtn) {
        resumeBtn.style.display = 'inline-flex';
        resumeBtn.innerText = '▶️ Resume Loop';
        resumeBtn.style.background = 'var(--orange)';
      }
      stopBtn.style.display = 'inline-flex';
    } else if (rawStatus === 'interrupted') {
      startBtn.style.display = 'none';
      pauseBtn.style.display = 'none';
      if (resumeBtn) {
        resumeBtn.style.display = 'inline-flex';
        resumeBtn.innerText = '▶️ Resume Loop (Recover)';
        resumeBtn.style.background = 'var(--orange)';
      }
      stopBtn.style.display = 'inline-flex';
    } else {
      startBtn.style.display = 'inline-flex';
      if (resumeBtn) resumeBtn.style.display = 'none';
      pauseBtn.style.display = 'none';
      stopBtn.style.display = 'none';
    }
  }

  // Render Active Sub-Agent & GitHub Tracking Issue
  const activeBox = document.getElementById('loopActiveAgentBox');
  if (activeBox) {
    let html = '';
    if (state.github_issue && state.github_issue.url) {
      const issueNum = state.github_issue.issue_number ? `#${state.github_issue.issue_number}` : 'Issue';
      html += `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; padding-bottom:6px; border-bottom:1px solid var(--ink-500);">
          <span style="font-size:12px; font-weight:700; color:var(--text);">🐙 GitHub Tracker:</span>
          <a href="${escapeHtml(state.github_issue.url)}" target="_blank" style="font-family:var(--font-mono); font-size:11.5px; color:var(--accent); font-weight:700; text-decoration:none; background:var(--ink-700); padding:2px 8px; border-radius:4px; border:1px solid var(--line-strong);">
            ${escapeHtml(issueNum)} ↗
          </a>
        </div>
      `;
    }

    if (state.active_subagents && state.active_subagents.length > 1) {
      let multiHtml = `
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; padding-bottom:6px; border-bottom:1px solid var(--ink-500);">
          <span style="font-weight:700; color:var(--accent); font-size:13.5px;">⚡ Parallel Fan-Out: ${state.active_subagents.length} / 8 Agents Active</span>
          <span class="file-status-badge status-a" style="background:var(--green-soft); color:var(--green); border-color:var(--green-strong);">PARALLEL CONCURRENCY</span>
        </div>
        <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:8px;">
      `;
      state.active_subagents.forEach(sa => {
        multiHtml += `
          <div style="background:var(--ink-900); border:1px solid var(--ink-500); border-left:3px solid var(--green); border-radius:6px; padding:6px 10px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-weight:700; color:var(--text-bright); font-size:12px;">${escapeHtml(sa.name)}</span>
              <span style="font-size:9.5px; font-family:var(--font-mono); color:var(--green); font-weight:700;">RUNNING</span>
            </div>
            <div style="font-size:10.5px; color:var(--text-muted);">${escapeHtml(sa.slot || '')}</div>
            <div style="font-size:11px; color:var(--accent); font-family:var(--font-mono); margin-top:2px;">
              ${escapeHtml(sa.status || 'Executing')}
            </div>
          </div>
        `;
      });
      multiHtml += `</div>`;
      activeBox.innerHTML = html + multiHtml;
      activeBox.style.display = 'block';
    } else if (state.active_subagent) {
      const sa = state.active_subagent;
      html += `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:700; color:var(--text-bright); font-size:13.5px;">⚡ Active: ${escapeHtml(sa.name)}</span>
          <span class="file-status-badge status-a">${escapeHtml(sa.slot || '')}</span>
        </div>
        <div style="font-size:12px; color:var(--accent); font-family:var(--font-mono); margin-top:2px;">
          Working on: <b>${escapeHtml(sa.task_title || '')}</b> (${escapeHtml(sa.status || 'Active')})
        </div>
      `;
      activeBox.innerHTML = html;
      activeBox.style.display = 'block';
    } else if (state.github_issue) {
      activeBox.innerHTML = html;
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
      taskContainer.innerHTML = '<div style="color:var(--text-muted); padding:16px; text-align:center; grid-column:1/-1;">No tasks scheduled yet. Start a goal to run Pre-Flight Research and Zero-Trust Multi-Agent Verification.</div>';
    } else {
      taskContainer.innerHTML = '';
      tasks.forEach((t) => {
        const card = document.createElement('div');
        const isCurrent = (
          t.id === state.current_task_id ||
          (state.current_task_ids && state.current_task_ids.includes(t.id)) ||
          t.status === 'in_progress'
        ) && (state.status === 'running' || state.status === 'recovering');

        card.className = `task-pipeline-card ${isCurrent ? 'in-progress' : (t.status === 'completed' ? 'completed' : '')}`;
        
        const roleColors = {
          pm: 'status-u',
          dev: 'status-m',
          qa: 'status-a',
          review: 'status-d',
          oracle: 'status-u'
        };
        const badgeClass = roleColors[t.role] || 'status-u';

        const attemptsHtml = t.attempts ? `<span style="font-size:10px; font-family:var(--font-mono); background:var(--ink-500); color:var(--accent); padding:1px 5px; border-radius:4px;">Attempt ${t.attempts}/3</span>` : '';
        const skillHtml = t.injected_skill ? `<div style="font-family:var(--font-mono); font-size:10.5px; color:var(--accent); background:var(--ink-900); padding:2px 6px; border-radius:4px; border:1px solid var(--ink-500);">🎯 Skill: ${escapeHtml(t.injected_skill)}</div>` : '';
        const certHtml = t.judge_certificate ? `<div style="font-size:10.5px; color:var(--green); background:var(--green-soft); padding:3px 6px; border-radius:4px; border:1px solid var(--green-strong); font-weight:700;">⚖️ Auto-Judge Verified</div>` : '';

        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="display:flex; align-items:center; gap:6px;">
              <span class="file-status-badge ${badgeClass}">${escapeHtml(t.role.toUpperCase())}</span>
              ${attemptsHtml}
            </div>
            <span style="font-size:11px; font-family:var(--font-mono); font-weight:700; color:${t.status === 'completed' ? 'var(--green)' : (isCurrent ? 'var(--accent)' : 'var(--text-muted)')};">
              ${isCurrent ? '⚡ IN PROGRESS' : escapeHtml(t.status.toUpperCase())}
            </span>
          </div>
          <div style="font-weight:700; color:var(--text-bright); font-size:13px; line-height:1.4;">${escapeHtml(t.title)}</div>
          <div style="font-size:11.5px; color:var(--text);">${escapeHtml(t.description || '')}</div>
          ${skillHtml}
          ${certHtml}
          <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent); background:var(--ink-900); padding:4px 8px; border-radius:4px; border:1px solid var(--ink-500);">
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
            <span style="font-size:11.5px; font-weight:700; color:var(--purple);">📡 ${escapeHtml(p.subagent)} ➔ 👑 Lead Advisor</span>
            <span style="font-size:10.5px; font-family:var(--font-mono); color:var(--text-muted);">${escapeHtml(p.timestamp)} (${p.duration}s)</span>
          </div>
          <div class="advisor-ping-q">❓ "${escapeHtml(p.question)}"</div>
          <div class="advisor-ping-a markdown-body">${parseMarkdown(p.answer)}</div>
        `;
        pingContainer.appendChild(div);
      });
    }
  }

  // Render Final Summary & Verification Certificate if complete
  const finalSummaryDiv = document.getElementById('loopFinalSummaryContainer');
  if (finalSummaryDiv) {
    const summaryText = state.final_summary || state.verification_certificate || "";
    if (summaryText && (state.status === 'completed' || state.status === 'idle')) {
      finalSummaryDiv.style.display = 'block';
      document.getElementById('loopFinalSummaryContent').innerHTML = parseMarkdown(summaryText);
    } else {
      finalSummaryDiv.style.display = 'none';
    }
  }

  // Update Live Telemetry Stream with status changes
  const stateKey = `${state.id || ''}_${state.status}_${state.current_step}_${state.tasks ? state.tasks.map(t=>t.status).join(',') : ''}_${(state.advisor_pings || []).length}`;
  if (stateKey !== lastLoopTaskStateKey) {
    lastLoopTaskStateKey = stateKey;
    if (state.status === 'running') {
      const activeTask = (state.tasks || []).find(t => t.status === 'in-progress' || t.status === 'running');
      if (activeTask) {
        appendLoopLiveLog(`Task active: "${activeTask.title}" assigned to [${activeTask.assigned_agent}]`, 'info', 'TASK');
      } else {
        appendLoopLiveLog(`Loop iteration step ${state.current_step || 1} executing. Status: ${state.status.toUpperCase()}`, 'info', 'LOOP');
      }
    } else if (state.status === 'completed') {
      appendLoopLiveLog(`All pipeline tasks completed with full verification certificate.`, 'success', 'JUDGE');
    } else if (state.status === 'failed') {
      appendLoopLiveLog(`Loop execution encountered failure state.`, 'error', 'ERROR');
    }
    
    // Check if new advisor ping
    const pings = state.advisor_pings || [];
    if (pings.length > 0) {
      const latestPing = pings[pings.length - 1];
      if (latestPing && latestPing._logged !== true) {
        latestPing._logged = true;
        appendLoopLiveLog(`Advisor Ping: ${latestPing.subagent} asked "${latestPing.question.substring(0, 48)}..."`, 'info', 'ADVISOR');
      }
    }
  }
}

function setLoopGoalPrompt(text) {
  document.getElementById('loopGoalInput').value = text;
}

// ─────────────────────────────────────────────────────────────
// FULL GITHUB DESKTOP CLIENT & CUSTOM CONTEXT MENU ENGINE
// ─────────────────────────────────────────────────────────────
let diffViewMode = 'unified';
let currentRawDiff = '';
let activeGhdSubTab = 'changes';
let allHistoryCommits = [];
let allGithubIssues = [];
let issueStateFilter = 'open';
let confirmActionCallback = null;

async function loadGitHubDesktopState() {
  try {
    const controller = new AbortController();
    const tId = setTimeout(() => controller.abort(), 3500);
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

    document.getElementById('ghdRepoName').innerText = data.repo_name || "Repository";
    document.getElementById('ghdCurrentBranch').innerText = data.branch || "main";
    document.getElementById('commitTargetBranch').innerText = data.branch || "main";
    
    const aheadCount = data.ahead || 0;
    const behindCount = data.behind || 0;
    const aheadEl = document.getElementById('ghdAheadCount');
    const behindEl = document.getElementById('ghdBehindCount');
    
    if (aheadEl) {
      aheadEl.innerText = aheadCount;
      aheadEl.style.display = aheadCount > 0 ? 'inline-block' : 'none';
    }
    if (behindEl) {
      behindEl.innerText = behindCount;
      behindEl.style.display = behindCount > 0 ? 'inline-block' : 'none';
    }

    const totalChanged = (data.staged?.length || 0) + (data.unstaged?.length || 0) + (data.untracked?.length || 0) || (data.changed_files ? data.changed_files.length : 0);
    const changesCountEl = document.getElementById('ghdChangesCount');
    if (changesCountEl) changesCountEl.innerText = totalChanged;

    const stashes = data.stashes || [];
    const stashesBadge = document.getElementById('ghdStashesBadgeCount');
    if (stashesBadge) stashesBadge.innerText = stashes.length;

    renderStashBanner(stashes);

    allBranches = data.branches || [];
    renderBranchModalList(allBranches, data.branch);

    allHistoryCommits = data.history || [];
    allGithubIssues = data.issues || [];

    renderChangesList(data);
    renderHistoryList(allHistoryCommits);
    renderBranchesTab(allBranches, data.branch);
    renderIssuesTab(allGithubIssues);
    renderStashesTab(stashes, data.worktrees || []);

  } catch(e) {
    handleServerDisconnected();
  }
}

function switchGhdTab(tab) {
  activeGhdSubTab = tab;
  if (window.innerWidth <= 768) {
    toggleGhdMobileView('list');
  }
  const tabs = ['changes', 'history', 'branches', 'issues', 'stashes'];
  tabs.forEach(t => {
    const btn = document.getElementById(`ghdTab${t.charAt(0).toUpperCase() + t.slice(1)}Btn`);
    const pane = document.getElementById(`ghd${t.charAt(0).toUpperCase() + t.slice(1)}Tab`);
    if (btn) btn.className = (t === tab) ? 'ghd-nav-tab active' : 'ghd-nav-tab';
    if (pane) pane.style.display = (t === tab) ? 'flex' : 'none';
  });

  if (tab === 'issues' && (!allGithubIssues || allGithubIssues.length === 0)) {
    loadGithubIssues();
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
      <span>📦 Stashed changes on <b>${escapeHtml(latest.branch || 'current')}</b></span>
      <span style="font-size:11px; color:var(--text-muted);">${escapeHtml(latest.date || '')}</span>
    </div>
    <div style="font-family:var(--font-mono); font-size:11.5px; color:var(--text); text-overflow:ellipsis; overflow:hidden; white-space:nowrap;">
      ${escapeHtml(latest.message || 'WIP Stash')}
    </div>
    <div style="display:flex; justify-content:flex-end; gap:8px; margin-top:4px;">
      <button class="action-btn action-btn--primary action-btn--sm" onclick="popStash(0)">
        ↩️ Restore
      </button>
      <button class="action-btn danger action-btn--sm" onclick="dropStash(0)">
        🗑️ Discard
      </button>
      <button class="action-btn action-btn--sm" onclick="switchGhdTab('stashes')">
        View All (${stashes.length})
      </button>
    </div>
  `;
}

function renderChangesList(data) {
  const staged = data.staged || [];
  const unstaged = data.unstaged || [];
  const untracked = data.untracked || [];
  
  const stagedSec = document.getElementById('ghdStagedSection');
  const stagedList = document.getElementById('ghdStagedItems');
  const stagedCountEl = document.getElementById('ghdStagedCount');
  
  const unstagedSec = document.getElementById('ghdUnstagedSection');
  const unstagedList = document.getElementById('ghdUnstagedItems');
  const unstagedCountEl = document.getElementById('ghdUnstagedCount');
  
  const untrackedSec = document.getElementById('ghdUntrackedSection');
  const untrackedList = document.getElementById('ghdUntrackedItems');
  const untrackedCountEl = document.getElementById('ghdUntrackedCount');
  
  const noChangesMsg = document.getElementById('ghdNoChangesMsg');

  if (stagedCountEl) stagedCountEl.innerText = staged.length;
  if (unstagedCountEl) unstagedCountEl.innerText = unstaged.length;
  if (untrackedCountEl) untrackedCountEl.innerText = untracked.length;

  const totalCount = staged.length + unstaged.length + untracked.length;

  if (totalCount === 0) {
    if (stagedSec) stagedSec.style.display = 'none';
    if (unstagedSec) unstagedSec.style.display = 'none';
    if (untrackedSec) untrackedSec.style.display = 'none';
    if (noChangesMsg) noChangesMsg.style.display = 'block';
    
    document.getElementById('ghdDiffTitle').innerText = "Working tree clean";
    document.getElementById('ghdDiffContent').innerHTML = '<div style="color:var(--text-muted); padding:30px; text-align:center;">✨ Working tree is completely clean. No modified files.</div>';
    document.getElementById('ghdDiscardFileBtn').style.display = 'none';
    document.getElementById('ghdToggleStageFileBtn').style.display = 'none';
    document.getElementById('ghdSendToLoopBtn').style.display = 'none';
    document.getElementById('ghdDiffStats').style.display = 'none';
    updateCommitBtnState();
    return;
  }

  if (noChangesMsg) noChangesMsg.style.display = 'none';

  // Render Staged Section
  if (stagedSec && stagedList) {
    stagedSec.style.display = staged.length > 0 ? 'flex' : 'none';
    stagedList.innerHTML = '';
    staged.forEach(f => {
      stagedList.appendChild(createFileRowElement(f, true));
    });
  }

  // Render Unstaged Section
  if (unstagedSec && unstagedList) {
    unstagedSec.style.display = unstaged.length > 0 ? 'flex' : 'none';
    unstagedList.innerHTML = '';
    unstaged.forEach(f => {
      unstagedList.appendChild(createFileRowElement(f, false));
    });
  }

  // Render Untracked Section
  if (untrackedSec && untrackedList) {
    untrackedSec.style.display = untracked.length > 0 ? 'flex' : 'none';
    untrackedList.innerHTML = '';
    untracked.forEach(f => {
      untrackedList.appendChild(createFileRowElement(f, false));
    });
  }

  const allList = [...staged, ...unstaged, ...untracked];
  if (!selectedGhdFile || !allList.find(f => f.path === selectedGhdFile)) {
    const first = allList[0];
    if (first) selectFileForDiff(first.path, first.staged || false);
  }
}

function createFileRowElement(f, isStaged) {
  const row = document.createElement('div');
  row.className = `ghd-file-row ${f.path === selectedGhdFile ? 'selected' : ''}`;
  row.setAttribute('data-context', 'file');
  row.setAttribute('data-path', f.path);
  row.setAttribute('data-staged', isStaged ? 'true' : 'false');
  row.setAttribute('data-status', f.status);
  row.onclick = () => selectFileForDiff(f.path, isStaged);

  const statusClass = `status-${(f.status || 'm').toLowerCase()}`;
  row.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; overflow:hidden; flex:1;">
      <input type="checkbox" ${checkedFiles.has(f.path) ? 'checked' : ''} onclick="event.stopPropagation(); toggleFileCheck('${escapeJs(f.path)}', this.checked)">
      <span style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${escapeHtml(f.path)}">${escapeHtml(f.path)}</span>
    </div>
    <div style="display:flex; align-items:center; gap:6px;">
      <div class="ghd-file-actions" onclick="event.stopPropagation()">
        ${isStaged ? 
          `<button class="ghd-mini-btn" onclick="unstageFile('${escapeJs(f.path)}')" title="Unstage file">↩️</button>` : 
          `<button class="ghd-mini-btn" onclick="stageFile('${escapeJs(f.path)}')" title="Stage file">📝</button>`
        }
        <button class="ghd-mini-btn ghd-mini-btn--danger" onclick="discardFileConfirm('${escapeJs(f.path)}')" title="Discard changes">🗑️</button>
      </div>
      <span class="file-status-badge ${statusClass}">${escapeHtml(f.status || 'M')}</span>
    </div>
  `;
  return row;
}

function toggleSectionCollapse(containerId) {
  const el = document.getElementById(containerId);
  if (el) {
    el.style.display = el.style.display === 'none' ? 'flex' : 'none';
  }
}

function toggleFileCheck(path, isChecked) {
  if (isChecked) checkedFiles.add(path);
  else checkedFiles.delete(path);
  updateSelectedCount();
}

function toggleSelectAllFiles(isChecked) {
  checkedFiles.clear();
  if (isChecked && currentGhdState) {
    const allFiles = [...(currentGhdState.staged || []), ...(currentGhdState.unstaged || []), ...(currentGhdState.untracked || [])];
    allFiles.forEach(f => checkedFiles.add(f.path));
  }
  const checkboxes = document.querySelectorAll('#ghdChangesList input[type="checkbox"]');
  checkboxes.forEach(cb => cb.checked = isChecked);
  updateSelectedCount();
}

function updateSelectedCount() {
  updateCommitBtnState();
}

function updateCommitBtnState() {
  const summary = document.getElementById('commitSummaryInput').value.trim();
  const btn = document.getElementById('commitActionBtn');
  const hasStaged = (currentGhdState && currentGhdState.staged && currentGhdState.staged.length > 0);
  const hasChecked = checkedFiles.size > 0;
  
  if (btn) {
    btn.disabled = (!hasStaged && !hasChecked) || !summary;
    if (hasStaged) {
      btn.innerText = `✓ Commit ${currentGhdState.staged.length} staged file(s) to ${currentGhdState.branch || 'main'}`;
    } else if (hasChecked) {
      btn.innerText = `✓ Stage & Commit ${checkedFiles.size} selected file(s) to ${currentGhdState ? currentGhdState.branch : 'main'}`;
    } else {
      btn.innerText = `✓ Commit to ${currentGhdState ? currentGhdState.branch : 'main'}`;
    }
  }
}

async function stageFile(path) {
  try {
    const res = await fetch('/api/git/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, files: [path] })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`📝 Staged ${path}`, "info", 1800);
      await loadGitHubDesktopState();
    } else {
      showToast(`Stage failed: ${data.error || data.stderr}`, "error");
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

async function unstageFile(path) {
  try {
    const res = await fetch('/api/git/unstage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, files: [path] })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`↩️ Unstaged ${path}`, "info", 1800);
      await loadGitHubDesktopState();
    } else {
      showToast(`Unstage failed: ${data.error || data.stderr}`, "error");
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

async function stageAllChanges() {
  try {
    const allFiles = [...(currentGhdState?.unstaged || []), ...(currentGhdState?.untracked || [])].map(f => f.path);
    if (allFiles.length === 0) {
      showToast("No unstaged files to stage", "info");
      return;
    }
    const res = await fetch('/api/git/stage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, files: allFiles })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Staged all ${allFiles.length} file(s)`, "success");
      await loadGitHubDesktopState();
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

async function unstageAllChanges() {
  try {
    const stagedFiles = (currentGhdState?.staged || []).map(f => f.path);
    if (stagedFiles.length === 0) {
      showToast("No staged files to unstage", "info");
      return;
    }
    const res = await fetch('/api/git/unstage', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, files: stagedFiles })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Unstaged all ${stagedFiles.length} file(s)`, "info");
      await loadGitHubDesktopState();
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

function discardFileConfirm(path) {
  openGhdConfirmModal(
    "⚠️ Discard File Changes",
    `Are you sure you want to discard all local changes to <b>${escapeHtml(path)}</b>? This cannot be undone.`,
    "Discard Changes",
    async () => {
      await executeDiscardFiles([path]);
    }
  );
}

function discardAllChangesConfirm() {
  const allFiles = [...(currentGhdState?.staged || []), ...(currentGhdState?.unstaged || []), ...(currentGhdState?.untracked || [])].map(f => f.path);
  if (allFiles.length === 0) return;
  openGhdConfirmModal(
    "⚠️ Discard ALL Local Changes",
    `Are you sure you want to discard all changes across <b>${allFiles.length} file(s)</b>? All unstaged edits and untracked files will be permanently deleted.`,
    "Discard All Changes",
    async () => {
      await executeDiscardFiles(allFiles);
    }
  );
}

async function executeDiscardFiles(files) {
  try {
    const res = await fetch('/api/git/discard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, files: files })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Discarded changes to ${files.length} file(s)`, "info");
      selectedGhdFile = "";
      await loadGitHubDesktopState();
    } else {
      showToast("Discard error: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function discardSelectedFile() {
  if (selectedGhdFile) {
    discardFileConfirm(selectedGhdFile);
  }
}

async function toggleStageSelectedFile() {
  if (!selectedGhdFile) return;
  const isStaged = (currentGhdState?.staged || []).some(f => f.path === selectedGhdFile);
  if (isStaged) {
    await unstageFile(selectedGhdFile);
  } else {
    await stageFile(selectedGhdFile);
  }
}

function sendSelectedFileToLoop() {
  if (!selectedGhdFile) return;
  const goalText = `Review, fix, and verify changes in file: ${selectedGhdFile}\n\nContext Diff:\n\`\`\`diff\n${currentRawDiff.slice(0, 1500)}\n\`\`\``;
  setLoopGoalPrompt(goalText);
  switchTab(2); // Switch to Auto-Dev Loop tab
  showToast(`🤖 Loaded '${selectedGhdFile}' into Auto-Dev Loop goal!`, "success");
}

function setDiffViewMode(mode) {
  diffViewMode = mode;
  const uBtn = document.getElementById('diffModeUnifiedBtn');
  const sBtn = document.getElementById('diffModeSplitBtn');
  if (uBtn) uBtn.className = mode === 'unified' ? 'diff-mode-btn active' : 'diff-mode-btn';
  if (sBtn) sBtn.className = mode === 'split' ? 'diff-mode-btn active' : 'diff-mode-btn';
  renderColoredDiff(currentRawDiff);
}

async function selectFileForDiff(filePath, isStaged) {
  selectedGhdFile = filePath;
  selectedGhdCommit = "";
  
  if (window.innerWidth <= 768) {
    toggleGhdMobileView('diff');
  }

  const rows = document.querySelectorAll('.ghd-file-row');
  rows.forEach(r => {
    if (r.getAttribute('data-path') === filePath) r.className = 'ghd-file-row selected';
    else r.className = 'ghd-file-row';
  });

  document.getElementById('ghdDiffTitle').innerText = `📄 ${filePath}`;
  
  const discardBtn = document.getElementById('ghdDiscardFileBtn');
  if (discardBtn) discardBtn.style.display = 'inline-block';
  
  const stageBtn = document.getElementById('ghdToggleStageFileBtn');
  if (stageBtn) {
    stageBtn.style.display = 'inline-block';
    stageBtn.innerText = isStaged ? '↩️ Unstage' : '📝 Stage';
  }
  
  const loopBtn = document.getElementById('ghdSendToLoopBtn');
  if (loopBtn) loopBtn.style.display = 'inline-block';

  try {
    const res = await fetch(`/api/git/diff?repo_path=${encodeURIComponent(currentRepoPath)}&file=${encodeURIComponent(filePath)}&staged=${isStaged ? 'true' : 'false'}`);
    const data = await res.json();
    currentRawDiff = data.diff || "No diff available.";
    renderColoredDiff(currentRawDiff);
  } catch(e) { handleServerDisconnected(); }
}

function renderColoredDiff(rawDiff) {
  const container = document.getElementById('ghdDiffContent');
  container.innerHTML = '';
  
  if (!rawDiff || rawDiff.trim() === '' || rawDiff === "No diff available.") {
    container.innerHTML = '<div style="color:var(--text-muted); padding:30px; text-align:center;">No changes recorded in diff for this selection.</div>';
    document.getElementById('ghdDiffStats').style.display = 'none';
    return;
  }

  const lines = rawDiff.split("\n");
  let additions = 0;
  let deletions = 0;

  lines.forEach(line => {
    if (line.startsWith('+') && !line.startsWith('+++')) additions++;
    else if (line.startsWith('-') && !line.startsWith('---')) deletions++;
  });

  const statsEl = document.getElementById('ghdDiffStats');
  if (statsEl) {
    statsEl.style.display = 'inline-block';
    statsEl.innerHTML = `<span style="color:var(--green);">+${additions}</span> <span style="color:var(--rose);">-${deletions}</span>`;
  }

  if (diffViewMode === 'split') {
    renderSplitDiff(lines, container);
  } else {
    renderUnifiedDiff(lines, container);
  }
}

function renderUnifiedDiff(lines, container) {
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

function renderSplitDiff(lines, container) {
  const wrapper = document.createElement('div');
  wrapper.className = 'split-diff-wrapper';

  const leftPane = document.createElement('div');
  leftPane.className = 'split-pane';
  const rightPane = document.createElement('div');
  rightPane.className = 'split-pane';

  const leftTable = document.createElement('table');
  leftTable.className = 'split-table';
  const rightTable = document.createElement('table');
  rightTable.className = 'split-table';

  let oldLineNum = 0;
  let newLineNum = 0;

  lines.forEach(line => {
    const lTr = document.createElement('tr');
    const rTr = document.createElement('tr');

    if (line.startsWith('@@')) {
      const match = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      if (match) {
        oldLineNum = parseInt(match[1], 10);
        newLineNum = parseInt(match[2], 10);
      }
      lTr.className = 'split-line-chunk';
      rTr.className = 'split-line-chunk';
      lTr.innerHTML = `<td class="split-line-num">...</td><td>${escapeHtml(line)}</td>`;
      rTr.innerHTML = `<td class="split-line-num">...</td><td>${escapeHtml(line)}</td>`;
    } else if (line.startsWith('-') && !line.startsWith('---')) {
      lTr.className = 'split-line-del';
      lTr.innerHTML = `<td class="split-line-num">${oldLineNum++}</td><td>${escapeHtml(line)}</td>`;
      rTr.className = 'split-line-empty';
      rTr.innerHTML = `<td class="split-line-num"></td><td></td>`;
    } else if (line.startsWith('+') && !line.startsWith('+++')) {
      lTr.className = 'split-line-empty';
      lTr.innerHTML = `<td class="split-line-num"></td><td></td>`;
      rTr.className = 'split-line-add';
      rTr.innerHTML = `<td class="split-line-num">${newLineNum++}</td><td>${escapeHtml(line)}</td>`;
    } else if (!line.startsWith('---') && !line.startsWith('+++') && !line.startsWith('diff --git')) {
      lTr.innerHTML = `<td class="split-line-num">${oldLineNum++}</td><td>${escapeHtml(line)}</td>`;
      rTr.innerHTML = `<td class="split-line-num">${newLineNum++}</td><td>${escapeHtml(line)}</td>`;
    } else {
      lTr.innerHTML = `<td class="split-line-num"></td><td>${escapeHtml(line)}</td>`;
      rTr.innerHTML = `<td class="split-line-num"></td><td>${escapeHtml(line)}</td>`;
    }

    leftTable.appendChild(lTr);
    rightTable.appendChild(rTr);
  });

  leftPane.appendChild(leftTable);
  rightPane.appendChild(rightTable);
  wrapper.appendChild(leftPane);
  wrapper.appendChild(rightPane);
  container.appendChild(wrapper);
}

async function ghdCommit() {
  const summary = document.getElementById('commitSummaryInput').value.trim();
  const desc = document.getElementById('commitDescInput').value.trim();
  if (!summary) return;

  const fileList = Array.from(checkedFiles);

  try {
    const res = await fetch('/api/git/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_path: currentRepoPath,
        summary: summary,
        description: desc,
        files: fileList
      })
    });
    const data = await res.json();
    if (data.success && data.committed) {
      showToast(`✓ Committed: ${data.short_hash} - ${summary}`, "success");
      document.getElementById('commitSummaryInput').value = '';
      document.getElementById('commitDescInput').value = '';
      checkedFiles.clear();
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
    if (btn) btn.innerText = "Pushing...";
    const res = await fetch('/api/git/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath })
    });
    const data = await res.json();
    await loadGitHubDesktopState();
    if (data.success) showToast("✓ Pushed to remote repository!", "success");
    else showToast("Push failed: " + (data.stderr || data.stdout || data.error), "error", 4500);
  } catch(e) { showToast("Push error: " + e.message, "error"); }
}

async function ghdPull() {
  try {
    const res = await fetch('/api/git/pull', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, rebase: false })
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

// ─────────────────────────────────────────────────────────────
// HISTORY TAB
// ─────────────────────────────────────────────────────────────
function renderHistoryList(commits) {
  const container = document.getElementById('ghdHistoryList');
  if (!container) return;
  container.innerHTML = '';

  if (!commits || commits.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:30px;">No commits found in history.</div>';
    return;
  }

  commits.forEach(c => {
    const div = document.createElement('div');
    div.className = `ghd-commit-item ${c.hash === selectedGhdCommit ? 'selected' : ''}`;
    div.setAttribute('data-context', 'commit');
    div.setAttribute('data-sha', c.hash);
    div.setAttribute('data-short-sha', c.short_hash);
    div.setAttribute('data-subject', c.subject);
    div.onclick = () => selectCommitForInspection(c);
    div.innerHTML = `
      <div class="ghd-commit-msg">${escapeHtml(c.subject)}</div>
      <div class="ghd-commit-meta">
        <span>👤 ${escapeHtml(c.author)}</span>
        <span>🕒 ${escapeHtml(c.date)}</span>
        <span style="color:var(--accent); font-weight:700;">${escapeHtml(c.short_hash)}</span>
      </div>
    `;
    container.appendChild(div);
  });
}

function filterHistoryList(val) {
  const query = val.toLowerCase();
  const filtered = allHistoryCommits.filter(c => 
    c.subject.toLowerCase().includes(query) ||
    c.author.toLowerCase().includes(query) ||
    c.hash.toLowerCase().includes(query) ||
    c.short_hash.toLowerCase().includes(query)
  );
  renderHistoryList(filtered);
}

async function selectCommitForInspection(commit) {
  selectedGhdCommit = commit.hash;
  selectedGhdFile = "";
  
  if (window.innerWidth <= 768) {
    toggleGhdMobileView('diff');
  }

  const items = document.querySelectorAll('.ghd-commit-item');
  items.forEach(i => {
    if (i.getAttribute('data-sha') === commit.hash) i.className = 'ghd-commit-item selected';
    else i.className = 'ghd-commit-item';
  });

  document.getElementById('ghdDiffTitle').innerText = `📜 ${commit.subject} (${commit.short_hash})`;
  document.getElementById('ghdDiscardFileBtn').style.display = 'none';
  document.getElementById('ghdToggleStageFileBtn').style.display = 'none';
  document.getElementById('ghdSendToLoopBtn').style.display = 'none';

  try {
    const res = await fetch(`/api/git/commit_detail?repo_path=${encodeURIComponent(currentRepoPath)}&hash=${encodeURIComponent(commit.hash)}`);
    const data = await res.json();
    currentRawDiff = data.diff || "No diff recorded for this commit.";
    renderColoredDiff(currentRawDiff);
  } catch(e) {}
}

// ─────────────────────────────────────────────────────────────
// BRANCHES TAB
// ─────────────────────────────────────────────────────────────
function renderBranchesTab(branches, currentBranch) {
  const container = document.getElementById('ghdBranchesList');
  if (!container) return;
  container.innerHTML = '';

  if (!branches || branches.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted); text-align:center; padding:30px;">No branches found.</div>';
    return;
  }

  const localBranches = branches.filter(b => !(typeof b === 'object' && b.remote));
  const remoteBranches = branches.filter(b => (typeof b === 'object' && b.remote));

  const localHeader = document.createElement('div');
  localHeader.className = 'ghd-section-header';
  localHeader.innerHTML = `<span>Local Branches (${localBranches.length})</span>`;
  container.appendChild(localHeader);

  localBranches.forEach(b => {
    const bName = typeof b === 'string' ? b : b.name;
    const isCurrent = (bName === currentBranch);
    const card = document.createElement('div');
    card.className = `ghd-card-item ${isCurrent ? 'active' : ''}`;
    card.setAttribute('data-context', 'branch');
    card.setAttribute('data-branch', bName);
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <span style="font-weight:700; color:#fff; font-family:var(--font-mono);">🌿 ${escapeHtml(bName)}</span>
        ${isCurrent ? '<span class="file-status-badge status-a">CURRENT</span>' : `
          <div style="display:flex; gap:4px;">
            <button class="ghd-mini-btn" onclick="ghdCheckoutBranch('${escapeJs(bName)}', false)" title="Checkout Branch">Switch</button>
            <button class="ghd-mini-btn" onclick="ghdMergeBranchConfirm('${escapeJs(bName)}')" title="Merge into current">Merge</button>
            <button class="ghd-mini-btn ghd-mini-btn--danger" onclick="ghdDeleteBranchConfirm('${escapeJs(bName)}')" title="Delete branch">🗑️</button>
          </div>
        `}
      </div>
      ${typeof b === 'object' && b.subject ? `
        <div style="font-size:11.5px; color:var(--text-muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          ${escapeHtml(b.subject)} (${escapeHtml(b.short_hash || '')})
        </div>
      ` : ''}
    `;
    container.appendChild(card);
  });

  if (remoteBranches.length > 0) {
    const remoteHeader = document.createElement('div');
    remoteHeader.className = 'ghd-section-header';
    remoteHeader.style.marginTop = '10px';
    remoteHeader.innerHTML = `<span>Remote Branches (${remoteBranches.length})</span>`;
    container.appendChild(remoteHeader);

    remoteBranches.forEach(b => {
      const bName = typeof b === 'string' ? b : b.name;
      const card = document.createElement('div');
      card.className = 'ghd-card-item';
      card.setAttribute('data-context', 'branch');
      card.setAttribute('data-branch', bName);
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:700; color:var(--text-muted); font-family:var(--font-mono);">🌐 ${escapeHtml(bName)}</span>
          <button class="ghd-mini-btn" onclick="ghdCheckoutBranch('${escapeJs(bName)}', false)">Checkout</button>
        </div>
      `;
      container.appendChild(card);
    });
  }
}

function filterBranchesTabList(val) {
  const query = val.toLowerCase();
  const filtered = allBranches.filter(b => {
    const name = typeof b === 'string' ? b : b.name;
    return name.toLowerCase().includes(query);
  });
  renderBranchesTab(filtered, currentGhdState ? currentGhdState.branch : "");
}

function toggleBranchModal() {
  const m = document.getElementById('branchModal');
  if (m) m.className = (m.className.includes('active')) ? 'branch-modal' : 'branch-modal active';
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
  if (!scroll) return;
  scroll.innerHTML = '';
  
  branches.forEach(b => {
    const bName = typeof b === 'string' ? b : b.name;
    const isCurrent = (bName === currentBranch);
    const row = document.createElement('div');
    row.className = `branch-item-row ${isCurrent ? 'current' : ''}`;
    row.setAttribute('data-context', 'branch');
    row.setAttribute('data-branch', bName);
    row.onclick = () => ghdCheckoutBranch(bName, false);
    row.innerHTML = `<span>🌿 ${escapeHtml(bName)}</span> ${isCurrent ? '<span style="color:var(--green); font-weight:700;">✓ Current</span>' : ''}`;
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

async function ghdCheckoutBranch(branchName, create = false, startPoint = "") {
  const m = document.getElementById('branchModal');
  if (m) m.className = 'branch-modal';

  const cleanName = branchName.trim().replace(/^origin\//, '').replace(/^remotes\/origin\//, '');
  if (currentGhdState && currentGhdState.branch === cleanName && !create) {
    return;
  }

  try {
    const res = await fetch('/api/git/branch/checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_path: currentRepoPath,
        branch: cleanName,
        create: create,
        start_point: startPoint
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Switched to branch '${cleanName}'`, "success");
      await loadGitHubDesktopState();
    } else {
      showToast(`Branch switch error: ${data.stderr || data.error}`, "error", 4500);
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

function ghdMergeBranchConfirm(sourceBranch) {
  openGhdConfirmModal(
    "🔀 Merge Branch",
    `Merge branch <b>${escapeHtml(sourceBranch)}</b> into <b>${escapeHtml(currentGhdState?.branch || 'main')}</b>?`,
    "Merge Branch",
    async () => {
      try {
        const res = await fetch('/api/git/branch/merge', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo_path: currentRepoPath, source_branch: sourceBranch })
        });
        const data = await res.json();
        if (data.success && data.merged) {
          showToast(`✓ Merged '${sourceBranch}' into '${currentGhdState?.branch}'`, "success");
          await loadGitHubDesktopState();
        } else {
          showToast(`Merge failed: ${data.stderr || data.error}`, "error", 4500);
        }
      } catch(e) { showToast(`Error: ${e.message}`, "error"); }
    }
  );
}

function ghdDeleteBranchConfirm(branchName) {
  openGhdConfirmModal(
    "🗑️ Delete Branch",
    `Are you sure you want to delete branch <b>${escapeHtml(branchName)}</b>?`,
    "Delete Branch",
    async () => {
      try {
        const res = await fetch('/api/git/branch/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ repo_path: currentRepoPath, branch: branchName, force: true })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`✓ Deleted branch '${branchName}'`, "info");
          await loadGitHubDesktopState();
        } else {
          showToast(`Delete failed: ${data.stderr || data.error}`, "error", 4500);
        }
      } catch(e) { showToast(`Error: ${e.message}`, "error"); }
    }
  );
}

function openNewBranchDialog(startPoint = "") {
  const modal = document.getElementById('ghdNewBranchModal');
  if (modal) {
    modal.style.display = 'flex';
    document.getElementById('newBranchNameInput').value = '';
    document.getElementById('newBranchStartPointInput').value = startPoint || (currentGhdState ? currentGhdState.branch : 'main');
    document.getElementById('newBranchNameInput').focus();
  }
}

function closeGhdNewBranchModal() {
  const modal = document.getElementById('ghdNewBranchModal');
  if (modal) modal.style.display = 'none';
}

async function submitCreateNewBranch() {
  const name = document.getElementById('newBranchNameInput').value.trim();
  const startPoint = document.getElementById('newBranchStartPointInput').value.trim();
  if (!name) {
    showToast("Please enter a valid branch name", "warn");
    return;
  }
  closeGhdNewBranchModal();
  await ghdCheckoutBranch(name, true, startPoint);
}

// ─────────────────────────────────────────────────────────────
// ISSUES & PRS TAB
// ─────────────────────────────────────────────────────────────
async function loadGithubIssues() {
  try {
    const res = await fetch(`/api/git/issues?repo_path=${encodeURIComponent(currentRepoPath)}`);
    const data = await res.json();
    allGithubIssues = data.issues || [];
    renderIssuesTab(allGithubIssues);
    const issuesCountEl = document.getElementById('ghdIssuesCount');
    if (issuesCountEl) issuesCountEl.innerText = allGithubIssues.length;
  } catch(e) {}
}

function renderIssuesTab(issues) {
  const container = document.getElementById('ghdIssuesList');
  if (!container) return;
  container.innerHTML = '';

  let filtered = issues || [];
  if (issueStateFilter !== 'all') {
    filtered = filtered.filter(i => (i.state || 'open').toLowerCase() === issueStateFilter);
  }

  if (filtered.length === 0) {
    container.innerHTML = `<div style="color:var(--text-muted); text-align:center; padding:30px;">No ${issueStateFilter} GitHub issues found.</div>`;
    return;
  }

  filtered.forEach(issue => {
    const card = document.createElement('div');
    card.className = 'ghd-card-item';
    card.setAttribute('data-context', 'issue');
    card.setAttribute('data-issue-number', issue.number);
    card.setAttribute('data-issue-title', issue.title);
    card.setAttribute('data-issue-url', issue.url || '');
    card.setAttribute('data-issue-state', issue.state || 'open');

    const isOpen = (issue.state || 'open').toLowerCase() === 'open';
    const statusBadge = isOpen ? 
      '<span class="file-status-badge status-a">OPEN</span>' : 
      '<span class="file-status-badge status-d">CLOSED</span>';

    const labelsHtml = (issue.labels || []).map(l => 
      `<span style="background:var(--ink-500); color:var(--accent); padding:1px 6px; border-radius:4px; font-size:10px; font-family:var(--font-mono);">${escapeHtml(l)}</span>`
    ).join(' ');

    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
        <span style="font-weight:700; color:#fff; font-size:12.5px;">#${issue.number} ${escapeHtml(issue.title)}</span>
        ${statusBadge}
      </div>
      ${labelsHtml ? `<div style="display:flex; flex-wrap:wrap; gap:4px;">${labelsHtml}</div>` : ''}
      <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
        <span style="font-size:11px; color:var(--text-muted);">👤 ${escapeHtml(issue.author || 'github')}</span>
        <div style="display:flex; gap:6px;">
          <button class="action-btn action-btn--success action-btn--sm" onclick="launchIssueInAutoDevLoop(${issue.number}, '${escapeJs(issue.title)}', '${escapeJs(issue.body || '')}')" title="Solve with Autonomous Swarm">
            🚀 Implement with Swarm AI
          </button>
          ${issue.url ? `<a href="${escapeHtml(issue.url)}" target="_blank" class="ghd-mini-btn" style="text-decoration:none;" title="View on GitHub">🌐</a>` : ''}
        </div>
      </div>
    `;
    container.appendChild(card);
  });
}

function filterIssuesByState(state) {
  issueStateFilter = state;
  const oBtn = document.getElementById('filterIssuesOpenBtn');
  const cBtn = document.getElementById('filterIssuesClosedBtn');
  const aBtn = document.getElementById('filterIssuesAllBtn');
  if (oBtn) oBtn.style.background = state === 'open' ? 'var(--ink-600)' : 'transparent';
  if (cBtn) cBtn.style.background = state === 'closed' ? 'var(--ink-600)' : 'transparent';
  if (aBtn) aBtn.style.background = state === 'all' ? 'var(--ink-600)' : 'transparent';
  renderIssuesTab(allGithubIssues);
}

function filterIssuesTabList(val) {
  const query = val.toLowerCase();
  const filtered = allGithubIssues.filter(i => 
    i.title.toLowerCase().includes(query) ||
    String(i.number).includes(query)
  );
  renderIssuesTab(filtered);
}

function launchIssueInAutoDevLoop(issueNum, issueTitle, issueBody) {
  const promptGoal = `Resolve GitHub Issue #${issueNum}: ${issueTitle}\n\n${issueBody}`.trim();
  setLoopGoalPrompt(promptGoal);
  switchTab(2); // Switch to Auto-Dev Loop tab
  showToast(`🚀 Loaded Issue #${issueNum} into Auto-Dev Loop goal!`, "success", 3500);
}

function openNewIssueDialog() {
  const modal = document.getElementById('ghdNewIssueModal');
  if (modal) {
    modal.style.display = 'flex';
    document.getElementById('newIssueTitleInput').value = '';
    document.getElementById('newIssueBodyInput').value = '';
    document.getElementById('newIssueLabelsInput').value = 'enhancement, swarm-auto';
    document.getElementById('newIssueTitleInput').focus();
  }
}

function closeGhdNewIssueModal() {
  const modal = document.getElementById('ghdNewIssueModal');
  if (modal) modal.style.display = 'none';
}

async function submitCreateNewIssue() {
  const title = document.getElementById('newIssueTitleInput').value.trim();
  const body = document.getElementById('newIssueBodyInput').value.trim();
  const rawLabels = document.getElementById('newIssueLabelsInput').value.trim();
  const labels = rawLabels ? rawLabels.split(',').map(s => s.trim()).filter(Boolean) : [];

  if (!title) {
    showToast("Please enter an issue title", "warn");
    return;
  }

  closeGhdNewIssueModal();
  try {
    const res = await fetch('/api/git/issue/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        repo_path: currentRepoPath,
        title: title,
        body: body,
        labels: labels
      })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Created GitHub issue #${data.issue_number}`, "success");
      await loadGithubIssues();
    } else {
      showToast(`Issue creation error: ${data.stderr || data.error}`, "error");
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

async function closeOrReopenIssue(issueNum, isClosed) {
  const endpoint = isClosed ? '/api/git/issue/reopen' : '/api/git/issue/close';
  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath, issue_number: issueNum })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ ${isClosed ? 'Reopened' : 'Closed'} issue #${issueNum}`, "info");
      await loadGithubIssues();
    }
  } catch(e) { showToast(`Error: ${e.message}`, "error"); }
}

// ─────────────────────────────────────────────────────────────
// STASHES & WORKTREES TAB
// ─────────────────────────────────────────────────────────────
function renderStashesTab(stashes, worktrees) {
  const stashesList = document.getElementById('ghdStashesInnerList');
  if (stashesList) {
    stashesList.innerHTML = '';
    if (!stashes || stashes.length === 0) {
      stashesList.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:8px;">No saved stashes.</div>';
    } else {
      stashes.forEach(s => {
        const card = document.createElement('div');
        card.className = 'ghd-card-item';
        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; color:#fff; font-family:var(--font-mono);">📦 stash@{${s.index}}</span>
            <span style="color:var(--accent); font-size:11px;">🌿 ${escapeHtml(s.branch)}</span>
          </div>
          <div style="font-size:12px; color:var(--text);">${escapeHtml(s.message)}</div>
          <div style="display:flex; justify-content:space-between; align-items:center; margin-top:4px;">
            <span style="font-size:10.5px; color:var(--text-muted);">🕒 ${escapeHtml(s.date || '')}</span>
            <div style="display:flex; gap:4px;">
              <button class="ghd-mini-btn" onclick="popStash(${s.index})" title="Pop/Restore stash">↩️ Pop</button>
              <button class="ghd-mini-btn ghd-mini-btn--danger" onclick="dropStash(${s.index})" title="Drop stash">🗑️</button>
            </div>
          </div>
        `;
        stashesList.appendChild(card);
      });
    }
  }

  const wtList = document.getElementById('ghdWorktreesInnerList');
  if (wtList) {
    wtList.innerHTML = '';
    if (!worktrees || worktrees.length === 0) {
      wtList.innerHTML = '<div style="color:var(--text-muted); font-size:12px; padding:8px;">No isolated worktrees.</div>';
    } else {
      worktrees.forEach(wt => {
        const card = document.createElement('div');
        card.className = 'ghd-card-item';
        card.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-weight:700; color:#fff; font-family:var(--font-mono);">${wt.is_main ? '👑 Main' : '🌳 ' + escapeHtml(wt.display_path || wt.path)}</span>
            <span style="color:var(--accent); font-size:11px;">🌿 ${escapeHtml(wt.branch || 'detached')}</span>
          </div>
          ${wt.is_main ? '' : `
            <div style="display:flex; justify-content:flex-end; margin-top:4px;">
              <button class="ghd-mini-btn ghd-mini-btn--danger" onclick="removeWorktreeAction('${escapeJs(wt.path)}')">🗑️ Remove</button>
            </div>
          `}
        `;
        wtList.appendChild(card);
      });
    }
  }
}

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
    } else {
      showToast("Error discarding stash: " + (data.stderr || data.error), "error", 4500);
    }
  } catch(e) { showToast("Error: " + e.message, "error"); }
}

async function openWorktreeModal() {
  const modal = document.getElementById('worktreeModal');
  if (modal) {
    modal.className = 'modal-overlay active';
    await loadWorktreesList();
  }
}

function closeWorktreeModal() {
  const modal = document.getElementById('worktreeModal');
  if (modal) modal.className = 'modal-overlay';
}

async function loadWorktreesList() {
  const container = document.getElementById('worktreesTableBody');
  if (!container) return;
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
        <td style="padding:10px 14px; font-family:var(--font-mono); color:var(--text-bright); font-weight:700;">
          ${isMain ? '👑 Main Repository' : '🌳 ' + escapeHtml(wt.display_path || wt.path)}
          ${isMain ? '<span class="file-status-badge status-a" style="margin-left:6px;">MAIN</span>' : ''}
        </td>
        <td style="padding:10px 14px; font-family:var(--font-mono); color:var(--accent);">🌿 ${escapeHtml(wt.branch || 'detached')}</td>
        <td style="padding:10px 14px; font-family:var(--font-mono); color:var(--text-muted); font-size:12px;">${escapeHtml(wt.commit || '')}</td>
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
      await fetch('/api/git/worktree/remove', {
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
// GENERIC CONFIRMATION MODAL
// ─────────────────────────────────────────────────────────────
function openGhdConfirmModal(title, message, btnText, onConfirm) {
  const modal = document.getElementById('ghdConfirmModal');
  const titleEl = document.getElementById('ghdConfirmTitle');
  const msgEl = document.getElementById('ghdConfirmMessage');
  const btnEl = document.getElementById('ghdConfirmBtn');

  if (titleEl) titleEl.innerHTML = title;
  if (msgEl) msgEl.innerHTML = message;
  if (btnEl) {
    btnEl.innerText = btnText;
    btnEl.onclick = async () => {
      closeGhdConfirmModal();
      if (typeof onConfirm === 'function') await onConfirm();
    };
  }
  if (modal) modal.style.display = 'flex';
}

function closeGhdConfirmModal() {
  const modal = document.getElementById('ghdConfirmModal');
  if (modal) modal.style.display = 'none';
}

// ─────────────────────────────────────────────────────────────
// CUSTOM RIGHT-CLICK CONTEXT MENU ENGINE
// ─────────────────────────────────────────────────────────────
function initCustomContextMenu() {
  const tabGit = document.getElementById('tabGit');
  const menu = document.getElementById('customContextMenu');
  if (!tabGit || !menu) return;

  tabGit.addEventListener('contextmenu', (e) => {
    e.preventDefault();
    
    // Find closest context element
    const fileRow = e.target.closest('[data-context="file"]');
    const branchItem = e.target.closest('[data-context="branch"]');
    const commitItem = e.target.closest('[data-context="commit"]');
    const issueItem = e.target.closest('[data-context="issue"]');

    let menuItems = [];

    if (fileRow) {
      const filePath = fileRow.getAttribute('data-path');
      const isStaged = fileRow.getAttribute('data-staged') === 'true';
      const fileStatus = fileRow.getAttribute('data-status') || 'M';

      menuItems = [
        { header: `File: ${filePath.split('/').pop()}` },
        {
          icon: isStaged ? '↩️' : '📝',
          label: isStaged ? 'Unstage File' : 'Stage File',
          shortcut: isStaged ? 'Ctrl+U' : 'Ctrl+S',
          action: () => isStaged ? unstageFile(filePath) : stageFile(filePath)
        },
        {
          icon: '👁️',
          label: 'View Diff in Viewer',
          action: () => selectFileForDiff(filePath, isStaged)
        },
        {
          icon: '📋',
          label: 'Copy Relative Path',
          action: () => {
            navigator.clipboard.writeText(filePath);
            showToast(`📋 Copied: ${filePath}`, "info", 1800);
          }
        },
        {
          icon: '🤖',
          label: 'Send to Auto-Dev Loop',
          action: () => {
            selectFileForDiff(filePath, isStaged).then(() => sendSelectedFileToLoop());
          }
        },
        { separator: true },
        {
          icon: '🗑️',
          label: 'Discard Changes...',
          danger: true,
          action: () => discardFileConfirm(filePath)
        }
      ];

    } else if (branchItem) {
      const branchName = branchItem.getAttribute('data-branch');
      const isCurrent = currentGhdState && currentGhdState.branch === branchName;

      menuItems = [
        { header: `Branch: ${branchName}` },
        ...(isCurrent ? [] : [
          {
            icon: '🔀',
            label: 'Switch to this Branch',
            action: () => ghdCheckoutBranch(branchName, false)
          }
        ]),
        {
          icon: '🌿',
          label: 'Create New Branch from Here...',
          action: () => openNewBranchDialog(branchName)
        },
        ...(isCurrent ? [] : [
          {
            icon: '🔄',
            label: `Merge '${branchName}' into '${currentGhdState?.branch || 'main'}'`,
            action: () => ghdMergeBranchConfirm(branchName)
          }
        ]),
        {
          icon: '⬆️',
          label: 'Push / Publish Branch',
          action: async () => {
            try {
              const res = await fetch('/api/git/push', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ repo_path: currentRepoPath, branch: branchName, set_upstream: true })
              });
              const data = await res.json();
              if (data.success) showToast(`✓ Pushed '${branchName}' to origin`, "success");
              else showToast(`Push failed: ${data.stderr || data.error}`, "error");
            } catch(e) { showToast(`Error: ${e.message}`, "error"); }
          }
        },
        ...(isCurrent ? [] : [
          { separator: true },
          {
            icon: '🗑️',
            label: 'Delete Branch...',
            danger: true,
            action: () => ghdDeleteBranchConfirm(branchName)
          }
        ])
      ];

    } else if (commitItem) {
      const sha = commitItem.getAttribute('data-sha');
      const shortSha = commitItem.getAttribute('data-short-sha');
      const subject = commitItem.getAttribute('data-subject');

      menuItems = [
        { header: `Commit: ${shortSha}` },
        {
          icon: '📋',
          label: 'Copy Commit SHA',
          action: () => {
            navigator.clipboard.writeText(sha);
            showToast(`📋 Copied SHA: ${shortSha}`, "info", 1800);
          }
        },
        {
          icon: '🌿',
          label: 'Create Branch from Commit...',
          action: () => openNewBranchDialog(sha)
        },
        {
          icon: '🔍',
          label: 'View Full Commit Diff',
          action: () => selectCommitForInspection({ hash: sha, short_hash: shortSha, subject: subject })
        },
        { separator: true },
        {
          icon: '↩️',
          label: 'Revert this Commit...',
          danger: true,
          action: () => {
            openGhdConfirmModal(
              "↩️ Revert Commit",
              `Create a revert commit that undoes changes made in <b>${escapeHtml(shortSha)} - ${escapeHtml(subject)}</b>?`,
              "Revert Commit",
              async () => {
                try {
                  const res = await fetch('/api/git/commit/revert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ repo_path: currentRepoPath, commit_sha: sha })
                  });
                  const data = await res.json();
                  if (data.success) {
                    showToast(`✓ Reverted commit ${shortSha}`, "success");
                    await loadGitHubDesktopState();
                  } else {
                    showToast(`Revert error: ${data.stderr || data.error}`, "error");
                  }
                } catch(e) { showToast(`Error: ${e.message}`, "error"); }
              }
            );
          }
        },
        {
          icon: '🔙',
          label: 'Reset to this Commit (Soft)...',
          danger: true,
          action: () => {
            openGhdConfirmModal(
              "🔙 Soft Reset",
              `Reset HEAD to commit <b>${escapeHtml(shortSha)}</b>? Your working changes will be preserved as uncommitted.`,
              "Reset (Soft)",
              async () => {
                try {
                  const res = await fetch('/api/git/commit/reset', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ repo_path: currentRepoPath, commit_sha: sha, mode: 'soft' })
                  });
                  const data = await res.json();
                  if (data.success) {
                    showToast(`✓ Soft reset to ${shortSha}`, "info");
                    await loadGitHubDesktopState();
                  }
                } catch(e) { showToast(`Error: ${e.message}`, "error"); }
              }
            );
          }
        }
      ];

    } else if (issueItem) {
      const issueNum = parseInt(issueItem.getAttribute('data-issue-number'), 10);
      const issueTitle = issueItem.getAttribute('data-issue-title');
      const issueUrl = issueItem.getAttribute('data-issue-url');
      const issueState = issueItem.getAttribute('data-issue-state') || 'open';
      const isOpen = issueState.toLowerCase() === 'open';

      menuItems = [
        { header: `Issue #${issueNum}` },
        {
          icon: '🚀',
          label: 'Launch Auto-Dev Loop on Issue',
          action: () => launchIssueInAutoDevLoop(issueNum, issueTitle, "")
        },
        ...(issueUrl ? [
          {
            icon: '🌐',
            label: 'View on GitHub',
            action: () => window.open(issueUrl, '_blank')
          }
        ] : []),
        { separator: true },
        {
          icon: isOpen ? '🔒' : '🔓',
          label: isOpen ? 'Close Issue' : 'Reopen Issue',
          action: () => closeOrReopenIssue(issueNum, !isOpen)
        }
      ];

    } else {
      // General Canvas / Empty Area
      menuItems = [
        { header: `Git: ${currentGhdState?.repo_name || 'Workspace'}` },
        {
          icon: '🔄',
          label: 'Fetch Origin All',
          action: () => ghdFetch()
        },
        {
          icon: '⬇️',
          label: 'Pull from Remote',
          action: () => ghdPull()
        },
        {
          icon: '⬆️',
          label: 'Push Commits to Remote',
          action: () => ghdPush()
        },
        { separator: true },
        {
          icon: '🌿',
          label: 'Create New Branch...',
          action: () => openNewBranchDialog()
        },
        {
          icon: '📦',
          label: 'Stash Working Changes...',
          action: () => quickStash()
        },
        {
          icon: '📤',
          label: 'Pop Latest Stash',
          action: () => popStash(0)
        },
        { separator: true },
        {
          icon: '💬',
          label: 'Transfer Git Status to Advisor Chat',
          action: () => {
            const prompt = `Here is the current Git status for repository '${currentGhdState?.repo_name}':\n- Current Branch: ${currentGhdState?.branch}\n- Ahead: ${currentGhdState?.ahead}, Behind: ${currentGhdState?.behind}\n- Staged Files: ${(currentGhdState?.staged || []).map(f=>f.path).join(', ') || 'None'}\n- Unstaged Files: ${(currentGhdState?.unstaged || []).map(f=>f.path).join(', ') || 'None'}\n\nPlease review these changes and recommend next steps.`;
            document.getElementById('promptInput').value = prompt;
            switchTab(1); // Switch to Chat Tab
            showToast("💬 Transferred Git status to Advisor prompt", "info");
          }
        }
      ];
    }

    renderCustomContextMenu(menu, menuItems, e.clientX, e.clientY);
  });

  // Global dismiss listeners
  document.addEventListener('click', () => hideCustomContextMenu());
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      hideCustomContextMenu();
      closeGhdConfirmModal();
      closeGhdNewBranchModal();
      closeGhdNewIssueModal();
    }
  });
}

function renderCustomContextMenu(menu, items, x, y) {
  menu.innerHTML = '';

  items.forEach(item => {
    if (item.header) {
      const h = document.createElement('div');
      h.className = 'context-menu-header';
      h.innerText = item.header;
      menu.appendChild(h);
    } else if (item.separator) {
      const sep = document.createElement('div');
      sep.className = 'context-menu-separator';
      menu.appendChild(sep);
    } else {
      const el = document.createElement('div');
      el.className = `context-menu-item ${item.danger ? 'danger' : ''}`;
      el.onclick = (ev) => {
        ev.stopPropagation();
        hideCustomContextMenu();
        if (typeof item.action === 'function') item.action();
      };
      el.innerHTML = `
        <span class="context-menu-label">
          <span class="context-menu-icon">${item.icon || '•'}</span>
          <span>${escapeHtml(item.label)}</span>
        </span>
        ${item.shortcut ? `<span class="context-menu-shortcut">${item.shortcut}</span>` : ''}
      `;
      menu.appendChild(el);
    }
  });

  menu.style.display = 'flex';
  menu.style.visibility = 'hidden';

  // Boundary collision detection
  const menuRect = menu.getBoundingClientRect();
  let left = x;
  let top = y;

  if (x + menuRect.width > window.innerWidth - 10) {
    left = window.innerWidth - menuRect.width - 10;
  }
  if (y + menuRect.height > window.innerHeight - 10) {
    top = window.innerHeight - menuRect.height - 10;
  }

  menu.style.left = `${Math.max(10, left)}px`;
  menu.style.top = `${Math.max(10, top)}px`;
  menu.style.visibility = 'visible';
}

function hideCustomContextMenu() {
  const menu = document.getElementById('customContextMenu');
  if (menu) menu.style.display = 'none';
}

// ─────────────────────────────────────────────────────────────
// Multi-Chat Session Logic
// ─────────────────────────────────────────────────────────────
let isLoopViewActive = false;

async function loadSessionsList() {
  try {
    const [loopRes, chatRes] = await Promise.all([
      fetch('/api/loop/sessions', { cache: 'no-store' }),
      fetch('/api/sessions', { cache: 'no-store' })
    ]);
    
    allLoopSessions = await loopRes.json() || [];
    const chatList = await chatRes.json() || [];
    
    const container = document.getElementById('sessionListContainer');
    if (!container) return;
    container.innerHTML = '';

    // 1. Autonomous Swarm Runs Section
    if (allLoopSessions.length > 0) {
      const loopHeader = document.createElement('div');
      loopHeader.className = 'sidebar-section-header';
      loopHeader.innerHTML = `<span>🚀 Swarm Runs (${allLoopSessions.length})</span>`;
      container.appendChild(loopHeader);

      const statusIcons = {
        running: '🟢',
        completed: '✅',
        paused: '⏸️',
        interrupted: '⚠️',
        recovering: '🔄',
        failed: '❌',
        idle: '⏹️'
      };

      allLoopSessions.forEach(s => {
        const sId = s.id || s.session_id;
        const icon = statusIcons[s.status] || '🔄';
        const title = s.title || s.name || s.goal || 'Untitled Loop Run';
        const isSelected = (sId === activeLoopSessionId && isLoopViewActive);
        
        const div = document.createElement('div');
        div.className = `session-item ${isSelected ? 'active' : ''}`;
        div.onclick = () => selectLoopSession(sId);
        div.title = `${title} (${s.status || 'idle'})`;
        div.innerHTML = `
          <span class="session-title-span">${icon} ${escapeHtml(title)}</span>
          <span class="session-item-badge">${escapeHtml(s.status || 'idle')}</span>
          <button class="session-del-btn" title="Delete run" onclick="event.stopPropagation(); deleteLoopSession('${sId}')">✕</button>
        `;
        container.appendChild(div);
      });
    }

    // 2. Direct Chat Conversations Section
    const chatHeader = document.createElement('div');
    chatHeader.className = 'sidebar-section-header';
    chatHeader.innerHTML = `<span>💬 Chats (${chatList.length})</span>`;
    container.appendChild(chatHeader);

    if (chatList.length === 0) {
      const emptyDiv = document.createElement('div');
      emptyDiv.style.padding = '6px 10px';
      emptyDiv.style.fontSize = '12px';
      emptyDiv.style.color = 'var(--text-dim)';
      emptyDiv.innerText = 'No direct chats';
      container.appendChild(emptyDiv);
    } else {
      if (!activeSessionId && !isLoopViewActive) activeSessionId = chatList[0].id;

      chatList.forEach(sess => {
        const isSelected = (sess.id === activeSessionId && !isLoopViewActive);
        const div = document.createElement('div');
        div.className = `session-item ${isSelected ? 'active' : ''}`;
        div.onclick = () => switchSession(sess.id);
        div.title = sess.title || 'Chat';
        div.innerHTML = `
          <span class="session-title-span">💬 ${escapeHtml(sess.title)}</span>
          <button class="session-del-btn" title="Delete chat" onclick="event.stopPropagation(); deleteSession('${sess.id}')">✕</button>
        `;
        container.appendChild(div);
      });
    }

    if (!isLoopViewActive && activeSessionId) {
      await loadActiveSessionMessages();
    }
  } catch(e) { handleServerDisconnected(); }
}

async function selectLoopSession(id) {
  isLoopViewActive = true;
  activeLoopSessionId = id;
  try { localStorage.setItem('swarm_active_loop_session', id); } catch(_) {}
  toggleMobileChatSidebar(false);

  try {
    const res = await fetch(`/api/loop/sessions/${encodeURIComponent(id)}/select`, { method: 'POST' });
    const data = await res.json();
    if (data.success && data.state) {
      renderLoopDashboard(data.state);
      renderLiveLoopStreamInChat(data.state);
    }
  } catch(e) {
    pollLoopState();
  }

  await loadSessionsList();
  showToast("Switched to Swarm Run", "info", 1500);
}

async function startNewSwarmLoop() {
  try {
    const res = await fetch('/api/loop/sessions/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New Swarm Run', goal: '', repo_path: currentRepoPath })
    });
    const sess = await res.json();
    if (sess && sess.id) {
      activeLoopSessionId = sess.id;
      isLoopViewActive = true;
      try { localStorage.setItem('swarm_active_loop_session', sess.id); } catch(_) {}
      toggleMobileChatSidebar(false);
      await loadSessionsList();
      pollLoopState();
      showToast("🚀 Created new Swarm Run", "success", 2000);
      const goalInput = document.getElementById('promptInput') || document.getElementById('loopGoalInput');
      if (goalInput) goalInput.focus();
    }
  } catch(e) { handleServerDisconnected(); }
}

async function deleteLoopSession(id) {
  try {
    await fetch('/api/loop/sessions/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id })
    });
    if (activeLoopSessionId === id) activeLoopSessionId = "";
    showToast("Swarm Run deleted", "info");
    await loadSessionsList();
    pollLoopState();
  } catch(e) { showToast("Failed to delete run: " + e.message, "error"); }
}

async function startNewChat() {
  try {
    isLoopViewActive = false;
    const res = await fetch('/api/sessions/new', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: 'New Chat', repo_path: currentRepoPath })
    });
    const sess = await res.json();
    activeSessionId = sess.id;
    toggleMobileChatSidebar(false);
    await loadSessionsList();
  } catch(e) { handleServerDisconnected(); }
}

async function switchSession(id) {
  isLoopViewActive = false;
  if (activeSessionId === id) {
    toggleMobileChatSidebar(false);
    return;
  }
  activeSessionId = id;
  toggleMobileChatSidebar(false);
  
  await loadSessionsList();
  await loadActiveSessionMessages();
  showToast("Switched chat session", "info", 1500);
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

let isChatUserScrolledUp = false;

function initChatScrollListener() {
  const container = document.getElementById('chatContainer');
  if (!container) return;
  container.addEventListener('scroll', () => {
    const threshold = 80;
    const distanceFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
    isChatUserScrolledUp = distanceFromBottom > threshold;
    updateScrollToBottomButton(distanceFromBottom > 150);
  });
}

function scrollChatToBottom(force = false) {
  const container = document.getElementById('chatContainer');
  if (!container) return;
  if (force || !isChatUserScrolledUp) {
    container.scrollTo({
      top: container.scrollHeight,
      behavior: force ? 'smooth' : 'auto'
    });
    isChatUserScrolledUp = false;
    updateScrollToBottomButton(false);
  }
}

function updateScrollToBottomButton(show) {
  let btn = document.getElementById('chatScrollBottomBtn');
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'chatScrollBottomBtn';
    btn.className = 'chat-scroll-bottom-btn';
    btn.innerHTML = '↓ Scroll to bottom';
    btn.onclick = () => {
      isChatUserScrolledUp = false;
      scrollChatToBottom(true);
    };
    const inputSec = document.querySelector('.input-section');
    if (inputSec) {
      inputSec.style.position = 'relative';
      inputSec.appendChild(btn);
    }
  }
  if (btn) {
    btn.style.display = show ? 'flex' : 'none';
  }
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
          <div class="msg-author">🌌 Swarm Autonomous Agent · ${escapeHtml(sess.title)}</div>
          <span class="status-badge badge-online">Ready</span>
        </div>
        <div class="markdown-body">
          <p>Session active. Ready for direct conversation, code analysis, or autonomous feature loops.</p>
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

        const stepsHtml = (turn.status_steps || []).map(s => `<div>${escapeHtml(s)}</div>`).join('');
        const planHtml = turn.plan ? renderCboPlanHtml(turn.plan, msgId) : '';
        const thoughtLabel = turn.thought_summary || (turn.tier === 'direct' ? `Direct Answer · ${turn.duration || 0.2}s` : (turn.tier === 'web_scout' ? `Web & Context7 Grounded · ${turn.duration || 1.1}s` : `Swarm Cross-Checked · ${turn.duration || 1.8}s`));
        
        const thoughtBlock = (turn.status_steps && turn.status_steps.length > 0) ? `
          <details class="qwen-thought-details">
            <summary class="qwen-thought-summary">
              <span class="qwen-thought-icon">⚡</span>
              <span class="qwen-thought-title">${escapeHtml(thoughtLabel)}</span>
              <span class="qwen-thought-chevron">▾</span>
            </summary>
            <div class="qwen-thought-body">
              <div class="status-timeline">${stepsHtml}</div>
              ${planHtml}
            </div>
          </details>
        ` : '';

        assistRow.innerHTML = `
          <div class="msg-assistant" id="${msgId}">
            <div class="msg-header">
              <div class="msg-author">🌌 Swarm Autonomous Agent</div>
              <div class="ghd-toolbar-group">
                <span class="chip chip--green">✓ ${turn.duration || 1.2}s (LFM 2.5 VL)</span>
              </div>
            </div>
            ${thoughtBlock}
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
    scrollChatToBottom(true);
  } catch(e) { handleServerDisconnected(); }
}

// ─────────────────────────────────────────────────────────────
// GROUPED ARTIFACTS VAULT (FILTERED BY SELECTED REPO)
// ─────────────────────────────────────────────────────────────
let vaultFilterMode = 'selected'; // 'selected' or 'all'

function toggleArtifactsFilter(mode) {
  vaultFilterMode = mode;
  const selBtn = document.getElementById('vaultFilterSelectedBtn');
  const allBtn = document.getElementById('vaultFilterAllBtn');
  if (selBtn && allBtn) {
    selBtn.style.background = (mode === 'selected') ? 'var(--primary-strong)' : 'var(--ink-500)';
    selBtn.style.color = (mode === 'selected') ? 'var(--text-bright)' : 'var(--text)';
    allBtn.style.background = (mode === 'all') ? 'var(--primary-strong)' : 'var(--ink-500)';
    allBtn.style.color = (mode === 'all') ? 'var(--text-bright)' : 'var(--text)';
  }
  loadArtifactsVault();
}

async function loadArtifactsVault() {
  try {
    const res = await fetch(`/api/artifacts?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const data = await res.json();
    const container = document.getElementById('groupedArtifactsContainer');
    container.innerHTML = '';

    let groups = data.groups || [];
    const selRepoName = data.selected_repo || (currentRepoPath ? currentRepoPath.split('/').pop() : '');

    const selBtn = document.getElementById('vaultFilterSelectedBtn');
    if (selBtn && selRepoName) {
      selBtn.innerText = `📁 Current Repo (${selRepoName})`;
    }

    if (vaultFilterMode === 'selected' && selRepoName) {
      groups = groups.filter(g => g.is_selected || g.repo_name.toLowerCase() === selRepoName.toLowerCase());
    }

    if (groups.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; color:var(--text-muted); padding:36px; background:var(--ink-800); border:1px solid var(--ink-500); border-radius:10px;">
          <div style="font-size:15px; font-weight:700; color:var(--text-bright); margin-bottom:6px;">No artifacts found for ${vaultFilterMode === 'selected' ? 'current repository (' + (selRepoName || 'Selected') + ')' : 'any repository'}</div>
          <div style="font-size:12.5px; margin-bottom:14px;">Generate an audit, implementation plan, or autonomous feature to produce markdown deliverables.</div>
          <button class="action-btn" onclick="toggleArtifactsFilter('all')">🌐 View All Repositories</button>
        </div>
      `;
      return;
    }

    groups.forEach(grp => {
      const card = document.createElement('div');
      card.className = 'repo-artifact-group';
      const isCurrentRepo = grp.is_selected || (selRepoName && grp.repo_name.toLowerCase() === selRepoName.toLowerCase());

      let rowsHtml = '';
      grp.artifacts.forEach(art => {
        const sizeKb = (art.size / 1024).toFixed(1) + ' KB';
        rowsHtml += `
          <tr style="border-bottom:1px solid var(--ink-600);">
            <td style="padding:10px 16px; font-weight:700; color:var(--text-bright);">📄 ${escapeHtml(art.name)}</td>
            <td style="padding:10px 16px;"><span class="file-status-badge status-u">${escapeHtml(art.type)}</span></td>
            <td style="padding:10px 16px; font-family:var(--font-mono); color:var(--text-muted); font-size:12px;">${sizeKb}</td>
            <td style="padding:10px 16px; font-family:var(--font-mono); color:var(--text-muted); font-size:12px;">${escapeHtml(art.modified)}</td>
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
        <div class="repo-group-header" onclick="toggleArtifactGroup('${escapeJs(grp.repo_name)}')" style="${isCurrentRepo ? 'border-left: 4px solid var(--accent); background:var(--ink-600);' : ''}">
          <div class="repo-group-title">
            <span>📁 Repository: <b>${escapeHtml(grp.repo_name)}</b></span>
            ${isCurrentRepo ? '<span class="file-status-badge status-a">ACTIVE REPO</span>' : ''}
            <span class="file-status-badge status-u">${grp.count} Document${grp.count === 1 ? '' : 's'}</span>
          </div>
          <span id="group-icon-${escapeJs(grp.repo_name)}" style="color:var(--accent); font-weight:700;">▾</span>
        </div>
        <div id="group-body-${escapeJs(grp.repo_name)}" style="display:block;">
          <table style="width:100%; border-collapse:collapse; background:var(--ink-900);">
            <thead>
              <tr style="background:var(--ink-850); border-bottom:1px solid var(--ink-500); color:var(--accent); font-size:11.5px; text-align:left;">
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

// ─────────────────────────────────────────────────────────────
// DYNAMIC 50+ INSTALLED SKILLS & CAPACITY CATALOG
// ─────────────────────────────────────────────────────────────
let allInstalledSkills = [];
let activeSkillCategory = 'all';

const SKILL_CATEGORY_META = {
  'all': { label: 'All Skills', icon: '⚡' },
  'Security & Audit': { label: 'Security & Audit', icon: '🛡️' },
  'Testing & QA': { label: 'Testing & QA', icon: '🧪' },
  'Architecture & Planning': { label: 'Architecture & Planning', icon: '📐' },
  'Frontend & UI/UX': { label: 'Frontend & UI/UX', icon: '🎨' },
  'Codebase Intelligence & Git': { label: 'Codebase Intelligence & Git', icon: '🌿' },
  'Agent Extensions & Customization': { label: 'Agent Extensions & Customization', icon: '🧩' },
  'Research & Documentation': { label: 'Research & Documentation', icon: '📚' }
};

function renderSkillCategoryPills() {
  const container = document.getElementById('skillCategoryPills');
  if (!container) return;

  const counts = { 'all': allInstalledSkills.length };
  allInstalledSkills.forEach(s => {
    const cat = (s.category || 'Research & Documentation').trim();
    counts[cat] = (counts[cat] || 0) + 1;
  });

  const categories = [
    'all',
    'Security & Audit',
    'Testing & QA',
    'Architecture & Planning',
    'Frontend & UI/UX',
    'Codebase Intelligence & Git',
    'Agent Extensions & Customization',
    'Research & Documentation'
  ];

  container.innerHTML = '';
  categories.forEach(cat => {
    const meta = SKILL_CATEGORY_META[cat] || { label: cat, icon: '🏷️' };
    const count = counts[cat] || 0;
    const btn = document.createElement('button');
    const isActive = (activeSkillCategory.trim().toLowerCase() === cat.trim().toLowerCase());
    btn.className = isActive ? 'action-btn active' : 'action-btn';
    btn.dataset.category = cat;
    btn.innerHTML = `${meta.icon} ${meta.label} <span style="opacity:0.75; font-size:11px; margin-left:2px;">(${count})</span>`;
    if (isActive) {
      btn.style.background = 'var(--ink-500)';
      btn.style.color = 'var(--accent)';
      btn.style.borderColor = 'var(--accent)';
    } else {
      btn.style.background = 'var(--ink-700)';
      btn.style.color = 'var(--text-muted)';
      btn.style.borderColor = 'var(--line-strong)';
    }
    btn.onclick = () => filterSkillsByCategory(cat);
    container.appendChild(btn);
  });
}

async function loadSkillsCatalog() {
  try {
    const res = await fetch('/api/skills/catalog', { cache: 'no-store' });
    const data = await res.json();
    allInstalledSkills = data.skills || [];
    
    const countBadge = document.getElementById('skillsTotalCountBadge');
    if (countBadge) {
      countBadge.innerText = `⚡ ${allInstalledSkills.length} Live Skills`;
    }
    renderSkillCategoryPills();
    renderSkillsGrid(allInstalledSkills);
  } catch(e) {}
}

function filterSkillsByCategory(cat) {
  activeSkillCategory = cat;
  
  const pills = document.querySelectorAll('#skillCategoryPills .action-btn');
  pills.forEach(p => {
    const isTarget = (p.dataset.category && p.dataset.category.trim().toLowerCase() === cat.trim().toLowerCase());
    if (isTarget) {
      p.className = 'action-btn active';
      p.style.background = 'var(--ink-500)';
      p.style.color = 'var(--accent)';
      p.style.borderColor = 'var(--accent)';
    } else {
      p.className = 'action-btn';
      p.style.background = 'var(--ink-700)';
      p.style.color = 'var(--text-muted)';
      p.style.borderColor = 'var(--line-strong)';
    }
  });

  applySkillsFilter();
}

function filterLegendCards(query) {
  applySkillsFilter(query);
}

function applySkillsFilter(searchQuery = "") {
  const inputEl = document.getElementById('legendFilterInput');
  const q = (typeof searchQuery === 'string' && searchQuery.trim() !== ''
    ? searchQuery
    : (inputEl ? inputEl.value : '')
  ).toLowerCase().trim();
  
  const filtered = allInstalledSkills.filter(s => {
    const sCat = (s.category || 'Research & Documentation').trim();
    const activeCat = (activeSkillCategory || 'all').trim();
    const matchesCat = (activeCat.toLowerCase() === 'all' || sCat.toLowerCase() === activeCat.toLowerCase());
    const text = (s.name + ' ' + s.description + ' ' + s.role + ' ' + sCat + ' ' + (s.tools || []).join(' ')).toLowerCase();
    const matchesQuery = (!q || text.includes(q));
    return matchesCat && matchesQuery;
  });
  renderSkillsGrid(filtered);
}

function renderSkillsGrid(skills) {
  const container = document.getElementById('dynamicSkillsCatalogContainer');
  if (!container) return;
  container.innerHTML = '';

  if (skills.length === 0) {
    container.innerHTML = '<div style="color:var(--text-muted); padding:24px; text-align:center; grid-column:1/-1;">No matching skills found for this category or filter.</div>';
    return;
  }

  skills.forEach(s => {
    const card = document.createElement('div');
    card.className = 'legend-card';
    const toolsHtml = (s.tools || []).map(t => `<span class="tool-tag">${escapeHtml(t)}</span>`).join(' ');
    
    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:8px;">
        <span style="font-weight:700; color:var(--text-bright); font-size:13.5px;">${escapeHtml(s.name)}</span>
        <span class="file-status-badge status-u" style="font-size:10px; white-space:nowrap;">${escapeHtml(s.category)}</span>
      </div>
      <div style="font-size:12px; color:var(--accent); font-weight:700;">${escapeHtml(s.role)}</div>
      <div style="font-size:12px; color:var(--text); line-height:1.45; flex:1;">${escapeHtml(s.description)}</div>
      <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:6px;">${toolsHtml}</div>
    `;
    container.appendChild(card);
  });
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

let lastDebugLogsSignature = "";

async function fetchLiveDebugLogs() {
  try {
    const res = await fetch('/api/debug/logs?limit=50', { cache: 'no-store' });
    const data = await res.json();
    const list = document.getElementById('debugLogList');
    if (!list) return;

    const logs = data.logs || [];
    const signature = logs.map(l => `${l.time_ms || l.timestamp}-${l.action}`).join('|');
    if (signature === lastDebugLogsSignature && list.children.length > 0) {
      return; // No new logs, do not touch DOM
    }
    lastDebugLogsSignature = signature;

    const isAtBottom = list.children.length === 0 || (list.scrollHeight - list.scrollTop - list.clientHeight) < 45;
    const previousScrollTop = list.scrollTop;

    list.innerHTML = '';

    logs.forEach(log => {
      const div = document.createElement('div');
      const lvl = (log.level || 'INFO').toLowerCase();
      div.className = `debug-log-entry ${lvl === 'error' ? 'error' : (lvl === 'warn' ? 'warn' : '')}`;
      div.innerHTML = `
        <div><span style="color:var(--text-muted);">[${escapeHtml(log.timestamp)}]</span> <b style="color:var(--accent);">[${escapeHtml(log.category)}]</b> ${escapeHtml(log.action)}</div>
        ${log.error ? `<div style="color:var(--rose); font-size:11px; margin-top:2px;">↳ ${escapeHtml(log.error)}</div>` : ''}
      `;
      list.appendChild(div);
    });

    if (isAtBottom) {
      list.scrollTop = list.scrollHeight;
    } else {
      list.scrollTop = previousScrollTop;
    }
  } catch(e) {}
}

async function clearDebugLogs() {
  lastDebugLogsSignature = "";
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

    // Restore the previously selected repo if it still exists; else default to first.
    let saved = "";
    try { saved = localStorage.getItem('swarm_selected_repo') || ""; } catch(_) {}
    const match = saved && repos.find(r => r.path === saved);
    currentRepoPath = match ? saved : repos[0].path;
    sel.value = currentRepoPath;
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
// Render a combined state snapshot (from the SSE stream or a one-shot fetch).
function applyStateSnapshot(data) {
  if (!data) return;
  handleServerConnected();

  if (data.metrics && data.metrics.gpu) {
    const gpu = data.metrics.gpu;
    const vramGb = (gpu.mem_used / 1024).toFixed(1);
    document.getElementById('vramVal').innerText = `VRAM: ${vramGb}/16GB (${gpu.mem_percent}%)`;
    document.getElementById('gpuVal').innerText = `GPU: ${gpu.util}% (${gpu.temp}°C)`;
    document.getElementById('ramVal').innerText = `RAM: ${data.metrics.ram_used_gb}/${data.metrics.ram_total_gb}GB`;
  }

  const mVal = document.getElementById('modelVal');
  if (mVal) {
    if (data.status && data.status.lfm) {
      mVal.innerText = 'LFM 2.5 VL: 2 SLOTS READY';
      mVal.style.color = 'var(--green)';
    } else {
      mVal.innerText = 'LFM 2.5 VL: HOST OFFLINE';
      mVal.style.color = 'var(--orange)';
    }
  }

  if (data.topology) renderDynamicTopology(data.topology);
  if (data.loop_state) {
    renderUnifiedAgentLoopState(data.loop_state);
  }
}

// ─────────────────────────────────────────────────────────────
// UNIFIED SWARM AGENT REAL-TIME LOOP RENDERER
// ─────────────────────────────────────────────────────────────
function renderUnifiedAgentLoopState(state) {
  if (!state) return;
  const currentId = state.id || state.session_id;
  if (currentId) activeLoopSessionId = currentId;

  // 1. Update Header Status Badge
  const badge = document.getElementById('agentLoopStatusBadge');
  const rawStatus = (state.status || 'idle').toLowerCase();
  if (badge) {
    if (rawStatus === 'running') {
      const taskCount = (state.tasks || []).length;
      const completedCount = (state.tasks || []).filter(t => t.status === 'completed').length;
      badge.innerHTML = `<span class="loop-spinner"></span> RUNNING (${completedCount}/${taskCount || 1} tasks · Iter ${state.iteration || 1})`;
      badge.className = 'status-badge badge-running';
    } else if (rawStatus === 'paused') {
      badge.innerText = '⏸️ PAUSED';
      badge.className = 'status-badge badge-paused';
    } else if (rawStatus === 'interrupted' || rawStatus === 'recovering') {
      badge.innerText = '⚠️ RECOVERABLE';
      badge.className = 'status-badge badge-interrupted';
    } else if (rawStatus === 'completed') {
      badge.innerText = '✅ GOAL COMPLETED';
      badge.className = 'status-badge badge-online';
    } else if (rawStatus === 'failed') {
      badge.innerText = '❌ LOOP STOPPED';
      badge.className = 'status-badge badge-offline';
    } else {
      badge.innerText = 'IDLE / READY';
      badge.className = 'status-badge badge-idle';
    }
  }

  // 2. Update Action Buttons in Agent Control Bar
  const startBtn = document.getElementById('agentStartBtn');
  const resumeBtn = document.getElementById('agentResumeBtn');
  const pauseBtn = document.getElementById('agentPauseBtn');
  const stopBtn = document.getElementById('agentStopBtn');

  if (startBtn && pauseBtn && stopBtn) {
    if (rawStatus === 'running') {
      startBtn.style.display = 'none';
      if (resumeBtn) resumeBtn.style.display = 'none';
      pauseBtn.style.display = 'inline-flex';
      stopBtn.style.display = 'inline-flex';
    } else if (rawStatus === 'paused' || rawStatus === 'interrupted') {
      startBtn.style.display = 'none';
      pauseBtn.style.display = 'none';
      if (resumeBtn) resumeBtn.style.display = 'inline-flex';
      stopBtn.style.display = 'inline-flex';
    } else {
      startBtn.style.display = 'inline-flex';
      if (resumeBtn) resumeBtn.style.display = 'none';
      pauseBtn.style.display = 'none';
      stopBtn.style.display = 'none';
    }
  }

  // 3. Update Progress Strip & Phase Pills
  const strip = document.getElementById('agentProgressStrip');
  const goalEl = document.getElementById('agentProgressGoal');
  const iterEl = document.getElementById('agentProgressIter');
  const taskPill = document.getElementById('agentActiveTaskPill');

  if (rawStatus === 'running' || rawStatus === 'paused') {
    if (strip) strip.style.display = 'flex';
    if (goalEl && state.goal) goalEl.innerText = state.goal;
    if (iterEl) iterEl.innerText = `Iter ${state.iteration || 1}/${state.max_iterations || 20}`;

    if (taskPill) {
      taskPill.style.display = 'inline-flex';
      taskPill.innerText = state.active_subagent ? `⚡ ${state.active_subagent}` : (state.current_task_id ? `⚡ Task: ${state.current_task_id}` : '⚡ Continuous Batching Slot');
    }

    const sub = (state.active_subagent || '').toLowerCase();
    const phasePlan = document.getElementById('phasePlan');
    const phaseDev = document.getElementById('phaseDev');
    const phaseQA = document.getElementById('phaseQA');

    [phasePlan, phaseDev, phaseQA].forEach(p => { if (p) p.className = 'phase-pill'; });

    if (sub.includes('architect') || sub.includes('research') || sub.includes('scout') || sub.includes('plan') || sub.includes('cbo') || sub.includes('pm') || sub.includes('preflight') || sub.includes('decompose')) {
      if (phasePlan) phasePlan.className = 'phase-pill active';
    } else if (sub.includes('draft') || sub.includes('dev') || sub.includes('pi')) {
      if (phaseDev) phaseDev.className = 'phase-pill active';
    } else if (sub.includes('qa') || sub.includes('test') || sub.includes('verifier') || sub.includes('judge') || sub.includes('sec') || sub.includes('security')) {
      if (phaseQA) phaseQA.className = 'phase-pill active';
    } else {
      if (phaseDev) phaseDev.className = 'phase-pill active';
    }
  } else {
    if (strip) strip.style.display = 'none';
    if (taskPill) taskPill.style.display = 'none';
  }

  // 4. Stream real-time events directly into active chat feed
  if (rawStatus === 'running' || rawStatus === 'paused' || rawStatus === 'completed') {
    renderLiveLoopStreamInChat(state);
  }
}

function renderLiveLoopStreamInChat(state) {
  const container = document.getElementById('chatContainer');
  if (!container) return;

  const currentLoopId = state.id || state.session_id || 'active';
  let card = document.getElementById(`loop-card-${currentLoopId}`);

  if (!card) {
    const logs = state.live_logs || [];
    if (logs.length === 0 && !state.goal) return;

    const assistRow = document.createElement('div');
    assistRow.className = 'msg-row';
    assistRow.id = `loop-row-${currentLoopId}`;
    assistRow.innerHTML = `
      <div class="msg-assistant" id="loop-card-${currentLoopId}">
        <div class="msg-header">
          <div class="msg-author">🌌 Swarm Autonomous Agent · Active Loop</div>
          <span class="status-badge badge-running" id="loop-card-badge-${currentLoopId}"><span class="loop-spinner"></span> Looping...</span>
        </div>
        <div class="status-timeline" id="loop-timeline-${currentLoopId}"></div>
        <div id="loop-tasks-${currentLoopId}" style="display:flex; flex-direction:column; gap:6px; margin-bottom:10px;"></div>
        <div class="markdown-body" id="loop-body-${currentLoopId}"></div>
        <div id="loop-escalation-${currentLoopId}"></div>
      </div>
    `;
    container.appendChild(assistRow);
    card = document.getElementById(`loop-card-${currentLoopId}`);
  }

  const cardBadge = document.getElementById(`loop-card-badge-${currentLoopId}`);
  if (cardBadge) {
    if (state.status === 'running') {
      cardBadge.innerHTML = `<span class="loop-spinner"></span> Running (Iter ${state.iteration || 1})`;
      cardBadge.className = 'status-badge badge-running';
    } else if (state.status === 'completed') {
      cardBadge.innerText = `✓ Completed in ${state.iteration || 1} iterations`;
      cardBadge.className = 'status-badge badge-online';
    } else if (state.status === 'paused') {
      cardBadge.innerText = '⏸️ Paused';
      cardBadge.className = 'status-badge badge-paused';
    }
  }

  const timeline = document.getElementById(`loop-timeline-${currentLoopId}`);
  if (timeline && state.live_logs) {
    const recentLogs = state.live_logs.slice(-8);
    timeline.innerHTML = recentLogs.map(l => {
      const cls = l.is_active ? 'step-active' : '';
      return `<div class="${cls}">[${escapeHtml(l.timestamp)}] ${escapeHtml(l.message)}</div>`;
    }).join('');
  }

  const tasksContainer = document.getElementById(`loop-tasks-${currentLoopId}`);
  if (tasksContainer && state.tasks && state.tasks.length > 0) {
    tasksContainer.innerHTML = state.tasks.map(t => {
      const st = t.status || 'pending';
      const icon = st === 'completed' ? '✓' : (st === 'running' ? '⚡' : (st === 'failed' ? '✗' : '○'));
      const badgeCls = st === 'completed' ? 'status-a' : (st === 'running' ? 'status-m' : (st === 'failed' ? 'status-d' : 'status-u'));
      return `
        <div class="task-event-card">
          <div class="task-event-card__head">
            <span class="task-event-card__title">${icon} ${escapeHtml(t.title || t.name)}</span>
            <span class="file-status-badge ${badgeCls}">${escapeHtml(st.toUpperCase())}</span>
          </div>
          ${t.subagent ? `<div style="font-size:11px; color:var(--text-muted);">Assigned: ${escapeHtml(t.subagent)}</div>` : ''}
          ${t.files_written && t.files_written.length ? `<div style="font-size:11px; color:var(--green);">📝 Files modified: ${escapeHtml(t.files_written.join(', '))}</div>` : ''}
        </div>
      `;
    }).join('');
  }

  const escContainer = document.getElementById(`loop-escalation-${currentLoopId}`);
  if (escContainer) {
    const pendingQuestions = (state.pending_user_questions || []).filter(q => !q.answered);
    if (pendingQuestions.length > 0) {
      escContainer.innerHTML = pendingQuestions.map(q => {
        const optionsHtml = (q.options && q.options.length > 0) ? `
          <div class="operator-options-group">
            <div class="operator-options-label">Recommended Options (Click to select):</div>
            <div class="operator-options-chips">
              ${q.options.map((opt, idx) => `
                <button type="button" class="operator-option-chip ${idx === 0 ? 'operator-option-chip--recommended' : ''}" 
                  onclick="selectOperatorOption('${escapeHtml(q.task_id)}', '${escapeHtml(opt.value).replace(/'/g, "\\'")}')"
                  title="Click to select this recommendation">
                  ${escapeHtml(opt.label)}
                </button>
              `).join('')}
            </div>
          </div>
        ` : '';

        return `
          <div class="operator-prompt-box">
            <div class="operator-prompt-title">❓ Agent Request for Guidance (${escapeHtml(q.subagent || 'Lead Advisor')})</div>
            <div style="font-size:13px; color:var(--text-bright); margin-bottom: 8px;">${escapeHtml(q.question)}</div>
            ${optionsHtml}
            <div class="operator-prompt-input-row" style="margin-top: 8px;">
              <input type="text" class="operator-prompt-input" id="input-esc-${q.task_id}" placeholder="Type your guidance or click a recommended option above..." onkeydown="if(event.key==='Enter') submitOperatorAnswer('${q.task_id}')">
              <button class="action-btn action-btn--accent" onclick="submitOperatorAnswer('${q.task_id}')">Send Guidance</button>
            </div>
          </div>
        `;
      }).join('');
    } else {
      escContainer.innerHTML = '';
    }
  }

  const bodyEl = document.getElementById(`loop-body-${currentLoopId}`);
  if (bodyEl && state.final_summary) {
    bodyEl.innerHTML = parseMarkdown(state.final_summary);
  }

  scrollChatToBottom(false);
}

function selectOperatorOption(taskId, value) {
  const input = document.getElementById(`input-esc-${taskId}`);
  if (input) {
    input.value = value;
    input.focus();
  }
}

async function submitOperatorAnswer(taskId) {
  const input = document.getElementById(`input-esc-${taskId}`);
  const answer = input ? input.value.trim() : '';
  if (!answer) {
    showToast("Please enter your guidance instructions first.", "warn");
    return;
  }

  try {
    const res = await fetch('/api/loop/answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task_id: taskId, answer: answer })
    });
    const data = await res.json();
    if (data.success) {
      showToast("✓ Guidance submitted — autonomous agent loop resumed!", "success", 2500);
      if (input) {
        input.value = '';
        input.disabled = true;
      }
      if (typeof fetchCurrentLoopStatus === 'function') {
        fetchCurrentLoopStatus();
      }
      if (typeof fetchLiveDebugLogs === 'function') {
        fetchLiveDebugLogs();
      }
    } else {
      showToast(`Guidance submission failed: ${data.error || 'Unknown error'}`, "danger", 3500);
    }
  } catch (err) {
    showToast(`Error submitting guidance: ${err.message}`, "danger");
  }
}

function startAutonomousLoopFromInput() {
  const promptInput = document.getElementById('promptInput');
  let prompt = promptInput ? promptInput.value.trim() : '';
  if (!prompt) {
    prompt = "Implement feature with clean architecture, QA tests, and full verification.";
    if (promptInput) promptInput.value = prompt;
  }
  submitMessage();
}

function sendQuickActionPrompt(action) {
  const promptInput = document.getElementById('promptInput');
  let text = "";
  if (action === 'implement') {
    text = "Implement new feature with clean architecture (≤35 lines per function, single-responsibility domain classes, dependency injection), QA unit tests, and security review.";
  } else if (action === 'test') {
    text = "Run the full project test suite, locate any failing tests or regression bugs, and draft surgical fixes with real verification.";
  } else if (action === 'audit') {
    text = "Run a comprehensive security, performance, and clean architecture audit on this repository and produce an authoritative blueprint.";
  } else if (action === 'scout') {
    text = "Scan the repository files, locate all entrypoints, project manifests, routes, and data models.";
  }
  if (promptInput) {
    promptInput.value = text;
    autoResize(promptInput);
    submitMessage();
  }
}

// Single real-time channel: one EventSource replaces per-second polling of
// /api/metrics and /api/loop/status. The browser makes the initial request;
// the server pushes updates and the client auto-reconnects on drop.
let _eventSource = null;
function initEventStream() {
  if (typeof EventSource === 'undefined') {
    // Fallback for ancient browsers: low-frequency polling.
    updateTelemetryAndTopology();
    if (!pollInterval) pollInterval = setInterval(updateTelemetryAndTopology, 3000);
    return;
  }
  try { if (_eventSource) _eventSource.close(); } catch(_) {}
  _eventSource = new EventSource('/api/events');
  _eventSource.addEventListener('state', (e) => {
    try { applyStateSnapshot(JSON.parse(e.data)); } catch(_) {}
  });
  _eventSource.onerror = () => {
    // EventSource retries automatically (server sends `retry:`); reflect offline meanwhile.
    handleServerDisconnected();
  };
}

// One-shot fetch — used as a fallback and for instant refresh after user actions.
async function updateTelemetryAndTopology() {
  try {
    const controller = new AbortController();
    const tId = setTimeout(() => controller.abort(), 2000);
    const res = await fetch('/api/metrics', { cache: 'no-store', signal: controller.signal });
    clearTimeout(tId);
    if (!res.ok) { handleServerDisconnected(); return; }
    applyStateSnapshot(await res.json());
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
      
      const toolsHtml = (s.tools || []).map(t => `<span style="font-family:var(--font-mono); font-size:9.5px; background:var(--ink-500); color:var(--accent); padding:2px 6px; border-radius:4px; border:1px solid var(--line-strong);">${escapeHtml(t)}</span>`).join(' ');

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:700; color:var(--text-bright); font-size:13px;">${escapeHtml(s.name)}</span>
          <span class="status-badge ${isRunning ? 'badge-running' : (s.status === 'online' ? 'badge-online' : 'badge-idle')}">${escapeHtml(s.status.toUpperCase())}</span>
        </div>
        <div style="font-size:10.5px; color:var(--text-muted); font-weight:700;">${escapeHtml(s.role || 'Level 3 Sub-Agent')}</div>
        <div style="font-family:var(--font-mono); font-size:11px; background:var(--ink-900); color:var(--accent); border:1px solid var(--ink-500); padding:3px 7px; border-radius:6px; font-weight:700;">🎯 Skill: ${escapeHtml(s.skill || 'Specialist')}</div>
        <div class="agent-task" style="font-family:var(--font-mono); font-size:11px; background:var(--ink-900); padding:6px 10px; border-radius:8px; border:1px solid var(--ink-500); color:var(--text-bright);">${escapeHtml(s.task || 'Idle')}</div>
        <div style="display:flex; flex-wrap:wrap; gap:4px;">${toolsHtml}</div>
      `;
      subContainer.appendChild(card);
    });
  }

  const activePillVal = document.getElementById('activeAgentsVal');
  if (activePillVal) {
    if (runningCount > 0) {
      activePillVal.innerText = `Status: Active`;
      activePillVal.style.color = 'var(--green)';
    } else {
      activePillVal.innerText = `Status: Ready`;
      activePillVal.style.color = 'var(--accent)';
    }
  }

  const badge = document.getElementById('agentCountBadge');
  if (badge) {
    if (runningCount > 0) {
      badge.innerText = `🟢 ${runningCount} / ${totalNodes} Agents Active (${runningCount} Running in Parallel)`;
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

// Kept for callers, but a no-op now: the SSE stream (/api/events) adapts its own
// cadence server-side — ~1s while agents run, ~3s idle — so no client interval is
// needed. Starting one here would double-render against the stream.
function setPollingSpeed(fast) { /* handled by the SSE stream */ }

window.addEventListener('DOMContentLoaded', async () => {
  initSplitResizers();
  initCustomContextMenu();
  initChatScrollListener();
  await loadRepos();
  await loadSessionsList();
  await loadLoopSessionsList();
  await pollLoopState();
  await loadModelCatalogAndAssignments();
  await loadSkillsCatalog();
  await loadBackendsStatus();
  initEventStream();

  try {
    const savedTab = localStorage.getItem('swarm_active_tab');
    if (savedTab) switchTab(savedTab);
  } catch(_) {}
});

window.addEventListener('resize', () => {
  if (window.innerWidth <= 768) {
    toggleGhdMobileView('list');
  }
});

function onRepoChanged() {
  const sel = document.getElementById('repoSelect');
  currentRepoPath = sel.value;
  try { localStorage.setItem('swarm_selected_repo', currentRepoPath); } catch(_) {}
  selectedGhdFile = "";
  selectedGhdCommit = "";
  loadGitHubDesktopState();
  loadArtifactsVault();
  loadLoopSessionsList();
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

let currentChatMode = 'chat';

function setChatMode(mode) {
  currentChatMode = mode;
  ['chat', 'apply', 'loop'].forEach(m => {
    const btn = document.getElementById(`mode${m.charAt(0).toUpperCase() + m.slice(1)}Btn`);
    if (btn) {
      if (m === mode) {
        btn.classList.add('active');
      } else {
        btn.classList.remove('active');
      }
    }
  });
  const map = {
    chat: "💬 Chat: Conversational coding help",
    apply: "🛠️ Apply: Apply code changes directly",
    loop: "🔁 Auto-Dev: Full autonomous loop"
  };
  showToast(map[mode] || mode, "info", 1800);
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
        <div class="msg-author">🤖 Direct Lead Advisor (Liquid LFM 2.5)</div>
        <span style="font-size:12px; color:var(--accent); font-weight:700;"><span class="spinner"></span> Thinking...</span>
      </div>
      <div class="status-timeline" id="status-${msgId}">
        <div class="step-active">➔ Decomposing intent & routing execution mode...</div>
      </div>
      <div class="markdown-body" id="body-${msgId}">
        <span style="color:var(--text-muted);">Generating response...</span>
      </div>
    </div>
  `;
  container.appendChild(assistRow);
  scrollChatToBottom(true);

  const btn = document.getElementById('sendBtn');
  btn.disabled = true;
  
  setPollingSpeed(true);

  try {
    let url = '/api/chat';
    let payloadMode = currentChatMode;
    
    if (currentChatMode === 'apply') {
      url = '/api/chat/apply';
    } else if (currentChatMode === 'chat') {
      payloadMode = 'auto';
    }

    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: prompt, repo_path: currentRepoPath, session_id: activeSessionId, mode: payloadMode })
    });
    const data = await res.json();

    if (data.type === 'loop_started') {
      const loopId = data.loop_id || `loop_${Date.now()}`;
      activeLoopSessionId = loopId;
      const card = document.getElementById(msgId);
      if (card) {
        card.id = `loop-card-${loopId}`;
        card.innerHTML = `
          <div class="msg-header">
            <div class="msg-author">🌌 Swarm Autonomous Agent · Active Execution</div>
            <span class="status-badge badge-running" id="loop-card-badge-${loopId}"><span class="loop-spinner"></span> Running...</span>
          </div>
          <div class="status-timeline" id="loop-timeline-${loopId}">
            ${(data.status_steps || []).map(s => `<div class="step-active">${escapeHtml(s)}</div>`).join('')}
          </div>
          <div id="loop-tasks-${loopId}" style="display:flex; flex-direction:column; gap:6px; margin-bottom:10px;"></div>
          <div class="markdown-body" id="loop-body-${loopId}">
            <p>🚀 <b>Autonomous Loop Initiated</b> for: <i>${escapeHtml(prompt)}</i></p>
          </div>
          <div id="loop-escalation-${loopId}"></div>
        `;
      }
      showToast("🚀 Autonomous Swarm Loop started!", "success", 2000);
      updateTelemetryAndTopology();
    } else {
      const statusEl = document.getElementById(`status-${msgId}`);
      if (statusEl) {
        const stepsHtml = (data.status_steps || []).map(s => `<div>${escapeHtml(s)}</div>`).join('');
        const planHtml = data.plan ? renderCboPlanHtml(data.plan, msgId) : '';
        const thoughtLabel = data.thought_summary || (data.tier === 'direct' ? `Direct Answer · ${data.duration || 0.2}s` : (data.tier === 'web_scout' ? `Web & Context7 Grounded · ${data.duration || 1.1}s` : `Swarm Cross-Checked · ${data.duration || 1.8}s`));
        
        statusEl.className = 'qwen-thought-details-wrapper';
        statusEl.innerHTML = `
          <details class="qwen-thought-details">
            <summary class="qwen-thought-summary">
              <span class="qwen-thought-icon">⚡</span>
              <span class="qwen-thought-title">${escapeHtml(thoughtLabel)}</span>
              <span class="qwen-thought-chevron">▾</span>
            </summary>
            <div class="qwen-thought-body">
              <div class="status-timeline">${stepsHtml}</div>
              ${planHtml}
            </div>
          </details>
        `;
      }

      const bodyEl = document.getElementById(`body-${msgId}`);
      if (bodyEl) {
        bodyEl.innerHTML = parseMarkdown(data.answer || "No response received.");
      }

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
        const cardEl = document.getElementById(msgId);
        if (cardEl) cardEl.appendChild(artDiv);
      }

      const headSpan = document.querySelector(`#${msgId} .msg-header span`);
      if (headSpan) {
        headSpan.innerText = `✓ ${data.duration || 1.2}s (Liquid LFM 2.5 VL)`;
        headSpan.style.color = 'var(--green)';
      }
    }

    await loadSessionsList();

  } catch (err) {
    const bodyEl = document.getElementById(`body-${msgId}`);
    if (bodyEl) {
      bodyEl.innerHTML = `<span style="color:var(--rose); font-weight:700;">Error: ${escapeHtml(err.message || err)}</span>`;
    }
  } finally {
    btn.disabled = false;
    setPollingSpeed(false);
    updateTelemetryAndTopology();
    scrollChatToBottom(false);
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
          <span style="font-weight:700; color:var(--text-bright);">${escapeHtml(n.name)}</span>
          <span style="color:var(--text-muted); font-size:11px;">(${escapeHtml(n.assigned_agent)})</span>
        </div>
        <div style="display:flex; align-items:center; gap:10px;">
          <span style="color:var(--text-muted); font-size:11px;">${escapeHtml(n.slot)}</span>
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
        <div style="font-size:12px; color:var(--text); font-style:italic;">
          Rationale: ${escapeHtml(plan.strategy_rationale || '')}
        </div>
        <div class="cbo-dag-list">
          <div style="font-weight:700; color:var(--accent); font-size:11px; margin-bottom:2px;">OPTIMIZED EXECUTION DAG:</div>
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

// ─────────────────────────────────────────────────────────────
// CLEAN ARCHITECTURE RULES MANAGER
// ─────────────────────────────────────────────────────────────
async function openRulesModal() {
  const modal = document.getElementById('rulesModal');
  if (modal) modal.className = 'modal-overlay active';
  await loadRulesData();
}

function closeRulesModal() {
  const modal = document.getElementById('rulesModal');
  if (modal) modal.className = 'modal-overlay';
}

function switchRulesTab(tab) {
  const globalBtn = document.getElementById('rulesTabGlobalBtn');
  const projectBtn = document.getElementById('rulesTabProjectBtn');
  const globalPane = document.getElementById('rulesGlobalPane');
  const projectPane = document.getElementById('rulesProjectPane');

  if (tab === 'global') {
    globalBtn.className = 'action-btn active';
    projectBtn.className = 'action-btn';
    globalPane.style.display = 'flex';
    projectPane.style.display = 'none';
  } else {
    globalBtn.className = 'action-btn';
    projectBtn.className = 'action-btn active';
    globalPane.style.display = 'none';
    projectPane.style.display = 'flex';
  }
}

async function loadRulesData() {
  try {
    const res = await fetch(`/api/rules?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const data = await res.json();
    
    const editor = document.getElementById('globalRulesEditor');
    if (editor) editor.value = data.global_rules || '';

    const repoNameSpan = document.getElementById('rulesProjectRepoName');
    const repoTitle = currentRepoPath ? currentRepoPath.split('/').pop() : 'Project';
    if (repoNameSpan) repoNameSpan.innerText = repoTitle;

    const projContainer = document.getElementById('projectRulesContent');
    if (projContainer) {
      if (data.project_rules && data.project_rules.has_rules) {
        projContainer.innerHTML = `
          <div style="font-weight:700; color:var(--accent); margin-bottom:8px;">
            ✓ Active Rules File: <code>${escapeHtml(data.project_rules.source)}</code>
          </div>
          ${parseMarkdown(data.project_rules.content)}
        `;
      } else {
        projContainer.innerHTML = `
          <div style="color:var(--text-muted); padding:16px; text-align:center;">
            No project-specific rule file (<code>RULE.md</code>, <code>GEMINI.md</code>, <code>CLAUDE.md</code>, or <code>.cursorrules</code>) detected in <b>${escapeHtml(repoTitle)}</b>.
            <br><span style="font-size:11.5px;">Global Clean Architecture rules are actively enforced.</span>
          </div>
        `;
      }
    }
  } catch(e) {
    showToast("Error loading rules: " + e.message, "error");
  }
}

async function saveGlobalRulesAction() {
  const editor = document.getElementById('globalRulesEditor');
  if (!editor) return;
  const content = editor.value.trim();
  if (!content) {
    showToast("Global rules content cannot be empty", "warn");
    return;
  }

  try {
    const res = await fetch('/api/rules/global', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content })
    });
    const data = await res.json();
    if (data.success) {
      showToast("✓ Global Clean Architecture rules saved!", "success");
    } else {
      showToast("Error saving rules: " + (data.error || "Failed"), "error");
    }
  } catch(e) {
    showToast("Error saving rules: " + e.message, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// SUPER-ORCHESTRATOR MULTI-ENGINE EXECUTION MATRIX
// ─────────────────────────────────────────────────────────────
async function loadBackendsStatus() {
  try {
    const res = await fetch('/api/backends/status', { cache: 'no-store' });
    const data = await res.json();
    const container = document.getElementById('superOrchestratorEnginesGrid');
    if (!container) return;
    container.innerHTML = '';

    const backends = data.backends || {};
    Object.values(backends).forEach(b => {
      const card = document.createElement('div');
      const isOnline = (b.status === 'ready' || b.status === 'online');
      card.style.cssText = `background:var(--ink-800); border:1.5px solid ${isOnline ? 'var(--green-strong)' : 'var(--line-strong)'}; border-radius:10px; padding:10px 12px; display:flex; flex-direction:column; gap:4px;`;
      
      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <span style="font-weight:700; color:var(--text-bright); font-size:12.5px;">${escapeHtml(b.name)}</span>
          <span class="status-badge ${isOnline ? 'badge-online' : 'badge-idle'}" id="status-badge-${b.id}" style="font-size:9.5px; padding:2px 6px;">${escapeHtml(b.status.toUpperCase())}</span>
        </div>
        <div style="font-size:10.5px; color:var(--text-muted); font-weight:700;">${escapeHtml(b.role)}</div>
        <div style="font-family:var(--font-mono); font-size:11px; color:var(--accent); background:var(--ink-900); padding:3px 6px; border-radius:4px; border:1px solid var(--ink-500); overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
          🏷️ ${escapeHtml(b.version)}
        </div>
        <div style="display:flex; justify-content:flex-end; margin-top:4px;">
          <button class="action-btn action-btn--sm" onclick="testSingleBackend('${escapeJs(b.id)}')">
            ⚡ Test Ping
          </button>
        </div>
      `;
      container.appendChild(card);
    });
  } catch(e) {}
}

async function testSingleBackend(backendId) {
  showToast(`Pinging ${backendId}...`, "info", 1500);
  try {
    const res = await fetch('/api/backends/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ backend_id: backendId })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ ${backendId} responded in ${data.duration_s}s!`, "success", 3000);
    } else {
      showToast(`⚠️ ${backendId} ping failed: ${data.error || 'No output'}`, "warn", 3500);
    }
  } catch(e) {
    showToast(`Error pinging ${backendId}: ${e.message}`, "error");
  }
}

async function testAllEnginesDiagnostic() {
  showToast("Running diagnostic on all 5 Super-Orchestrator engines...", "info", 2500);
  const ids = ["claude_code", "agy_gemini", "context7_mcp", "liquid_lfm", "qwen_oracle"];
  for (const id of ids) {
    await testSingleBackend(id);
  }
}

// ─────────────────────────────────────────────────────────────
// UNIVERSAL CONTRACTS & DOCUSAURUS ENGINE CONTROLLER
// ─────────────────────────────────────────────────────────────

let activeContractsCatalog = null;
let currentContractsCategory = 'all';

async function loadContractsCatalog() {
  const container = document.getElementById('contractsCatalogContainer');
  if (!container) return;

  container.innerHTML = `
    <div style="text-align:center; padding:30px; color:var(--text-muted);">
      <div style="font-size:24px; margin-bottom:8px;">🔍</div>
      <div>Scanning repository for OpenAPI, FlatBuffers, SCXML statecharts, and CEL invariants...</div>
    </div>
  `;

  try {
    const res = await fetch(`/api/contracts/catalog?repo_path=${encodeURIComponent(currentRepoPath)}`, { cache: 'no-store' });
    const catalog = await res.json();
    activeContractsCatalog = catalog;

    const summary = catalog.summary || {};
    const openapiCount = catalog.openapi ? catalog.openapi.reduce((acc, s) => acc + (s.endpoint_count || s.endpoints?.length || 0), 0) : 0;
    const asyncapiCount = catalog.asyncapi ? catalog.asyncapi.reduce((acc, s) => acc + (s.channel_count || s.channels?.length || 0), 0) : 0;
    const fbCount = catalog.flatbuffers ? catalog.flatbuffers.reduce((acc, s) => acc + (s.tables?.length || 0), 0) : 0;
    const protoCount = catalog.protobuf ? catalog.protobuf.reduce((acc, s) => acc + (s.messages?.length || 0), 0) : 0;
    const scxmlCount = summary.statecharts_count || (catalog.statecharts?.length || 0);
    const celCount = summary.cel_invariants_count || (catalog.cel_invariants?.length || 0);

    const elO = document.getElementById('metricOpenApiCount');
    if (elO) elO.innerText = openapiCount;
    const elA = document.getElementById('metricAsyncApiCount');
    if (elA) elA.innerText = asyncapiCount;
    const elF = document.getElementById('metricFlatBuffersCount');
    if (elF) elF.innerText = fbCount;
    const elP = document.getElementById('metricProtobufCount');
    if (elP) elP.innerText = protoCount;
    const elS = document.getElementById('metricStatechartsCount');
    if (elS) elS.innerText = scxmlCount;
    const elC = document.getElementById('metricCelCount');
    if (elC) elC.innerText = celCount;

    renderContractsCatalog(catalog);
  } catch (e) {
    container.innerHTML = `
      <div style="background:var(--ink-600); border:1.5px solid var(--rose-strong); border-radius:8px; padding:20px; color:var(--rose);">
        <div style="font-weight:700; font-size:14px; margin-bottom:6px;">⚠️ Error loading contracts catalog</div>
        <div style="font-size:12.5px;">${escapeHtml(e.message)}</div>
      </div>
    `;
  }
}

function renderContractsCatalog(catalog) {
  const container = document.getElementById('contractsCatalogContainer');
  if (!container) return;
  container.innerHTML = '';

  const total = catalog.total_contracts || 0;
  const celInvariants = catalog.cel_invariants || [];
  
  if (total === 0 && celInvariants.length === 0) {
    container.innerHTML = `
      <div style="text-align:center; padding:40px 20px; background:var(--ink-800); border:1px solid var(--ink-500); border-radius:10px;">
        <div style="font-size:28px; margin-bottom:8px;">📜</div>
        <div style="font-size:15px; font-weight:700; color:var(--text-bright); margin-bottom:6px;">No Contract Specifications Detected in Repository</div>
        <div style="font-size:12.5px; color:var(--text-muted); max-width:600px; margin:0 auto 16px auto;">
          Add OpenAPI (<code>openapi.yaml</code> / <code>*.openapi.json</code>), FlatBuffers (<code>*.fbs</code>), Protobuf (<code>*.proto</code>), SCXML state machines (<code>*.scxml</code>), or CEL invariants (<code>invariants.yaml</code>) to your project.
        </div>
        <button class="action-btn action-btn--primary" onclick="exportContractsToDocusaurusAction()">
          📚 Initialize Docusaurus Docs Structure
        </button>
      </div>
    `;
    return;
  }

  // 1. OpenAPI Specs
  if (catalog.openapi && catalog.openapi.length > 0) {
    catalog.openapi.forEach((spec) => {
      const card = document.createElement('div');
      card.className = 'contract-spec-card';
      card.dataset.category = 'openapi';
      card.style.background = 'var(--ink-800)';
      card.style.border = '1.5px solid var(--ink-500)';
      card.style.borderRadius = '10px';
      card.style.padding = '16px';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '12px';

      let endpointsHtml = '';
      (spec.endpoints || []).forEach(ep => {
        const methodColors = {
          GET: 'var(--accent)',
          POST: 'var(--green)',
          PUT: 'var(--amber)',
          DELETE: 'var(--rose)',
          PATCH: 'var(--purple)'
        };
        const color = methodColors[ep.method] || 'var(--text-muted)';
        endpointsHtml += `
          <div style="display:flex; justify-content:space-between; align-items:center; background:var(--ink-900); border:1px solid var(--line); border-radius:6px; padding:6px 12px; font-size:12px;">
            <div style="display:flex; align-items:center; gap:10px;">
              <span style="font-family:var(--font-mono); font-weight:700; color:${color}; font-size:11px; background:rgba(255,255,255,0.06); padding:2px 6px; border-radius:4px;">${escapeHtml(ep.method)}</span>
              <span style="font-family:var(--font-mono); font-weight:700; color:var(--text-bright);">${escapeHtml(ep.path)}</span>
            </div>
            <span style="color:var(--text-muted); font-size:11.5px;">${escapeHtml(ep.summary || ep.operation_id || '')}</span>
          </div>
        `;
      });

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">📜</span>
            <span style="font-weight:700; color:var(--text-bright); font-size:14px;">${escapeHtml(spec.title || 'OpenAPI Specification')}</span>
            <span class="file-status-badge status-a">OpenAPI v${escapeHtml(spec.spec_version || '3.0')}</span>
          </div>
          <span style="font-size:11.5px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(spec.filepath || '')}</span>
        </div>
        <div style="font-size:12px; color:var(--text);">${escapeHtml(spec.description || 'RESTful API contract endpoints & schemas.')}</div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${endpointsHtml}
        </div>
      `;
      container.appendChild(card);
    });
  }

  // 2. AsyncAPI Specs
  if (catalog.asyncapi && catalog.asyncapi.length > 0) {
    catalog.asyncapi.forEach((spec) => {
      const card = document.createElement('div');
      card.className = 'contract-spec-card';
      card.dataset.category = 'asyncapi';
      card.style.background = 'var(--ink-800)';
      card.style.border = '1.5px solid var(--ink-500)';
      card.style.borderRadius = '10px';
      card.style.padding = '16px';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '12px';

      let channelsHtml = '';
      (spec.channels || []).forEach(ch => {
        channelsHtml += `
          <div style="display:flex; justify-content:space-between; align-items:center; background:var(--ink-900); border:1px solid var(--line); border-radius:6px; padding:6px 12px; font-size:12px;">
            <div style="display:flex; align-items:center; gap:8px;">
              <span style="font-family:var(--font-mono); font-weight:700; color:var(--accent); font-size:11px;">CHANNEL</span>
              <span style="font-family:var(--font-mono); font-weight:700; color:var(--text-bright);">${escapeHtml(ch.name)}</span>
              <span style="color:var(--text-muted); font-size:11px;">(${escapeHtml(ch.address || '')})</span>
            </div>
            <span style="color:var(--purple); font-size:11.5px; font-weight:700;">${(ch.messages || []).length} Message(s)</span>
          </div>
        `;
      });

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">📡</span>
            <span style="font-weight:700; color:var(--text-bright); font-size:14px;">${escapeHtml(spec.title || 'AsyncAPI Specification')}</span>
            <span class="file-status-badge status-m">AsyncAPI v${escapeHtml(spec.spec_version || '3.0')}</span>
          </div>
          <span style="font-size:11.5px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(spec.filepath || '')}</span>
        </div>
        <div style="font-size:12px; color:var(--text);">${escapeHtml(spec.description || 'Event-driven message channels and payload contracts.')}</div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${channelsHtml}
        </div>
      `;
      container.appendChild(card);
    });
  }

  // 3. FlatBuffers Schemas
  if (catalog.flatbuffers && catalog.flatbuffers.length > 0) {
    catalog.flatbuffers.forEach((spec) => {
      const card = document.createElement('div');
      card.className = 'contract-spec-card';
      card.dataset.category = 'flatbuffers';
      card.style.background = 'var(--ink-800)';
      card.style.border = '1.5px solid var(--ink-500)';
      card.style.borderRadius = '10px';
      card.style.padding = '16px';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '12px';

      let tablesHtml = '';
      (spec.tables || []).forEach(tbl => {
        const fieldsList = (tbl.fields || []).map(f => `${f.name}:${f.type}${f.required ? '!' : ''}`).join(', ');
        tablesHtml += `
          <div style="background:var(--ink-900); border:1px solid var(--line); border-radius:6px; padding:8px 12px; font-size:12px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <span style="font-weight:700; color:var(--amber); font-family:var(--font-mono);">table ${escapeHtml(tbl.name)} ${tbl.is_root ? '<span class="file-status-badge status-a">ROOT</span>' : ''}</span>
              <span style="color:var(--text-muted); font-size:11px;">${(tbl.fields || []).length} fields</span>
            </div>
            <div style="font-family:var(--font-mono); font-size:11.5px; color:var(--text);">${escapeHtml(fieldsList)}</div>
          </div>
        `;
      });

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">⚡</span>
            <span style="font-weight:700; color:var(--text-bright); font-size:14px;">${escapeHtml(spec.title || 'FlatBuffers Schema')}</span>
            <span class="file-status-badge status-u">FlatBuffers (.fbs)</span>
          </div>
          <span style="font-size:11.5px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(spec.filepath || '')}</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${tablesHtml}
        </div>
      `;
      container.appendChild(card);
    });
  }

  // 4. Protobuf Schemas
  if (catalog.protobuf && catalog.protobuf.length > 0) {
    catalog.protobuf.forEach((spec) => {
      const card = document.createElement('div');
      card.className = 'contract-spec-card';
      card.dataset.category = 'protobuf';
      card.style.background = 'var(--ink-800)';
      card.style.border = '1.5px solid var(--ink-500)';
      card.style.borderRadius = '10px';
      card.style.padding = '16px';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '12px';

      let msgHtml = '';
      (spec.messages || []).forEach(m => {
        msgHtml += `
          <div style="display:flex; justify-content:space-between; align-items:center; background:var(--ink-900); border:1px solid var(--line); border-radius:6px; padding:6px 12px; font-size:12px;">
            <span style="font-family:var(--font-mono); font-weight:700; color:var(--purple);">message ${escapeHtml(m.name)}</span>
            <span style="color:var(--text-muted); font-size:11.5px;">${(m.fields || []).length} field(s)</span>
          </div>
        `;
      });

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">📦</span>
            <span style="font-weight:700; color:var(--text-bright); font-size:14px;">${escapeHtml(spec.title || 'Protobuf Schema')}</span>
            <span class="file-status-badge status-m">${escapeHtml(spec.syntax || 'proto3')}</span>
          </div>
          <span style="font-size:11.5px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(spec.filepath || '')}</span>
        </div>
        <div style="display:flex; flex-direction:column; gap:6px;">
          ${msgHtml}
        </div>
      `;
      container.appendChild(card);
    });
  }

  // 5. SCXML Statecharts with Mermaid Diagrams
  if (catalog.statecharts && catalog.statecharts.length > 0) {
    catalog.statecharts.forEach((sc) => {
      const card = document.createElement('div');
      card.className = 'contract-spec-card';
      card.dataset.category = 'statecharts';
      card.style.background = 'var(--ink-800)';
      card.style.border = '1.5px solid var(--ink-500)';
      card.style.borderRadius = '10px';
      card.style.padding = '16px';
      card.style.display = 'flex';
      card.style.flexDirection = 'column';
      card.style.gap = '12px';

      let transRows = '';
      (sc.transitions || []).forEach(tr => {
        transRows += `
          <tr style="border-bottom:1px solid var(--line);">
            <td style="padding:6px 12px; font-family:var(--font-mono); color:var(--accent); font-weight:700;">${escapeHtml(tr.source)}</td>
            <td style="padding:6px 12px; font-family:var(--font-mono); color:var(--green); font-weight:700;">${escapeHtml(tr.target)}</td>
            <td style="padding:6px 12px; font-family:var(--font-mono); color:var(--amber);">${escapeHtml(tr.event || '*')}</td>
            <td style="padding:6px 12px; font-family:var(--font-mono); color:var(--text);">${escapeHtml(tr.condition || '—')}</td>
          </tr>
        `;
      });

      card.innerHTML = `
        <div style="display:flex; justify-content:space-between; align-items:center;">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-size:16px;">🔄</span>
            <span style="font-weight:700; color:var(--text-bright); font-size:14px;">${escapeHtml(sc.name || 'State Machine')}</span>
            <span class="file-status-badge status-a">Initial: ${escapeHtml(sc.initial_state || 'None')}</span>
          </div>
          <span style="font-size:11.5px; color:var(--text-muted); font-family:var(--font-mono);">${escapeHtml(sc.filepath || '')}</span>
        </div>

        <div>
          <div style="font-size:11.5px; color:var(--text-muted); font-weight:700; margin-bottom:6px;">📊 Docusaurus-Compatible Mermaid State Diagram:</div>
          <pre style="background:var(--ink-900); border:1px solid var(--line); border-radius:8px; padding:12px; color:var(--accent); font-family:var(--font-mono); font-size:12px; overflow-x:auto; line-height:1.4;"><code>${escapeHtml(sc.mermaid || '')}</code></pre>
        </div>

        <div>
          <div style="font-size:11.5px; color:var(--text-muted); font-weight:700; margin-bottom:6px;">🔄 State Transition Invariants:</div>
          <table style="width:100%; border-collapse:collapse; background:var(--ink-900); border:1px solid var(--line); border-radius:8px; font-size:11.5px;">
            <thead>
              <tr style="background:var(--ink-900); border-bottom:1px solid var(--line); color:var(--text-muted); text-align:left;">
                <th style="padding:6px 12px;">Source</th>
                <th style="padding:6px 12px;">Target</th>
                <th style="padding:6px 12px;">Event</th>
                <th style="padding:6px 12px;">Guard Condition</th>
              </tr>
            </thead>
            <tbody>
              ${transRows}
            </tbody>
          </table>
        </div>
      `;
      container.appendChild(card);
    });
  }

  // 6. CEL Invariant Rules
  if (catalog.cel_invariants && catalog.cel_invariants.length > 0) {
    const card = document.createElement('div');
    card.className = 'contract-spec-card';
    card.dataset.category = 'cel';
    card.style.background = 'var(--ink-800)';
    card.style.border = '1.5px solid var(--ink-500)';
    card.style.borderRadius = '10px';
    card.style.padding = '16px';
    card.style.display = 'flex';
    card.style.flexDirection = 'column';
    card.style.gap = '12px';

    let rulesRows = '';
    catalog.cel_invariants.forEach(inv => {
      const sevColors = {
        CRITICAL: 'var(--rose)',
        ERROR: 'var(--rose)',
        WARN: 'var(--amber)',
        INFO: 'var(--accent)'
      };
      const sevColor = sevColors[inv.severity] || 'var(--rose)';
      rulesRows += `
        <tr style="border-bottom:1px solid var(--line);">
          <td style="padding:8px 12px;"><span style="font-family:var(--font-mono); font-weight:700; font-size:10.5px; color:${sevColor}; background:rgba(255,255,255,0.06); padding:2px 6px; border-radius:4px;">${escapeHtml(inv.severity || 'ERROR')}</span></td>
          <td style="padding:8px 12px; font-weight:700; color:var(--text-bright);">${escapeHtml(inv.name)}</td>
          <td style="padding:8px 12px; font-family:var(--font-mono); color:var(--accent);">${escapeHtml(inv.target || 'global')}</td>
          <td style="padding:8px 12px; font-family:var(--font-mono); color:var(--green);"><code>${escapeHtml(inv.rule)}</code></td>
          <td style="padding:8px 12px; color:var(--text);">${escapeHtml(inv.description || '')}</td>
        </tr>
      `;
    });

    card.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:center;">
        <div style="display:flex; align-items:center; gap:8px;">
          <span style="font-size:16px;">🛡️</span>
          <span style="font-weight:700; color:var(--text-bright); font-size:14px;">CEL (Common Expression Language) Invariants</span>
          <span class="file-status-badge status-a">${catalog.cel_invariants.length} Rule(s)</span>
        </div>
      </div>

      <table style="width:100%; border-collapse:collapse; background:var(--ink-900); border:1px solid var(--line); border-radius:8px; font-size:12px;">
        <thead>
          <tr style="background:var(--ink-900); border-bottom:1px solid var(--line); color:var(--text-muted); text-align:left;">
            <th style="padding:8px 12px;">Severity</th>
            <th style="padding:8px 12px;">Rule Name</th>
            <th style="padding:8px 12px;">Target Scope</th>
            <th style="padding:8px 12px;">CEL Expression</th>
            <th style="padding:8px 12px;">Description</th>
          </tr>
        </thead>
        <tbody>
          ${rulesRows}
        </tbody>
      </table>
    `;
    container.appendChild(card);
  }

  filterContractsCategory(currentContractsCategory);
}

function filterContractsCategory(cat) {
  currentContractsCategory = cat;
  const pills = document.querySelectorAll('#contractsCategoryPills .action-btn');
  pills.forEach(p => {
    p.className = (p.dataset.cat === cat) ? 'action-btn active' : 'action-btn';
  });

  const cards = document.querySelectorAll('.contract-spec-card');
  cards.forEach(card => {
    if (cat === 'all' || card.dataset.category === cat) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

function searchContracts(query) {
  const q = (query || '').toLowerCase().trim();
  const cards = document.querySelectorAll('.contract-spec-card');
  cards.forEach(card => {
    const text = card.innerText.toLowerCase();
    const matchesCat = (currentContractsCategory === 'all' || card.dataset.category === currentContractsCategory);
    if (matchesCat && (!q || text.includes(q))) {
      card.style.display = 'flex';
    } else {
      card.style.display = 'none';
    }
  });
}

async function exportContractsToDocusaurusAction() {
  showToast("Compiling contracts to Docusaurus markdown hierarchy...", "info", 2000);
  try {
    const res = await fetch('/api/contracts/export_docusaurus', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ repo_path: currentRepoPath })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`✓ Exported ${data.exported_files_count} Docusaurus docs to ${data.contracts_dir}!`, "success", 4000);
    } else {
      showToast(`⚠️ Docusaurus export error: ${data.error || 'Failed'}`, "warn", 3500);
    }
  } catch (e) {
    showToast(`Export error: ${e.message}`, "error");
  }
}

async function executeCelLiveTest() {
  const expr = document.getElementById('celTestExprInput')?.value.trim();
  const rawContext = document.getElementById('celTestContextInput')?.value.trim();
  const badge = document.getElementById('celLiveVerdictBadge');

  if (!expr) {
    showToast("Please enter a CEL expression to test", "warn");
    return;
  }

  let context = {};
  try {
    context = JSON.parse(rawContext || "{}");
  } catch (e) {
    showToast(`Invalid JSON Context: ${e.message}`, "error");
    return;
  }

  try {
    const res = await fetch('/api/contracts/validate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        invariants: [{ name: "interactive_test_rule", rule: expr }],
        context: context
      })
    });
    const data = await res.json();
    if (data.valid) {
      if (badge) {
        badge.className = 'file-status-badge status-a';
        badge.innerText = 'PASSED (TRUE)';
      }
      showToast("✓ CEL Expression Evaluated to TRUE (Valid)", "success", 2500);
    } else {
      if (badge) {
        badge.className = 'file-status-badge status-d';
        badge.innerText = 'FAILED (FALSE)';
      }
      const failInfo = data.results && data.results[0] ? data.results[0].error : "Rule evaluated to false";
      showToast(`⚠️ CEL Rule Failed: ${failInfo}`, "warn", 3500);
    }
  } catch (e) {
    showToast(`CEL Validation error: ${e.message}`, "error");
  }
}



