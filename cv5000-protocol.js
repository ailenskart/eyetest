/**
 * Topcon CV-5000 Phoropter + Chart Control Protocol
 *
 * Real API Reference: curl_API.md
 * Base URL: https://rajasthan-royals.preprod.lenskart.com
 * Dashboard: https://rajasthan-royals.preprod.lenskart.com/dashboard
 *
 * Architecture:
 *   Brain UI (this app) ──HTTP──▶ Broker (preprod) ──WebSocket──▶ Agent (Windows) ──▶ CV-5000
 *
 * Device Management (Multi-Brain):
 *   GET  /devices                          → List available phoropters
 *   POST /devices/{id}/acquire             → Lock device for exclusive use
 *   POST /devices/{id}/release             → Unlock device
 *   POST /devices/{id}/heartbeat           → Keep lock alive (every 15s)
 *
 * Phoropter Control:
 *   POST /phoropter/{id}/run-tests         → Execute test cases (power, JCC, chart)
 *   POST /phoropter/{id}/reset             → Reset to 0/0/180
 *   POST /phoropter/{id}/pinhole           → Activate pinhole (Alt+V menu)
 *   POST /phoropter/{id}/occluder          → Set occluder (Alt+V menu)
 *   POST /phoropter/{id}/sync-state        → Sync internal state (no clicks)
 *   POST /phoropter/{id}/screenshot        → Capture agent screen (base64 JPEG)
 *
 * Payload Format:
 *   Power:  { test_cases: [{ case_id, aux_lens, right_eye: {sph,cyl,axis}, left_eye: {sph,cyl,axis} }] }
 *   JCC:    { test_cases: [{ jcc: "handle"|"increase"|"decrease"|"power_axis_switch"|"R"|"L"|"BINO" }] }
 *   Chart:  { test_cases: [{ chart: { tab: "Chart1", chart_items: ["chart_19"] } }] }
 *
 * aux_lens mapping:
 *   "AuxLensL" → JCC R mode (tests Right eye, occludes Left)
 *   "AuxLensR" → JCC L mode (tests Left eye, occludes Right)
 *   "BINO"     → Binocular mode
 *   "OFF"      → Clear occluder
 */

class CV5000Protocol {
    constructor(config = {}) {
        this.baseUrl = config.baseUrl || 'https://rajasthan-royals.preprod.lenskart.com';
        this.phoroptertId = config.phoroptertId || '';
        this.brainId = config.brainId || `brain_${Date.now()}`;
        this.brainName = config.brainName || 'AI Eye Test';

        this.simulatedMode = config.simulatedMode !== undefined ? config.simulatedMode : true;
        this.connectionStatus = 'disconnected';
        this.commandLog = [];
        this.listeners = new Map();
        this.heartbeatInterval = null;

        // Chart ID mapping (logical name → CV-5000 chart ID)
        // From curl_API.md Section 3: Chart Controls
        this.chartMap = {
            'echart_400':               'chart_9',
            'snellen_chart_200_150':    'chart_10',
            'snellen_chart_100_80':     'chart_11',
            'snellen_chart_70_60_50':   'chart_12',
            'snellen_chart_40_30_25':   'chart_13',
            'snellen_chart_20_15_10':   'chart_14',
            'snellen_chart_20_20_20':   'chart_15',
            'snellen_chart_25_20_15':   'chart_16',
            'duochrome':                'chart_17',
            'jcc_chart':                'chart_19',
            'bino_chart':               'chart_20',
            'near_chart':               'chart_5',
        };

        // All charts for Phase A (Distance Vision)
        this.allCharts = [
            'echart_400',
            'snellen_chart_200_150',
            'snellen_chart_100_80',
            'snellen_chart_70_60_50',
            'snellen_chart_40_30_25',
            'snellen_chart_25_20_15',
            'snellen_chart_20_20_20',
            'snellen_chart_20_15_10',
        ];

        // Snellen charts only (for refraction phases B & D)
        this.snellenCharts = this.allCharts.slice(1);

        // VA mapping
        this.chartVA = {
            'echart_400':               '20/400',
            'snellen_chart_200_150':    '20/200',
            'snellen_chart_100_80':     '20/100',
            'snellen_chart_70_60_50':   '20/70',
            'snellen_chart_40_30_25':   '20/40',
            'snellen_chart_25_20_15':   '20/25',
            'snellen_chart_20_20_20':   '20/20',
            'snellen_chart_20_15_10':   '20/15',
        };

        // VA size options per chart (from curl_API.md Section 3.1)
        this.chartSizeOptions = {
            'chart_10': ['200', '150'],
            'chart_11': ['100', '80'],
            'chart_12': ['70', '60', '50'],
            'chart_13': ['40', '30', '25'],
            'chart_14': ['20', '15', '10'],
            'chart_15': ['20_1', '20_2', '20_3'],
            'chart_16': ['25', '20', '15'],
            'chart_20': ['R', 'L'],
        };

        // Current machine state (internal tracking)
        this.state = {
            r_sph: 0.0, r_cyl: 0.0, r_axis: 180.0, r_add: 0.0,
            l_sph: 0.0, l_cyl: 0.0, l_axis: 180.0, l_add: 0.0,
            pd: 63.0,
            aux_lens: 'BINO',
            chart: '',
        };
    }

    // ─── Event System ─────────────────────────────
    on(event, cb) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(cb);
    }
    emit(event, data) {
        (this.listeners.get(event) || []).forEach(cb => cb(data));
    }

    // ═══════════════════════════════════════════════
    // DEVICE MANAGEMENT (Multi-Brain)
    // ═══════════════════════════════════════════════

    /**
     * List available phoropter devices from the broker.
     * GET /devices or GET /devices?all=true
     */
    async listDevices(showAll = false) {
        const url = `${this.baseUrl}/devices${showAll ? '?all=true' : ''}`;
        this._log('DEVICE', `Listing devices (all=${showAll})`);

        if (this.simulatedMode) {
            return [{ id: 'simulated-1', status: 'AVAILABLE', name: 'Simulated CV-5000' }];
        }

        try {
            const resp = await fetch(url);
            const data = await resp.json();
            this.emit('devices-loaded', data);
            return data;
        } catch (err) {
            this._log('ERROR', `List devices failed: ${err.message}`);
            this.emit('error', { type: 'device-list', error: err.message });
            return [];
        }
    }

    /**
     * Get single device info.
     * GET /devices/{Phoropter-ID}
     */
    async getDevice(deviceId) {
        if (this.simulatedMode) return { id: deviceId, status: 'AVAILABLE' };

        try {
            const resp = await fetch(`${this.baseUrl}/devices/${deviceId || this.phoroptertId}`);
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Get device failed: ${err.message}`);
            return null;
        }
    }

    /**
     * Acquire exclusive access to a phoropter device.
     * POST /devices/{Phoropter-ID}/acquire
     * Body: { brain_id, name }
     */
    async acquireDevice(deviceId) {
        this.phoroptertId = deviceId || this.phoroptertId;
        this._log('DEVICE', `Acquiring ${this.phoroptertId} as ${this.brainId}`);

        if (this.simulatedMode) {
            this.connectionStatus = 'acquired';
            this.emit('device-acquired', { id: this.phoroptertId, simulated: true });
            return { status: 'SUCCESS' };
        }

        try {
            const resp = await fetch(`${this.baseUrl}/devices/${this.phoroptertId}/acquire`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ brain_id: this.brainId, name: this.brainName }),
            });
            const data = await resp.json();

            if (data.status === 'SUCCESS' || resp.ok) {
                this.connectionStatus = 'acquired';
                this.emit('device-acquired', { id: this.phoroptertId, data });
                this._startHeartbeat();
                this._log('DEVICE', `Acquired ${this.phoroptertId}`);
            } else {
                this._log('ERROR', `Acquire failed: ${data.reason || JSON.stringify(data)}`);
                this.emit('error', { type: 'acquire', data });
            }

            return data;
        } catch (err) {
            this._log('ERROR', `Acquire failed: ${err.message}`);
            this.emit('error', { type: 'acquire', error: err.message });
            return { status: 'FAILED', reason: err.message };
        }
    }

    /**
     * Release the device lock.
     * POST /devices/{Phoropter-ID}/release
     */
    async releaseDevice() {
        this._stopHeartbeat();
        this._log('DEVICE', `Releasing ${this.phoroptertId}`);

        if (this.simulatedMode) {
            this.connectionStatus = 'disconnected';
            this.emit('device-released', { id: this.phoroptertId });
            return { status: 'SUCCESS' };
        }

        try {
            const resp = await fetch(`${this.baseUrl}/devices/${this.phoroptertId}/release`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ brain_id: this.brainId }),
            });
            this.connectionStatus = 'disconnected';
            this.emit('device-released', { id: this.phoroptertId });
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Release failed: ${err.message}`);
            return { status: 'FAILED', reason: err.message };
        }
    }

    /**
     * Send heartbeat to keep the device lock alive.
     * POST /devices/{Phoropter-ID}/heartbeat (every 15s, auto-release after 60s)
     */
    async sendHeartbeat() {
        if (this.simulatedMode) return { status: 'ok' };

        try {
            const resp = await fetch(`${this.baseUrl}/devices/${this.phoroptertId}/heartbeat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ brain_id: this.brainId }),
            });
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Heartbeat failed: ${err.message}`);
            return { status: 'FAILED' };
        }
    }

    _startHeartbeat() {
        this._stopHeartbeat();
        this.heartbeatInterval = setInterval(() => this.sendHeartbeat(), 15000);
        this._log('DEVICE', 'Heartbeat started (every 15s)');
    }

    _stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }

    // ═══════════════════════════════════════════════
    // OUTPUT 2: Chart Control Commands
    // ═══════════════════════════════════════════════

    /**
     * Display a chart on the phoropter.
     * POST /phoropter/{id}/run-tests
     * Payload: { test_cases: [{ chart: { tab, chart_items } }] }
     */
    async setChart(chartName, size = null, tab = 'Chart1') {
        const chartId = this.chartMap[chartName];
        if (!chartId) {
            console.warn(`Unknown chart: ${chartName}`);
            return;
        }

        const chartItems = size ? [chartId, String(size)] : [chartId];
        const payload = {
            test_cases: [{ chart: { tab, chart_items: chartItems } }]
        };

        this.state.chart = chartName;
        this._log('CHART', `${chartName}${size ? ` size=${size}` : ''}`);
        this.emit('state-update', this.getState());
        return this._sendCommand(payload);
    }

    async setChartNear() {
        return this.setChart('near_chart', null, 'Chart5');
    }

    // ═══════════════════════════════════════════════
    // OUTPUT 4: Phoropter Control Commands
    // ═══════════════════════════════════════════════

    /**
     * Set power and aux_lens.
     * POST /phoropter/{id}/run-tests
     * Payload: { test_cases: [{ case_id, aux_lens, right_eye:{sph,cyl,axis}, left_eye:{sph,cyl,axis} }] }
     */
    async setPower(params = {}) {
        const testCase = { case_id: 1 };
        const rightEye = {};
        const leftEye = {};

        if (params.r_sph !== undefined) { rightEye.sph = params.r_sph; this.state.r_sph = params.r_sph; }
        if (params.r_cyl !== undefined) { rightEye.cyl = params.r_cyl; this.state.r_cyl = params.r_cyl; }
        if (params.r_axis !== undefined) { rightEye.axis = params.r_axis; this.state.r_axis = params.r_axis; }
        if (params.r_add !== undefined) { rightEye.add = params.r_add; this.state.r_add = params.r_add; }
        if (params.l_sph !== undefined) { leftEye.sph = params.l_sph; this.state.l_sph = params.l_sph; }
        if (params.l_cyl !== undefined) { leftEye.cyl = params.l_cyl; this.state.l_cyl = params.l_cyl; }
        if (params.l_axis !== undefined) { leftEye.axis = params.l_axis; this.state.l_axis = params.l_axis; }
        if (params.l_add !== undefined) { leftEye.add = params.l_add; this.state.l_add = params.l_add; }

        if (Object.keys(rightEye).length) testCase.right_eye = rightEye;
        if (Object.keys(leftEye).length) testCase.left_eye = leftEye;

        // Map occluder names to aux_lens values
        if (params.occluder) {
            const auxMap = {
                'Left_Occluded': 'AuxLensL',   // occludes Left → tests Right
                'Right_Occluded': 'AuxLensR',   // occludes Right → tests Left
                'BINO': 'BINO',
            };
            testCase.aux_lens = auxMap[params.occluder] || params.occluder;
            this.state.aux_lens = testCase.aux_lens;
        }
        if (params.aux_lens) {
            testCase.aux_lens = params.aux_lens;
            this.state.aux_lens = params.aux_lens;
        }

        const desc = `R(${this._fd(this.state.r_sph)}/${this._fd(this.state.r_cyl)}/${this.state.r_axis}) ` +
                     `L(${this._fd(this.state.l_sph)}/${this._fd(this.state.l_cyl)}/${this.state.l_axis}) Aux:${testCase.aux_lens || '-'}`;
        this._log('POWER', desc);
        this.emit('state-update', this.getState());

        // Send power command
        await this._sendCommand({ test_cases: [testCase] });

        // Also set JCC eye mode for occluder changes
        if (params.occluder && !params._skipJccMode) {
            const jccMap = { 'Left_Occluded': 'R', 'Right_Occluded': 'L', 'BINO': 'BINO' };
            const jccMode = jccMap[params.occluder];
            if (jccMode) await this.jccControl(jccMode);
        }
    }

    /**
     * Set power with previous state for accurate click calculations.
     * Recommended mode — provides prev_right_eye/prev_left_eye/prev_aux_lens.
     */
    async setPowerWithPrevState(params) {
        const testCase = {
            case_id: 1,
            prev_right_eye: { sph: params.prev_r_sph, cyl: params.prev_r_cyl, axis: params.prev_r_axis },
            prev_left_eye: { sph: params.prev_l_sph, cyl: params.prev_l_cyl, axis: params.prev_l_axis },
            right_eye: { sph: params.r_sph, cyl: params.r_cyl, axis: params.r_axis },
            left_eye: { sph: params.l_sph, cyl: params.l_cyl, axis: params.l_axis },
        };

        if (params.prev_r_add !== undefined) testCase.prev_right_eye.add = params.prev_r_add;
        if (params.prev_l_add !== undefined) testCase.prev_left_eye.add = params.prev_l_add;
        if (params.r_add !== undefined) { testCase.right_eye.add = params.r_add; this.state.r_add = params.r_add; }
        if (params.l_add !== undefined) { testCase.left_eye.add = params.l_add; this.state.l_add = params.l_add; }
        if (params.prev_aux_lens) testCase.prev_aux_lens = params.prev_aux_lens;
        if (params.aux_lens) testCase.aux_lens = params.aux_lens;

        // Update internal state
        this.state.r_sph = params.r_sph;
        this.state.r_cyl = params.r_cyl;
        this.state.r_axis = params.r_axis;
        this.state.l_sph = params.l_sph;
        this.state.l_cyl = params.l_cyl;
        this.state.l_axis = params.l_axis;
        if (params.aux_lens) this.state.aux_lens = params.aux_lens;

        this._log('POWER_PREV', `R(${this._fd(params.r_sph)}) L(${this._fd(params.l_sph)})`);
        this.emit('state-update', this.getState());
        return this._sendCommand({ test_cases: [testCase] });
    }

    /**
     * Perform JCC operation.
     * POST /phoropter/{id}/run-tests
     * Payload: { test_cases: [{ jcc: action }] }
     *
     * Actions: "handle" | "increase" | "decrease" | "power_axis_switch" | "R" | "L" | "BINO"
     */
    async jccControl(action) {
        const payload = { test_cases: [{ jcc: action }] };
        this._log('JCC', action);
        return this._sendCommand(payload);
    }

    /**
     * Activate pinhole.
     * POST /phoropter/{id}/pinhole
     */
    async setPinhole() {
        this._log('PINHOLE', 'Activated');
        if (this.simulatedMode) return { success: true, simulated: true };

        try {
            const resp = await fetch(`${this.baseUrl}/phoropter/${this.phoroptertId}/pinhole`, { method: 'POST' });
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Pinhole failed: ${err.message}`);
            return { success: false, error: err.message };
        }
    }

    /**
     * Set occluder via menu shortcut.
     * POST /phoropter/{id}/occluder
     */
    async setOccluder() {
        this._log('OCCLUDER', 'Menu shortcut');
        if (this.simulatedMode) return { success: true, simulated: true };

        try {
            const resp = await fetch(`${this.baseUrl}/phoropter/${this.phoroptertId}/occluder`, { method: 'POST' });
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Occluder failed: ${err.message}`);
            return { success: false, error: err.message };
        }
    }

    /**
     * Reset phoropter to 0/0/180 baseline.
     * POST /phoropter/{id}/reset
     */
    async resetPhoropter() {
        this.state = {
            r_sph: 0.0, r_cyl: 0.0, r_axis: 180.0, r_add: 0.0,
            l_sph: 0.0, l_cyl: 0.0, l_axis: 180.0, l_add: 0.0,
            pd: 63.0, aux_lens: 'BINO', chart: '',
        };
        this._log('RESET', 'Phoropter reset to 0/0/180');
        this.emit('state-update', this.getState());

        if (this.simulatedMode) return { success: true, simulated: true };

        try {
            const resp = await fetch(`${this.baseUrl}/phoropter/${this.phoroptertId}/reset`, { method: 'POST' });
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Reset failed: ${err.message}`);
            return { success: false, error: err.message };
        }
    }

    /**
     * Sync internal state without physical clicks.
     * POST /phoropter/{id}/sync-state
     * Useful when brain knows the state better than the agent.
     */
    async syncState(state) {
        const payload = {};
        if (state.right_eye) payload.right_eye = state.right_eye;
        if (state.left_eye) payload.left_eye = state.left_eye;
        if (state.aux_lens) payload.aux_lens = state.aux_lens;
        if (state.pd) payload.pd = state.pd;

        this._log('SYNC', `State sync: ${JSON.stringify(payload).substring(0, 100)}`);

        if (this.simulatedMode) return { success: true, simulated: true };

        try {
            const resp = await fetch(`${this.baseUrl}/phoropter/${this.phoroptertId}/sync-state`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            return resp.json();
        } catch (err) {
            this._log('ERROR', `Sync failed: ${err.message}`);
            return { success: false, error: err.message };
        }
    }

    /**
     * Capture live screenshot of the agent's screen.
     * POST /phoropter/{id}/screenshot
     * Returns base64-encoded JPEG string.
     */
    async captureScreenshot() {
        this._log('SCREENSHOT', 'Capturing');

        if (this.simulatedMode) return null;

        try {
            const resp = await fetch(`${this.baseUrl}/phoropter/${this.phoroptertId}/screenshot`, {
                method: 'POST',
                headers: { 'x-brain-id': this.brainId },
            });
            const base64 = await resp.text();
            this.emit('screenshot', { base64 });
            return base64;
        } catch (err) {
            this._log('ERROR', `Screenshot failed: ${err.message}`);
            return null;
        }
    }

    // ─── Communication ────────────────────────────

    async _sendCommand(payload) {
        const cmd = { type: 'run-tests', params: payload, timestamp: new Date().toISOString() };
        this.emit('command', cmd);

        if (this.simulatedMode) {
            return { success: true, simulated: true };
        }

        const endpoint = `${this.baseUrl}/phoropter/${this.phoroptertId}/run-tests`;
        try {
            const resp = await fetch(endpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            return resp.json();
        } catch (err) {
            console.error('CV-5000 command failed:', err);
            this._log('ERROR', err.message);
            return { success: false, error: err.message };
        }
    }

    // ─── State Access ─────────────────────────────

    getState() { return { ...this.state }; }
    getChartVA(chartName) { return this.chartVA[chartName] || '?'; }

    // ─── Logging ──────────────────────────────────

    _log(type, detail) {
        const entry = { timestamp: new Date().toISOString(), type, detail, simulated: this.simulatedMode };
        this.commandLog.push(entry);
        this.emit('command-log', entry);
    }

    getCommandLog() { return [...this.commandLog]; }
    _fd(v) { return (v >= 0 ? '+' : '') + v.toFixed(2); }

    // ─── Cleanup ──────────────────────────────────

    async destroy() {
        this._stopHeartbeat();
        if (this.connectionStatus === 'acquired') {
            await this.releaseDevice();
        }
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CV5000Protocol;
}
