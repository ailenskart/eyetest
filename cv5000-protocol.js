/**
 * Topcon CV-5000 Phoropter + Chart Control Protocol
 *
 * Maps to the reference implementation's API patterns:
 *   - set_chart(chart_name, size?)     → Output 2: Chart Control
 *   - set_power(params)                → Output 4: Phoropter Control
 *   - set_power_with_prev_state(params)→ Output 4: with delta calculation
 *   - jcc_control(action)              → Output 4: JCC operations
 *   - set_pinhole()                    → Output 4: Pinhole activation
 *   - reset_phoropter()                → Output 4: Reset to baseline
 *
 * Communication modes:
 *   A) HTTP POST to CV-5000 API endpoint (production)
 *   B) Simulated mode (development/testing)
 */

class CV5000Protocol {
    constructor(config = {}) {
        this.baseUrl = config.baseUrl || '';
        this.phoroptertId = config.phoroptertId || 'phoropter-1';
        this.apiEndpoint = `${this.baseUrl}/phoropter/${this.phoroptertId}/run-tests`;
        this.simulatedMode = true;
        this.connectionStatus = 'disconnected';
        this.commandLog = [];
        this.listeners = new Map();

        // Chart ID mapping (logical name → CV-5000 chart ID)
        // Matches reference: interactive_session.py chart_map
        this.chartMap = {
            'echart_400':               'chart_9',
            'snellen_chart_200_150':    'chart_10',
            'snellen_chart_100_80':     'chart_11',
            'snellen_chart_70_60_50':   'chart_12',
            'snellen_chart_40_30_25':   'chart_13',
            'snellen_chart_20_15_10':   'chart_14',
            'snellen_chart_20_20_20':   'chart_15',
            'snellen_20_20':            'chart_15',
            'snellen_chart_25_20_15':   'chart_16',
            'duochrome':                'chart_17',
            'jcc_chart':                'chart_19',
            'bino_chart':               'chart_20',
            'near_chart':               'chart_5',
        };

        // All charts available for Phase A (Distance Vision)
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
        this.snellenCharts = this.allCharts.slice(1); // exclude E-chart

        // Snellen chart to VA mapping
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

        // Current machine state (internal tracking)
        this.state = {
            r_sph: 0.0, r_cyl: 0.0, r_axis: 180.0, r_add: 0.0,
            l_sph: 0.0, l_cyl: 0.0, l_axis: 180.0, l_add: 0.0,
            pd: 63.0,
            occluder: 'BINO',
            chart: '',
            jccMode: null, // 'axis' or 'power'
            jccFlipState: 'flip1',
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

    // ─── Connection ───────────────────────────────
    async connect(config = {}) {
        if (config.baseUrl) {
            this.baseUrl = config.baseUrl;
            this.phoroptertId = config.phoroptertId || this.phoroptertId;
            this.apiEndpoint = `${this.baseUrl}/phoropter/${this.phoroptertId}/run-tests`;
        }

        // Try to connect to real CV-5000 API
        if (this.baseUrl && !config.forceSimulated) {
            try {
                const resp = await fetch(`${this.baseUrl}/health`, { signal: AbortSignal.timeout(3000) });
                if (resp.ok) {
                    this.simulatedMode = false;
                    this.connectionStatus = 'connected';
                    this.emit('connection', { status: 'connected', simulated: false });
                    this._log('SYSTEM', 'Connected to CV-5000 API');
                    return 'connected';
                }
            } catch (e) {
                // Fall through to simulated
            }
        }

        this.simulatedMode = true;
        this.connectionStatus = 'simulated';
        this.emit('connection', { status: 'simulated', simulated: true });
        this._log('SYSTEM', 'Running in simulated mode');
        return 'simulated';
    }

    // ─── Output 2: Chart Control Commands ─────────

    /**
     * Display a chart on the phoropter.
     * @param {string} chartName - Logical chart name (e.g., 'snellen_chart_200_150')
     * @param {string} [size] - Optional VA size highlight (e.g., '40' for 20/40)
     * @param {string} [tab] - Chart tab (default 'Chart1', 'Chart5' for near)
     */
    async setChart(chartName, size = null, tab = 'Chart1') {
        const chartId = this.chartMap[chartName];
        if (!chartId) {
            console.warn(`Unknown chart: ${chartName}`);
            return;
        }

        const chartItems = size ? [chartId, size] : [chartId];
        const payload = {
            test_cases: [{ chart: { tab, chart_items: chartItems } }]
        };

        this.state.chart = chartName;
        this._log('CHART', `${chartName}${size ? ` size=${size}` : ''}`);
        this.emit('state-update', this.getState());
        return this._sendCommand(payload);
    }

    /** Switch to Near Vision chart tab */
    async setChartNear() {
        return this.setChart('near_chart', null, 'Chart5');
    }

    // ─── Output 4: Phoropter Control Commands ─────

    /**
     * Set power and occluder on the phoropter.
     * Matches reference: interactive_session.py set_power()
     */
    async setPower(params = {}) {
        const { r_sph, r_cyl, r_axis, l_sph, l_cyl, l_axis,
                r_add, l_add, occluder } = params;

        const payload = { test_cases: [{}] };
        const rightEye = {};
        const leftEye = {};

        if (r_sph !== undefined) { rightEye.sph = r_sph; this.state.r_sph = r_sph; }
        if (r_cyl !== undefined) { rightEye.cyl = r_cyl; this.state.r_cyl = r_cyl; }
        if (r_axis !== undefined) { rightEye.axis = r_axis; this.state.r_axis = r_axis; }
        if (r_add !== undefined) { rightEye.add = r_add; this.state.r_add = r_add; }
        if (l_sph !== undefined) { leftEye.sph = l_sph; this.state.l_sph = l_sph; }
        if (l_cyl !== undefined) { leftEye.cyl = l_cyl; this.state.l_cyl = l_cyl; }
        if (l_axis !== undefined) { leftEye.axis = l_axis; this.state.l_axis = l_axis; }
        if (l_add !== undefined) { leftEye.add = l_add; this.state.l_add = l_add; }

        if (Object.keys(rightEye).length) payload.test_cases[0].right_eye = rightEye;
        if (Object.keys(leftEye).length) payload.test_cases[0].left_eye = leftEye;

        // Occluder → JCC eye mode mapping (for non-JCC phases)
        let jccEyeMode = null;
        if (occluder) {
            this.state.occluder = occluder;
            if (occluder === 'Left_Occluded') jccEyeMode = 'R';
            else if (occluder === 'Right_Occluded') jccEyeMode = 'L';
            else if (occluder === 'BINO') jccEyeMode = 'BINO';
        }

        const desc = `R(${this._fd(this.state.r_sph)}/${this._fd(this.state.r_cyl)}/${this.state.r_axis}) ` +
                     `L(${this._fd(this.state.l_sph)}/${this._fd(this.state.l_cyl)}/${this.state.l_axis}) Occ:${occluder || '-'}`;
        this._log('POWER', desc);
        this.emit('state-update', this.getState());

        await this._sendCommand(payload);

        // Set JCC eye mode for non-JCC phases
        if (jccEyeMode) {
            await this.jccControl(jccEyeMode);
        }
    }

    /**
     * Set power with previous state for accurate delta calculations.
     * Matches reference: interactive_session.py set_power_with_prev_state()
     */
    async setPowerWithPrevState(params) {
        const payload = {
            test_cases: [{
                case_id: 1,
                prev_right_eye: { sph: params.prev_r_sph, cyl: params.prev_r_cyl, axis: params.prev_r_axis },
                prev_left_eye: { sph: params.prev_l_sph, cyl: params.prev_l_cyl, axis: params.prev_l_axis },
                right_eye: { sph: params.r_sph, cyl: params.r_cyl, axis: params.r_axis },
                left_eye: { sph: params.l_sph, cyl: params.l_cyl, axis: params.l_axis },
            }]
        };

        if (params.prev_r_add !== undefined) payload.test_cases[0].prev_right_eye.add = params.prev_r_add;
        if (params.prev_l_add !== undefined) payload.test_cases[0].prev_left_eye.add = params.prev_l_add;
        if (params.r_add !== undefined) { payload.test_cases[0].right_eye.add = params.r_add; this.state.r_add = params.r_add; }
        if (params.l_add !== undefined) { payload.test_cases[0].left_eye.add = params.l_add; this.state.l_add = params.l_add; }
        if (params.prev_aux_lens) payload.test_cases[0].prev_aux_lens = params.prev_aux_lens;
        if (params.aux_lens) payload.test_cases[0].aux_lens = params.aux_lens;

        // Update internal state
        this.state.r_sph = params.r_sph;
        this.state.r_cyl = params.r_cyl;
        this.state.r_axis = params.r_axis;
        this.state.l_sph = params.l_sph;
        this.state.l_cyl = params.l_cyl;
        this.state.l_axis = params.l_axis;

        this._log('POWER_PREV', `R(${this._fd(params.r_sph)}) L(${this._fd(params.l_sph)})`);
        this.emit('state-update', this.getState());
        return this._sendCommand(payload);
    }

    /**
     * Perform JCC operation.
     * @param {string} action - 'handle'|'increase'|'decrease'|'power_axis_switch'|'R'|'L'|'BINO'
     */
    async jccControl(action) {
        const payload = { test_cases: [{ jcc: action }] };
        this._log('JCC', action);
        return this._sendCommand(payload);
    }

    /** Activate pinhole on the phoropter */
    async setPinhole() {
        const url = `${this.baseUrl}/phoropter/${this.phoroptertId}/pinhole`;
        this._log('PINHOLE', 'Activated');
        if (!this.simulatedMode) {
            return fetch(url, { method: 'POST' });
        }
    }

    /** Reset phoropter to neutral/baseline state */
    async resetPhoropter() {
        this.state = {
            r_sph: 0.0, r_cyl: 0.0, r_axis: 180.0, r_add: 0.0,
            l_sph: 0.0, l_cyl: 0.0, l_axis: 180.0, l_add: 0.0,
            pd: 63.0, occluder: 'BINO', chart: '', jccMode: null, jccFlipState: 'flip1',
        };
        this._log('RESET', 'Phoropter reset to 0/0/180');
        this.emit('state-update', this.getState());

        if (!this.simulatedMode) {
            return fetch(`${this.baseUrl}/phoropter/${this.phoroptertId}/reset`, { method: 'POST' });
        }
    }

    // ─── Communication ────────────────────────────

    async _sendCommand(payload) {
        if (this.simulatedMode) {
            // Simulated mode: just return success
            return { success: true, simulated: true };
        }

        try {
            const resp = await fetch(this.apiEndpoint, {
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

    getState() {
        return { ...this.state };
    }

    getChartVA(chartName) {
        return this.chartVA[chartName] || '?';
    }

    // ─── Logging ──────────────────────────────────

    _log(type, detail) {
        const entry = {
            timestamp: new Date().toISOString(),
            type,
            detail,
            simulated: this.simulatedMode,
        };
        this.commandLog.push(entry);
        this.emit('command-log', entry);
    }

    getCommandLog() { return [...this.commandLog]; }

    _fd(v) {
        return (v >= 0 ? '+' : '') + v.toFixed(2);
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = CV5000Protocol;
}
