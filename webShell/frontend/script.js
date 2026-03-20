// ==================== DOM References ====================
const loginOverlay = document.getElementById('login-overlay');
const connectBtn = document.getElementById('connect-btn');
const cancelLoginBtn = document.getElementById('cancel-login-btn');
const sftpToggle = document.getElementById('sftp-toggle');
const sftpPanel = document.getElementById('sftp-side-panel');
const sftpList = document.getElementById('sftp-list');
const remotePathLabel = document.getElementById('remote-path');
const statusText = document.getElementById('status-text');
const dashboard = document.getElementById('dashboard');
const terminalWrapper = document.getElementById('terminal-wrapper');
const termContainer = document.getElementById('terminal-container');
const dashboardTab = document.getElementById('dashboard-tab');
const tabBar = document.getElementById('tab-bar');
const ctxConnect = document.getElementById('ctx-connect');

// ==================== State ====================
let activeSessions = {}; // sid -> { term, fitAddon, socket, tab, div, host, user, port, path }
let currentSid = null;
let loginDialogMode = 'connect';

// ==================== URL Detection ====================
const loc = window.location;
const API_BASE = (loc.protocol === 'file:')
    ? 'http://127.0.0.1:8100'
    : `${loc.protocol}//${loc.host}`;
const WS_BASE = (loc.protocol === 'file:')
    ? 'ws://127.0.0.1:8100'
    : `${loc.protocol === 'https:' ? 'wss' : 'ws'}://${loc.host}`;

// ==================== Session Management (Backend based) ====================
let sessions = [];

let sessionsTree = null;
let expandedFolders = new Set(["."]); // Default root folder expanded

async function loadSessions() {
    try {
        const resp = await fetch(`${API_BASE}/sessions`);
        if (resp.ok) {
            sessionsTree = await resp.json();
            renderSidebar();
            renderDashboardGrid();
        }
    } catch (e) {
        console.error('Failed to load sessions:', e);
    }
}

async function saveSessionToBackend(data) {
    // Add current folder context if creating new
    if (data.folder === undefined) {
        if (lastRightClickedNode && lastRightClickedNode.type === 'file') {
            const parts = lastRightClickedPath.split('/');
            parts.pop();
            data.folder = parts.join('/');
            if (data.folder === ".") data.folder = "";
        } else {
            data.folder = lastRightClickedPath === "." ? "" : lastRightClickedPath;
        }
    }
    
    // Pass original session info if editing, so backend can rename/update correctly
    if (loginDialogMode === 'edit' && lastRightClickedNode && lastRightClickedNode.type === 'file') {
        data.originalName = lastRightClickedNode.name;
        data.originalPath = lastRightClickedNode.path;
    }

    try {
        const resp = await fetch(`${API_BASE}/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (resp.ok) {
            await loadSessions();
        }
    } catch (e) {
        console.error('Failed to save session:', e);
    }
}

function renderSidebar() {
    const sidebarList = document.getElementById('session-list');
    const sidebar = document.getElementById('sidebar');
    if (!sidebarList) return;
    sidebarList.innerHTML = '';

    if (sessionsTree) {
        const rootLi = createTreeNode(sessionsTree);
        sidebarList.appendChild(rootLi);
    }

    sidebar.addEventListener('contextmenu', (e) => {
        // Only trigger sidebar-wide menu if clicking on the background
        if (e.target === sidebar || e.target === sidebarList || e.target.classList.contains('panel-header')) {
            e.preventDefault();
            showContextMenu(e.clientX, e.clientY, null, ".");
        }
    });
}

function createTreeNode(node) {
    const li = document.createElement('li');
    const isFolder = node.type === 'folder';
    const isExpanded = expandedFolders.has(node.path);

    li.className = isFolder ? 'folder-node' : 'file-node';
    li.dataset.path = node.path;

    const content = document.createElement('div');
    content.className = 'tree-content';

    const iconClass = isFolder
        ? (isExpanded ? 'fa-folder-open' : 'fa-folder')
        : 'fa-terminal';
    const iconColor = isFolder ? '#e6a817' : '#c0392b';

    content.innerHTML = `
        <span class="toggle-icon">${isFolder ? (isExpanded ? '▾' : '▸') : ''}</span>
        <i class="fas ${iconClass}" style="color:${iconColor}"></i>
        <span class="node-name">${node.name}</span>
    `;

    li.appendChild(content);

    if (isFolder) {
        const ul = document.createElement('ul');
        ul.className = 'tree-children' + (isExpanded ? '' : ' hidden');
        if (node.children) {
            node.children.forEach(child => {
                ul.appendChild(createTreeNode(child));
            });
        }
        li.appendChild(ul);

        content.addEventListener('click', (e) => {
            e.stopPropagation();
            if (expandedFolders.has(node.path)) expandedFolders.delete(node.path);
            else expandedFolders.add(node.path);
            renderSidebar();
        });
    } else {
        content.addEventListener('click', (e) => {
            e.stopPropagation();
            showPropertiesFromNode(node);
        });

        content.addEventListener('dblclick', (e) => {
            e.stopPropagation();
            showPropertiesFromNode(node);
            loginDialogMode = 'connect';
            connectBtn.click();
        });
    }

    content.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        e.stopPropagation();
        showContextMenu(e.clientX, e.clientY, isFolder ? null : node, node.path);
    });

    return li;
}

function renderDashboardGrid() {
    const grid = document.getElementById('qs-grid');
    if (!grid) return;
    grid.innerHTML = '';

    function findFiles(node, list) {
        if (node.type === 'file') list.push(node);
        if (node.children) node.children.forEach(c => findFiles(c, list));
    }

    const allFiles = [];
    if (sessionsTree) findFiles(sessionsTree, allFiles);

    allFiles.forEach((s) => {
        const div = document.createElement('div');
        div.className = 'qs-item';
        const letter = (s.name || s.host || '?')[0].toUpperCase();
        div.innerHTML = `
            <div class="qs-icon">${letter}</div>
            <div class="qs-label">${s.name}</div>
        `;
        div.addEventListener('click', () => {
            showPropertiesFromNode(s);
            loginDialogMode = 'connect';
            document.getElementById('connect-btn').innerText = '连接';
            loginOverlay.classList.remove('hidden');
        });
        grid.appendChild(div);
    });
}

function showPropertiesFromNode(node) {
    document.getElementById('session-name-input').value = node.name || '';
    document.getElementById('host').value = node.host || '';
    document.getElementById('port').value = node.port || 22;
    document.getElementById('username').value = node.user || '';
    document.getElementById('password').value = node.pass || '';

    document.getElementById('prop-name').innerText = node.name;
    document.getElementById('prop-host').innerText = node.host || '--';
    document.getElementById('prop-user').innerText = node.user || '--';
    document.getElementById('prop-port').innerText = node.port || 22;
    document.getElementById('prop-type').innerText = node.type === 'folder' ? '文件夹' : '会话';
}

let lastRightClickedNode = null;
let lastRightClickedPath = ".";

function showContextMenu(x, y, node, path) {
    const ctxMenu = document.getElementById('context-menu');
    if (!ctxMenu) return;
    lastRightClickedNode = node;
    lastRightClickedPath = path;

    ctxMenu.style.left = x + 'px';
    ctxMenu.style.top = y + 'px';
    ctxMenu.classList.remove('hidden');

    const editItem = document.getElementById('ctx-edit');
    const connectItem = document.getElementById('ctx-connect');

    if (node === null) {
        if (editItem) editItem.classList.add('hidden');
        if (connectItem) connectItem.classList.add('hidden');
    } else {
        if (editItem) editItem.classList.remove('hidden');
        if (connectItem) connectItem.classList.remove('hidden');
    }
}

window.addEventListener('click', () => {
    const ctxMenu = document.getElementById('context-menu');
    if (ctxMenu) ctxMenu.classList.add('hidden');
});

document.addEventListener('DOMContentLoaded', () => {
    loadSessions();
    loadKeys();
    loadActiveSessions();
    renderQuickCommands();

    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const btn = document.getElementById('connect-btn');
            if (btn) btn.click();
        });
    }

    // Platform-specific UI adjustments
    const isMac = navigator.platform.toUpperCase().indexOf('MAC') >= 0;
    if (isMac) {
        const openFolderItem = document.getElementById('ctx-open-folder');
        if (openFolderItem) {
            openFolderItem.innerHTML = `<i class="fas fa-external-link-alt" style="margin-right: 8px; width:14px"></i> 在访达中打开`;
        }
    }

    // Sidebar Context Menu Handlers
    document.getElementById('ctx-new').addEventListener('click', () => {
        document.getElementById('new-conn-btn').click();
    });

    document.getElementById('ctx-mkdir').addEventListener('click', async () => {
        const folderName = prompt("请输入文件夹名称:");
        if (!folderName) return;
        const newPath = lastRightClickedPath === "." ? folderName : `${lastRightClickedPath}/${folderName}`;
        try {
            const resp = await fetch(`${API_BASE}/sessions/mkdir`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: newPath })
            });
            if (resp.ok) loadSessions();
        } catch (e) { console.error("Mkdir failed", e); }
    });

    document.getElementById('ctx-open-folder').addEventListener('click', async () => {
        try {
            await fetch(`${API_BASE}/sessions/open-folder`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: lastRightClickedPath })
            });
        } catch (e) { console.error("Open folder failed", e); }
    });

    document.getElementById('ctx-expand-all').addEventListener('click', () => {
        function expand(node) {
            if (node.type === 'folder') {
                expandedFolders.add(node.path);
                if (node.children) node.children.forEach(expand);
            }
        }
        if (sessionsTree) expand(sessionsTree);
        renderSidebar();
    });

    document.getElementById('ctx-collapse-all').addEventListener('click', () => {
        expandedFolders.clear();
        expandedFolders.add(".");
        renderSidebar();
    });

    document.getElementById('ctx-toggle-props').addEventListener('click', () => {
        const panel = document.querySelector('.properties-panel');
        const isHidden = panel.classList.toggle('hidden');
        // Simple visual feedback: add a checkmark if visible
        const item = document.getElementById('ctx-toggle-props');
        item.innerHTML = `<i class="fas ${isHidden ? 'fa-info-circle' : 'fa-check-circle'}" style="margin-right: 8px; width:14px"></i> ${isHidden ? '显示' : '隐藏'}属性窗格`;
    });

    document.getElementById('ctx-edit').addEventListener('click', () => {
        if (lastRightClickedNode) {
            showPropertiesFromNode(lastRightClickedNode);
            loginDialogMode = 'edit';
            document.getElementById('connect-btn').innerText = '保存';
            loginOverlay.classList.remove('hidden');
        }
    });

    document.getElementById('ctx-delete').addEventListener('click', async () => {
        if (!lastRightClickedPath || lastRightClickedPath === ".") {
            alert("不能删除根目录");
            return;
        }

        const isFolder = !lastRightClickedNode || lastRightClickedNode.type === 'folder';
        const msg = isFolder
            ? `确定要删除文件夹 "${lastRightClickedPath}" 及其所有内容吗？`
            : `确定要删除会话 "${lastRightClickedNode.name}" 吗？`;

        if (!confirm(msg)) return;

        try {
            const resp = await fetch(`${API_BASE}/sessions?path=${encodeURIComponent(lastRightClickedPath)}`, {
                method: 'DELETE'
            });
            if (resp.ok) loadSessions();
            else {
                const err = await resp.json();
                alert("删除失败: " + err.message);
            }
        } catch (e) { console.error("Delete failed", e); }
    });

    document.getElementById('ctx-connect').addEventListener('click', () => {
        if (lastRightClickedNode && lastRightClickedNode.type === 'file') {
            showPropertiesFromNode(lastRightClickedNode);
            loginDialogMode = 'connect';
            connectBtn.click();
        }
    });

    if (sftpToggle) {
        sftpToggle.addEventListener('click', () => {
            sftpPanel.classList.toggle('hidden');
            if (!sftpPanel.classList.contains('hidden')) {
                if (currentSid && activeSessions[currentSid]) {
                    loadSFTP(activeSessions[currentSid].path || '.');
                }
                loadLocalFiles(localPath);
            }
        });
    }
});

async function loadKeys() {
    try {
        const resp = await fetch(`${API_BASE}/keys`);
        if (resp.ok) {
            const keys = await resp.json();
            const select = document.getElementById('key-select');
            if (keys.length > 0) {
                select.innerHTML = '<option value="">-- 请选择私钥 --</option>';
                keys.forEach(k => {
                    const opt = document.createElement('option');
                    opt.value = k;
                    opt.innerText = k;
                    select.appendChild(opt);
                });
            }
        }
    } catch (e) {
        console.error('Failed to load keys:', e);
    }
}

// ==================== UI Toggle ====================
function showDashboard() {
    dashboard.classList.remove('hidden');
    terminalWrapper.classList.add('hidden');
    Object.values(activeSessions).forEach(s => s.div.classList.add('hidden'));
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    dashboardTab.classList.add('active');
    currentSid = null;
    statusText.innerText = '就绪';
    document.getElementById('connection-info').innerText = '';
}

function showTerminal(sid) {
    if (!sid || !activeSessions[sid]) return;
    currentSid = sid;
    const s = activeSessions[sid];

    dashboard.classList.add('hidden');
    terminalWrapper.classList.remove('hidden');

    Object.keys(activeSessions).forEach(id => {
        const item = activeSessions[id];
        if (id === sid) {
            item.div.classList.remove('hidden');
            item.tab.classList.add('active');
            document.getElementById('connection-info').innerText = `${item.user}@${item.host}:${item.port}`;
            statusText.innerText = item.socket && item.socket.readyState === WebSocket.OPEN ? '已连接' : '已断开';
            setTimeout(() => {
                if (item.fitAddon) { try { item.fitAddon.fit(); } catch (e) { } }
                item.term.focus();
                // Send explicit resize after fit so backend knows
                sendResize(sid);
            }, 100);

            if (!sftpPanel.classList.contains('hidden')) {
                loadSFTP(item.path || '.');
            }
        } else {
            item.div.classList.add('hidden');
            item.tab.classList.remove('active');
        }
    });
    dashboardTab.classList.remove('active');
}

function closeSession(sid) {
    const s = activeSessions[sid];
    if (!s) return;

    // Call backend to actually terminate the session
    fetch(`${API_BASE}/session/${sid}`, { method: 'DELETE' }).catch(e => console.error("Error deleting session:", e));

    if (s.socket) { s.socket.onclose = null; s.socket.close(); }
    if (s.term && s.term._resizeObserver) { s.term._resizeObserver.disconnect(); }
    if (s.div && s.div.parentNode) s.div.parentNode.removeChild(s.div);
    if (s.tab && s.tab.parentNode) s.tab.parentNode.removeChild(s.tab);
    if (s.term) s.term.dispose();
    delete activeSessions[sid];
    if (currentSid === sid) {
        const sids = Object.keys(activeSessions);
        if (sids.length > 0) showTerminal(sids[sids.length - 1]);
        else showDashboard();
    }
}

dashboardTab.addEventListener('click', showDashboard);

const disconnectBtn = document.getElementById('disconnect-btn');
if (disconnectBtn) {
    disconnectBtn.addEventListener('click', () => {
        if (currentSid && activeSessions[currentSid]) {
            closeSession(currentSid);
        }
    });
}

const reconnectBtn = document.getElementById('reconnect-btn');
if (reconnectBtn) {
    reconnectBtn.addEventListener('click', () => {
        if (currentSid && activeSessions[currentSid]) {
            const s = activeSessions[currentSid];
            // Pre-fill form with current session info
            document.getElementById('host').value = s.host;
            document.getElementById('port').value = s.port;
            document.getElementById('username').value = s.user;
            // Password remains what was last in the form or from properties
            loginDialogMode = 'connect';
            document.getElementById('connect-btn').innerText = '重新连接';
            loginOverlay.classList.remove('hidden');
        }
    });
}

// ==================== Connection ====================
document.getElementById('new-conn-btn').addEventListener('click', () => {
    document.getElementById('session-name-input').value = '';
    document.getElementById('host').value = '';
    document.getElementById('port').value = '22';
    document.getElementById('username').value = 'root';
    document.getElementById('password').value = '';
    loginDialogMode = 'connect';
    document.getElementById('connect-btn').innerText = '连接';
    loginOverlay.classList.remove('hidden');
});

const qsNewBtn = document.getElementById('qs-new-btn');
if (qsNewBtn) qsNewBtn.addEventListener('click', () => document.getElementById('new-conn-btn').click());

cancelLoginBtn.addEventListener('click', () => loginOverlay.classList.add('hidden'));

connectBtn.addEventListener('click', async () => {
    const name = document.getElementById('session-name-input').value.trim();
    const host = document.getElementById('host').value.trim();
    const port = document.getElementById('port').value.trim() || '22';
    const username = document.getElementById('username').value.trim() || 'root';
    const password = document.getElementById('password').value;
    const shouldSave = document.getElementById('save-session-checkbox').checked;
    const useKey = document.getElementById('use-key-checkbox').checked;
    const keyName = document.getElementById('key-select').value;

    if (!host) { alert('请填写主机地址'); return; }
    if (useKey && !keyName) { alert('请选择私钥文件'); return; }

    if (shouldSave) await saveSessionToBackend({ name: name || host, host, port, user: username, pass: password });

    loginOverlay.classList.add('hidden');

    if (loginDialogMode === 'edit') {
        return; // Edit mode only saves and hides
    }

    statusText.innerText = '正在连接...';

    try {
        const resp = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ host, port: parseInt(port), username, password, use_key: useKey, key_name: keyName, name: name })
        });
        if (!resp.ok) {
            const err = await resp.json();
            alert('连接失败: ' + (err.message || '未知错误'));
            statusText.innerText = '连接失败';
            return;
        }
        const result = await resp.json();
        addSessionTab(result.sessionId, name || host, host, username, port);
    } catch (e) {
        alert('网络错误: ' + e.message);
        statusText.innerText = '网络错误';
    }
});

function addSessionTab(sid, title, host, user, port) {
    if (activeSessions[sid]) return;
    const tContainer = document.getElementById('terminal-container');
    const tBar = document.getElementById('tab-bar');
    if (!tContainer || !tBar) return;

    try {
        const sDiv = document.createElement('div');
        sDiv.className = 'terminal-instance';
        tContainer.appendChild(sDiv);

        const tab = document.createElement('div');
        tab.className = 'tab session-tab';
        tab.innerHTML = `<i class="fas fa-terminal"></i> <span>${title}</span>`;

        const closeBtn = document.createElement('div');
        closeBtn.className = 'tab-close';
        closeBtn.innerHTML = '<i class="fas fa-times"></i>';
        closeBtn.addEventListener('click', (e) => { e.stopPropagation(); closeSession(sid); });
        tab.appendChild(closeBtn);

        tab.addEventListener('click', () => showTerminal(sid));
        tab.addEventListener('dblclick', () => closeSession(sid));
        tab.addEventListener('mousedown', (e) => { if (e.button === 1) { e.preventDefault(); closeSession(sid); } });

        tBar.appendChild(tab);

        const sessionObj = initTerminal(sid, sDiv, tab, host, user, port);
        sessionObj.path = '.';
        sessionObj.sid = sid;
        activeSessions[sid] = sessionObj;
        showTerminal(sid);
    } catch (e) { console.error(`Failed to add session tab for ${sid}:`, e); }
}

async function loadActiveSessions() {
    try {
        const resp = await fetch(`${API_BASE}/active-sessions`);
        if (resp.ok) {
            const sessions = await resp.json();
            sessions.forEach(s => addSessionTab(s.sid, s.title || `${s.user}@${s.host}`, s.host, s.user, s.port));
        }
    } catch (e) { console.error('[Restoration] Failed to restore active sessions:', e); }
}

// ==================== Terminal ====================
const MOBA_HIGHLIGHTS = [
    { regex: /(^|[^A-Za-z_&-])(accepted|allowed|enabled|connected|successfully|成功|正确|successful|succeeded|success)(?=[^A-Za-z_-]|$)/gi, code: '$1\x1b[1;32m$2\x1b[m' },
    { regex: /([=>"':.,;({\[][ ]*)(true|yes|ok)(?=[ ]*[\]=>"':.,;)} ])/gi, code: '$1\x1b[1;32m$2\x1b[m' },
    { regex: /(^|[^A-Za-z_&-])((?:(?:bad|wrong|incorrect|improper|invalid|unsupported|bad)(?: file| memory)?(?: descriptor|alloc(?:ation)?|addr(?:ess)?|owner(?:ship)?|arg(?:ument)?|param(?:eter)?|setting|length|filename)|not properly|improperly|(?:operation |connection |authentication |access |permission )?(?:denied|disallowed|not allowed|refused|problem|failed|failure|not permitted)|no [A-Za-z]+(?: [A-Za-z]+)? found|invalid|unsupported|not supported|seg(?:mentation )?fault|错误|corruption|corrupted|corrupt|overflow|underrun|not ok|unimplemented|unsuccessfull|not implemented|errors?|\(ee\)|\(ni\)))(?=[^A-Za-z_-]|$)/gi, code: '$1\x1b[1;31m$2\x1b[m' },
    { regex: /([=>"':.,;({\[][ ]*)(false|no|ko)(?=[ ]*[\]=>"':.,;)} ])/gi, code: '$1\x1b[1;31m$2\x1b[m' },
    { regex: /(^|[^A-Za-z_&-])(\[\-w[A-Za-z-]+\]|caught signal [0-9]+|警告|cannot|(?:connection (?:to (?:remote host|[a-z0-9.]+) )?)?(?:closed|terminated|stopped|not responding)|exited|no more [A-Za-z] available|unexpected|(?:command |binary |file )?not found|(?:o)+ps|out of (?:space|memory)|low (?:memory|disk)|unknown|disabled|disconnected|deprecated|refused|disconnect(?:ion)?|attention|warnings?|exclamation|alerts?|\(ww\)|\(\?\?\)|could not|unable to)(?=[^A-Za-z_-]|$)/gi, code: '$1\x1b[1;33m$2\x1b[m' },
    { regex: /\b(localhost|([1-9]|[1-9][0-9]|1[0-9][0-9]|2[0-4][0-9]|25[0-4])\.[0-9]+\.[0-9]+\.[0-9]+|null|none)\b/gi, code: '\x1b[1;36m$1\x1b[m' },
    { regex: /(^|[^A-Za-z_&-])(last (failed )?login:|launching|checking|loading|creating|building|important|booting|starting|notice|informational|informations?|info|信息|note|\(ii\)|\(\!\!\))(?=[^A-Za-z_-]|$)/gi, code: '$1\x1b[1;37m$2\x1b[m' },
    { regex: /\b(http(s)?:\/\/[A-Za-z0-9_.:/&?=%~#{}()@+-]+)\b/gi, code: '\x1b[4;34m$1\x1b[m' }
];

function applyMobaHighlight(text) {
    let highlighted = text;
    MOBA_HIGHLIGHTS.forEach(h => { highlighted = highlighted.replace(h.regex, h.code); });
    return highlighted;
}

const fontSizeSelect = document.getElementById('font-size-select');

function initTerminal(sid, container, tabEl, host, user, port) {
    const term = new Terminal({
        cursorBlink: true,
        cursorStyle: 'underline',
        cursorInactiveStyle: 'underline',
        // Note: xterm.js might not directly expose cursor_blink_rate in older versions this way, but we will add standard config if available.
        // Or handle it via standard options object if using 5.x+
        windowOptions: {},
        fontFamily: '"Sarasa Fixed SC", "Sarasa Term SC", "Sarasa Mono SC", "Menlo", "Monaco", monospace',
        fontSize: parseInt(fontSizeSelect.value) || 14,
        theme: { background: '#000000', foreground: '#ffffff', cursor: '#eeeeee', cursorAccent: '#eeeeee' }
    });
    // Add custom cursor blink options through internal API if needed. For standard xterm 5.x:
    if (term.options) {
        term.options.cursorBlink = true;
        term.options.cursorBlinkRate = 166;
    }

    // Correct instantiation for the UMD version of FitAddon
    const fitAddon = window.FitAddon ? new window.FitAddon.FitAddon() : null;
    if (!fitAddon) console.error("FitAddon not found! Resize will fail.");

    term.loadAddon(fitAddon);
    term.open(container);

    // Initial fit with small delay for layout
    setTimeout(() => { if (fitAddon) { try { fitAddon.fit(); sendResize(sid); } catch (e) { } } }, 100);
    term.focus();

    term.write('\x1b[33mConnecting...\x1b[0m\r\n');

    const socket = new WebSocket(`${WS_BASE}/ws/${sid}`);
    socket.binaryType = 'arraybuffer';

    term.onResize(size => {
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'resize', cols: size.cols, rows: size.rows }));
        }
    });

    socket.onopen = () => {
        if (sid === currentSid) statusText.innerText = '会话已建立';
        sendResize(sid);
    };
    socket.onmessage = (event) => {
        let text = (event.data instanceof ArrayBuffer) ? new TextDecoder().decode(event.data) : event.data;
        if (typeof event.data === 'string' && text.startsWith('{"__type__": "sftp_progress"')) {
            try {
                const p = JSON.parse(text);
                const status = document.getElementById('status-text');
                if (status) {
                    if (p.total > 0) {
                        const percent = Math.round((p.transferred / p.total) * 100);
                        const namesrc = p.src.split(/[\/\\]/).pop();
                        status.innerText = `[传输中] ${namesrc}: ${formatSize(p.transferred)} / ${formatSize(p.total)} (${percent}%)`;
                    } else {
                        status.innerText = `[传输中] ${p.src}...`;
                    }
                }
                return;
            } catch(e) {}
        }
        term.write(applyMobaHighlight(text));
    };
    socket.onclose = () => { term.write('\r\n\x1b[31m--- 连接已断开 ---\x1b[0m\r\n'); if (sid === currentSid) statusText.innerText = '已断开'; };

    term.attachCustomKeyEventHandler((ev) => {
        if (ev.type === 'keydown' && (ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 'c' && term.hasSelection()) {
            document.execCommand('copy');
            return false;
        }
        return true;
    });

    term.onData(data => {
        if (socket.readyState === WebSocket.OPEN) {
            socket.send(data);
        }
    });

    // Use ResizeObserver for bullet-proof fitting with debounce
    let resizeTimer = null;
    if (fitAddon && window.ResizeObserver) {
        const ro = new ResizeObserver(() => {
            if (resizeTimer) clearTimeout(resizeTimer);
            resizeTimer = setTimeout(() => {
                if (container.offsetWidth > 10 && container.offsetHeight > 10) {
                    try {
                        fitAddon.fit();
                        sendResize(sid);
                    } catch (e) { console.error("Fit error:", e); }
                }
            }, 50);
        });
        ro.observe(container);
        term._resizeObserver = ro;
    }

    return { term, fitAddon, socket, tab: tabEl, div: container, host, user, port };
}

fontSizeSelect.addEventListener('change', () => {
    const newSize = parseInt(fontSizeSelect.value);
    Object.values(activeSessions).forEach(s => {
        s.term.options.fontSize = newSize;
        setTimeout(() => { if (s.fitAddon) { try { s.fitAddon.fit(); } catch (e) { } } sendResize(s.sid); }, 50);
    });
});

window.addEventListener('resize', () => { if (currentSid && activeSessions[currentSid]) { const s = activeSessions[currentSid]; if (s.fitAddon) { try { s.fitAddon.fit(); } catch (e) { } } sendResize(currentSid); } });

function sendResize(sid) {
    const s = activeSessions[sid || currentSid];
    if (s && s.socket && s.socket.readyState === WebSocket.OPEN) s.socket.send(JSON.stringify({ type: 'resize', cols: s.term.cols, rows: s.term.rows }));
}

// ==================== Selection & Editor State ====================
let selections = { local: new Set(), remote: new Set() };
let lastSelectedIndex = { local: -1, remote: -1 };
let monacoEditor = null;
let currentEditingPath = null;
let currentEditingPane = null; // 'local' or 'remote'

const customTooltip = document.createElement('div');
customTooltip.style.cssText = 'position:fixed; background:#ffffe0; border:1px solid #000; padding:4px 8px; box-shadow:2px 2px 5px rgba(0,0,0,0.3); z-index:10000; display:none; font-size:12px; pointer-events:none; white-space:pre-wrap; color:#333;';
document.body.appendChild(customTooltip);

let isDragging = false;
let dragStartIdx = -1;
window.addEventListener('mouseup', () => { isDragging = false; });

// Initialize Monaco
require.config({ paths: { vs: 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.43.0/min/vs' } });

function openEditor(pane, filename) {
    const sid = currentSid;
    if (!sid && pane === 'remote') return;

    currentEditingPath = pane === 'local' ? `${localPath}/${filename}` : `${activeSessions[sid].path}/${filename}`;
    currentEditingPane = pane;
    document.getElementById('editor-filename').innerText = filename;
    document.getElementById('editor-overlay').classList.remove('hidden');

    const url = pane === 'local' ? `${API_BASE}/local/read?path=${encodeURIComponent(currentEditingPath)}` : `${API_BASE}/sftp/read/${sid}?path=${encodeURIComponent(currentEditingPath)}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            if (!monacoEditor) {
                require(['vs/editor/editor.main'], () => {
                    monaco.editor.defineTheme('webshell-dark', {
                        base: 'vs-dark',
                        inherit: true,
                        rules: [
                            { token: '', foreground: 'ffffd3' },
                            { token: 'variable', foreground: 'ffffd3' },
                            { token: 'variable.predefined', foreground: 'ff981e' },
                            { token: 'variable.parameter', foreground: 'ffffd3' },
                            { token: 'constant', foreground: 'fba0b8' },
                            { token: 'comment', foreground: 'ae9b8a', fontStyle: 'italic' },
                            { token: 'number', foreground: 'fba0b8' },
                            { token: 'tag', foreground: 'a8e493' },
                            { token: 'delimiter', foreground: 'ffffd3' },
                            { token: 'string', foreground: 'dbde2d' },
                            { token: 'keyword', foreground: 'ff573e' },
                            { token: 'identifier', foreground: 'ffffd3' },
                            { token: 'type', foreground: 'ffe038' },
                            { token: 'type.identifier', foreground: 'ffe038' },
                            { token: 'function', foreground: 'ffe038' },
                            { token: 'operator', foreground: 'ffffd3' }
                        ],
                        colors: {
                            'editor.background': '#1d2021',
                            'editor.foreground': '#ffffd3',
                            'editorCursor.foreground': '#ffffd3',
                            'editor.lineHighlightBackground': '#282828',
                            'editorLineNumber.foreground': '#665c54',
                            'editorLineNumber.activeForeground': '#a89984',
                            'editorIndentGuide.background': '#3c3836',
                            'editorIndentGuide.activeBackground': '#504945',
                            'editor.selectionBackground': '#504945',
                            'editorWidget.background': '#282828',
                            'editorWidget.border': '#3c3836'
                        }
                    });

                    monacoEditor = monaco.editor.create(document.getElementById('monaco-container'), {
                        value: data.content || '',
                        language: getLanguage(filename),
                        theme: 'webshell-dark',
                        automaticLayout: true,
                        fontSize: 14,
                        lineHeight: 22,
                        fontFamily: '"Sarasa Fixed SC", "JetBrains Mono", "Menlo", "Consolas", monospace',
                        minimap: { enabled: true },
                        scrollbar: {
                            verticalScrollbarSize: 10,
                            horizontalScrollbarSize: 10,
                            useShadows: false
                        },
                        renderLineHighlight: 'all',
                        cursorStyle: 'line',
                        cursorBlinking: 'blink',
                        scrollBeyondLastLine: false
                    });

                    // Add save command
                    monacoEditor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, saveFile);
                });
            } else {
                monacoEditor.setValue(data.content || '');
                monaco.editor.setModelLanguage(monacoEditor.getModel(), getLanguage(filename));
            }
        });
}

function getLanguage(filename) {
    const ext = filename.split('.').pop().toLowerCase();
    const map = {
        'js': 'javascript', 'ts': 'typescript', 'py': 'python',
        'html': 'html', 'css': 'css', 'json': 'json', 'md': 'markdown',
        'sh': 'shell', 'bash': 'shell', 'c': 'c', 'cpp': 'cpp', 'h': 'cpp',
        'java': 'java', 'php': 'php', 'go': 'go', 'yml': 'yaml', 'yaml': 'yaml',
        'xml': 'xml', 'sql': 'sql', 'conf': 'ini', 'ini': 'ini'
    };
    return map[ext] || 'plaintext';
}

async function saveFile() {
    if (!monacoEditor || !currentEditingPath) return;
    const content = monacoEditor.getValue();
    const sid = currentSid;

    statusText.innerText = '正在保存...';
    try {
        const url = currentEditingPane === 'local' ? `${API_BASE}/local/write` : `${API_BASE}/sftp/write/${sid}`;
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: currentEditingPath, content: content })
        });
        if (resp.ok) {
            const tip = document.getElementById('editor-save-tip');
            const msg = currentEditingPane === 'remote' ? '文件已保存到远程服务器' : '保存成功';
            statusText.innerText = msg;
            if (tip) {
                tip.innerText = msg;
                tip.style.opacity = '1';
                setTimeout(() => { tip.style.opacity = '0'; }, 1000);
            }
        } else {
            alert('保存失败');
        }
    } catch (e) {
        alert('保存错误');
    }
}

document.getElementById('editor-save').addEventListener('click', saveFile);
document.getElementById('editor-close').addEventListener('click', () => document.getElementById('editor-overlay').classList.add('hidden'));

// --- Selection Logic ---
function handleSelection(pane, index, event, files) {
    const paneSet = selections[pane];
    const name = files[index].name;
    if (name === '..') return;

    if (event.ctrlKey || event.metaKey) {
        if (paneSet.has(name)) paneSet.delete(name);
        else paneSet.add(name);
    } else if (event.shiftKey && lastSelectedIndex[pane] !== -1) {
        paneSet.clear();
        const start = Math.min(lastSelectedIndex[pane], index);
        const end = Math.max(lastSelectedIndex[pane], index);
        for (let i = start; i <= end; i++) {
            if (files[i].name !== '..') paneSet.add(files[i].name);
        }
    } else {
        paneSet.clear();
        paneSet.add(name);
    }
    lastSelectedIndex[pane] = index;
    renderSelection(pane);
}

function renderSelection(pane) {
    const list = pane === 'local' ? localList : sftpList;
    const paneSet = selections[pane];
    Array.from(list.children).forEach(li => {
        const name = li.querySelector('.name').innerText;
        if (paneSet.has(name)) li.classList.add('selected');
        else li.classList.remove('selected');
    });
}

// ==================== SFTP ====================
let localPath = '.';
const localList = document.getElementById('local-list');
const localPathLabel = document.getElementById('local-path');

// Global Key Listeners for Selection
window.addEventListener('keydown', (e) => {
    if (e.ctrlKey && e.key === 'a') {
        const pane = document.activeElement.closest('.xftp-pane')?.id === 'local-pane' ? 'local' : 'remote';
        if (pane && !sftpPanel.classList.contains('hidden')) {
            e.preventDefault();
            const list = pane === 'local' ? localList : sftpList;
            selections[pane].clear();
            Array.from(list.children).forEach(li => {
                const name = li.querySelector('.name').innerText;
                if (name !== '..') selections[pane].add(name);
            });
            renderSelection(pane);
        }
    }
});

// Context Menu for Xftp
const xftpContextMenu = document.getElementById('xftp-context-menu');
let rightClickedPane = null;

function showXftpContextMenu(x, y, pane) {
    rightClickedPane = pane;
    xftpContextMenu.style.left = '0px';
    xftpContextMenu.style.top = '0px';
    xftpContextMenu.classList.remove('hidden');

    // Hide edit if multiple selected
    const editItem = document.querySelector('.xftp-edit-item');
    if (selections[pane].size > 1) editItem.classList.add('hidden');
    else editItem.classList.remove('hidden');

    // Adjust position to avoid clipping
    const rect = xftpContextMenu.getBoundingClientRect();
    let left = x;
    let top = y;

    if (left + rect.width > window.innerWidth) {
        left = window.innerWidth - rect.width - 5;
    }
    if (top + rect.height > window.innerHeight) {
        top = window.innerHeight - rect.height - 5;
    }

    xftpContextMenu.style.left = left + 'px';
    xftpContextMenu.style.top = top + 'px';
}

window.addEventListener('click', () => xftpContextMenu.classList.add('hidden'));

document.getElementById('xftp-ctx-edit').addEventListener('click', () => {
    const filename = Array.from(selections[rightClickedPane])[0];
    if (filename) openEditor(rightClickedPane, filename);
});

document.getElementById('remote-pane').addEventListener('contextmenu', (e) => {
    e.preventDefault();
    selections.remote.clear();
    renderSelection('remote');
    showXftpContextMenu(e.clientX, e.clientY, 'remote');
});

document.getElementById('xftp-ctx-new-file').addEventListener('click', async () => {
    if (rightClickedPane !== 'remote') return;
    const session = activeSessions[currentSid];
    if (!session) return;
    const name = prompt('新建文件名:');
    if (!name) return;
    const path = session.path === '.' || session.path === '/' ? name : `${session.path}/${name}`;
    const formData = new FormData();
    formData.append('path', path);
    const resp = await fetch(`${API_BASE}/sftp/touch/${currentSid}`, { method: 'POST', body: formData });
    if (resp.ok) loadSFTP(session.path);
    else alert('新建文件失败');
});

document.getElementById('xftp-ctx-new-folder').addEventListener('click', async () => {
    if (rightClickedPane !== 'remote') return;
    const session = activeSessions[currentSid];
    if (!session) return;
    const name = prompt('新建文件夹名:');
    if (!name) return;
    const path = session.path === '.' || session.path === '/' ? name : `${session.path}/${name}`;
    const formData = new FormData();
    formData.append('path', path);
    const resp = await fetch(`${API_BASE}/sftp/mkdir/${currentSid}`, { method: 'POST', body: formData });
    if (resp.ok) loadSFTP(session.path);
    else alert('新建文件夹失败');
});

async function batchTransfer(pane, strategy) {
    const selectedFiles = Array.from(selections[pane]);
    if (selectedFiles.length === 0) return;

    const direction = pane === 'local' ? 'upload' : 'download';
    for (const file of selectedFiles) {
        // Strategy logic (overwrite vs skip)
        // Here we could implement more complex logic, but for now we'll call transferFile
        await transferFile(direction, file, strategy);
    }
}

document.getElementById('xftp-ctx-transfer-overwrite').addEventListener('click', () => batchTransfer(rightClickedPane, 'overwrite'));
document.getElementById('xftp-ctx-transfer-skip').addEventListener('click', () => batchTransfer(rightClickedPane, 'skip'));

function renderBreadcrumbs(pane, path) {
    const container = document.getElementById(pane === 'local' ? 'local-path' : 'remote-path');
    if (!container) return;
    container.innerHTML = '';

    const isWindowsPath = path.includes('\\') || (path.length > 1 && path[1] === ':');
    const separator = isWindowsPath ? '\\' : '/';

    // Clean up path and split
    const parts = path.split(separator).filter(p => p.length > 0);

    // Root item
    const rootItem = document.createElement('span');
    rootItem.className = 'breadcrumb-item';
    rootItem.innerText = isWindowsPath ? '此电脑' : '/';
    rootItem.onclick = () => pane === 'local' ? loadLocalFiles(isWindowsPath ? 'C:\\' : '/') : loadSFTP('/');
    container.appendChild(rootItem);

    parts.forEach((part, index) => {
        // 根节点已经显示了分隔符本身，第一项前不需要再加一个 separator
        if (index > 0) {
            const sep = document.createElement('span');
            sep.className = 'breadcrumb-separator';
            sep.innerText = separator;
            container.appendChild(sep);
        }

        const item = document.createElement('span');
        item.className = 'breadcrumb-item';
        item.innerText = part;

        // Reconstruct path
        let targetPath;
        if (isWindowsPath) {
            targetPath = parts.slice(0, index + 1).join('\\');
            if (targetPath.length === 2 && targetPath[1] === ':') targetPath += '\\';
        } else {
            targetPath = '/' + parts.slice(0, index + 1).join('/');
        }

        item.onclick = () => pane === 'local' ? loadLocalFiles(targetPath) : loadSFTP(targetPath);
        container.appendChild(item);
    });
}

// --- Local Files ---
let sortState = {
    local: { key: 'name', dir: 'asc' },
    remote: { key: 'name', dir: 'asc' }
};
let localFilesData = [];

document.querySelectorAll('.sortable').forEach(el => {
    el.addEventListener('click', (e) => {
        const pane = el.getAttribute('data-pane');
        const key = el.getAttribute('data-sort');
        if (sortState[pane].key === key) {
            sortState[pane].dir = sortState[pane].dir === 'asc' ? 'desc' : 'asc';
        } else {
            sortState[pane].key = key;
            sortState[pane].dir = 'asc';
        }
        
        const parent = el.closest('.pane-list-header');
        parent.querySelectorAll('.sort-icon').forEach(icon => {
            icon.className = 'fas fa-sort sort-icon';
        });
        const activeIcon = el.querySelector('.sort-icon');
        activeIcon.className = sortState[pane].dir === 'asc' ? 'fas fa-sort-up sort-icon' : 'fas fa-sort-down sort-icon';

        if (pane === 'local') renderLocalFiles(localFilesData);
        else renderSFTPFiles(remoteFilesData);
    });
});

async function loadLocalFiles(path) {
    try {
        const resp = await fetch(`${API_BASE}/local/list?path=${encodeURIComponent(path)}`);
        if (resp.ok) {
            const data = await resp.json();
            localPath = data.path;
            renderBreadcrumbs('local', localPath);
            selections.local.clear();
            renderLocalFiles(data.files);
        }
    } catch (e) { console.error("Local list failed", e); }
}

function renderLocalFiles(files) {
    if (files !== localFilesData) localFilesData = files;
    localList.innerHTML = '';
    let displayFiles = files.filter(f => f.name !== '.');
    const sortConf = sortState.local;
    displayFiles.sort((a, b) => {
        if (a.is_dir !== b.is_dir) return b.is_dir - a.is_dir;
        let vA = (a[sortConf.key] === undefined || a[sortConf.key] === null) ? 0 : a[sortConf.key];
        let vB = (b[sortConf.key] === undefined || b[sortConf.key] === null) ? 0 : b[sortConf.key];
        let res = 0;
        if (sortConf.key === 'name') res = String(vA).localeCompare(String(vB));
        else res = vA - vB;
        return sortConf.dir === 'asc' ? res : -res;
    });

    displayFiles.forEach((file, index) => {
        const li = document.createElement('li');
        li.className = 'sftp-item';
        const icon = file.is_dir ? 'fa-folder' : 'fa-file';
        const mtimeStr = file.mtime ? new Date(file.mtime * 1000).toLocaleString() : '--';
        li.innerHTML = `<i class="fas ${icon}" style="color:${file.is_dir ? '#e6a817' : '#7f8c8d'}"></i><span class="name">${file.name}</span><span class="size">${file.is_dir ? '--' : formatSize(file.size)}</span><span class="mtime">${mtimeStr}</span>`;
        const ownerStr = (file.uid !== undefined ? file.uid : '-') + ':' + (file.gid !== undefined ? file.gid : '-');
        const tooltipStr = `名称: ${file.name}\n修改时间: ${mtimeStr}\n所有者: ${ownerStr}\n权限: ${file.permissions || '--'}`;

        li.addEventListener('mousemove', (e) => {
            if (!isDragging) {
                customTooltip.innerText = tooltipStr;
                customTooltip.style.display = 'block';
                let tx = e.clientX + 15;
                let ty = e.clientY + 15;
                if (tx + 180 > window.innerWidth) tx = e.clientX - 180;
                if (ty + 80 > window.innerHeight) ty = e.clientY - 80;
                customTooltip.style.left = tx + 'px';
                customTooltip.style.top = ty + 'px';
            } else {
                customTooltip.style.display = 'none';
            }
        });
        li.addEventListener('mouseleave', () => { customTooltip.style.display = 'none'; });
        li.addEventListener('mousedown', () => { customTooltip.style.display = 'none'; });

        li.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            isDragging = true;
            dragStartIdx = index;
            handleSelection('local', index, e, displayFiles);
        });

        li.addEventListener('mouseenter', (e) => {
            if (isDragging) {
                const paneSet = selections['local'];
                paneSet.clear();
                const start = Math.min(dragStartIdx, index);
                const end = Math.max(dragStartIdx, index);
                for (let i = start; i <= end; i++) {
                    if (displayFiles[i].name !== '..') paneSet.add(displayFiles[i].name);
                }
                lastSelectedIndex['local'] = index;
                renderSelection('local');
            }
        });

        li.addEventListener('dblclick', (e) => {
            if (file.is_dir) {
                const separator = localPath.includes('\\') ? '\\' : '/';
                let newPath;
                if (file.name === '..') {
                    const parts = localPath.split(separator).filter(p => p);
                    parts.pop();
                    newPath = separator === '/'
                        ? '/' + parts.join('/')
                        : (parts.length > 0 ? parts.join('\\') : 'C:\\');
                } else {
                    newPath = localPath.endsWith(separator) ? localPath + file.name : localPath + separator + file.name;
                }
                loadLocalFiles(newPath);
            } else {
                openEditor('local', file.name);
            }
        });

        li.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!selections.local.has(file.name)) handleSelection('local', index, { ctrlKey: false, shiftKey: false }, displayFiles);
            showXftpContextMenu(e.clientX, e.clientY, 'local');
        });

        localList.appendChild(li);
    });
}

document.getElementById('local-up').addEventListener('click', () => loadLocalFiles('..'));
document.getElementById('local-refresh').addEventListener('click', () => loadLocalFiles(localPath));

async function loadSFTP(path) {
    if (!currentSid || !activeSessions[currentSid]) return;
    const session = activeSessions[currentSid];
    sftpList.innerHTML = '<li style="padding:10px;color:#888">加载中...</li>';
    try {
        const resp = await fetch(`${API_BASE}/sftp/list/${currentSid}?path=${encodeURIComponent(path)}`);
        if (resp.ok) {
            const data = await resp.json();
            // Use the absolute path returned by the backend
            session.path = data.path;
            renderBreadcrumbs('remote', data.path);
            selections.remote.clear();
            renderSFTPFiles(data.files);
        }
        else { sftpList.innerHTML = '<li style="padding:10px;color:red">加载失败</li>'; }
    } catch (e) { sftpList.innerHTML = '<li style="padding:10px;color:red">网络错误</li>'; }
}

let remoteFilesData = [];

function renderSFTPFiles(files) {
    if (files !== remoteFilesData) remoteFilesData = files;
    sftpList.innerHTML = '';
    let displayFiles = files.filter(f => f.name !== '.');
    const sortConf = sortState.remote;
    displayFiles.sort((a, b) => {
        if (a.is_dir !== b.is_dir) return b.is_dir - a.is_dir;
        let vA = (a[sortConf.key] === undefined || a[sortConf.key] === null) ? 0 : a[sortConf.key];
        let vB = (b[sortConf.key] === undefined || b[sortConf.key] === null) ? 0 : b[sortConf.key];
        let res = 0;
        if (sortConf.key === 'name') res = String(vA).localeCompare(String(vB));
        else res = vA - vB;
        return sortConf.dir === 'asc' ? res : -res;
    });

    displayFiles.forEach((file, index) => {
        const li = document.createElement('li');
        li.className = 'sftp-item';
        const icon = file.is_dir ? 'fa-folder' : 'fa-file';
        const mtimeStr = file.mtime ? new Date(file.mtime * 1000).toLocaleString() : '--';
        li.innerHTML = `<i class="fas ${icon}" style="color:${file.is_dir ? '#e6a817' : '#7f8c8d'}"></i><span class="name">${file.name}</span><span class="size">${file.is_dir ? '--' : formatSize(file.size)}</span><span class="mtime">${mtimeStr}</span>`;
        const ownerStr = (file.uid !== undefined ? file.uid : '-') + ':' + (file.gid !== undefined ? file.gid : '-');
        const tooltipStr = `名称: ${file.name}\n修改时间: ${mtimeStr}\n所有者: ${ownerStr}\n权限: ${file.permissions || '--'}`;

        li.addEventListener('mousemove', (e) => {
            if (!isDragging) {
                customTooltip.innerText = tooltipStr;
                customTooltip.style.display = 'block';
                let tx = e.clientX + 15;
                let ty = e.clientY + 15;
                if (tx + 180 > window.innerWidth) tx = e.clientX - 180;
                if (ty + 80 > window.innerHeight) ty = e.clientY - 80;
                customTooltip.style.left = tx + 'px';
                customTooltip.style.top = ty + 'px';
            } else {
                customTooltip.style.display = 'none';
            }
        });
        li.addEventListener('mouseleave', () => { customTooltip.style.display = 'none'; });
        li.addEventListener('mousedown', () => { customTooltip.style.display = 'none'; });

        li.addEventListener('mousedown', (e) => {
            if (e.button !== 0) return;
            isDragging = true;
            dragStartIdx = index;
            handleSelection('remote', index, e, displayFiles);
        });

        li.addEventListener('mouseenter', (e) => {
            if (isDragging) {
                const paneSet = selections['remote'];
                paneSet.clear();
                const start = Math.min(dragStartIdx, index);
                const end = Math.max(dragStartIdx, index);
                for (let i = start; i <= end; i++) {
                    if (displayFiles[i].name !== '..') paneSet.add(displayFiles[i].name);
                }
                lastSelectedIndex['remote'] = index;
                renderSelection('remote');
            }
        });

        li.addEventListener('dblclick', (e) => {
            if (file.is_dir) {
                const session = activeSessions[currentSid];
                const currentPath = session.path;
                let newPath;
                if (currentPath.endsWith('/')) {
                    newPath = currentPath + file.name;
                } else {
                    newPath = currentPath + '/' + file.name;
                }
                loadSFTP(newPath);
            } else {
                openEditor('remote', file.name);
            }
        });

        li.addEventListener('contextmenu', (e) => {
            e.preventDefault();
            e.stopPropagation();
            if (!selections.remote.has(file.name)) handleSelection('remote', index, { ctrlKey: false, shiftKey: false }, displayFiles);
            showXftpContextMenu(e.clientX, e.clientY, 'remote');
        });

        sftpList.appendChild(li);
    });
}

// SFTP Context Menu Actions
document.getElementById('xftp-ctx-copy-path').addEventListener('click', () => {
    if (rightClickedPane !== 'remote') return;
    const filename = Array.from(selections.remote)[0];
    const session = activeSessions[currentSid];
    
    let fullPath = session.path;
    if (filename && filename !== '..') {
        fullPath = (session.path === '.' || session.path === '/') ? `/${filename}` : `${session.path}/${filename}`;
    }

    const fallbackCopyTextToClipboard = (text) => {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed";
        textArea.style.opacity = "0";
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand('copy');
            statusText.innerText = '路径已复制到剪贴板';
        } catch (err) {
            console.error('Fallback: oops, unable to copy', err);
            statusText.innerText = '复制路径失败';
        }
        document.body.removeChild(textArea);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(fullPath).then(() => {
            statusText.innerText = '路径已复制到剪贴板';
        }).catch(() => fallbackCopyTextToClipboard(fullPath));
    } else {
        fallbackCopyTextToClipboard(fullPath);
    }
});

document.getElementById('xftp-ctx-rename').addEventListener('click', async () => {
    if (rightClickedPane !== 'remote') return;
    const oldName = Array.from(selections.remote)[0];
    const newName = prompt('重命名为:', oldName);
    if (!newName || newName === oldName) return;

    const session = activeSessions[currentSid];
    const oldPath = session.path === '.' || session.path === '/' ? oldName : `${session.path}/${oldName}`;
    const newPath = session.path === '.' || session.path === '/' ? newName : `${session.path}/${newName}`;

    const formData = new FormData();
    formData.append('old_path', oldPath);
    formData.append('new_path', newPath);

    const resp = await fetch(`${API_BASE}/sftp/rename/${currentSid}`, { method: 'POST', body: formData });
    if (resp.ok) loadSFTP(session.path);
    else alert('重命名失败');
});

document.getElementById('xftp-ctx-delete').addEventListener('click', async () => {
    if (rightClickedPane !== 'remote') return;
    const selected = Array.from(selections.remote);
    if (!confirm(`确定要删除选中的 ${selected.length} 个项目吗?`)) return;

    const session = activeSessions[currentSid];
    for (const name of selected) {
        const path = session.path === '.' || session.path === '/' ? name : `${session.path}/${name}`;
        await fetch(`${API_BASE}/sftp/delete/${currentSid}?path=${encodeURIComponent(path)}`, { method: 'DELETE' });
    }
    loadSFTP(session.path);
});

document.getElementById('xftp-ctx-chmod').addEventListener('click', async () => {
    if (rightClickedPane !== 'remote') return;
    const name = Array.from(selections.remote)[0];
    const file = remoteFilesData.find(f => f.name === name);
    const mode = prompt('更改权限 (八进制, 如 755):', file ? file.permissions.replace('0o', '') : '644');
    if (!mode) return;

    const session = activeSessions[currentSid];
    const path = session.path === '.' || session.path === '/' ? name : `${session.path}/${name}`;
    const formData = new FormData();
    formData.append('path', path);
    formData.append('mode', mode);

    const resp = await fetch(`${API_BASE}/sftp/chmod/${currentSid}`, { method: 'POST', body: formData });
    if (resp.ok) loadSFTP(session.path);
    else alert('更改权限失败');
});

document.getElementById('xftp-ctx-props').addEventListener('click', () => {
    if (rightClickedPane !== 'remote') return;
    const name = Array.from(selections.remote)[0];
    const file = remoteFilesData.find(f => f.name === name);
    if (!file) return;

    const session = activeSessions[currentSid];
    const fullPath = session.path === '.' || session.path === '/' ? name : `${session.path}/${name}`;
    const date = new Date(file.mtime * 1000).toLocaleString();

    alert(`属性:\n名称: ${file.name}\n路径: ${fullPath}\n大小: ${formatSize(file.size)}\n权限: ${file.permissions}\nUID/GID: ${file.uid}/${file.gid}\n修改时间: ${date}`);
});

// --- Transfer Logic ---
async function transferFile(direction, filename, strategy = 'overwrite') {
    if (!currentSid) return;
    const session = activeSessions[currentSid];
    const localFull = localPath === '/' ? `/${filename}` : `${localPath}/${filename}`;
    const remoteFull = session.path === '.' || session.path === '/' ? filename : `${session.path}/${filename}`;

    // Here we could check for existence if strategy is 'skip', but for simplicity:
    statusText.innerText = `正在传输 ${filename} (${strategy})...`;

    try {
        const resp = await fetch(`${API_BASE}/sftp/transfer/${currentSid}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                direction: direction,
                local_path: localFull,
                remote_path: remoteFull
                // strategy: strategy // Backend needs to support this for true skip
            })
        });
        if (resp.ok) {
            statusText.innerText = '传输成功';
            if (direction === 'upload') loadSFTP(session.path);
            else loadLocalFiles(localPath);
        }
    } catch (e) { console.error('Transfer failed', e); }
}

function formatSize(bytes) {
    if (!bytes) return '0 B';
    const k = 1024, sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

document.getElementById('sftp-up').addEventListener('click', () => {
    const session = activeSessions[currentSid];
    if (!session || session.path === '.' || session.path === '/') return;
    const parts = session.path.split('/');
    parts.pop();
    loadSFTP(parts.join('/') || '/');
});

document.getElementById('sftp-refresh').addEventListener('click', () => { if (currentSid) loadSFTP(activeSessions[currentSid].path); });

function downloadFile(filename) {
    const session = activeSessions[currentSid];
    const fullPath = session.path === '.' ? filename : `${session.path}/${filename}`;
    window.open(`${API_BASE}/sftp/download/${currentSid}?path=${encodeURIComponent(fullPath)}`, '_blank');
}

const uploadBtn = document.getElementById('upload-btn');
const uploadInput = document.getElementById('upload-input');
uploadBtn.addEventListener('click', () => uploadInput.click());

uploadInput.addEventListener('change', async () => {
    if (!uploadInput.files.length || !currentSid) return;
    const file = uploadInput.files[0], session = activeSessions[currentSid];
    const formData = new FormData();
    formData.append('file', file);
    formData.append('remote_path', session.path);
    statusText.innerText = `正在上传 ${file.name}...`;
    try {
        const resp = await fetch(`${API_BASE}/sftp/upload/${currentSid}`, { method: 'POST', body: formData });
        if (resp.ok) { statusText.innerText = '上传成功'; loadSFTP(session.path); }
        else { statusText.innerText = '上传失败'; }
    } catch (e) { statusText.innerText = '上传错误'; }
    uploadInput.value = '';
});

// ==================== Quick Command Bar ====================
let quickCommands = JSON.parse(localStorage.getItem('quickCommands')) || [
    { label: '密码', command: 'password\n' },
    { label: '密钥', command: 'cat ~/.ssh/id_rsa.pub\n' },
    { label: '更新', command: 'apt update && apt upgrade -y\n' },
    { label: 'bbr', command: 'lsmod | grep bbr\n' },
    { label: 'Docker', command: 'docker ps\n' },
    { label: 'Ctrl+C', command: '\\x03' },
    { label: 'Ctrl+Z', command: '\\x1a' },
    { label: 'Ctrl+X', command: '\\x18' },
    { label: '粘贴', command: '' },
    { label: '退出', command: 'exit\n' }
];

const quickCmdBar = document.getElementById('quick-cmd-bar');
const quickCmdList = document.getElementById('quick-cmd-list');

document.getElementById('toggle-quick-cmd').addEventListener('click', () => {
    quickCmdBar.classList.toggle('hidden');
    // Ensure terminal resizes when layout changes
    if (currentSid && !document.getElementById('terminal-wrapper').classList.contains('hidden')) {
        setTimeout(() => {
            const s = activeSessions[currentSid];
            if (s && s.fitAddon) {
                try { s.fitAddon.fit(); } catch (e) { }
                sendResize(currentSid);
            }
        }, 50);
    }
});

function renderQuickCommands() {
    quickCmdList.innerHTML = '';
    quickCommands.forEach((cmd, idx) => {
        const btn = document.createElement('div');
        btn.className = 'quick-cmd-item';
        btn.innerText = cmd.label;
        btn.addEventListener('click', async () => {
            if (cmd.label === '粘贴') {
                try {
                    const text = await navigator.clipboard.readText();
                    sendQuickCommand(text);
                } catch (e) {
                    console.error('Clipboard read failed', e);
                }
            } else {
                sendQuickCommand(cmd.command);
            }
        });
        quickCmdList.appendChild(btn);
    });
}

function sendQuickCommand(cmdString) {
    if (!currentSid || !activeSessions[currentSid]) return;
    const session = activeSessions[currentSid];
    if (session.socket && session.socket.readyState === WebSocket.OPEN) {
        // Parse \x sequences
        const parsedData = cmdString.replace(/\\x([0-9a-fA-F]{2})/g, (match, hex) => {
            return String.fromCharCode(parseInt(hex, 16));
        }).replace(/\\n/g, '\n').replace(/\\r/g, '\r');

        session.socket.send(parsedData);
        session.term.focus();
    }
}

// Quick Command Editor Logic
const quickCmdModal = document.getElementById('quick-cmd-modal');
const quickCmdEditList = document.getElementById('quick-cmd-edit-list');

document.getElementById('add-quick-cmd-btn').addEventListener('click', () => {
    quickCmdModal.classList.remove('hidden');
    renderQuickCmdEditList();
});

document.getElementById('close-quick-cmd-btn').addEventListener('click', () => {
    quickCmdModal.classList.add('hidden');
});

document.getElementById('save-quick-cmd-btn').addEventListener('click', () => {
    localStorage.setItem('quickCommands', JSON.stringify(quickCommands));
    renderQuickCommands();
    quickCmdModal.classList.add('hidden');
});

function renderQuickCmdEditList() {
    quickCmdEditList.innerHTML = '';
    quickCommands.forEach((cmd, idx) => {
        const row = document.createElement('li');
        row.className = 'cmd-edit-row';
        row.innerHTML = `
            <input type="text" value="${cmd.label}" style="width:100px" data-idx="${idx}" class="edit-label">
            <input type="text" value="${cmd.command.replace(/'/g, "&#39;").replace(/"/g, "&quot;")}" style="flex:1" data-idx="${idx}" class="edit-value">
            <button class="del-cmd-btn" data-idx="${idx}" title="删除"><i class="fas fa-trash"></i></button>
        `;
        quickCmdEditList.appendChild(row);
    });

    // Attach listeners after render
    document.querySelectorAll('.edit-label').forEach(el => el.addEventListener('input', (e) => {
        quickCommands[e.target.dataset.idx].label = e.target.value;
    }));
    document.querySelectorAll('.edit-value').forEach(el => el.addEventListener('input', (e) => {
        quickCommands[e.target.dataset.idx].command = e.target.value;
    }));
    document.querySelectorAll('.del-cmd-btn').forEach(el => el.addEventListener('click', (e) => {
        quickCommands.splice(e.currentTarget.dataset.idx, 1);
        renderQuickCmdEditList();
    }));
}

document.getElementById('btn-add-cmd').addEventListener('click', () => {
    const label = document.getElementById('cmd-label-input').value.trim();
    const value = document.getElementById('cmd-value-input').value.trim();
    if (label !== '') {
        quickCommands.push({ label, command: value });
        document.getElementById('cmd-label-input').value = '';
        document.getElementById('cmd-value-input').value = '';
        renderQuickCmdEditList();
    }
});

// Initial Render
renderQuickCommands();
