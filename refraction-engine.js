/**
 * Subjective Refraction Engine — 10-Phase State Machine
 *
 * Ported from reference: eye_test_engine/interactive_session.py
 * Implements the complete clinical subjective refraction protocol:
 *
 *   Phase A: Distance Vision (BINO + E-chart)
 *   Phase B: Right Eye Refraction (Left_Occluded + Snellen)
 *   Phase E: JCC Axis Right (jcc_chart + Flip1/Flip2)
 *   Phase F: JCC Power Right (jcc_chart + Flip1/Flip2)
 *   Phase G: Duochrome Right (duochrome chart)
 *   Phase D: Left Eye Refraction (Right_Occluded + Snellen)
 *   Phase H: JCC Axis Left (jcc_chart + Flip1/Flip2)
 *   Phase I: JCC Power Left (jcc_chart + Flip1/Flip2)
 *   Phase J: Duochrome Left (duochrome chart)
 *   Phase K: Binocular Balance (BINO + bino_chart)
 *
 * Rules (from reference docs):
 *   - SPH: -0.25D steps | CYL: ±0.25D | AXIS: ±5° (±10° for MUCH better)
 *   - "Able to read" → next smaller chart
 *   - "Blurry" → add -0.25D SPH, stay on same chart
 *   - "Unable to read" → add -0.25D SPH, increment counter
 *   - Exit to JCC: 2 consecutive "Unable to read" with SPH changes, OR 20/20 reached
 *   - JCC: Flip1 (2s) → Flip2 → patient choice → adjust → repeat until "Both Same" or reversal
 *   - Duochrome: Red → -0.25D SPH (RAM), Green → +0.25D SPH (GAP)
 *   - Binocular Balance: Top blurry → +0.25D L_SPH, Bottom blurry → +0.25D R_SPH
 */

class RefractionEngine {
    constructor(cv5000) {
        this.cv5000 = cv5000;
        this.listeners = new Map();

        // ── Phase definitions (matching reference) ──
        this.phaseNames = {
            'distance_vision':       'Phase A: Distance Vision (Step 2.1)',
            'right_eye_refraction':  'Phase B: Right Eye Refraction (Step 6.1)',
            'jcc_axis_right':        'Phase E: JCC Axis Right (Step 6.2)',
            'jcc_power_right':       'Phase F: JCC Power Right (Step 6.2)',
            'duochrome_right':       'Phase G: Duochrome Right (Step 6.2)',
            'left_eye_refraction':   'Phase D: Left Eye Refraction (Step 6.3)',
            'jcc_axis_left':         'Phase H: JCC Axis Left (Step 6.4)',
            'jcc_power_left':        'Phase I: JCC Power Left (Step 6.4)',
            'duochrome_left':        'Phase J: Duochrome Left (Step 6.4)',
            'binocular_balance':     'Phase K: Binocular Balance (Step 6.5)',
        };

        this.phaseOrder = [
            'distance_vision',
            'right_eye_refraction',
            'jcc_axis_right',
            'jcc_power_right',
            'duochrome_right',
            'left_eye_refraction',
            'jcc_axis_left',
            'jcc_power_left',
            'duochrome_left',
            'binocular_balance',
        ];

        // ── Current state ──
        this.currentPhase = 'distance_vision';
        this.currentRow = this._initRow();
        this.sessionHistory = [];

        // ── Patient data (Input 1) ──
        this.patientData = {
            age: null, gender: null,
            autorefraction: { OD: { sph: 0, cyl: 0, axis: 180 }, OS: { sph: 0, cyl: 0, axis: 180 } },
            lensometry: { OD: { sph: 0, cyl: 0, axis: 180, add: 0 }, OS: { sph: 0, cyl: 0, axis: 180, add: 0 }, hasOldRx: false },
            pd: 63,
        };

        // ── Refraction tracking ──
        this.currentChartIndex = 0;
        this.unableReadCount = 0;

        // ── JCC tracking ──
        this.jccFlipState = 'flip1';
        this.jccLastChoice = null;
        this.jccSameChoiceCount = 0;
        this.jccPowerZeroFlip1Count = 0;

        // ── Duochrome tracking ──
        this.duochromeLastChoice = null;
        this.duochromeSameChoiceCount = 0;

        // ── Prev State (one-level undo) ──
        this.previousState = null;
        this.showPrevStateOption = false;

        // ── Safety flags ──
        this.flags = [];
        this.examStarted = false;
        this.examComplete = false;
        this.rowCounter = 0;
    }

    // ─── Event System ──────────────────────────────
    on(event, cb) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(cb);
    }
    emit(event, data) {
        (this.listeners.get(event) || []).forEach(cb => cb(data));
    }

    // ─── Init ──────────────────────────────────────
    _initRow() {
        return {
            r_sph: 0.0, r_cyl: 0.0, r_axis: 180.0, r_add: 0.0,
            l_sph: 0.0, l_cyl: 0.0, l_axis: 180.0, l_add: 0.0,
            occluder_state: 'BINO',
            chart_display: '',
        };
    }

    _copyRowState() {
        return { ...this.currentRow };
    }

    _updateState(params) {
        if (params.occluder !== undefined) this.currentRow.occluder_state = params.occluder;
        if (params.chart !== undefined) this.currentRow.chart_display = params.chart;
    }

    // ─── Patient Data (Input 1) ────────────────────
    setPatientData(data) {
        Object.assign(this.patientData, data);
    }

    // ─── Progress ──────────────────────────────────
    getProgress() {
        const idx = this.phaseOrder.indexOf(this.currentPhase);
        return {
            currentPhase: this.currentPhase,
            phaseName: this.phaseNames[this.currentPhase] || this.currentPhase,
            phaseIndex: idx,
            totalPhases: this.phaseOrder.length,
            percent: Math.round((Math.max(0, idx) / (this.phaseOrder.length - 1)) * 100),
            phases: this.phaseOrder.map((p, i) => ({
                id: p,
                name: this.phaseNames[p],
                status: i < idx ? 'completed' : i === idx ? 'active' : 'pending',
            })),
            flags: this.flags,
        };
    }

    getPower() {
        return {
            right: { sph: this.currentRow.r_sph, cyl: this.currentRow.r_cyl, axis: this.currentRow.r_axis, add: this.currentRow.r_add },
            left: { sph: this.currentRow.l_sph, cyl: this.currentRow.l_cyl, axis: this.currentRow.l_axis, add: this.currentRow.l_add },
        };
    }

    // ─── Build Response (matches reference _build_response) ──
    _buildResponse() {
        const phase = this.currentPhase;
        const response = {
            phase: this.phaseNames[phase] || phase,
            phaseId: phase,
            question: this._getQuestion(),
            intents: this._getIntents(),
            power: this.getPower(),
            occluder: this.currentRow.occluder_state,
            chart: this.currentRow.chart_display,
            chartVA: this.cv5000.getChartVA(this.currentRow.chart_display),
            progress: this.getProgress(),
        };

        // Add chart_info for phases with chart selection
        if (phase === 'distance_vision') {
            response.chart_info = {
                available_charts: this.cv5000.allCharts,
                current_index: this.currentChartIndex,
                current_chart: this.cv5000.allCharts[this.currentChartIndex],
            };
        } else if (phase === 'right_eye_refraction' || phase === 'left_eye_refraction') {
            response.chart_info = {
                available_charts: this.cv5000.snellenCharts,
                current_index: this.currentChartIndex,
                current_chart: this.cv5000.snellenCharts[this.currentChartIndex],
            };
        }

        return response;
    }

    _getQuestion() {
        switch (this.currentPhase) {
            case 'distance_vision':
                return 'Please look at the chart. Are you able to see the big E clearly?';
            case 'right_eye_refraction':
                return "I'm covering your left eye. Please read the line you can see clearly.";
            case 'left_eye_refraction':
                return "I'm covering your right eye. Please read the line you can see clearly.";
            case 'jcc_axis_right': case 'jcc_axis_left':
                return this.jccFlipState === 'flip1'
                    ? 'Focus on the dot chart. This is Flip 1. (Flip 2 will show automatically in 2 seconds)'
                    : 'Now this is Flip 2. Which was better?';
            case 'jcc_power_right': case 'jcc_power_left':
                return this.jccFlipState === 'flip1'
                    ? 'Focus on the dot chart. This is Flip 1. (Flip 2 will show automatically in 2 seconds)'
                    : 'Now this is Flip 2. Which was better?';
            case 'duochrome_right': case 'duochrome_left':
                return 'Which is clearer: the letters on the red side or the green side, or are they the same?';
            case 'binocular_balance':
                return 'You should see 2 lines at top and bottom. Focus on the last letter. Which one is less blurry than the others (if there is one)?';
            default:
                return 'Please describe what you see.';
        }
    }

    _getIntents() {
        const phase = this.currentPhase;
        let intents = [];

        switch (phase) {
            case 'distance_vision':
                intents = ['Able to read', 'Blurry', 'Unable to read'];
                break;
            case 'right_eye_refraction':
            case 'left_eye_refraction':
                intents = ['Able to read', 'Blurry', 'Unable to read'];
                if (this.showPrevStateOption && this.previousState) {
                    intents.push('Prev State');
                }
                break;
            case 'jcc_axis_right': case 'jcc_axis_left':
                if (this.jccFlipState === 'flip1') {
                    intents = [];
                } else {
                    intents = [
                        'Flip 1 was better (GAP Axis - increase axis by 5\u00B0)',
                        'Flip 2 was better (RAM Axis - decrease axis by 5\u00B0)',
                        'Flip 1 was MUCH better (GAP Axis - increase axis by 10\u00B0)',
                        'Flip 2 was MUCH better (RAM Axis - decrease axis by 10\u00B0)',
                        'Both Same (no change needed)',
                        'Repeat (show Flip 1 and Flip 2 again)',
                    ];
                }
                break;
            case 'jcc_power_right': case 'jcc_power_left':
                if (this.jccFlipState === 'flip1') {
                    intents = [];
                } else {
                    intents = [
                        'Flip 1 was better (GAP Power - increase cylinder by 0.25D)',
                        'Flip 2 was better (RAM Power - decrease cylinder by 0.25D)',
                        'Flip 1 was MUCH better (GAP Power - increase cylinder by 0.50D)',
                        'Flip 2 was MUCH better (RAM Power - decrease cylinder by 0.50D)',
                        'Both Same (no change needed)',
                        'Repeat (show Flip 1 and Flip 2 again)',
                    ];
                }
                break;
            case 'duochrome_right': case 'duochrome_left':
                intents = ['Red', 'Green', 'Both Same'];
                break;
            case 'binocular_balance':
                intents = ['Top is blurry [Right Eye]', 'Bottom is blurry [Left Eye]', 'Both are same'];
                if (this.showPrevStateOption && this.previousState) {
                    intents.push('Prev State');
                }
                break;
        }

        return intents;
    }

    // ─── Start Exam ────────────────────────────────
    async startExam() {
        this.examStarted = true;
        this.currentPhase = 'distance_vision';

        // Apply AR starting values if available
        const ar = this.patientData.autorefraction;
        if (ar.OD.sph !== 0 || ar.OD.cyl !== 0 || ar.OS.sph !== 0 || ar.OS.cyl !== 0) {
            this.currentRow.r_sph = ar.OD.sph;
            this.currentRow.r_cyl = ar.OD.cyl;
            this.currentRow.r_axis = ar.OD.axis;
            this.currentRow.l_sph = ar.OS.sph;
            this.currentRow.l_cyl = ar.OS.cyl;
            this.currentRow.l_axis = ar.OS.axis;

            await this.cv5000.setPower({
                r_sph: ar.OD.sph, r_cyl: ar.OD.cyl, r_axis: ar.OD.axis,
                l_sph: ar.OS.sph, l_cyl: ar.OS.cyl, l_axis: ar.OS.axis,
                occluder: 'BINO',
            });
        }

        this.currentChartIndex = 0;
        await this.cv5000.setChart(this.cv5000.allCharts[0]);
        this.currentRow.occluder_state = 'BINO';
        this.currentRow.chart_display = this.cv5000.allCharts[0];

        this.emit('phase-change', this.getProgress());
        return this._buildResponse();
    }

    // ─── Process Response (main entry point) ───────
    async processResponse(intent) {
        this.rowCounter++;
        this.sessionHistory.push({
            row: this.rowCounter,
            timestamp: new Date().toISOString(),
            phase: this.currentPhase,
            intent,
            power: this.getPower(),
            occluder: this.currentRow.occluder_state,
            chart: this.currentRow.chart_display,
        });

        switch (this.currentPhase) {
            case 'distance_vision':        return this._processDistanceVision(intent);
            case 'right_eye_refraction':   return this._processRefraction('right', intent);
            case 'jcc_axis_right':         return this._processJCCAxis('right', intent);
            case 'jcc_power_right':        return this._processJCCPower('right', intent);
            case 'duochrome_right':        return this._processDuochrome('right', intent);
            case 'left_eye_refraction':    return this._processRefraction('left', intent);
            case 'jcc_axis_left':          return this._processJCCAxis('left', intent);
            case 'jcc_power_left':         return this._processJCCPower('left', intent);
            case 'duochrome_left':         return this._processDuochrome('left', intent);
            case 'binocular_balance':      return this._processBinocularBalance(intent);
            default:
                return { phase: 'complete', status: 'complete', question: 'Test complete!', intents: [] };
        }
    }

    // ═══════════════════════════════════════════════
    // PHASE A: Distance Vision
    // ═══════════════════════════════════════════════
    async _processDistanceVision(intent) {
        if (intent === 'Unable to read') {
            await this.cv5000.setPinhole();
            this.flags.push({ type: 'pinhole_triggered', phase: 'distance_vision', detail: 'Patient unable to read E-chart' });

            const response = this._buildResponse();
            response.question = 'With pinhole: Can you see the E clearly now?';
            response.intents = ['Able to read with pinhole', 'Still unable to read'];
            return response;
        }

        if (intent === 'Still unable to read') {
            this.flags.push({ type: 'pinhole_no_improvement', phase: 'distance_vision', detail: 'Pinhole did not improve vision — possible pathology, needs optometrist review' });
        }

        return this._transitionToRefraction('right');
    }

    // ═══════════════════════════════════════════════
    // PHASE B & D: Eye Refraction (shared logic)
    // ═══════════════════════════════════════════════
    async _transitionToRefraction(eye) {
        this.currentPhase = eye === 'right' ? 'right_eye_refraction' : 'left_eye_refraction';
        this.currentChartIndex = 0;
        this.unableReadCount = 0;
        this.previousState = null;
        this.showPrevStateOption = false;

        const occluder = eye === 'right' ? 'Left_Occluded' : 'Right_Occluded';
        this.currentRow = this._copyRowState();
        this.currentRow.occluder_state = occluder;
        this.currentRow.chart_display = this.cv5000.snellenCharts[0];

        await this.cv5000.setChart(this.cv5000.snellenCharts[0]);
        await this.cv5000.setPower({ occluder });

        this.emit('phase-change', this.getProgress());
        return this._buildResponse();
    }

    async _processRefraction(eye, intent) {
        const sphKey = eye === 'right' ? 'r_sph' : 'l_sph';
        const auxLens = eye === 'right' ? 'AuxLensL' : 'AuxLensR';
        const nextJccPhase = eye === 'right'
            ? () => this._transitionToJCCAxis('right')
            : () => this._transitionToJCCAxis('left');

        // ── Prev State ──
        if (intent === 'Prev State') {
            if (this.previousState) {
                await this.cv5000.setPowerWithPrevState({
                    prev_r_sph: this.currentRow.r_sph, prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
                    prev_l_sph: this.currentRow.l_sph, prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
                    r_sph: this.previousState.r_sph, r_cyl: this.previousState.r_cyl, r_axis: this.previousState.r_axis,
                    l_sph: this.previousState.l_sph, l_cyl: this.previousState.l_cyl, l_axis: this.previousState.l_axis,
                    prev_aux_lens: auxLens, aux_lens: auxLens,
                });
                Object.assign(this.currentRow, this.previousState);
                this.previousState = null;
                this.showPrevStateOption = false;
            }
            return this._buildResponse();
        }

        if (intent !== 'Blurry' && intent !== 'Unable to read') {
            this.showPrevStateOption = false;
        }

        // ── Able to read → next chart ──
        if (intent === 'Able to read') {
            const currentChart = this.cv5000.snellenCharts[this.currentChartIndex];
            if (currentChart === 'snellen_chart_20_20_20') {
                return nextJccPhase();
            }
            if (this.currentChartIndex < this.cv5000.snellenCharts.length - 1) {
                this.currentChartIndex++;
                this.unableReadCount = 0;
                this.currentRow = this._copyRowState();
                this.currentRow.chart_display = this.cv5000.snellenCharts[this.currentChartIndex];
                await this.cv5000.setChart(this.cv5000.snellenCharts[this.currentChartIndex]);
            } else {
                return nextJccPhase();
            }
            return this._buildResponse();
        }

        // ── Blurry / Unable to read → -0.25D SPH ──
        if (intent === 'Blurry' || intent === 'Unable to read') {
            this._savePrevState();
            const prevSph = this.currentRow[sphKey];
            const newSph = prevSph - 0.25;
            this.currentRow = this._copyRowState();
            this.currentRow[sphKey] = newSph;

            await this.cv5000.setPowerWithPrevState({
                prev_r_sph: eye === 'right' ? prevSph : this.currentRow.r_sph,
                prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
                prev_l_sph: eye === 'left' ? prevSph : this.currentRow.l_sph,
                prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
                r_sph: this.currentRow.r_sph, r_cyl: this.currentRow.r_cyl, r_axis: this.currentRow.r_axis,
                l_sph: this.currentRow.l_sph, l_cyl: this.currentRow.l_cyl, l_axis: this.currentRow.l_axis,
                prev_aux_lens: auxLens, aux_lens: auxLens,
            });

            this.showPrevStateOption = true;

            if (intent === 'Blurry') {
                this.unableReadCount = 0;
            } else {
                this.unableReadCount++;
                if (this.unableReadCount >= 2) {
                    return nextJccPhase();
                }
            }
            return this._buildResponse();
        }

        return this._buildResponse();
    }

    _savePrevState() {
        this.previousState = { ...this.currentRow };
    }

    // ═══════════════════════════════════════════════
    // PHASE E/H: JCC Axis
    // ═══════════════════════════════════════════════
    async _transitionToJCCAxis(eye) {
        this.currentPhase = eye === 'right' ? 'jcc_axis_right' : 'jcc_axis_left';
        this.jccFlipState = 'flip1';
        this._resetJCCChoiceTracking();

        const flipPrefix = eye === 'right' ? 'Right_Axis' : 'Left_Axis';
        this.currentRow = this._copyRowState();
        this._updateState({ occluder: `${flipPrefix}_Flip1`, chart: 'jcc_chart' });
        await this.cv5000.setChart('jcc_chart');

        this.emit('phase-change', this.getProgress());
        const response = this._buildResponse();
        response.auto_flip = true;
        response.flip_wait_seconds = 2;
        return response;
    }

    async _processJCCAxis(eye, intent) {
        const axisKey = eye === 'right' ? 'r_axis' : 'l_axis';
        const flipPrefix = eye === 'right' ? 'Right_Axis' : 'Left_Axis';
        const nextPhase = eye === 'right'
            ? () => this._transitionToJCCPower('right')
            : () => this._transitionToJCCPower('left');

        if (this.jccFlipState === 'flip1') {
            if (intent === 'AUTO_FLIP') {
                this.jccFlipState = 'flip2';
                this.currentRow = this._copyRowState();
                this._updateState({ occluder: `${flipPrefix}_Flip2` });
                await this.cv5000.jccControl('handle');
                return this._buildResponse();
            }
            const response = this._buildResponse();
            response.auto_flip = true;
            response.flip_wait_seconds = 2;
            return response;
        }

        // ── Flip 2 responses ──
        if (intent.includes('Repeat')) {
            await this.cv5000.jccControl('handle');
            this.jccFlipState = 'flip1';
            this.currentRow = this._copyRowState();
            this._updateState({ occluder: `${flipPrefix}_Flip1` });
            const response = this._buildResponse();
            response.auto_flip = true;
            response.flip_wait_seconds = 2;
            return response;
        }

        if (intent.includes('Both Same')) {
            return nextPhase();
        }

        let delta = 0;
        let choiceLabel = '';
        if (intent.includes('MUCH better') && (intent.includes('GAP Axis') || intent.includes('Flip 1'))) {
            delta = 10; choiceLabel = 'flip1';
            await this.cv5000.jccControl('increase');
            await this.cv5000.jccControl('increase');
        } else if (intent.includes('GAP Axis') || (intent.includes('Flip 1') && intent.includes('better'))) {
            delta = 5; choiceLabel = 'flip1';
            await this.cv5000.jccControl('increase');
        } else if (intent.includes('MUCH better') && (intent.includes('RAM Axis') || intent.includes('Flip 2'))) {
            delta = -10; choiceLabel = 'flip2';
            await this.cv5000.jccControl('decrease');
            await this.cv5000.jccControl('decrease');
        } else if (intent.includes('RAM Axis') || (intent.includes('Flip 2') && intent.includes('better'))) {
            delta = -5; choiceLabel = 'flip2';
            await this.cv5000.jccControl('decrease');
        }

        if (delta !== 0) {
            const reversal = this._recordJCCChoice(choiceLabel);
            this.currentRow = this._copyRowState();
            this.currentRow[axisKey] += delta;
            if (this.currentRow[axisKey] > 180) this.currentRow[axisKey] -= 180;
            if (this.currentRow[axisKey] < 0) this.currentRow[axisKey] += 180;

            if (reversal) return nextPhase();

            await this.cv5000.jccControl('handle');
            this.jccFlipState = 'flip1';
            this._updateState({ occluder: `${flipPrefix}_Flip1` });
            const response = this._buildResponse();
            response.auto_flip = true;
            response.flip_wait_seconds = 2;
            return response;
        }

        return this._buildResponse();
    }

    // ═══════════════════════════════════════════════
    // PHASE F/I: JCC Power
    // ═══════════════════════════════════════════════
    async _transitionToJCCPower(eye) {
        this.currentPhase = eye === 'right' ? 'jcc_power_right' : 'jcc_power_left';
        this.jccFlipState = 'flip1';
        this._resetJCCChoiceTracking();
        this.jccPowerZeroFlip1Count = 0;

        const flipPrefix = eye === 'right' ? 'Right_Power' : 'Left_Power';
        this.currentRow = this._copyRowState();
        this._updateState({ occluder: `${flipPrefix}_Flip1`, chart: 'jcc_chart' });
        await this.cv5000.jccControl('power_axis_switch');

        this.emit('phase-change', this.getProgress());
        const response = this._buildResponse();
        response.auto_flip = true;
        response.flip_wait_seconds = 2;
        return response;
    }

    async _processJCCPower(eye, intent) {
        const cylKey = eye === 'right' ? 'r_cyl' : 'l_cyl';
        const sphKey = eye === 'right' ? 'r_sph' : 'l_sph';
        const flipPrefix = eye === 'right' ? 'Right_Power' : 'Left_Power';
        const nextPhase = eye === 'right'
            ? () => this._transitionToDuochrome('right')
            : () => this._transitionToDuochrome('left');

        if (this.jccFlipState === 'flip1') {
            if (intent === 'AUTO_FLIP') {
                this.jccFlipState = 'flip2';
                this.currentRow = this._copyRowState();
                this._updateState({ occluder: `${flipPrefix}_Flip2` });
                await this.cv5000.jccControl('handle');
                return this._buildResponse();
            }
            const response = this._buildResponse();
            response.auto_flip = true;
            response.flip_wait_seconds = 2;
            return response;
        }

        if (intent.includes('Repeat')) {
            await this.cv5000.jccControl('handle');
            this.jccFlipState = 'flip1';
            this.currentRow = this._copyRowState();
            this._updateState({ occluder: `${flipPrefix}_Flip1` });
            const response = this._buildResponse();
            response.auto_flip = true;
            response.flip_wait_seconds = 2;
            return response;
        }

        if (intent.includes('Both Same')) {
            return nextPhase();
        }

        const isGAP = intent.includes('GAP Power') || (intent.includes('Flip 1') && intent.includes('better'));
        const isRAM = intent.includes('RAM Power') || (intent.includes('Flip 2') && intent.includes('better'));
        const isMuch = intent.includes('MUCH better');
        const steps = isMuch ? 2 : 1;

        if (isGAP) {
            // CYL = 0 special handling
            if (Math.abs(this.currentRow[cylKey]) < 0.001) {
                this.jccPowerZeroFlip1Count++;
                if (this.jccPowerZeroFlip1Count === 1) {
                    await this.cv5000.jccControl('handle');
                    this.jccFlipState = 'flip1';
                    this.currentRow = this._copyRowState();
                    this._updateState({ occluder: `${flipPrefix}_Flip1` });
                    const response = this._buildResponse();
                    response.auto_flip = true;
                    response.flip_wait_seconds = 2;
                    return response;
                } else {
                    this.jccPowerZeroFlip1Count = 0;
                    return nextPhase();
                }
            }

            const reversal = this._recordJCCChoice('flip1');
            this.currentRow = this._copyRowState();
            for (let i = 0; i < steps; i++) {
                const wasAt = this._isAtCylThreshold(this.currentRow[cylKey]);
                await this.cv5000.jccControl('increase');
                this.currentRow[cylKey] += 0.25;
                if (wasAt && !this._isAtCylThreshold(this.currentRow[cylKey])) {
                    this.currentRow[sphKey] -= 0.25;
                }
            }
            if (reversal) return nextPhase();
        }

        if (isRAM) {
            const reversal = this._recordJCCChoice('flip2');
            this.currentRow = this._copyRowState();
            for (let i = 0; i < steps; i++) {
                const wasAt = this._isAtCylThreshold(this.currentRow[cylKey]);
                await this.cv5000.jccControl('decrease');
                this.currentRow[cylKey] -= 0.25;
                if (!wasAt && this._isAtCylThreshold(this.currentRow[cylKey])) {
                    this.currentRow[sphKey] += 0.25;
                }
            }
            if (reversal) return nextPhase();
        }

        if (isGAP || isRAM) {
            await this.cv5000.jccControl('handle');
            this.jccFlipState = 'flip1';
            this._updateState({ occluder: `${flipPrefix}_Flip1` });
            const response = this._buildResponse();
            response.auto_flip = true;
            response.flip_wait_seconds = 2;
            return response;
        }

        return this._buildResponse();
    }

    _isAtCylThreshold(cyl) {
        const absCyl = Math.abs(cyl);
        return absCyl > 0.001 && Math.abs(absCyl % 0.50) < 0.001;
    }

    // ═══════════════════════════════════════════════
    // PHASE G/J: Duochrome
    // ═══════════════════════════════════════════════
    async _transitionToDuochrome(eye) {
        this.currentPhase = eye === 'right' ? 'duochrome_right' : 'duochrome_left';
        this._resetDuochromeChoiceTracking();

        const occluder = eye === 'right' ? 'Left_Occluded' : 'Right_Occluded';
        this.currentRow = this._copyRowState();
        this._updateState({ occluder, chart: 'duochrome' });
        await this.cv5000.setChart('duochrome');

        this.emit('phase-change', this.getProgress());
        return this._buildResponse();
    }

    async _processDuochrome(eye, intent) {
        const sphKey = eye === 'right' ? 'r_sph' : 'l_sph';
        const auxLens = eye === 'right' ? 'AuxLensL' : 'AuxLensR';
        const nextTransition = eye === 'right'
            ? () => this._transitionToRefraction('left')
            : () => this._transitionToBinocularBalance();

        if (intent === 'Both Same') {
            return nextTransition();
        }

        let sphDelta = 0;
        if (intent === 'Red') {
            // RAM: Red Add Minus → -0.25D SPH
            sphDelta = -0.25;
            const reversal = this._recordDuochromeChoice('red');
            if (reversal) {
                // Apply adjustment then transition
                await this._applyDuochromeSphChange(eye, sphKey, sphDelta, auxLens);
                const response = await nextTransition();
                response.power = this.getPower();
                return response;
            }
        } else if (intent === 'Green') {
            // GAP: Green Add Plus → +0.25D SPH
            sphDelta = 0.25;
            const reversal = this._recordDuochromeChoice('green');
            if (reversal) {
                await this._applyDuochromeSphChange(eye, sphKey, sphDelta, auxLens);
                const response = await nextTransition();
                response.power = this.getPower();
                return response;
            }
        }

        if (sphDelta !== 0) {
            await this._applyDuochromeSphChange(eye, sphKey, sphDelta, auxLens);
            return this._buildResponse();
        }

        return nextTransition();
    }

    async _applyDuochromeSphChange(eye, sphKey, sphDelta, auxLens) {
        const prevSph = this.currentRow[sphKey];
        this.currentRow = this._copyRowState();
        this.currentRow[sphKey] = prevSph + sphDelta;

        await this.cv5000.setPowerWithPrevState({
            prev_r_sph: eye === 'right' ? prevSph : this.currentRow.r_sph,
            prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
            prev_l_sph: eye === 'left' ? prevSph : this.currentRow.l_sph,
            prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
            r_sph: this.currentRow.r_sph, r_cyl: this.currentRow.r_cyl, r_axis: this.currentRow.r_axis,
            l_sph: this.currentRow.l_sph, l_cyl: this.currentRow.l_cyl, l_axis: this.currentRow.l_axis,
            prev_aux_lens: auxLens, aux_lens: auxLens,
        });
    }

    // ═══════════════════════════════════════════════
    // PHASE K: Binocular Balance
    // ═══════════════════════════════════════════════
    async _transitionToBinocularBalance() {
        this.currentPhase = 'binocular_balance';
        this.previousState = null;
        this.showPrevStateOption = false;

        this.currentRow = this._copyRowState();
        this._updateState({ occluder: 'BINO', chart: 'bino_chart' });

        await this.cv5000.setChart('bino_chart');
        await this.cv5000.setPower({ occluder: 'BINO' });
        await this.cv5000.jccControl('BINO');

        this.emit('phase-change', this.getProgress());
        return this._buildResponse();
    }

    async _processBinocularBalance(intent) {
        if (intent === 'Prev State') {
            if (this.previousState) {
                await this.cv5000.setPowerWithPrevState({
                    prev_r_sph: this.currentRow.r_sph, prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
                    prev_l_sph: this.currentRow.l_sph, prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
                    r_sph: this.previousState.r_sph, r_cyl: this.previousState.r_cyl, r_axis: this.previousState.r_axis,
                    l_sph: this.previousState.l_sph, l_cyl: this.previousState.l_cyl, l_axis: this.previousState.l_axis,
                    prev_aux_lens: 'BINO', aux_lens: 'BINO',
                });
                Object.assign(this.currentRow, this.previousState);
                this.previousState = null;
                this.showPrevStateOption = false;
            }
            return this._buildResponse();
        }

        if (intent === 'Both are same') {
            this.examComplete = true;
            return this._generateFinalPrescription();
        }

        this._savePrevState();

        if (intent.includes('Top is blurry') || intent.includes('Right Eye')) {
            const prevLSph = this.currentRow.l_sph;
            this.currentRow = this._copyRowState();
            this.currentRow.l_sph = prevLSph + 0.25;
            await this.cv5000.setPowerWithPrevState({
                prev_r_sph: this.currentRow.r_sph, prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
                prev_l_sph: prevLSph, prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
                r_sph: this.currentRow.r_sph, r_cyl: this.currentRow.r_cyl, r_axis: this.currentRow.r_axis,
                l_sph: this.currentRow.l_sph, l_cyl: this.currentRow.l_cyl, l_axis: this.currentRow.l_axis,
                prev_aux_lens: 'BINO', aux_lens: 'BINO',
            });
        } else if (intent.includes('Bottom is blurry') || intent.includes('Left Eye')) {
            const prevRSph = this.currentRow.r_sph;
            this.currentRow = this._copyRowState();
            this.currentRow.r_sph = prevRSph + 0.25;
            await this.cv5000.setPowerWithPrevState({
                prev_r_sph: prevRSph, prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
                prev_l_sph: this.currentRow.l_sph, prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
                r_sph: this.currentRow.r_sph, r_cyl: this.currentRow.r_cyl, r_axis: this.currentRow.r_axis,
                l_sph: this.currentRow.l_sph, l_cyl: this.currentRow.l_cyl, l_axis: this.currentRow.l_axis,
                prev_aux_lens: 'BINO', aux_lens: 'BINO',
            });
        }

        this.showPrevStateOption = true;
        return this._buildResponse();
    }

    // ═══════════════════════════════════════════════
    // OUTPUT 3: Final Prescription
    // ═══════════════════════════════════════════════
    _generateFinalPrescription() {
        const rx = {
            right: {
                sph: this._round(this.currentRow.r_sph, 0.25),
                cyl: this._round(this.currentRow.r_cyl, 0.25),
                axis: Math.round(this.currentRow.r_axis),
                add: this._round(this.currentRow.r_add, 0.25),
            },
            left: {
                sph: this._round(this.currentRow.l_sph, 0.25),
                cyl: this._round(this.currentRow.l_cyl, 0.25),
                axis: Math.round(this.currentRow.l_axis),
                add: this._round(this.currentRow.l_add, 0.25),
            },
            pd: this.patientData.pd,
            examDate: new Date().toISOString(),
            flags: this.flags,
            sessionHistory: this.sessionHistory,
        };

        this.emit('exam-complete', rx);

        return {
            phase: 'Test Complete',
            phaseId: 'complete',
            status: 'complete',
            question: 'Your eye test is complete! Here is your final prescription.',
            intents: [],
            prescription: rx,
            power: this.getPower(),
            progress: { ...this.getProgress(), percent: 100 },
        };
    }

    // ─── JCC Choice Tracking (reversal detection) ──
    _resetJCCChoiceTracking() {
        this.jccLastChoice = null;
        this.jccSameChoiceCount = 0;
    }

    _recordJCCChoice(choice) {
        if (choice === this.jccLastChoice) {
            this.jccSameChoiceCount++;
            return false;
        }
        const reversal = this.jccLastChoice !== null && this.jccSameChoiceCount >= 1;
        this.jccLastChoice = choice;
        this.jccSameChoiceCount = 1;
        return reversal;
    }

    // ─── Duochrome Choice Tracking ─────────────────
    _resetDuochromeChoiceTracking() {
        this.duochromeLastChoice = null;
        this.duochromeSameChoiceCount = 0;
    }

    _recordDuochromeChoice(choice) {
        if (choice === this.duochromeLastChoice) {
            this.duochromeSameChoiceCount++;
            return false;
        }
        const reversal = this.duochromeLastChoice !== null && this.duochromeSameChoiceCount >= 1;
        this.duochromeLastChoice = choice;
        this.duochromeSameChoiceCount = 1;
        return reversal;
    }

    // ─── Chart Switching ───────────────────────────
    async switchChart(chartIndex) {
        let chartList;
        if (this.currentPhase === 'distance_vision') {
            chartList = this.cv5000.allCharts;
        } else if (this.currentPhase === 'right_eye_refraction' || this.currentPhase === 'left_eye_refraction') {
            chartList = this.cv5000.snellenCharts;
        } else {
            throw new Error(`Chart switching not allowed in phase: ${this.currentPhase}`);
        }

        if (chartIndex < 0 || chartIndex >= chartList.length) {
            throw new Error(`Invalid chart index: ${chartIndex}`);
        }

        this.currentChartIndex = chartIndex;
        this.currentRow = this._copyRowState();
        this.currentRow.chart_display = chartList[chartIndex];
        await this.cv5000.setChart(chartList[chartIndex]);

        return this._buildResponse();
    }

    // ─── Export ────────────────────────────────────
    exportExamData() {
        return {
            patientData: this.patientData,
            finalPrescription: this.getPower(),
            flags: this.flags,
            sessionHistory: this.sessionHistory,
            examDate: new Date().toISOString(),
        };
    }

    _round(value, step) {
        return Math.round(value / step) * step;
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = RefractionEngine;
}
