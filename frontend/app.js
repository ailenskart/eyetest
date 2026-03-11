// Eye Test Engine Frontend Application
// Integrates with Flask API backend and Phoropter API

const CONFIG = {
    // Priority: window.BACKEND_URL > localhost:5050 (if dev) > same-origin
    backendUrl: (typeof window !== 'undefined' && window.BACKEND_URL)
        ? window.BACKEND_URL
        : ((typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'))
            ? 'http://localhost:5050' : ''),
    phoropterUrl: 'https://rajasthan-royals.preprod.lenskart.com',
    get phoropterId() {
        const el = document.getElementById('phoropterIdInput');
        return (el && el.value.trim()) ? el.value.trim() : 'phoropter-1';
    }
};

// ── Request logging (curl commands) ─────────────────────────────────────
function buildCurlFromFetch(url, options) {
    const u = typeof url === 'string' ? url : (url.url || '');
    const absUrl = u.startsWith('http') ? u : new URL(u, window.location.origin).href;
    const method = (options && options.method) ? String(options.method).toUpperCase() : 'GET';
    const headers = options && options.headers ? (options.headers instanceof Headers
        ? Object.fromEntries(options.headers.entries())
        : options.headers) : {};
    let body = options && options.body !== undefined ? options.body : null;
    if (typeof body === 'object' && body !== null && !(body instanceof String)) {
        try { body = JSON.stringify(body); } catch (_) { body = String(body); }
    }
    const escapeShell = (s) => (s || '').replace(/'/g, "'\\''");
    const parts = ['curl -X ' + method + " '" + escapeShell(absUrl) + "'"];
    const skipHeaders = ['accept-encoding'];
    Object.keys(headers).forEach((k) => {
        if (skipHeaders.includes(k.toLowerCase())) return;
        const v = headers[k];
        if (v !== undefined && v !== null) {
            parts.push("-H '" + escapeShell(k + ': ' + v) + "'");
        }
    });
    if (body != null && body !== '' && method !== 'GET') {
        parts.push("-d '" + escapeShell(body) + "'");
    }
    return parts.join(' \\\n  ');
}

function addRequestLog(curlString, method, url) {
    if (typeof document === 'undefined' || !document.getElementById('requestLogsContent')) return;
    const container = document.getElementById('requestLogsContent');
    const placeholder = document.getElementById('requestLogsPlaceholder');
    if (placeholder) placeholder.style.display = 'none';
    const absUrl = url.startsWith('http') ? url : new URL(url, window.location.origin).href;
    const time = new Date().toLocaleTimeString(undefined, { hour12: false });
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `
        <div class="log-entry-header">
            <span class="log-entry-method">${method}</span>
            <span>${time}</span>
            <span style="flex:1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${absUrl}">${absUrl}</span>
        </div>
        <pre class="log-entry-curl">${(curlString || '').replace(/</g, '&lt;').replace(/>/g, '&gt;')}</pre>
    `;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
}

function clearRequestLogs() {
    const container = document.getElementById('requestLogsContent');
    const placeholder = document.getElementById('requestLogsPlaceholder');
    if (container) {
        container.innerHTML = '';
        if (placeholder) {
            container.appendChild(placeholder);
            placeholder.style.display = 'block';
            placeholder.textContent = 'No requests yet.';
        }
    }
}

// ── Logs panel: password gate, minimize by default, expand from right ───
const LOGS_PASSWORD = 'Shantanu';
const LOGS_UNLOCK_HOURS = 24;
const LOGS_STORAGE_DENIED = 'eyeTest_logsUnlockDenied';
const LOGS_STORAGE_UNTIL = 'eyeTest_logsUnlockUntil';

function isLogsAccessDenied() {
    try {
        return localStorage.getItem(LOGS_STORAGE_DENIED) === 'true';
    } catch (_) {
        return false;
    }
}

function getLogsUnlockUntil() {
    try {
        const v = localStorage.getItem(LOGS_STORAGE_UNTIL);
        return v ? parseInt(v, 10) : 0;
    } catch (_) {
        return 0;
    }
}

function setLogsUnlockUntil(untilMs) {
    try {
        localStorage.setItem(LOGS_STORAGE_UNTIL, String(untilMs));
    } catch (_) {}
}

function setLogsAccessDenied() {
    try {
        localStorage.setItem(LOGS_STORAGE_DENIED, 'true');
    } catch (_) {}
}

function isLogsUnlocked() {
    if (isLogsAccessDenied()) return false;
    const until = getLogsUnlockUntil();
    return until > Date.now();
}

function openLogsPasswordModal() {
    const modal = document.getElementById('logsPasswordModal');
    const input = document.getElementById('logsPasswordInput');
    const err = document.getElementById('logsPasswordError');
    if (modal) modal.classList.add('active');
    if (input) {
        input.value = '';
        input.focus();
    }
    if (err) err.classList.remove('visible');
}

function closeLogsPasswordModal() {
    const modal = document.getElementById('logsPasswordModal');
    if (modal) modal.classList.remove('active');
}

function submitLogsPassword() {
    const input = document.getElementById('logsPasswordInput');
    const err = document.getElementById('logsPasswordError');
    const value = (input && input.value) ? input.value.trim() : '';
    if (value !== LOGS_PASSWORD) {
        setLogsAccessDenied();
        if (err) {
            err.textContent = 'Incorrect password. Logs access is disabled on this browser.';
            err.classList.add('visible');
        }
        closeLogsPasswordModal();
        const tab = document.getElementById('logsTabBtn');
        if (tab) tab.classList.add('hidden');
        return;
    }
    const until = Date.now() + LOGS_UNLOCK_HOURS * 60 * 60 * 1000;
    setLogsUnlockUntil(until);
    closeLogsPasswordModal();
    openLogsPanel();
}

function requestShowLogsPanel() {
    if (isLogsAccessDenied()) {
        return;
    }
    if (isLogsUnlocked()) {
        openLogsPanel();
        return;
    }
    openLogsPasswordModal();
}

function openLogsPanel() {
    const main = document.querySelector('.main-content');
    const tab = document.getElementById('logsTabBtn');
    if (main) main.classList.add('logs-expanded');
    if (tab) tab.classList.add('hidden');
}

function closeLogsPanel() {
    const main = document.querySelector('.main-content');
    const tab = document.getElementById('logsTabBtn');
    if (main) main.classList.remove('logs-expanded');
    if (tab && !isLogsAccessDenied()) tab.classList.remove('hidden');
}

const _originalFetch = window.fetch;
window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    const options = init || (input && typeof input === 'object' ? {
        method: input.method,
        headers: input.headers,
        body: input.body
    } : {});
    const method = (options.method || 'GET').toUpperCase();
    const absUrl = url.startsWith('http') ? url : new URL(url, window.location.origin).href;
    try {
        const curl = buildCurlFromFetch(input, options);
        addRequestLog(curl, method, absUrl);
    } catch (e) {
        console.warn('Request log build failed:', e);
    }
    return _originalFetch.call(this, input, init);
};

let sessionState = {
    sessionId: null,
    currentPhase: null,
    currentChart: null,  // Track current chart to avoid duplicate setChart calls
    currentChartIndex: 0,  // Track current chart index
    availableCharts: [],  // List of available charts
    intentsLocked: false,
    responseCount: 0,
    history: []
};

// Pinhole toggle state (Specific Optotype section)
let pinholeActive = false;

// Stored power values
let storedPower = {
    ar: null,  // {right: {sph, cyl, axis}, left: {sph, cyl, axis}}
    lenso: null  // {right: {sph, cyl, axis}, left: {sph, cyl, axis}}
};

let currentAppliedPower = 'none';  // 'none', 'ar', or 'lenso'

let _configReady = false;

let operatorName = '';  // cached optometrist name
let customerName = '';
let customerAge = '';
let customerGender = '';

// Memory state for store/restore/swap
let memoryState = null;       // {power: {right: {...}, left: {...}}}
let memoryMode = 'mem';       // 'mem' | 'memS' | 'memR'
let _realtimeBeforeRestore = null;

// Optotype mapping for VA charts (Chart 1)
const OPTOTYPE_MAP = {
    "snellen_chart_200_150": ["200", "150"],
    "snellen_chart_100_80": ["100", "80"],
    "snellen_chart_70_60_50": ["70", "60", "50"],
    "snellen_chart_40_30_25": ["40", "30", "25"],
    "snellen_chart_20_15_10": ["20", "15", "10"],
    "snellen_chart_20_20_20": ["20_1", "20_2", "20_3"],
    "snellen_chart_25_20_15": ["25", "20", "15"],
    "bino_chart": ["R", "L"]
};

let currentOptotype = null;

async function fetchConfig() {
    console.log('[CONFIG] Fetching runtime config from same-origin...');
    try {
        // Always hit same-origin /api/config first to get the real backend URL
        const resp = await fetch('/api/config');
        if (resp.ok) {
            const data = await resp.json();
            if (data.backend_url) {
                CONFIG.backendUrl = data.backend_url;
                console.log('[CONFIG] Backend URL overridden from server:', CONFIG.backendUrl);
            }
            if (data.phoropter_base_url) {
                CONFIG.phoropterUrl = data.phoropter_base_url;
                console.log('[CONFIG] Phoropter Base URL set to:', CONFIG.phoropterUrl);
            }
        } else {
            console.warn('[CONFIG] Failed to fetch config, status:', resp.status);
        }
    } catch (err) {
        console.warn('[CONFIG] Could not fetch session config:', err);
    } finally {
        _configReady = true;
        const btn = document.getElementById('startTestBtn');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Start Eye Test';
        }
    }
}

function savePhoropterId() {
    const el = document.getElementById('phoropterIdInput');
    if (!el) return;
    const id = el.value.trim() || 'phoropter-1';
    el.value = id;
    localStorage.setItem('phoropterId', id);
    console.log(`Phoropter ID set to: ${id}`);
}

// ── Device Management ────────────────────────────────
const TEST_DEVICE_ID = 'Test';
let _deviceTypeaheadBuffer = '';
let _deviceTypeaheadTimer = null;

function isTestDeviceId(deviceId = CONFIG.phoropterId) {
    return String(deviceId || '').trim().toLowerCase() === TEST_DEVICE_ID.toLowerCase();
}

function setupDeviceTypeahead() {
    const select = document.getElementById('phoropterIdInput');
    if (!select || select.dataset.typeaheadBound === '1') return;

    select.dataset.typeaheadBound = '1';
    select.addEventListener('keydown', (event) => {
        if (select.disabled) return;
        const key = event.key;

        if (key === 'Escape') {
            _deviceTypeaheadBuffer = '';
            return;
        }

        if (key === 'Backspace') {
            _deviceTypeaheadBuffer = _deviceTypeaheadBuffer.slice(0, -1);
            return;
        }

        if (key.length !== 1 || event.ctrlKey || event.metaKey || event.altKey) {
            return;
        }

        _deviceTypeaheadBuffer += key.toLowerCase();
        if (_deviceTypeaheadTimer) clearTimeout(_deviceTypeaheadTimer);
        _deviceTypeaheadTimer = setTimeout(() => {
            _deviceTypeaheadBuffer = '';
        }, 800);

        const options = Array.from(select.options || []);
        const startsWithMatch = options.find(opt =>
            String(opt.value || '').toLowerCase().startsWith(_deviceTypeaheadBuffer)
        );
        const includesMatch = startsWithMatch || options.find(opt =>
            String(opt.value || '').toLowerCase().includes(_deviceTypeaheadBuffer)
        );

        if (includesMatch) {
            select.value = includesMatch.value;
            onDeviceSelectionChanged();
            event.preventDefault();
        }
    });
}

async function fetchDevices() {
    const select = document.getElementById('phoropterIdInput');
    if (!select) return;

    // If device is already acquired, just show that device and skip the fetch
    if (_deviceAcquired) {
        const acquiredId = localStorage.getItem('phoropterId') || '';
        if (acquiredId) {
            select.innerHTML = '';
            const opt = document.createElement('option');
            opt.value = acquiredId;
            opt.textContent = isTestDeviceId(acquiredId)
                ? `${acquiredId} (test mode)`
                : `${acquiredId} (connected)`;
            opt.selected = true;
            select.appendChild(opt);
            select.disabled = true;
        }
        return;
    }

    try {
        const resp = await fetch(`${CONFIG.backendUrl}/api/devices`);
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const data = await resp.json();

        const devices = Array.isArray(data) ? data : (data.devices || []);
        select.innerHTML = '';

        const savedId = localStorage.getItem('phoropterId');
        const deviceIds = devices
            .map(dev => dev.device_id || dev.id || dev.name || '')
            .filter(Boolean);
        if (!deviceIds.some(id => String(id).toLowerCase() === TEST_DEVICE_ID.toLowerCase())) {
            deviceIds.unshift(TEST_DEVICE_ID);
        }

        if (deviceIds.length === 0) {
            deviceIds.push(TEST_DEVICE_ID);
        }

        deviceIds.forEach(id => {
            const opt = document.createElement('option');
            opt.value = id;
            opt.textContent = isTestDeviceId(id) ? `${id} (safe mode)` : id;
            if (id === savedId) opt.selected = true;
            select.appendChild(opt);
        });

        if (!select.value && deviceIds.length > 0) {
            select.value = deviceIds[0];
        }
        if (select.value) {
            localStorage.setItem('phoropterId', select.value);
        }
        setupDeviceTypeahead();
        onDeviceSelectionChanged();
    } catch (err) {
        console.warn('Could not fetch devices:', err);
        select.innerHTML = '';
        select.innerHTML = `
            <option value="${TEST_DEVICE_ID}">${TEST_DEVICE_ID} (safe mode)</option>
            <option value="phoropter-1">phoropter-1 (default)</option>
        `;
        const savedId = localStorage.getItem('phoropterId');
        select.value = savedId || TEST_DEVICE_ID;
        if (!select.value) {
            select.value = TEST_DEVICE_ID;
        }
        localStorage.setItem('phoropterId', select.value);
        setupDeviceTypeahead();
        onDeviceSelectionChanged();
    }
}

function onDeviceSelectionChanged() {
    const select = document.getElementById('phoropterIdInput');
    const acquireBtn = document.getElementById('acquireDeviceBtn');
    if (!select) return;

    const id = select.value;
    if (id) {
        localStorage.setItem('phoropterId', id);
        if (acquireBtn && !_deviceAcquired && !isTestDeviceId(id)) {
            acquireBtn.style.display = 'inline-block';
        } else if (acquireBtn) {
            acquireBtn.style.display = 'none';
        }
    } else {
        if (acquireBtn) acquireBtn.style.display = 'none';
    }
}

let _cachedClientIp = null;

async function getClientIp() {
    if (_cachedClientIp) return _cachedClientIp;
    try {
        const resp = await fetch('https://api.ipify.org?format=json');
        const data = await resp.json();
        _cachedClientIp = data.ip || 'unknown';
    } catch {
        _cachedClientIp = 'unknown';
    }
    return _cachedClientIp;
}

async function getBrainId() {
    const ip = await getClientIp();
    const name = (operatorName || 'unknown').replace(/\s+/g, '_');
    return `${name}@${ip}`;
}

async function acquireSelectedDevice() {
    const deviceId = CONFIG.phoropterId;
    if (!deviceId) return;

    if (isTestDeviceId(deviceId)) {
        _deviceAcquired = true;
        const select = document.getElementById('phoropterIdInput');
        const btn = document.getElementById('acquireDeviceBtn');
        if (select) select.disabled = true;
        if (btn) btn.style.display = 'none';
        addToHistory('Test mode active: physical phoropter commands are skipped', 'info');
        return;
    }

    const btn = document.getElementById('acquireDeviceBtn');
    if (btn) { btn.disabled = true; btn.textContent = 'Acquiring...'; }

    try {
        const brainId = await getBrainId();
        const resp = await fetch(`${CONFIG.backendUrl}/api/devices/${deviceId}/acquire`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brain_id: brainId, name: operatorName || 'Eye Test UI' })
        });
        const data = await resp.json();

        if (resp.ok) {
            _deviceAcquired = true;
            if (btn) btn.style.display = 'none';
            document.getElementById('phoropterIdInput').disabled = true;
            console.log('Device acquired:', deviceId, data);
        } else {
            alert(`Could not acquire ${deviceId}: ${data.error || data.reason || resp.status}`);
            if (btn) { btn.disabled = false; btn.textContent = 'Acquire'; }
        }
    } catch (err) {
        alert(`Failed to acquire device: ${err.message}`);
        if (btn) { btn.disabled = false; btn.textContent = 'Acquire'; }
    }
}

async function releaseDevice() {
    const deviceId = CONFIG.phoropterId;
    if (!deviceId) return;

    if (isTestDeviceId(deviceId)) {
        _deviceAcquired = false;
        const select = document.getElementById('phoropterIdInput');
        if (select) select.disabled = false;
        const btn = document.getElementById('acquireDeviceBtn');
        if (btn) {
            btn.style.display = 'none';
            btn.disabled = false;
            btn.textContent = 'Acquire';
        }
        return;
    }

    try {
        const brainId = await getBrainId();
        // Release via backend proxy (avoids CORS) -> proxies to .../devices/{Phoropter-ID}/release
        const base = (CONFIG.backendUrl && CONFIG.backendUrl.length > 0) ? CONFIG.backendUrl : '';
        const url = base ? `${base}/api/devices/${deviceId}/release` : `/api/devices/${deviceId}/release`;
        const resp = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ brain_id: brainId })
        });
        if (resp.ok) {
            console.log('Device released:', deviceId);
            addToHistory('Device released', 'success');
        } else {
            console.warn('Release returned', resp.status, await resp.text());
            addToHistory(`Release failed: ${resp.status}`, 'warning');
        }
    } catch (err) {
        console.warn('Could not release device:', err);
        addToHistory('Release failed: ' + (err.message || 'network error'), 'warning');
    }

    _deviceAcquired = false;
    document.getElementById('phoropterIdInput').disabled = false;

    const btn = document.getElementById('acquireDeviceBtn');
    if (btn) {
        btn.style.display = 'inline-block';
        btn.disabled = false;
        btn.textContent = 'Acquire';
        btn.style.background = '';
    }
}

// Initialize
// ── Session Persistence (survives refresh) ───────────

const SESSION_STORAGE_KEY = 'eyeTestSession';

let _deviceAcquired = false;

function _saveSessionToStorage() {
    if (!sessionState.sessionId) return;
    const data = {
        sessionId: sessionState.sessionId,
        responseCount: sessionState.responseCount,
        storedPower: storedPower,
        currentAppliedPower: currentAppliedPower,
        deviceAcquired: _deviceAcquired,
        deviceId: CONFIG.phoropterId,
        memoryState: memoryState,
    };
    try { sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(data)); }
    catch (e) { console.warn('sessionStorage write failed:', e); }
}

function _clearSessionStorage() {
    try { sessionStorage.removeItem(SESSION_STORAGE_KEY); } catch (_) { }
}

async function _tryRestoreSession() {
    let saved;
    try { saved = JSON.parse(sessionStorage.getItem(SESSION_STORAGE_KEY)); }
    catch (_) { return false; }
    if (!saved || !saved.sessionId) return false;

    try {
        // 1. Verify internet / backend is reachable
        const statusResp = await fetch(`${CONFIG.backendUrl}/api/session/${saved.sessionId}/status`);
        if (!statusResp.ok) {
            console.warn('Backend session gone, starting fresh');
            _clearSessionStorage();
            return false;
        }

        // 2. If device was acquired, verify the lock is still alive via heartbeat
        if (saved.deviceAcquired && saved.deviceId && !isTestDeviceId(saved.deviceId)) {
            const brainId = await getBrainId();
            const hbResp = await fetch(`${CONFIG.backendUrl}/api/devices/${saved.deviceId}/heartbeat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ brain_id: brainId })
            });
            if (hbResp.status !== 200 && hbResp.status !== 202) {
                console.warn(`Heartbeat returned ${hbResp.status}, device lock lost — starting fresh`);
                _clearSessionStorage();
                return false;
            }
        }

        const data = await statusResp.json();

        // Restore JS state
        sessionState.sessionId = saved.sessionId;
        sessionState.responseCount = saved.responseCount || data.total_rows || 0;
        storedPower = saved.storedPower || { ar: null, lenso: null };
        currentAppliedPower = saved.currentAppliedPower || 'none';

        // Restore memory state
        if (saved.memoryState) {
            memoryState = saved.memoryState;
            memoryMode = 'memS';
            _realtimeBeforeRestore = null;
            _updateMemButton();
        }

        // Restore UI
        document.getElementById('welcomeScreen').style.display = 'none';
        document.getElementById('testScreen').style.display = 'block';

        updateSessionInfo(data);
        displayQuestion(data);
        updateStatusIndicator(true);
        updatePowerButtonStates(currentAppliedPower);

        if (storedPower.ar) {
            document.getElementById('applyArBtn').disabled = false;
            document.getElementById('applyArBtn').title = 'Apply AR Power';
        }
        if (storedPower.lenso) {
            document.getElementById('applyLensoBtn').disabled = false;
            document.getElementById('applyLensoBtn').title = 'Apply Lenso Power';
        }

        // Restore device acquisition state
        if (saved.deviceAcquired && saved.deviceId) {
            _deviceAcquired = true;
            const select = document.getElementById('phoropterIdInput');
            if (select) { select.value = saved.deviceId; select.disabled = true; }
            const acqBtn = document.getElementById('acquireDeviceBtn');
            if (acqBtn) acqBtn.style.display = 'none';
        }

        addToHistory('Session restored after refresh', 'info');
        console.log('Session restored:', saved.sessionId);
        return true;
    } catch (err) {
        console.warn('No internet or backend unreachable, starting fresh:', err);
        _clearSessionStorage();
        return false;
    }
}

function toggleSection(sectionId) {
    const section = sectionId === 'ar'
        ? document.getElementById('arPowerSection')
        : sectionId === 'session-status'
            ? document.getElementById('section-session-status')
        : document.getElementById('section-' + sectionId);
    const arrowEl = sectionId === 'history' ? document.getElementById('historyArrow')
        : sectionId === 'commands' ? document.getElementById('commandsArrow')
        : sectionId === 'ar' ? document.getElementById('arArrow')
        : sectionId === 'session-status' ? document.getElementById('sessionStatusArrow')
        : null;
    if (!section || !arrowEl) return;
    section.classList.toggle('collapsed');
    arrowEl.textContent = section.classList.contains('collapsed') ? '▶' : '▼';
}

document.addEventListener('DOMContentLoaded', async () => {
    console.log('Eye Test Engine Frontend Loaded');

    // Start with Test History and Chart Commands collapsed (compact row visible)
    const sectionHistory = document.getElementById('section-history');
    const sectionCommands = document.getElementById('section-commands');
    const sectionStatus = document.getElementById('section-session-status');
    const historyArrow = document.getElementById('historyArrow');
    const commandsArrow = document.getElementById('commandsArrow');
    const statusArrow = document.getElementById('sessionStatusArrow');
    if (sectionHistory) sectionHistory.classList.add('collapsed');
    if (sectionCommands) sectionCommands.classList.add('collapsed');
    if (sectionStatus) sectionStatus.classList.add('collapsed');
    if (historyArrow) historyArrow.textContent = '▶';
    if (commandsArrow) commandsArrow.textContent = '▶';
    if (statusArrow) statusArrow.textContent = '▶';

    // Logs panel: hide tab if access was previously denied on this browser
    const logsTab = document.getElementById('logsTabBtn');
    if (logsTab && isLogsAccessDenied()) logsTab.classList.add('hidden');

    // 1. Initial config from same-origin (Vercel or localhost)
    // This MUST complete before we try to restore or start a session
    await fetchConfig();

    updateStatusIndicator(false);
    updateCustomerStatusPanel();
    populateDirectCommands();
    bindTableInteractions();
    checkOptometristName();

    // 2. Fetch devices from the RESOLVED backendUrl
    await fetchDevices();

    // 3. Try to restore session from the RESOLVED backendUrl
    await _tryRestoreSession();

    // 4. Keep live view visible by default in the right panel
    openScreenshotModal();

    updateArPowerDisplay();
});

// ── Optometrist Name Cache (Dynamic TTL) ─────────────

const OPTOMETRIST_CACHE_KEY = 'optometristName';
const OPTOMETRIST_TS_KEY = 'optometristNameTimestamp';
const OPTOMETRIST_TTL_KEY = 'optometristTTL'; // Store chosen TTL in hours

function checkOptometristName() {
    const cached = localStorage.getItem(OPTOMETRIST_CACHE_KEY);
    const ts = parseInt(localStorage.getItem(OPTOMETRIST_TS_KEY) || '0', 10);
    const ttlHours = parseInt(localStorage.getItem(OPTOMETRIST_TTL_KEY) || '0', 10);
    
    // If TTL is 0, it means "Ask every time" - but we still need to allow it for the current session
    // Actually, the user says "ask... everytime", so if ttl is 0, we only keep it for this instance of the script?
    // Let's use the persistence logic: if ttl is 0, it's always expired for the next 'check'.
    
    const ttlMs = ttlHours * 60 * 60 * 1000;
    const expired = ttlHours === 0 || (Date.now() - ts) > ttlMs;

    if (cached && !expired) {
        operatorName = cached;
        return true;
    }

    // Default: clear and show modal
    operatorName = '';
    const modal = document.getElementById('optometristModal');
    if (modal) {
        modal.classList.add('active');
        const input = document.getElementById('optometristNameInput');
        if (input) setTimeout(() => input.focus(), 200);
    }
    return false;
}

function saveOptometristName() {
    const input = document.getElementById('optometristNameInput');
    const name = (input ? input.value.trim() : '');
    const persistenceSelect = document.getElementById('optometristPersistenceSelect');
    const ttlHours = persistenceSelect ? parseInt(persistenceSelect.value, 10) : 0;

    if (!name) {
        input.style.borderColor = '#f44336';
        input.placeholder = 'Name is required';
        return;
    }
    
    operatorName = name;
    localStorage.setItem(OPTOMETRIST_CACHE_KEY, name);
    localStorage.setItem(OPTOMETRIST_TS_KEY, String(Date.now()));
    localStorage.setItem(OPTOMETRIST_TTL_KEY, String(ttlHours));

    const modal = document.getElementById('optometristModal');
    if (modal) modal.classList.remove('active');
}

// ── Manual Refraction Adjustments ─────────────────────

let manualControlsLocked = false;
let _manualAutoUnlockTimer = null;
let typeModeActive = false;
let _typeModeEditing = false;
let _phoropterBusy = false;

function _setPhoropterBusy(busy) {
    _phoropterBusy = busy;
    // When busy from intents, visually lock manual controls
    const cells = document.querySelectorAll('.rt-val');
    if (busy) {
        cells.forEach(c => c.classList.add('locked'));
    } else if (!manualControlsLocked) {
        cells.forEach(c => c.classList.remove('locked'));
    }
}

function _setIntentsDisabled(disabled) {
    document.querySelectorAll('.intent-button').forEach(btn => {
        btn.disabled = disabled;
        btn.style.opacity = disabled ? '0.45' : '';
    });
}

function _setManualLock(locked) {
    manualControlsLocked = locked;
    const btn = document.getElementById('manualLockBtn');
    const cells = document.querySelectorAll('.rt-val');
    if (locked) {
        if (btn) { btn.textContent = '🔒'; btn.classList.add('locked'); }
        cells.forEach(c => c.classList.add('locked'));
    } else {
        if (btn) { btn.textContent = '🔓'; btn.classList.remove('locked'); }
        cells.forEach(c => c.classList.remove('locked'));
    }
}

function toggleManualLock() {
    if (_manualAutoUnlockTimer) {
        clearTimeout(_manualAutoUnlockTimer);
        _manualAutoUnlockTimer = null;
    }
    if (!manualControlsLocked && typeModeActive) _exitTypeMode();
    _setManualLock(!manualControlsLocked);
}

// ── Type Mode ────────────────────────────────────────

function toggleTypeMode() {
    if (typeModeActive) {
        _exitTypeMode();
    } else {
        _enterTypeMode();
    }
}

function _enterTypeMode() {
    typeModeActive = true;
    if (manualControlsLocked) _setManualLock(false);

    const btn = document.getElementById('typeModeBtn');
    if (btn) btn.classList.add('active');

    document.querySelectorAll('.rt-val[data-param]').forEach(el => {
        el.classList.add('type-mode');
        el.setAttribute('data-tip', 'Click to type value');
    });
}

function _exitTypeMode() {
    _commitActiveInput(false);
    typeModeActive = false;
    _typeModeEditing = false;

    const btn = document.getElementById('typeModeBtn');
    if (btn) btn.classList.remove('active');

    document.querySelectorAll('.rt-val[data-param]').forEach(el => {
        el.classList.remove('type-mode');
        el.setAttribute('data-tip', 'Right-click = +  |  Left-click = −');
    });
}

function _getTypableFields() {
    return Array.from(document.querySelectorAll('.rt-val[data-param]'));
}

function _openInputInCell(cell) {
    if (!cell || cell.querySelector('.rt-type-input')) return;

    _typeModeEditing = true;
    const originalText = cell.textContent.trim();

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'rt-type-input';
    input.value = originalText.replace(/[+°]/g, '');
    input.dataset.originalValue = originalText;

    if (cell.dataset.param === 'axis') {
        input.inputMode = 'numeric';
        input.pattern = '[0-9]*';
    } else {
        input.inputMode = 'decimal';
    }

    input.addEventListener('keydown', (e) => _handleTypeInputKey(e, cell, input));
    input.addEventListener('blur', () => {
        setTimeout(() => {
            if (cell.contains(input)) {
                _restoreCell(cell, input.dataset.originalValue);
                _typeModeEditing = false;
            }
        }, 50);
    });

    cell.textContent = '';
    cell.appendChild(input);
    input.focus();
    input.select();
}

function _restoreCell(cell, text) {
    const input = cell.querySelector('.rt-type-input');
    if (input) input.remove();
    cell.textContent = text;
    _typeModeEditing = false;
}

function _handleTypeInputKey(e, cell, input) {
    if (e.key === 'Enter') {
        e.preventDefault();
        _commitActiveInput(true);
    } else if (e.key === 'Escape') {
        e.preventDefault();
        _restoreCell(cell, input.dataset.originalValue);
    } else if (e.key === 'Tab') {
        e.preventDefault();
        const parsed = _parseTypedValue(cell.dataset.param, input.value);
        if (parsed !== null) {
            _restoreCell(cell, _formatCellValue(cell.dataset.param, parsed));
        } else {
            _restoreCell(cell, input.dataset.originalValue);
        }
        const fields = _getTypableFields();
        const idx = fields.indexOf(cell);
        const next = fields[(idx + 1) % fields.length];
        _openInputInCell(next);
    }
}

function _parseTypedValue(param, raw) {
    const s = raw.replace(/[+°\s]/g, '').trim();
    if (s === '') return null;
    const n = parseFloat(s);
    if (isNaN(n)) return null;
    if (param === 'axis') {
        const rounded = Math.round(n / 5) * 5;
        if (rounded <= 0 || rounded > 180) return 180;
        return rounded;
    }
    if (param === 'cyl') {
        if (n > 0) return 0;
        return Math.round(n * 4) / 4;
    }
    if (param === 'add') {
        if (n < 0) return 0;
        return Math.round(n * 4) / 4;
    }
    return Math.round(n * 4) / 4;
}

function _normalizeAxisDisplay(val) {
    const n = Math.round(parseFloat(val) || 0);
    return (n === 0 || n === 180) ? '180' : String(n);
}

function _formatCellValue(param, val) {
    if (param === 'axis') return _normalizeAxisDisplay(val);
    if (param === 'add') return '+' + val.toFixed(2);
    return (val >= 0 ? '+' : '') + val.toFixed(2);
}

async function _commitActiveInput(submit) {
    if (!submit) {
        document.querySelectorAll('.rt-type-input').forEach(input => {
            const cell = input.parentElement;
            if (cell) _restoreCell(cell, input.dataset.originalValue);
        });
        _typeModeEditing = false;
        return;
    }

    const fields = _getTypableFields();
    const power = {
        right: { sph: 0, cyl: 0, axis: 180, add: 0 },
        left: { sph: 0, cyl: 0, axis: 180, add: 0 }
    };
    const oldPower = sessionState.lastResponse?.power || { right: { sph: 0, cyl: 0, axis: 180, add: 0 }, left: { sph: 0, cyl: 0, axis: 180, add: 0 } };
    let anyChanged = false;

    for (const cell of fields) {
        const eye = cell.dataset.eye === 'R' ? 'right' : 'left';
        const param = cell.dataset.param;
        const input = cell.querySelector('.rt-type-input');
        const rawText = input ? input.value : cell.textContent;
        const parsed = _parseTypedValue(param, rawText);

        if (parsed !== null) {
            power[eye][param] = parsed;
        } else {
            power[eye][param] = oldPower[eye]?.[param] || (param === 'axis' ? 180 : 0);
        }

        const orig = oldPower[eye]?.[param] || (param === 'axis' ? 180 : 0);
        if (Math.abs(power[eye][param] - orig) > 0.001) anyChanged = true;

        _restoreCell(cell, _formatCellValue(param, power[eye][param]));
    }

    _typeModeEditing = false;

    if (!anyChanged || !sessionState.sessionId) return;

    _setPhoropterBusy(true);
    _setIntentsDisabled(true);
    try {
        showLoading(true);
        const currentOccluder = document.getElementById('occluderState').textContent || 'BINO';

        if (sessionState.sessionId) {
            try {
                await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/sync-power`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(power)
                });
            } catch (syncErr) {
                console.warn('Failed to sync typed power to backend:', syncErr);
            }
        }

        await syncBrokerState(oldPower, currentOccluder);
        await setPower(power, currentOccluder);

        if (!sessionState.lastResponse) sessionState.lastResponse = {};
        sessionState.lastResponse.power = power;
        updateSessionInfo({ ...sessionState.lastResponse, power });

        sessionState.responseCount++;
        document.getElementById('responseCount').textContent = sessionState.responseCount;
        addToHistory('Typed power applied', 'adjust');
        _saveSessionToStorage();
        refreshScreenshotIfModalOpen();
    } catch (error) {
        console.error('Error applying typed power:', error);
        alert('Failed to apply typed power.');
    } finally {
        showLoading(false);
        _setPhoropterBusy(false);
        _setIntentsDisabled(false);
    }
}

function bindTableInteractions() {
    const table = document.getElementById('refractionTable');
    if (table) {
        table.oncontextmenu = function (e) {
            e.preventDefault();
            e.stopPropagation();
            return false;
        };
        table.querySelectorAll('.rt-val').forEach(el => {
            el.setAttribute('data-tip', 'R = +  |  L = −');
            el.addEventListener('mousedown', (event) => handleTableMousedown(event, el));
        });
    }
}

async function handleTableMousedown(event, el) {
    if (_phoropterBusy) return;
    if (!sessionState.sessionId) {
        alert('Please start a test session first.');
        return;
    }

    if (typeModeActive) {
        event.preventDefault();
        event.stopPropagation();
        if (el.dataset.param) _openInputInCell(el);
        return;
    }

    if (manualControlsLocked) return;

    // button 0 = left, button 2 = right
    const action = (event.button === 0) ? 'subtract' : (event.button === 2 ? 'add' : null);
    if (!action) return;

    event.preventDefault();
    event.stopPropagation();

    const param = el.dataset.param;
    const eye = el.dataset.eye;

    let delta = 0.25;
    if (param === 'axis') delta = 5;

    if (action === 'subtract') delta = -delta;

    _setManualLock(true);
    if (_manualAutoUnlockTimer) clearTimeout(_manualAutoUnlockTimer);
    _manualAutoUnlockTimer = setTimeout(() => {
        _manualAutoUnlockTimer = null;
        _setManualLock(false);
    }, 1000);

    await applyManualPowerChange(eye, param, delta);
}

async function applyManualPowerChange(eye, param, delta) {
    if (!sessionState.lastResponse || !sessionState.lastResponse.power) return;
    _setPhoropterBusy(true);
    _setIntentsDisabled(true);

    const p = sessionState.lastResponse.power;
    const eyeKey = eye === 'R' ? 'right' : 'left';

    if (!p[eyeKey]) {
        p[eyeKey] = { sph: 0, cyl: 0, axis: 180 };
    }

    // Snapshot the pre-adjustment state for broker sync
    const prevPower = {
        right: { sph: p.right?.sph || 0, cyl: p.right?.cyl || 0, axis: p.right?.axis || 180 },
        left: { sph: p.left?.sph || 0, cyl: p.left?.cyl || 0, axis: p.left?.axis || 180 }
    };

    let current = parseFloat(p[eyeKey][param]) || 0;
    let newVal = current + delta;

    if (param === 'axis') {
        // Axis 0° = 180°; wrap to 1–180. When at 10 and decrease by 10 → 180, not 0.
        newVal = Math.round(newVal);
        newVal = ((newVal - 1) % 180 + 180) % 180 + 1;
        if (newVal === 0) newVal = 180;
    }

    p[eyeKey][param] = newVal;

    // Update UI optimistically
    updateSessionInfo(sessionState.lastResponse);

    try {
        showLoading(true);
        const reqPower = {
            right: {
                sph: p.right.sph || 0,
                cyl: p.right.cyl || 0,
                axis: p.right.axis || 180
            },
            left: {
                sph: p.left.sph || 0,
                cyl: p.left.cyl || 0,
                axis: p.left.axis || 180
            }
        };

        const currentOccluder = document.getElementById('occluderState').textContent || 'BINO';

        // Sync the manually adjusted power with the backend session state
        if (sessionState.sessionId) {
            try {
                await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/sync-power`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(reqPower)
                });
            } catch (syncErr) {
                console.warn('Failed to sync manual power to backend:', syncErr);
            }
        }

        // Tell the broker what the phoropter's actual state is before sending
        // the new target. JCC increase/decrease commands move the phoropter
        // without updating the broker's internal tracker, so without this the
        // broker would calculate clicks from a stale baseline.
        await syncBrokerState(prevPower, currentOccluder);
        await setPower(reqPower, currentOccluder);

        sessionState.responseCount++;
        document.getElementById('responseCount').textContent = sessionState.responseCount;
        addToHistory(`Manual Adjust: ${param.toUpperCase()} ${delta > 0 ? '+' : ''}${delta} [${eye}]`, 'adjust');
        _saveSessionToStorage();
        refreshScreenshotIfModalOpen();
    } catch (error) {
        console.error('Error applying manual power:', error);
        alert('Failed to push manual power to phoropter. Try again.');
    } finally {
        showLoading(false);
        _setPhoropterBusy(false);
        _setIntentsDisabled(false);
    }
}

async function syncBrokerState(power, occluder) {
    if (isTestDeviceId()) return;

    const right = power.right || { sph: 0, cyl: 0, axis: 180 };
    const left = power.left || { sph: 0, cyl: 0, axis: 180 };

    let auxLens = "OFF";
    if (occluder === "Left_Occluded") auxLens = "AuxLensL";
    else if (occluder === "Right_Occluded") auxLens = "AuxLensR";

    const rAxis = (right.axis === 0) ? 180 : (right.axis || 180);
    const lAxis = (left.axis === 0) ? 180 : (left.axis || 180);
    const rightEye = { sph: right.sph, cyl: right.cyl, axis: rAxis };
    const leftEye = { sph: left.sph, cyl: left.cyl, axis: lAxis };
    if (right.add !== undefined && right.add !== 0) rightEye.add = right.add;
    if (left.add !== undefined && left.add !== 0) leftEye.add = left.add;

    const payload = {
        right_eye: rightEye,
        left_eye: leftEye,
        aux_lens: auxLens
    };

    try {
        await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/sync-state`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } catch (err) {
        console.warn('Failed to sync broker state:', err);
    }
}

// ── Modals & Flow ─────────────────────────────────────

function openArPowerModal() {
    const modal = document.getElementById('arPowerModal');
    if (modal) {
        modal.classList.add('active');
    }
}

function closeArPowerModal() {
    const modal = document.getElementById('arPowerModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

function openLensoPowerModal() {
    const modal = document.getElementById('lensoPowerModal');
    if (modal) {
        modal.classList.add('active');
    }
}

function _showStartupModalWithTimeout(openModal, closeModal, modalId, timeoutMs) {
    return new Promise((resolve) => {
        const modal = document.getElementById(modalId);
        if (!modal) {
            resolve(false);
            return;
        }

        let settled = false;
        const finish = (interacted) => {
            if (settled) return;
            settled = true;
            clearTimeout(timer);
            modal.removeEventListener('click', onInteract, true);
            modal.removeEventListener('input', onInteract, true);
            modal.removeEventListener('focusin', onInteract, true);
            resolve(interacted);
        };

        const onInteract = (event) => {
            if (!modal.classList.contains('active')) return;
            if (!event || !event.target) return;
            const target = event.target;
            if (target.closest('input, select, textarea, button, label')) {
                finish(true);
            }
        };

        modal.addEventListener('click', onInteract, true);
        modal.addEventListener('input', onInteract, true);
        modal.addEventListener('focusin', onInteract, true);
        openModal();

        const timer = setTimeout(() => {
            if (!settled) {
                closeModal();
                finish(false);
            }
        }, timeoutMs);
    });
}

async function runStartupPowerModalFlow() {
    const arInteracted = await _showStartupModalWithTimeout(
        openArPowerModal,
        closeArPowerModal,
        'arPowerModal',
        5000
    );
    if (arInteracted) return;
    await _showStartupModalWithTimeout(
        openLensoPowerModal,
        closeLensoPowerModal,
        'lensoPowerModal',
        5000
    );
}

function updateCustomerStatusPanel() {
    const nameEl = document.getElementById('customerNameStatus');
    const ageEl = document.getElementById('customerAgeStatus');
    const genderEl = document.getElementById('customerGenderStatus');
    if (nameEl) nameEl.textContent = customerName || '-';
    if (ageEl) ageEl.textContent = customerAge || '-';
    if (genderEl) genderEl.textContent = customerGender || '-';
}

function _setFieldValidityStyles(el, valid) {
    if (!el) return;
    el.style.borderColor = valid ? '#d7dcf5' : '#f44336';
}

function validateCustomerDetails() {
    const customerInput = document.getElementById('customerNameInput');
    const customerAgeInput = document.getElementById('customerAgeInput');
    const customerGenderInput = document.getElementById('customerGenderInput');

    const name = customerInput ? customerInput.value.trim() : '';
    const ageRaw = customerAgeInput ? customerAgeInput.value.trim() : '';
    const gender = customerGenderInput ? customerGenderInput.value.trim() : '';
    const nameRegex = /^[A-Za-z][A-Za-z\s.'-]{1,59}$/;
    const ageNum = Number(ageRaw);
    const ageValid = /^\d{1,3}$/.test(ageRaw) && Number.isInteger(ageNum) && ageNum >= 1 && ageNum <= 120;
    const genderAllowed = ['Male', 'Female', 'Other', 'Prefer not to say'];
    const genderValid = genderAllowed.includes(gender);
    const nameValid = nameRegex.test(name);

    _setFieldValidityStyles(customerInput, nameValid);
    _setFieldValidityStyles(customerAgeInput, ageValid);
    _setFieldValidityStyles(customerGenderInput, genderValid);

    if (!nameValid || !ageValid || !genderValid) {
        const errors = [];
        if (!nameValid) errors.push('Customer name must be 2-60 characters and contain only letters, spaces, apostrophe, dot, or hyphen.');
        if (!ageValid) errors.push('Age must be an integer between 1 and 120.');
        if (!genderValid) errors.push('Please select a valid gender option.');
        alert(errors.join('\n'));
        return null;
    }

    return { name, age: String(ageNum), gender };
}

function closeLensoPowerModal() {
    const modal = document.getElementById('lensoPowerModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// ── Live screenshot modal (draggable, zoomable, resizable; refresh when open; backdrop does not block clicks) ───
let _screenshotDragInited = false;
let _screenshotZoom = 1;
const SCREENSHOT_ZOOM_MIN = 0.25;
const SCREENSHOT_ZOOM_MAX = 3;
const SCREENSHOT_ZOOM_STEP = 0.25;
const SCREENSHOT_HISTORY_MAX = 50;
let _screenshotHistory = [];   // { base64, ts }
let _screenshotHistoryIndex = -1;

function isScreenshotModalOpen() {
    const backdrop = document.getElementById('screenshotModalBackdrop');
    return backdrop && backdrop.classList.contains('active');
}

function isScreenshotDocked() {
    const backdrop = document.getElementById('screenshotModalBackdrop');
    if (!backdrop) return false;
    return !!backdrop.closest('.info-panel');
}

async function fetchScreenshot() {
    if (isTestDeviceId()) return null;

    try {
        const brainId = await getBrainId();
        const resp = await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/screenshot`, {
            method: 'POST',
            headers: { 'x-brain-id': brainId }
        });
        if (!resp.ok) return null;
        let rawText = await resp.text();
        let base64 = rawText.trim();
        if (base64.startsWith('"') && base64.endsWith('"')) base64 = base64.slice(1, -1);
        if (base64.startsWith('{')) {
            try {
                const parsed = JSON.parse(rawText);
                base64 = parsed.image || parsed.screenshot || parsed.data || rawText;
            } catch (_) {}
        }
        base64 = base64.replace(/\s+/g, '');
        return base64 && base64.length > 50 ? base64 : null;
    } catch (e) {
        console.warn('Screenshot fetch failed:', e);
        return null;
    }
}

function formatScreenshotTimestamp(ts) {
    if (ts == null) return '';
    const d = new Date(ts);
    return d.toLocaleString(undefined, {
        dateStyle: 'short',
        timeStyle: 'medium',
        hour12: false
    });
}

function updateScreenshotTimestamp() {
    const el = document.getElementById('screenshotTimestamp');
    if (!el) return;
    if (_screenshotHistoryIndex < 0 || _screenshotHistoryIndex >= _screenshotHistory.length) {
        el.textContent = '';
        el.style.display = 'none';
        return;
    }
    const entry = _screenshotHistory[_screenshotHistoryIndex];
    el.textContent = formatScreenshotTimestamp(entry.ts);
    el.style.display = 'block';
}

function setScreenshotImage(base64) {
    const img = document.getElementById('screenshotImage');
    const wrap = document.getElementById('screenshotImgWrap');
    const loading = document.getElementById('screenshotLoading');
    const err = document.getElementById('screenshotError');
    if (!img || !loading || !err) return;
    if (base64) {
        _screenshotHistory.push({ base64, ts: Date.now() });
        if (_screenshotHistory.length > SCREENSHOT_HISTORY_MAX) {
            _screenshotHistory = _screenshotHistory.slice(-SCREENSHOT_HISTORY_MAX);
        }
        _screenshotHistoryIndex = _screenshotHistory.length - 1;
        img.src = 'data:image/jpeg;base64,' + base64;
        img.classList.add('loaded');
        loading.style.display = 'none';
        err.style.display = 'none';
        if (wrap) wrap.style.transform = `scale(${_screenshotZoom})`;
        updateScreenshotTimestamp();
        updateScreenshotNavUI();
    } else {
        img.removeAttribute('src');
        img.classList.remove('loaded');
        loading.style.display = 'none';
        err.style.display = 'block';
        updateScreenshotTimestamp();
        updateScreenshotNavUI();
    }
}

function showScreenshotAtIndex(index) {
    if (index < 0 || index >= _screenshotHistory.length) return;
    _screenshotHistoryIndex = index;
    const img = document.getElementById('screenshotImage');
    const wrap = document.getElementById('screenshotImgWrap');
    const loading = document.getElementById('screenshotLoading');
    const err = document.getElementById('screenshotError');
    if (!img) return;
    const entry = _screenshotHistory[index];
    img.src = 'data:image/jpeg;base64,' + entry.base64;
    img.classList.add('loaded');
    if (loading) loading.style.display = 'none';
    if (err) err.style.display = 'none';
    if (wrap) wrap.style.transform = `scale(${_screenshotZoom})`;
    updateScreenshotTimestamp();
    updateScreenshotNavUI();
}

function updateScreenshotNavUI() {
    const prevBtn = document.getElementById('screenshotPrevBtn');
    const nextBtn = document.getElementById('screenshotNextBtn');
    const latestBtn = document.getElementById('screenshotLatestBtn');
    const label = document.getElementById('screenshotHistoryLabel');
    const n = _screenshotHistory.length;
    if (prevBtn) prevBtn.disabled = n === 0 || _screenshotHistoryIndex <= 0;
    if (nextBtn) nextBtn.disabled = n === 0 || _screenshotHistoryIndex >= n - 1;
    if (latestBtn) latestBtn.disabled = n === 0 || _screenshotHistoryIndex === n - 1;
    if (label) {
        if (n === 0) label.textContent = '—';
        else label.textContent = `${_screenshotHistoryIndex + 1} / ${n}`;
    }
}

function screenshotShowPrevious() {
    if (_screenshotHistoryIndex > 0) showScreenshotAtIndex(_screenshotHistoryIndex - 1);
}

function screenshotShowNext() {
    if (_screenshotHistoryIndex < _screenshotHistory.length - 1) showScreenshotAtIndex(_screenshotHistoryIndex + 1);
}

function screenshotShowLatest() {
    if (_screenshotHistory.length > 0) showScreenshotAtIndex(_screenshotHistory.length - 1);
}

function applyScreenshotZoom() {
    const wrap = document.getElementById('screenshotImgWrap');
    const label = document.getElementById('screenshotZoomLabel');
    if (wrap) wrap.style.transform = `scale(${_screenshotZoom})`;
    if (label) label.textContent = Math.round(_screenshotZoom * 100) + '%';
}

function refreshScreenshotIfModalOpen() {
    if (!isScreenshotModalOpen()) return;
    (async () => {
        const loading = document.getElementById('screenshotLoading');
        const err = document.getElementById('screenshotError');
        if (loading) loading.style.display = 'block';
        if (err) err.style.display = 'none';
        const base64 = await fetchScreenshot();
        if (isScreenshotModalOpen()) setScreenshotImage(base64);
    })();
}

function openScreenshotModal() {
    const backdrop = document.getElementById('screenshotModalBackdrop');
    const modal = document.getElementById('screenshotModal');
    if (!backdrop || !modal) return;
    if (!_screenshotDragInited) {
        if (!isScreenshotDocked()) {
            initScreenshotModalDrag();
        }
        initScreenshotModalZoom();
        initScreenshotModalResize();
        _screenshotDragInited = true;
    }
    if (isScreenshotDocked()) {
        modal.style.left = '';
        modal.style.top = '';
        modal.style.transform = '';
    }
    _screenshotZoom = 1;
    applyScreenshotZoom();
    backdrop.classList.add('active');
    refreshScreenshotIfModalOpen();
}

function closeScreenshotModal() {
    const backdrop = document.getElementById('screenshotModalBackdrop');
    if (backdrop) backdrop.classList.remove('active');
}

function toggleScreenshotModal() {
    if (isScreenshotModalOpen()) closeScreenshotModal();
    else openScreenshotModal();
}

function initScreenshotModalDrag() {
    const modal = document.getElementById('screenshotModal');
    const header = document.getElementById('screenshotModalHeader');
    if (!modal || !header) return;
    let dragging = false;
    let startX, startY, startLeft, startTop;

    function onPointerMove(e) {
        if (!dragging) return;
        const dx = e.clientX - startX;
        const dy = e.clientY - startY;
        modal.style.left = (startLeft + dx) + 'px';
        modal.style.top = (startTop + dy) + 'px';
        e.preventDefault();
    }
    function onPointerUp(e) {
        if (!dragging) return;
        dragging = false;
        try { header.releasePointerCapture(e.pointerId); } catch (_) {}
        document.removeEventListener('pointermove', onPointerMove, true);
        document.removeEventListener('pointerup', onPointerUp, true);
        document.removeEventListener('pointercancel', onPointerUp, true);
        e.preventDefault();
    }

    header.addEventListener('pointerdown', (e) => {
        if (e.button !== 0) return;
        if (e.target.closest('button')) return;
        dragging = true;
        const rect = modal.getBoundingClientRect();
        startLeft = rect.left;
        startTop = rect.top;
        startX = e.clientX;
        startY = e.clientY;
        modal.style.left = startLeft + 'px';
        modal.style.top = startTop + 'px';
        modal.style.transform = 'none';
        try { header.setPointerCapture(e.pointerId); } catch (_) {}
        document.addEventListener('pointermove', onPointerMove, true);
        document.addEventListener('pointerup', onPointerUp, true);
        document.addEventListener('pointercancel', onPointerUp, true);
        e.preventDefault();
    });
}

function initScreenshotModalZoom() {
    const wrap = document.getElementById('screenshotImgWrap');
    const img = document.getElementById('screenshotImage');
    const zoomIn = document.getElementById('screenshotZoomIn');
    const zoomOut = document.getElementById('screenshotZoomOut');
    if (!wrap || !zoomIn || !zoomOut) return;

    function setZoom(delta) {
        _screenshotZoom = Math.max(SCREENSHOT_ZOOM_MIN, Math.min(SCREENSHOT_ZOOM_MAX, _screenshotZoom + delta));
        applyScreenshotZoom();
    }
    zoomIn.addEventListener('click', (e) => { e.preventDefault(); setZoom(SCREENSHOT_ZOOM_STEP); });
    zoomOut.addEventListener('click', (e) => { e.preventDefault(); setZoom(-SCREENSHOT_ZOOM_STEP); });
    if (img) {
        img.addEventListener('wheel', (e) => {
            if (!isScreenshotModalOpen()) return;
            e.preventDefault();
            setZoom(e.deltaY > 0 ? -0.1 : 0.1);
        }, { passive: false });
    }
}

function initScreenshotModalResize() {
    const modal = document.getElementById('screenshotModal');
    const handle = document.getElementById('screenshotResizeHandle');
    if (!modal || !handle) return;
    let resizing = false;
    let startX, startY, startW, startH;

    handle.addEventListener('mousedown', (e) => {
        if (e.button !== 0) return;
        e.preventDefault();
        resizing = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = modal.getBoundingClientRect();
        startW = rect.width;
        startH = rect.height;
    });
    const onMove = (e) => {
        if (!resizing) return;
        const dw = e.clientX - startX;
        const dh = e.clientY - startY;
        startX = e.clientX;
        startY = e.clientY;
        const w = Math.max(320, startW + dw);
        const h = Math.max(200, startH + dh);
        modal.style.width = w + 'px';
        modal.style.height = h + 'px';
        modal.style.maxWidth = '95vw';
        modal.style.maxHeight = '90vh';
        startW = w;
        startH = h;
    };
    const onUp = () => {
        resizing = false;
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
    };
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
}

function parseArValue(value, fallback) {
    if (value === '' || value === null || value === undefined) {
        return fallback;
    }
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}

function formatPowerVal(v) {
    if (v == null || !Number.isFinite(v)) return '—';
    return (v >= 0 ? '+' : '') + v.toFixed(2);
}
function formatAxisVal(v) {
    if (v == null || !Number.isFinite(v)) return '—';
    return String(Math.round(v));
}

function updateArPowerDisplay() {
    const section = document.getElementById('arPowerSection');
    if (!section) return;
    const ar = storedPower.ar;
    if (!ar || !ar.right || !ar.left) {
        section.style.display = 'none';
        return;
    }
    const r = ar.right;
    const l = ar.left;
    const set = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
    };
    set('arPowerRSph', formatPowerVal(r.sph));
    set('arPowerRCyl', formatPowerVal(r.cyl));
    set('arPowerRAxis', formatAxisVal(r.axis));
    set('arPowerLSph', formatPowerVal(l.sph));
    set('arPowerLCyl', formatPowerVal(l.cyl));
    set('arPowerLAxis', formatAxisVal(l.axis));
    section.style.display = 'block';
}

function saveArPower() {
    const rightSph = parseArValue(document.getElementById('arRightSph').value, null);
    const rightCyl = parseArValue(document.getElementById('arRightCyl').value, null);
    const rightAxis = parseArValue(document.getElementById('arRightAxis').value, null);
    const leftSph = parseArValue(document.getElementById('arLeftSph').value, null);
    const leftCyl = parseArValue(document.getElementById('arLeftCyl').value, null);
    const leftAxis = parseArValue(document.getElementById('arLeftAxis').value, null);

    // Check if all values are provided for both eyes
    const rightComplete = rightSph !== null && rightCyl !== null && rightAxis !== null;
    const leftComplete = leftSph !== null && leftCyl !== null && leftAxis !== null;

    if (!rightComplete || !leftComplete) {
        alert('Please enter complete power values for both eyes (SPH, CYL, AXIS).');
        return;
    }

    // Store AR power
    storedPower.ar = {
        right: { sph: rightSph, cyl: rightCyl, axis: rightAxis },
        left: { sph: leftSph, cyl: leftCyl, axis: leftAxis }
    };

    // Enable AR button and show AR section above Current Power
    document.getElementById('applyArBtn').disabled = false;
    document.getElementById('applyArBtn').title = 'Apply AR Power';
    updateArPowerDisplay();

    addToHistory('AR power values saved', 'info');
    closeArPowerModal();
}

function saveLensoPower() {
    const rightSph = parseArValue(document.getElementById('lensoRightSph').value, null);
    const rightCyl = parseArValue(document.getElementById('lensoRightCyl').value, null);
    const rightAxis = parseArValue(document.getElementById('lensoRightAxis').value, null);
    const leftSph = parseArValue(document.getElementById('lensoLeftSph').value, null);
    const leftCyl = parseArValue(document.getElementById('lensoLeftCyl').value, null);
    const leftAxis = parseArValue(document.getElementById('lensoLeftAxis').value, null);

    // Check if all values are provided for both eyes
    const rightComplete = rightSph !== null && rightCyl !== null && rightAxis !== null;
    const leftComplete = leftSph !== null && leftCyl !== null && leftAxis !== null;

    if (!rightComplete || !leftComplete) {
        alert('Please enter complete power values for both eyes (SPH, CYL, AXIS).');
        return;
    }

    // Store Lenso power
    storedPower.lenso = {
        right: { sph: rightSph, cyl: rightCyl, axis: rightAxis },
        left: { sph: leftSph, cyl: leftCyl, axis: leftAxis }
    };

    // Enable Lenso button
    document.getElementById('applyLensoBtn').disabled = false;
    document.getElementById('applyLensoBtn').title = 'Apply Lenso Power';

    addToHistory('Lenso power values saved', 'info');
    closeLensoPowerModal();
}

function updateLocalPhoropterState(partial) {
    const base = sessionState.lastResponse || {};
    sessionState.lastResponse = {
        ...base,
        ...partial,
        power: partial.power || base.power,
        occluder: partial.occluder !== undefined ? partial.occluder : base.occluder,
        chart: partial.chart !== undefined ? partial.chart : base.chart,
        phase: partial.phase !== undefined ? partial.phase : base.phase
    };
}

function _formatPowerTooltip(label, power) {
    if (!power) return `${label}: none`;
    const r = power.right || { sph: 0, cyl: 0, axis: 180 };
    const l = power.left || { sph: 0, cyl: 0, axis: 180 };
    return [
        `${label}:`,
        `  R: ${r.sph.toFixed(2)} / ${r.cyl.toFixed(2)} / ${r.axis.toFixed(0)}°`,
        `  L: ${l.sph.toFixed(2)} / ${l.cyl.toFixed(2)} / ${l.axis.toFixed(0)}°`
    ].join('\n');
}

function _updateMemButton() {
    const btn = document.getElementById('memBtn');
    if (!btn) return;

    if (memoryMode === 'mem') {
        btn.textContent = 'Mem';
        btn.title = 'Memory';
    } else if (memoryMode === 'memS') {
        btn.textContent = 'MemS';
        btn.title = _formatPowerTooltip('Stored', memoryState?.power)
            + '\n\nClick to restore these values to phoropter';
    } else if (memoryMode === 'memR') {
        btn.textContent = 'MemR';
        btn.title = _formatPowerTooltip('Realtime (before restore)', _realtimeBeforeRestore)
            + '\n\nClick to switch back to realtime values';
    }
}

async function handleMemClick() {
    if (_phoropterBusy) return;
    if (!sessionState.sessionId) {
        alert('Please start a test session first.');
        return;
    }

    if (memoryMode === 'mem') {
        _memStore();
    } else if (memoryMode === 'memS') {
        await _memRestore();
    } else if (memoryMode === 'memR') {
        await _memSwapBack();
    }
}

function _memStore() {
    const currentState = sessionState.lastResponse;
    if (!currentState || !currentState.power) {
        alert('Current phoropter state is not available yet.');
        return;
    }

    memoryState = {
        power: JSON.parse(JSON.stringify(currentState.power))
    };

    memoryMode = 'memS';
    _updateMemButton();
    _saveSessionToStorage();
    addToHistory('Memory stored', 'info');
}

async function _memRestore() {
    if (!memoryState || !memoryState.power) return;

    // Save current realtime values before overwriting
    const currentPower = sessionState.lastResponse?.power;
    _realtimeBeforeRestore = currentPower
        ? JSON.parse(JSON.stringify(currentPower))
        : null;

    _setPhoropterBusy(true);
    _setIntentsDisabled(true);
    try {
        showLoading(true);
        const currentOccluder = document.getElementById('occluderState').textContent || 'BINO';

        if (currentPower) {
            await syncBrokerState({ right: currentPower.right, left: currentPower.left }, currentOccluder);
        }
        await setPower(memoryState.power, currentOccluder);

        if (sessionState.sessionId) {
            try {
                await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/sync-power`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(memoryState.power)
                });
            } catch (e) { console.warn('sync-power failed:', e); }
        }

        if (!sessionState.lastResponse) sessionState.lastResponse = {};
        sessionState.lastResponse.power = JSON.parse(JSON.stringify(memoryState.power));
        updateSessionInfo(sessionState.lastResponse);

        memoryMode = 'memR';
        _updateMemButton();
        addToHistory('Phoropter loaded with memory state', 'success');
    } catch (error) {
        console.error('Error restoring memory state:', error);
        alert('Failed to restore memory state.');
    } finally {
        showLoading(false);
        _setPhoropterBusy(false);
        _setIntentsDisabled(false);
        refreshScreenshotIfModalOpen();
    }
}

async function _memSwapBack() {
    if (!_realtimeBeforeRestore) return;

    _setPhoropterBusy(true);
    _setIntentsDisabled(true);
    try {
        showLoading(true);
        const currentOccluder = document.getElementById('occluderState').textContent || 'BINO';
        const currentPower = sessionState.lastResponse?.power;

        if (currentPower) {
            await syncBrokerState({ right: currentPower.right, left: currentPower.left }, currentOccluder);
        }
        await setPower(_realtimeBeforeRestore, currentOccluder);

        if (sessionState.sessionId) {
            try {
                await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/sync-power`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(_realtimeBeforeRestore)
                });
            } catch (e) { console.warn('sync-power failed:', e); }
        }

        if (!sessionState.lastResponse) sessionState.lastResponse = {};
        sessionState.lastResponse.power = JSON.parse(JSON.stringify(_realtimeBeforeRestore));
        updateSessionInfo(sessionState.lastResponse);

        memoryMode = 'memS';
        _updateMemButton();
        addToHistory('Switched back to realtime values', 'info');
    } catch (error) {
        console.error('Error swapping back to realtime:', error);
        alert('Failed to switch back to realtime values.');
    } finally {
        showLoading(false);
        _setPhoropterBusy(false);
        _setIntentsDisabled(false);
        refreshScreenshotIfModalOpen();
    }
}

function clearMemory() {
    memoryState = null;
    memoryMode = 'mem';
    _realtimeBeforeRestore = null;
    _updateMemButton();
    _saveSessionToStorage();
    addToHistory('Memory cleared', 'info');
}

async function applyStoredPower(type) {
    if (_phoropterBusy) return;
    if (!sessionState.sessionId) {
        alert('Please start a test session first.');
        return;
    }

    const power = type === 'ar' ? storedPower.ar : storedPower.lenso;

    if (!power) {
        alert(`No ${type.toUpperCase()} power values stored. Please set them first.`);
        return;
    }

    _setPhoropterBusy(true);
    _setIntentsDisabled(true);
    try {
        showLoading(true);

        // Sync broker to current phoropter state before applying new absolute values
        const currentOccluder = document.getElementById('occluderState').textContent || 'BINO';
        if (sessionState.lastResponse && sessionState.lastResponse.power) {
            await syncBrokerState(sessionState.lastResponse.power, currentOccluder);
        }

        await setPower(power, 'BINO');

        currentAppliedPower = type;
        updatePowerButtonStates(type);

        sessionState.responseCount++;
        document.getElementById('responseCount').textContent = sessionState.responseCount;
        const label = type === 'ar' ? 'AR' : 'Lenso';
        addToHistory(`${label} power applied`, 'info');
        _saveSessionToStorage();

        // Update refraction table to reflect applied power
        const fmtSign = (v) => (v >= 0 ? '+' : '') + v.toFixed(2);
        const rSph = document.getElementById('rt-r-sph');
        const rCyl = document.getElementById('rt-r-cyl');
        const rAxis = document.getElementById('rt-r-axis');
        const lSph = document.getElementById('rt-l-sph');
        const lCyl = document.getElementById('rt-l-cyl');
        const lAxis = document.getElementById('rt-l-axis');
        if (rSph) rSph.textContent = fmtSign(power.right.sph);
        if (rCyl) rCyl.textContent = fmtSign(power.right.cyl);
        if (rAxis) rAxis.textContent = power.right.axis.toFixed(0);
        if (lSph) lSph.textContent = fmtSign(power.left.sph);
        if (lCyl) lCyl.textContent = fmtSign(power.left.cyl);
        if (lAxis) lAxis.textContent = power.left.axis.toFixed(0);
        document.getElementById('occluderState').textContent = 'BINO';

        // Sync applied power to backend session state
        if (sessionState.sessionId) {
            try {
                await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/sync-power`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(power)
                });
            } catch (syncErr) {
                console.warn('Failed to sync applied power to backend:', syncErr);
            }
        }

        if (!sessionState.lastResponse) {
            sessionState.lastResponse = {};
        }
        sessionState.lastResponse.power = power;
    } catch (error) {
        console.error(`Error applying ${type} power:`, error);
        alert(`Failed to apply ${type.toUpperCase()} power. Please try again.`);
    } finally {
        showLoading(false);
        _setPhoropterBusy(false);
        _setIntentsDisabled(false);
        refreshScreenshotIfModalOpen();
    }
}

function updatePowerButtonStates(activeType) {
    const arBtn = document.getElementById('applyArBtn');
    const lensoBtn = document.getElementById('applyLensoBtn');

    // Remove active class from all
    arBtn.classList.remove('active');
    lensoBtn.classList.remove('active');

    // Add active class to selected
    if (activeType === 'ar') {
        arBtn.classList.add('active');
    } else if (activeType === 'lenso') {
        lensoBtn.classList.add('active');
    }
}

// Start Test
async function startTest() {
    if (!_configReady) {
        alert('Still connecting to backend. Please wait a moment.');
        return;
    }

    const btn = document.getElementById('startTestBtn');
    if (btn) btn.disabled = true;

    try {
        // Ensure optometrist is identified
        if (!checkOptometristName()) {
            if (btn) btn.disabled = false;
            return;
        }

        const customerDetails = validateCustomerDetails();
        if (!customerDetails) {
            if (btn) btn.disabled = false;
            return;
        }

        // 1. Instantly switch to test screen and show modals
        customerName = customerDetails.name;
        customerAge = customerDetails.age;
        customerGender = customerDetails.gender;

        document.getElementById('welcomeScreen').style.display = 'none';
        document.getElementById('testScreen').style.display = 'block';
        updateCustomerStatusPanel();

        // Start modal flow instantly (non-blocking for hardware/backend tasks)
        runStartupPowerModalFlow();

        // 2. Perform hardware and backend initialization in background/parallel
        // We still show loading for the background tasks, but the modals are already on top.
        showLoading(true);

        // Generate session ID
        const sessionId = 'session_' + Date.now();
        sessionState.sessionId = sessionId;
        sessionState.currentChart = null;

        // Perform bridge/phoropter reset and session start concurrently
        const [resetRes, sessionRes] = await Promise.allSettled([
            resetPhoropter(),
            fetch(`${CONFIG.backendUrl}/api/session/start`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ session_id: sessionId, phoropter_id: CONFIG.phoropterId })
            })
        ]);

        if (sessionRes.status === 'rejected' || !sessionRes.value.ok) {
            throw new Error('Failed to start session on backend');
        }

        const data = await sessionRes.value.json();

        // 3. Finalize UI with backend data
        updateSessionInfo(data);
        displayQuestion(data);

        // Set phoropter for first phase (this might take a few seconds)
        await setPhoropter(data);

        addToHistory('Test started', 'success');
        updateStatusIndicator(true);
        _saveSessionToStorage();

        if (data.auto_flip) {
            await handleAutoFlip(data.flip_wait_seconds || 2);
        }

    } catch (error) {
        console.error('Error starting test:', error);
        alert(`Failed to start test. Make sure the backend server is running at ${CONFIG.backendUrl}.`);
        
        // Bail back to welcome screen on hard failure
        document.getElementById('welcomeScreen').style.display = 'block';
        document.getElementById('testScreen').style.display = 'none';
        if (btn) btn.disabled = false;
    } finally {
        showLoading(false);
        refreshScreenshotIfModalOpen();
    }
}

// Submit Intent Response
async function submitIntent(intent) {
    if (sessionState.intentsLocked || _phoropterBusy) {
        return;
    }
    try {
        showLoading(true);
        sessionState.intentsLocked = true;
        _setPhoropterBusy(true);

        // Hide all intent buttons during processing
        const intentButtonsContainer = document.getElementById('intentButtons');
        intentButtonsContainer.innerHTML = '<div class="alert alert-info">Processing...</div>';

        // Record response
        sessionState.responseCount++;
        addToHistory(`Response: ${intent}`, 'info');

        // Send to backend
        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intent: intent })
        });

        if (!response.ok) {
            throw new Error('Failed to submit response');
        }

        const data = await response.json();

        // Check if test is complete
        if (data.phase === 'complete' || data.status === 'complete') {
            await completeTest();
            return;
        }

        // Update UI for next question
        updateSessionInfo(data);

        // Update phoropter first
        await setPhoropter(data);

        // If we're about to auto-flip (e.g. after "Repeat" intent), refresh live view now so user can confirm Flip 1
        if (data.auto_flip) {
            refreshScreenshotIfModalOpen();
        }

        // Display question and intents AFTER processing is complete
        displayQuestion(data);
        _saveSessionToStorage();

        // Check if auto-flip is needed (JCC Flip1 → Flip2)
        if (data.auto_flip) {
            await handleAutoFlip(data.flip_wait_seconds || 2);
        }

    } catch (error) {
        console.error('Error submitting intent:', error);
        alert('Failed to submit response. Please try again.');
        sessionState.intentsLocked = false;
        const intentButtons = document.querySelectorAll('.intent-button');
        intentButtons.forEach(btn => btn.disabled = false);
    } finally {
        _setPhoropterBusy(false);
        showLoading(false);
        refreshScreenshotIfModalOpen();
    }
}

// Handle Automatic Flip (Flip1 → wait → Flip2)
async function handleAutoFlip(waitSeconds) {
    try {
        // Hide intent buttons during auto-flip countdown
        const intentButtonsContainer = document.getElementById('intentButtons');
        const originalContent = intentButtonsContainer.innerHTML;
        intentButtonsContainer.innerHTML = '';

        // Show countdown in question box
        const questionBox = document.querySelector('.question-box');
        const countdownDiv = document.createElement('div');
        countdownDiv.id = 'flipCountdown';
        countdownDiv.style.cssText = 'background: #fff3e0; padding: 15px; margin-top: 15px; border-radius: 5px; text-align: center; font-size: 1.2em; color: #f57c00; font-weight: bold;';
        questionBox.appendChild(countdownDiv);

        // Countdown timer
        for (let i = waitSeconds; i > 0; i--) {
            countdownDiv.textContent = `⏱️ Showing Flip 2 in ${i} second${i > 1 ? 's' : ''}...`;
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        countdownDiv.textContent = '⏱️ Now showing Flip 2...';

        // Call backend with AUTO_FLIP to show Flip2
        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/respond`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ intent: 'AUTO_FLIP' })
        });

        if (!response.ok) {
            throw new Error('Failed to auto-flip');
        }

        const data = await response.json();

        // Remove countdown
        if (countdownDiv.parentNode) {
            countdownDiv.parentNode.removeChild(countdownDiv);
        }

        // Update UI with Flip2 state
        updateSessionInfo(data);
        displayQuestion(data);

        // Note: displayQuestion() creates fresh enabled buttons

        addToHistory('Flip 2 displayed', 'info');
        refreshScreenshotIfModalOpen();

    } catch (error) {
        console.error('Error during auto-flip:', error);
        alert('Failed to show Flip 2. Please try again.');
    }
}

// Display Question and Intents
function displayQuestion(data) {
    // Update phase badge
    const phaseName = data.phase || 'Unknown Phase';
    document.getElementById('phaseBadge').textContent = phaseName;

    // Update question
    const question = data.question || 'Please describe what you see.';
    document.getElementById('questionText').textContent = question;

    // Update chart selector visibility and content
    updateChartSelector(data);

    // Update optotype selector
    updateOptotypeSelector(data);

    // Update intents
    const intents = data.intents || [];
    const intentButtons = document.getElementById('intentButtons');
    intentButtons.innerHTML = '';
    sessionState.intentsLocked = false;

    // If no intents (Flip1 state), show waiting message
    if (intents.length === 0 && data.auto_flip) {
        const waitingMsg = document.createElement('div');
        waitingMsg.className = 'alert alert-info';
        waitingMsg.textContent = 'Please observe Flip 1. Flip 2 will show automatically...';
        intentButtons.appendChild(waitingMsg);
        return;
    }

    intents.forEach((intent, index) => {
        const button = document.createElement('button');
        button.className = 'intent-button';
        button.textContent = `${index + 1}. ${intent}`;
        button.onclick = () => submitIntent(intent);
        intentButtons.appendChild(button);
    });
}

// Update Chart Selector
function updateChartSelector(data) {
    const chartSelector = document.getElementById('chartSelector');
    const chartGrid = document.getElementById('chartGrid');

    // Check if we're in Phase A (distance vision) or Phase B (right or left eye refraction)
    const isPhaseA = data.phase && data.phase.includes('Distance Vision');
    const isPhaseB = data.phase && (
        data.phase.includes('Right Eye Refraction') ||
        data.phase.includes('Left Eye Refraction')
    );

    if ((isPhaseA || isPhaseB) && data.chart_info) {
        // Show chart selector
        chartSelector.classList.add('active');

        // Update session state
        sessionState.availableCharts = data.chart_info.available_charts || [];
        sessionState.currentChartIndex = data.chart_info.current_index || 0;

        // Build chart grid
        chartGrid.innerHTML = '';
        sessionState.availableCharts.forEach((chart, index) => {
            const button = document.createElement('button');
            button.className = 'chart-button';
            if (index === sessionState.currentChartIndex) {
                button.classList.add('active');
            }

            const chartName = document.createElement('div');
            chartName.className = 'chart-name';
            chartName.textContent = formatChartName(chart);

            const chartSize = document.createElement('div');
            chartSize.className = 'chart-size';
            chartSize.textContent = extractChartSize(chart);

            button.appendChild(chartName);
            button.appendChild(chartSize);
            button.onclick = () => switchChart(index);

            chartGrid.appendChild(button);
        });
    } else {
        // Hide chart selector for other phases
        chartSelector.classList.remove('active');
    }
}

// Update Optotype Selector
function updateOptotypeSelector(data, forceShow = false) {
    const optotypeSelector = document.getElementById('optotypeSelector');
    const optotypeGrid = document.getElementById('optotypeGrid');

    // Get chart from data or current session state
    const currentChartName = data.chart || sessionState.availableCharts[sessionState.currentChartIndex];

    // Check if we're in Phase A or B where optotypes are supported
    const isPhaseA = data.phase && data.phase.includes('Distance Vision');
    const isPhaseB = data.phase && (
        data.phase.includes('Right Eye Refraction') ||
        data.phase.includes('Left Eye Refraction')
    );

    const availableOptotypes = OPTOTYPE_MAP[currentChartName];

    if (forceShow || ((isPhaseA || isPhaseB) && availableOptotypes)) {
        optotypeSelector.classList.add('active');
        optotypeGrid.innerHTML = '';

        if (availableOptotypes) {
            availableOptotypes.forEach(optotype => {
                const button = document.createElement('button');
                button.className = 'optotype-button';
                if (optotype === currentOptotype) {
                    button.classList.add('active');
                }
                button.textContent = optotype;
                button.onclick = () => switchOptotype(optotype);
                optotypeGrid.appendChild(button);
            });

            const pinholeBtn = document.createElement('button');
            pinholeBtn.id = 'pinholeToggleBtn';
            pinholeBtn.className = 'optotype-button pinhole-button';
            pinholeBtn.onclick = () => activatePinhole();
            _updatePinholeButtonUI(pinholeBtn);
            optotypeGrid.appendChild(pinholeBtn);
        } else {
            optotypeGrid.innerHTML = '<div style="font-size: 0.9em; color: #666; padding: 10px;">No specific optotypes for this chart</div>';
        }
    } else {
        optotypeSelector.classList.remove('active');
    }
}

// Populate Direct Chart Commands
function populateDirectCommands() {
    const container = document.getElementById('directCommands');
    if (!container) return;

    container.innerHTML = `
        <div class="command-group">
            <select id="directChartSelect" class="phase-jump select" style="width: 100%; min-width: 0; border-color: #667eea; margin-bottom: 12px; height: 38px; padding: 4px 10px; font-size: 0.95em;">
                <option value="">-- Choose Chart --</option>
            </select>
            <div id="directOptotypeGrid" class="optotype-grid" style="grid-template-columns: repeat(auto-fit, minmax(60px, 1fr)); gap: 8px;">
                <!-- Buttons populated based on selection -->
            </div>
        </div>
    `;

    const select = document.getElementById('directChartSelect');
    const grid = document.getElementById('directOptotypeGrid');

    const chartGroups = [
        { id: "snellen_chart_200_150", label: "Chart 200/150", optotypes: ["200", "150"] },
        { id: "snellen_chart_100_80", label: "Chart 100/80", optotypes: ["100", "80"] },
        { id: "snellen_chart_70_60_50", label: "Chart 70/60/50", optotypes: ["70", "60", "50"] },
        { id: "snellen_chart_40_30_25", label: "Chart 40/30/25", optotypes: ["40", "30", "25"] },
        { id: "snellen_chart_20_15_10", label: "Chart 20/15/10", optotypes: ["20", "15", "10"] },
        { id: "snellen_chart_20_20_20", label: "Chart 20/20 (Cols)", optotypes: ["20_1", "20_2", "20_3"] },
        { id: "snellen_chart_25_20_15", label: "Chart 25/20/15", optotypes: ["25", "20", "15"] },
        { id: "bino_chart", label: "Chart 20 (R/L)", optotypes: ["R", "L"] }
    ];

    chartGroups.forEach(group => {
        const option = document.createElement('option');
        option.value = group.id;
        option.textContent = group.label;
        select.appendChild(option);
    });

    select.onchange = () => {
        const groupId = select.value;
        const group = chartGroups.find(g => g.id === groupId);
        grid.innerHTML = '';
        if (group) {
            group.optotypes.forEach(opt => {
                const btn = document.createElement('button');
                btn.className = 'optotype-button';
                btn.style.padding = '8px 4px';
                btn.style.fontSize = '0.9em';
                btn.textContent = opt;
                btn.onclick = () => executeDirectCommand(groupId, opt);
                grid.appendChild(btn);
            });
        }
    };
}

async function executeDirectCommand(chartName, optotype) {
    if (!sessionState.sessionId) {
        // Start a temporary session if none exists
        if (confirm('No active session. Start a quick test session?')) {
            await startTest();
        } else {
            return;
        }
    }

    try {
        showLoading(true);
        currentOptotype = optotype;

        // Find if this chart is in available charts to keep internal state in sync
        const chartIdx = sessionState.availableCharts.indexOf(chartName);
        if (chartIdx !== -1) {
            sessionState.currentChartIndex = chartIdx;
            // Update the main chart selector UI if active
            const chartButtons = document.querySelectorAll('.chart-button');
            chartButtons.forEach((btn, idx) => {
                if (idx === chartIdx) btn.classList.add('active');
                else btn.classList.remove('active');
            });
        }

        await setChart(chartName, optotype);

        // Update current optotype UI and FORCE it to show (opens UI completely)
        updateOptotypeSelector({ chart: chartName, phase: sessionState.currentPhase }, true);

        addToHistory(`Direct command: ${chartName} [${optotype}]`, 'info');
    } catch (error) {
        console.error('Error executing direct command:', error);
        alert('Failed to execute command. Please check console.');
    } finally {
        showLoading(false);
    }
}

// Update Optotype Selector
function updateOptotypeSelector(data) {
    const optotypeSelector = document.getElementById('optotypeSelector');
    const optotypeGrid = document.getElementById('optotypeGrid');
    const currentChartName = sessionState.availableCharts[sessionState.currentChartIndex];

    // Check if we're in Phase A or B where optotypes are supported
    const isPhaseA = data.phase && data.phase.includes('Distance Vision');
    const isPhaseB = data.phase && (
        data.phase.includes('Right Eye Refraction') ||
        data.phase.includes('Left Eye Refraction')
    );

    const availableOptotypes = OPTOTYPE_MAP[currentChartName];

    if ((isPhaseA || isPhaseB) && availableOptotypes) {
        optotypeSelector.classList.add('active');
        optotypeGrid.innerHTML = '';

        availableOptotypes.forEach(optotype => {
            const button = document.createElement('button');
            button.className = 'optotype-button';
            if (optotype === currentOptotype) {
                button.classList.add('active');
            }
            button.textContent = optotype;
            button.onclick = () => switchOptotype(optotype);
            optotypeGrid.appendChild(button);
        });

        const pinholeBtn = document.createElement('button');
        pinholeBtn.id = 'pinholeToggleBtn';
        pinholeBtn.className = 'optotype-button pinhole-button';
        pinholeBtn.onclick = () => activatePinhole();
        _updatePinholeButtonUI(pinholeBtn);
        optotypeGrid.appendChild(pinholeBtn);
    } else {
        optotypeSelector.classList.remove('active');
    }
}

// Update pinhole button text and visual state
function _updatePinholeButtonUI(btn) {
    if (!btn) return;
    btn.textContent = pinholeActive ? 'Remove Pinhole' : 'Pinhole';
    btn.classList.toggle('active', pinholeActive);
}

// Toggle pinhole on phoropter (activate / remove)
async function activatePinhole() {
    if (!sessionState.sessionId) {
        alert('No active session');
        return;
    }
    const btn = document.getElementById('pinholeToggleBtn');
    if (!btn) return;
    if (btn.disabled) return;

    const prevState = pinholeActive;
    const isActivating = !pinholeActive;
    const endpoint = isActivating ? 'pinhole' : 'occluder';

    btn.disabled = true;
    showLoading(true);
    try {
        if (isTestDeviceId()) {
            pinholeActive = isActivating;
            _updatePinholeButtonUI(btn);
            addToHistory(`Test mode: ${isActivating ? 'pinhole' : 'occluder'} command skipped`, 'info');
            btn.disabled = false;
            showLoading(false);
            return;
        }
        const res = await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/${endpoint}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        if (!res.ok) {
            throw new Error(`API returned ${res.status}`);
        }
        pinholeActive = isActivating;
        _updatePinholeButtonUI(btn);
        addToHistory(isActivating ? 'Pinhole activated' : 'Pinhole removed', 'info');
    } catch (error) {
        console.error(`Error ${isActivating ? 'activating' : 'removing'} pinhole:`, error);
        alert(`Failed to ${isActivating ? 'activate' : 'remove'} pinhole. Please try again.`);
        // Revert UI to previous state
        pinholeActive = prevState;
        _updatePinholeButtonUI(btn);
    } finally {
        btn.disabled = false;
        showLoading(false);
        refreshScreenshotIfModalOpen();
    }
}

// Switch to a specific optotype
async function switchOptotype(optotype) {
    if (!sessionState.sessionId) {
        alert('No active session');
        return;
    }

    if (optotype === currentOptotype) {
        // Already selected, but allow re-clicking to trigger phoropter if needed
    }

    try {
        showLoading(true);
        currentOptotype = optotype;

        const chartName = sessionState.availableCharts[sessionState.currentChartIndex];
        await setChart(chartName, optotype);

        // Update UI state
        const buttons = document.querySelectorAll('.optotype-button');
        buttons.forEach(btn => {
            if (btn.textContent === optotype) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        addToHistory(`Select optotype: ${optotype}`, 'info');
    } catch (error) {
        console.error('Error switching optotype:', error);
        alert('Failed to switch optotype. Please try again.');
    } finally {
        showLoading(false);
        refreshScreenshotIfModalOpen();
    }
}

// Format chart name for display
function formatChartName(chartName) {
    // Convert "snellen_chart_200_150" to "Chart 200/150"
    const match = chartName.match(/snellen_chart_(.+)/);
    if (match) {
        return `Chart ${match[1].replace(/_/g, '/')}`;
    }
    return chartName;
}

// Extract chart size for display
function extractChartSize(chartName) {
    // Convert "snellen_chart_200_150" to "20/200 - 20/150"
    const match = chartName.match(/snellen_chart_(\d+)_(\d+)(?:_(\d+))?/);
    if (match) {
        if (match[3]) {
            return `20/${match[1]} - 20/${match[2]} - 20/${match[3]}`;
        }
        return `20/${match[1]} - 20/${match[2]}`;
    }
    return '';
}

// Switch to a different chart
async function switchChart(chartIndex) {
    if (!sessionState.sessionId) {
        alert('No active session');
        return;
    }

    if (chartIndex === sessionState.currentChartIndex) {
        return; // Already on this chart
    }

    try {
        showLoading(true);

        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/switch-chart`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chart_index: chartIndex })
        });

        if (!response.ok) {
            throw new Error('Failed to switch chart');
        }

        const data = await response.json();

        // Reset optotype when switching chart
        currentOptotype = null;

        // Update phoropter
        await setPhoropter(data);

        // Update UI
        updateSessionInfo(data);
        displayQuestion(data);

        addToHistory(`Switched to chart ${chartIndex + 1}`, 'info');

    } catch (error) {
        console.error('Error switching chart:', error);
        alert('Failed to switch chart. Please try again.');
    } finally {
        showLoading(false);
        refreshScreenshotIfModalOpen();
    }
}

// Update Session Info Panel
function updateSessionInfo(data) {
    document.getElementById('sessionId').textContent = sessionState.sessionId;
    document.getElementById('sessionStatus').textContent = 'Active';
    document.getElementById('currentPhase').textContent = data.phase || '-';
    document.getElementById('responseCount').textContent = sessionState.responseCount;

    // Update power info
    if (data.power) {
        const right = data.power.right || { sph: 0, cyl: 0, axis: 180 };
        const left = data.power.left || { sph: 0, cyl: 0, axis: 180 };

        // Update refraction table cells directly
        const rSphDoc = document.getElementById('rt-r-sph');
        if (rSphDoc) rSphDoc.textContent = (right.sph >= 0 ? '+' : '') + right.sph.toFixed(2);

        const rCylDoc = document.getElementById('rt-r-cyl');
        if (rCylDoc) rCylDoc.textContent = (right.cyl >= 0 ? '+' : '') + right.cyl.toFixed(2);

        const rAxisDoc = document.getElementById('rt-r-axis');
        if (rAxisDoc) rAxisDoc.textContent = _normalizeAxisDisplay(right.axis);

        const lSphDoc = document.getElementById('rt-l-sph');
        if (lSphDoc) lSphDoc.textContent = (left.sph >= 0 ? '+' : '') + left.sph.toFixed(2);

        const lCylDoc = document.getElementById('rt-l-cyl');
        if (lCylDoc) lCylDoc.textContent = (left.cyl >= 0 ? '+' : '') + left.cyl.toFixed(2);

        const lAxisDoc = document.getElementById('rt-l-axis');
        if (lAxisDoc) lAxisDoc.textContent = _normalizeAxisDisplay(left.axis);

        // Show ADD column only during near vision phases
        const phaseText = (data.phase || '').toLowerCase();
        const isNearPhase = phaseText.includes('near vision');
        const addColHeader = document.getElementById('addColHeader');
        const rAddCell = document.getElementById('rt-r-add');
        const lAddCell = document.getElementById('rt-l-add');
        const addDisplay = isNearPhase ? '' : 'none';
        if (addColHeader) addColHeader.style.display = addDisplay;
        if (rAddCell) rAddCell.style.display = addDisplay;
        if (lAddCell) lAddCell.style.display = addDisplay;

        if (isNearPhase) {
            const rAdd = (right.add || 0);
            const lAdd = (left.add || 0);
            if (rAddCell) rAddCell.textContent = '+' + rAdd.toFixed(2);
            if (lAddCell) lAddCell.textContent = '+' + lAdd.toFixed(2);
        }
    }

    // Update occluder and chart
    document.getElementById('occluderState').textContent = data.occluder || 'BINO';
    document.getElementById('chartDisplay').textContent = data.chart || '-';

    sessionState.currentPhase = data.phase;
    sessionState.lastResponse = data;
}

// Phoropter Control Functions
async function resetPhoropter() {
    try {
        if (isTestDeviceId()) {
            addToHistory('Test mode: reset skipped', 'info');
            refreshScreenshotIfModalOpen();
            return;
        }
        const response = await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/reset`, {
            method: 'POST'
        });

        if (response.ok) {
            addToHistory('Phoropter reset to 0/0/180', 'success');
        }
        refreshScreenshotIfModalOpen();
    } catch (error) {
        console.error('Error resetting phoropter:', error);
        addToHistory('Warning: Could not reset phoropter', 'warning');
        refreshScreenshotIfModalOpen();
    }
}

async function setPhoropter(data) {
    try {
        // Set chart only if it has changed (avoids duplicate JCC chart calls during flip cycles)
        if (data.chart && (data.chart !== sessionState.currentChart || currentOptotype !== null)) {
            if (data.chart !== sessionState.currentChart) {
                currentOptotype = null;
            }
            await setChart(data.chart, currentOptotype);
            sessionState.currentChart = data.chart;
        }

        // Set power and occluder (skip for phases where backend applies power with prev_state)
        // - JCC/duochrome: phoropter handles internally
        // - Near ADD (P/Q/R): backend uses set_power_with_prev_state; frontend would double-apply
        const phaseText = (data.phase || '').toLowerCase();
        const isJccPhase = phaseText.includes('jcc') || data.chart === 'jcc_chart';
        const isDuochromePhase = phaseText.includes('duochrome') || data.chart === 'duochrome';
        const isNearAddPhase = phaseText.includes('near vision') || phaseText.includes('near_add');
        if (data.power && !isJccPhase && !isDuochromePhase && !isNearAddPhase) {
            await setPower(data.power, data.occluder);
        }

    } catch (error) {
        console.error('Error setting phoropter:', error);
        addToHistory('Warning: Could not update phoropter', 'warning');
    }
}

async function setChart(chartName, optotype = null) {
    const chartMap = {
        "echart_400": "chart_9",
        "snellen_chart_200_150": "chart_10",
        "snellen_chart_100_80": "chart_11",
        "snellen_chart_70_60_50": "chart_12",
        "snellen_chart_40_30_25": "chart_13",
        "snellen_chart_20_15_10": "chart_14",
        "snellen_chart_20_20_20": "chart_15",
        "snellen_chart_25_20_15": "chart_16",
        "duochrome": "chart_17",
        "jcc_chart": "chart_19",
        "bino_chart": "chart_20",
    };

    const chartId = chartMap[chartName];
    if (!chartId) return;

    const chartItems = [chartId];
    if (optotype) {
        chartItems.push(optotype);
    }

    const payload = {
        test_cases: [{
            chart: {
                tab: "Chart1",
                chart_items: chartItems
            }
        }]
    };

    if (isTestDeviceId()) {
        addToHistory(`Test mode chart: ${chartName}${optotype ? ` [${optotype}]` : ''}`, 'info');
        return;
    }

    await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/run-tests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    addToHistory(`Chart: ${chartName}`, 'info');
}

async function setPower(power, occluder) {
    const right = power.right || { sph: 0, cyl: 0, axis: 180 };
    const left = power.left || { sph: 0, cyl: 0, axis: 180 };

    // Map occluder
    let auxLens = "OFF";
    if (occluder === "Left_Occluded") {
        auxLens = "AuxLensL";
    } else if (occluder === "Right_Occluded") {
        auxLens = "AuxLensR";
    }

    // Axis 0° = 180°; normalize before sending to phoropter
    const rAxis = (right.axis === 0) ? 180 : (right.axis || 180);
    const lAxis = (left.axis === 0) ? 180 : (left.axis || 180);
    const rightEye = { sph: right.sph, cyl: right.cyl, axis: rAxis };
    const leftEye = { sph: left.sph, cyl: left.cyl, axis: lAxis };
    if (right.add !== undefined && right.add !== 0) rightEye.add = right.add;
    if (left.add !== undefined && left.add !== 0) leftEye.add = left.add;

    const payload = {
        test_cases: [{
            aux_lens: auxLens,
            right_eye: rightEye,
            left_eye: leftEye
        }]
    };

    if (isTestDeviceId()) {
        addToHistory(`Test mode power update - Occluder: ${occluder}`, 'info');
        return;
    }

    await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/run-tests`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    });

    addToHistory(`Power updated - Occluder: ${occluder}`, 'info');
}

// Complete Test - shows prescription + screenshot for validation; does NOT store or release yet
async function completeTest() {
    try {
        // Get prescription preview without storing (store: false)
        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/end`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                store: false,
                ar: storedPower.ar || null,
                lenso: storedPower.lenso || null,
                operator_name: operatorName || null
            })
        });

        if (!response.ok) {
            throw new Error('Failed to end session');
        }

        const data = await response.json();

        // Capture final screenshot before releasing device
        let screenshotBase64 = null;
        if (!isTestDeviceId()) {
            try {
                console.log('Capturing screenshot from phoropter...');
                const brainId = await getBrainId();
                const ssResp = await fetch(`${CONFIG.phoropterUrl}/phoropter/${CONFIG.phoropterId}/screenshot`, {
                    method: 'POST',
                    headers: { 'x-brain-id': brainId }
                });
                if (ssResp.ok) {
                    const rawText = await ssResp.text();
                    screenshotBase64 = rawText.trim();
                    if (screenshotBase64.startsWith('"') && screenshotBase64.endsWith('"')) {
                        screenshotBase64 = screenshotBase64.slice(1, -1);
                    }
                    if (screenshotBase64.startsWith('{')) {
                        try {
                            const parsed = JSON.parse(rawText);
                            screenshotBase64 = parsed.image || parsed.screenshot || parsed.data || rawText;
                        } catch (_) { }
                    }
                    screenshotBase64 = screenshotBase64.replace(/\s+/g, '');
                }
            } catch (ssErr) {
                console.error('Screenshot capture exception:', ssErr);
            }
        }

        // Hide test screen, show complete screen
        document.getElementById('testScreen').style.display = 'none';
        document.getElementById('completeScreen').style.display = 'block';
        const feedbackEl = document.getElementById('completeQualitativeFeedback');
        if (feedbackEl) feedbackEl.value = '';

        // Reset validation UI state
        const validationBtns = document.getElementById('completeValidationButtons');
        const afterValidation = document.getElementById('completeAfterValidation');
        const validationPrompt = document.getElementById('completeValidationPrompt');
        if (validationBtns) validationBtns.style.display = 'flex';
        if (afterValidation) afterValidation.style.display = 'none';
        if (validationPrompt) validationPrompt.style.display = 'block';

        // Display final prescription
        if (data.final_prescription) {
            const rx = data.final_prescription;
            const rAdd = rx.right_eye.add || 0;
            const lAdd = rx.left_eye.add || 0;
            const formatAdd = (value) => {
                const n = Number(value || 0);
                return `${n >= 0 ? '+' : ''}${n.toFixed(2)}`;
            };
            const prescriptionHtml = `
                <div class="info-section">
                    <h4>Final Prescription</h4>
                    <div class="info-item">
                        <span class="info-label">Right Eye (OD)</span>
                        <span class="info-value">
                            SPH: ${rx.right_eye.sph.toFixed(2)} | 
                            CYL: ${rx.right_eye.cyl.toFixed(2)} | 
                            AXIS: ${rx.right_eye.axis.toFixed(0)}° |
                            ADD: ${formatAdd(rAdd)}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Left Eye (OS)</span>
                        <span class="info-value">
                            SPH: ${rx.left_eye.sph.toFixed(2)} | 
                            CYL: ${rx.left_eye.cyl.toFixed(2)} | 
                            AXIS: ${rx.left_eye.axis.toFixed(0)}° |
                            ADD: ${formatAdd(lAdd)}
                        </span>
                    </div>
                    <div class="info-item">
                        <span class="info-label">Total Responses</span>
                        <span class="info-value">${data.total_rows || sessionState.responseCount}</span>
                    </div>
                </div>
            `;

            document.getElementById('finalPrescription').innerHTML = prescriptionHtml;

            if (screenshotBase64 && screenshotBase64.length > 100) {
                try {
                    const screenshotDiv = document.createElement('div');
                    screenshotDiv.className = 'info-section';
                    screenshotDiv.style.marginTop = '20px';
                    screenshotDiv.innerHTML = `
                        <h4>Final Phoropter View</h4>
                        <img src="data:image/jpeg;base64,${screenshotBase64}" 
                             alt="Phoropter Screenshot"
                             style="width: 100%; max-width: 800px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.15); margin-top: 10px;">
                    `;
                    document.getElementById('finalPrescription').appendChild(screenshotDiv);
                } catch (imgErr) {
                    console.error('Failed to append screenshot:', imgErr);
                }
            }
        }

        updateStatusIndicator(false);
        document.getElementById('sessionStatus').textContent = 'Awaiting validation';
        addToHistory('Test complete – please validate prescription matches image', 'info');

        // Release device when End Test is pressed (middle or end of test)
        await releaseDevice();

    } catch (error) {
        console.error('Error completing test:', error);
        alert('Failed to complete test properly.');
        _clearSessionStorage();
        await releaseDevice();
    }
}

// Sign-off: store CSV and release phoropter
async function signOff() {
    const signOffBtn = document.getElementById('signOffBtn');
    const powerBtn = document.getElementById('powerDoesNotMatchBtn');
    if (signOffBtn) signOffBtn.disabled = true;
    if (powerBtn) powerBtn.disabled = true;

    try {
        const feedbackEl = document.getElementById('completeQualitativeFeedback');
        const qualitativeFeedback = feedbackEl ? String(feedbackEl.value || '').trim() : '';
        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/end`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                store: true,
                ar: storedPower.ar || null,
                lenso: storedPower.lenso || null,
                operator_name: operatorName || null,
                customer_name: customerName || null,
                customer_age: customerAge || null,
                customer_gender: customerGender || null,
                qualitative_feedback: qualitativeFeedback || null
            })
        });

        if (!response.ok) {
            throw new Error('Failed to store session');
        }

        const data = await response.json();
        document.getElementById('completeValidationButtons').style.display = 'none';
        document.getElementById('completeValidationPrompt').style.display = 'none';
        const msgEl = document.getElementById('completeResultMessage');
        if (msgEl) {
            let msg = 'Prescription signed off. Data stored successfully.';
            let isWarning = false;
            if (data.remote_storage) {
                if (data.remote_storage.saved) {
                    msg += ` Saved to ${data.remote_storage.backend}.`;
                    addToHistory(`Saved to ${data.remote_storage.backend}`, 'success');
                } else {
                    msg += ` (Cloud save failed: ${data.remote_storage.error || 'unknown'})`;
                    isWarning = true;
                    addToHistory(`Remote save failed: ${data.remote_storage.error}`, 'warning');
                }
            }
            msgEl.textContent = msg;
            msgEl.className = isWarning ? 'alert alert-warning' : 'alert alert-success';
        }
        document.getElementById('completeAfterValidation').style.display = 'block';
        addToHistory('Prescription signed off – data stored', 'success');
    } catch (error) {
        console.error('Sign-off error:', error);
        alert('Failed to store data. Please try again.');
        if (signOffBtn) signOffBtn.disabled = false;
        if (powerBtn) powerBtn.disabled = false;
        return;
    } finally {
        _clearSessionStorage();
        await releaseDevice();
    }
}

// Power does not match: discard session, do not store CSV, release phoropter
async function powerDoesNotMatch() {
    const signOffBtn = document.getElementById('signOffBtn');
    const powerBtn = document.getElementById('powerDoesNotMatchBtn');
    if (signOffBtn) signOffBtn.disabled = true;
    if (powerBtn) powerBtn.disabled = true;

    try {
        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/discard`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });

        if (!response.ok) {
            throw new Error('Failed to discard session');
        }

        document.getElementById('completeValidationButtons').style.display = 'none';
        document.getElementById('completeValidationPrompt').style.display = 'none';
        const msgEl = document.getElementById('completeResultMessage');
        if (msgEl) {
            msgEl.textContent = 'Session discarded. Prescription did not match – no data stored.';
            msgEl.className = 'alert alert-warning';
        }
        document.getElementById('completeAfterValidation').style.display = 'block';
        addToHistory('Prescription did not match – session discarded', 'info');
    } catch (error) {
        console.error('Discard error:', error);
        alert('Failed to discard. Please try again.');
        if (signOffBtn) signOffBtn.disabled = false;
        if (powerBtn) powerBtn.disabled = false;
        return;
    } finally {
        _clearSessionStorage();
        await releaseDevice();
    }
}

// Start new test – return to welcome screen
function startNewTest() {
    document.getElementById('completeScreen').style.display = 'none';
    const feedbackEl = document.getElementById('completeQualitativeFeedback');
    if (feedbackEl) feedbackEl.value = '';
    document.getElementById('testScreen').style.display = 'none';
    document.getElementById('welcomeScreen').style.display = 'block';
    document.getElementById('sessionStatus').textContent = 'Not Started';
    const customerInput = document.getElementById('customerNameInput');
    if (customerInput) customerInput.value = '';
    const customerAgeInput = document.getElementById('customerAgeInput');
    if (customerAgeInput) customerAgeInput.value = '';
    const customerGenderInput = document.getElementById('customerGenderInput');
    if (customerGenderInput) customerGenderInput.value = '';
    customerName = '';
    customerAge = '';
    customerGender = '';
    updateCustomerStatusPanel();

    // Reset session state for a fresh start
    sessionState.sessionId = null;
    sessionState.currentPhase = null;
    sessionState.currentChart = null;
    sessionState.currentChartIndex = 0;
    sessionState.availableCharts = [];
    sessionState.intentsLocked = false;
    sessionState.responseCount = 0;
    sessionState.history = [];
    pinholeActive = false;

    // Re-enable Start Eye Test button
    const btn = document.getElementById('startTestBtn');
    if (btn) {
        btn.disabled = false;
        btn.textContent = 'Start Eye Test';
    }
    updateStatusIndicator(false);
}

// End Test Early
async function endTest() {
    if (confirm('Are you sure you want to end the test?')) {
        await completeTest();
    }
}

// UI Helper Functions
function showLoading(show) {
    const loader = document.getElementById('loadingIndicator');
    if (show) {
        loader.classList.add('active');
    } else {
        loader.classList.remove('active');
    }
}

function updateStatusIndicator(active) {
    const indicator = document.getElementById('statusIndicator');
    if (active) {
        indicator.classList.add('status-active');
        indicator.classList.remove('status-inactive');
    } else {
        indicator.classList.add('status-inactive');
        indicator.classList.remove('status-active');
    }
}

function addToHistory(message, type = 'info') {
    const timestamp = new Date().toLocaleTimeString();
    const historyLog = document.getElementById('historyLog');

    // Clear "no history" message
    if (sessionState.history.length === 0) {
        historyLog.innerHTML = '';
    }

    const item = document.createElement('div');
    item.className = 'history-item';
    item.innerHTML = `<strong>${timestamp}</strong> - ${message}`;

    historyLog.insertBefore(item, historyLog.firstChild);
    sessionState.history.push({ timestamp, message, type });

    // Keep only last 20 items
    while (historyLog.children.length > 20) {
        historyLog.removeChild(historyLog.lastChild);
    }
}

// Jump to Phase
async function jumpToPhase() {
    const select = document.getElementById('phaseSelect');
    const jumpBtn = document.getElementById('jumpBtn');
    const targetPhase = select.value;

    if (!targetPhase) {
        alert('Please select a phase');
        return;
    }

    if (!sessionState.sessionId) {
        alert('Please start a test session first');
        return;
    }

    jumpBtn.disabled = true;

    try {
        showLoading(true);

        const response = await fetch(`${CONFIG.backendUrl}/api/session/${sessionState.sessionId}/jump`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ phase: targetPhase })
        });

        if (!response.ok) {
            throw new Error('Failed to jump to phase');
        }

        const data = await response.json();

        // Update UI
        updateSessionInfo(data);
        displayQuestion(data);

        // Show test screen if not visible
        document.getElementById('welcomeScreen').style.display = 'none';
        document.getElementById('testScreen').style.display = 'block';

        addToHistory(`Jumped to ${data.phase}`, 'info');

        // If auto_flip is requested, start countdown
        if (data.auto_flip) {
            await handleAutoFlip(data.flip_wait_seconds || 2);
        }

        showLoading(false);

    } catch (error) {
        console.error('Error jumping to phase:', error);
        alert('Failed to jump to phase. Please try again.');
        showLoading(false);
    } finally {
        jumpBtn.disabled = false;
        refreshScreenshotIfModalOpen();
    }
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Block intent shortcuts while type mode input is active
    if (_typeModeEditing) return;

    // Number keys 1-9 to select intents
    if (e.key >= '1' && e.key <= '9') {
        const index = parseInt(e.key) - 1;
        const buttons = document.querySelectorAll('.intent-button');
        if (buttons[index]) {
            buttons[index].click();
        }
    }
});
