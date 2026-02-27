/**
 * Subjective Refraction Engine — 12-Phase State Machine
 *
 * Ported from reference: eye_test_engine/interactive_session.py
 * Implements the complete clinical subjective refraction protocol:
 *
 *   Phase A:  Distance Vision (BINO + E-chart)
 *   Phase A2: Fogging Right Eye (+2.00D fog to relax accommodation)
 *   Phase B:  Right Eye Refraction / De-fog (Left_Occluded + Snellen)
 *   Phase E:  JCC Axis Right (jcc_chart + Flip1/Flip2)
 *   Phase F:  JCC Power Right (jcc_chart + Flip1/Flip2)
 *   Phase G:  Duochrome Right (duochrome chart)
 *   Phase C2: Fogging Left Eye (+2.00D fog to relax accommodation)
 *   Phase D:  Left Eye Refraction / De-fog (Right_Occluded + Snellen)
 *   Phase H:  JCC Axis Left (jcc_chart + Flip1/Flip2)
 *   Phase I:  JCC Power Left (jcc_chart + Flip1/Flip2)
 *   Phase J:  Duochrome Left (duochrome chart)
 *   Phase K:  Binocular Balance (BINO + bino_chart)
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
            'fogging_right':         'Phase A2: Fogging Right Eye (Step 3.1)',
            'right_eye_refraction':  'Phase B: Right Eye Refraction / De-fog (Step 6.1)',
            'jcc_axis_right':        'Phase E: JCC Axis Right (Step 6.2)',
            'jcc_power_right':       'Phase F: JCC Power Right (Step 6.2)',
            'duochrome_right':       'Phase G: Duochrome Right (Step 6.2)',
            'fogging_left':          'Phase C2: Fogging Left Eye (Step 3.2)',
            'left_eye_refraction':   'Phase D: Left Eye Refraction / De-fog (Step 6.3)',
            'jcc_axis_left':         'Phase H: JCC Axis Left (Step 6.4)',
            'jcc_power_left':        'Phase I: JCC Power Left (Step 6.4)',
            'duochrome_left':        'Phase J: Duochrome Left (Step 6.4)',
            'binocular_balance':     'Phase K: Binocular Balance (Step 6.5)',
        };

        this.phaseOrder = [
            'distance_vision',
            'fogging_right',
            'right_eye_refraction',
            'jcc_axis_right',
            'jcc_power_right',
            'duochrome_right',
            'fogging_left',
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

        // ── Fogging ──
        this.lastFogCalc = null; // stores last fog calculation details for rationale
    }

    // ─── Dynamic Fog Calculation ──────────────────
    _calculateFogAmount(eye) {
        const age = this.patientData.age || 30;
        const ar = eye === 'right' ? this.patientData.autorefraction.OD : this.patientData.autorefraction.OS;
        const lm = eye === 'right' ? this.patientData.lensometry.OD : this.patientData.lensometry.OS;
        const hasOldRx = this.patientData.lensometry.hasOldRx;

        // ── 1. Base fog by age (accommodation amplitude) ──
        // Younger patients accommodate more aggressively → need more fog
        let baseFog, ageReason;
        if (age <= 15)      { baseFog = 2.50; ageReason = `Age ${age} (<=15): very strong accommodation — 2.50D base fog`; }
        else if (age <= 25) { baseFog = 2.00; ageReason = `Age ${age} (16-25): strong accommodation — 2.00D base fog`; }
        else if (age <= 35) { baseFog = 1.50; ageReason = `Age ${age} (26-35): moderate accommodation — 1.50D base fog`; }
        else if (age <= 45) { baseFog = 1.00; ageReason = `Age ${age} (36-45): weakening accommodation — 1.00D base fog`; }
        else                { baseFog = 0.75; ageReason = `Age ${age} (>45): presbyopic, minimal accommodation — 0.75D base fog`; }

        // ── 2. Adjust for high refractive error ──
        // High refractive errors: the eye is already deeply corrected,
        // large fog on top can cause excessive blur that disorients the patient
        let arAdjust = 0, arReason;
        const absSph = Math.abs(ar.sph);
        if (absSph > 8.0) {
            arAdjust = -0.75;
            arReason = `High error (|AR SPH| = ${absSph.toFixed(2)} > 8.00) — reducing fog by 0.75D to avoid disorientation`;
        } else if (absSph > 6.0) {
            arAdjust = -0.50;
            arReason = `Moderate-high error (|AR SPH| = ${absSph.toFixed(2)} > 6.00) — reducing fog by 0.50D`;
        } else if (absSph > 4.0) {
            arAdjust = -0.25;
            arReason = `Moderate error (|AR SPH| = ${absSph.toFixed(2)} > 4.00) — reducing fog by 0.25D`;
        } else {
            arReason = `Normal range (|AR SPH| = ${absSph.toFixed(2)} <= 4.00) — no adjustment needed`;
        }

        // ── 3. Cross-check with old Rx ──
        // If patient has an old Rx and the AR differs significantly, note it
        let lmNote = '';
        if (hasOldRx && lm.sph !== 0) {
            const diff = Math.abs(ar.sph - lm.sph);
            if (diff > 1.5) {
                lmNote = `Note: AR SPH (${ar.sph.toFixed(2)}) differs from old Rx (${lm.sph.toFixed(2)}) by ${diff.toFixed(2)}D — large change, verify AR accuracy.`;
            }
        }

        const finalFog = Math.round(Math.max(0.50, baseFog + arAdjust) * 4) / 4; // round to 0.25D

        return {
            amount: finalFog,
            baseFog,
            arAdjust,
            ageReason,
            arReason,
            lmNote,
            formula: `${baseFog.toFixed(2)}D (age) ${arAdjust !== 0 ? (arAdjust > 0 ? '+' : '') + arAdjust.toFixed(2) + 'D (AR adj)' : ''} = ${finalFog.toFixed(2)}D`.trim(),
        };
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
            rationale: this._getRationale(),
            arReference: this.patientData.autorefraction,
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
            case 'fogging_right':
                return "I've added extra plus power to intentionally blur your right eye. Can you confirm everything looks blurry?";
            case 'fogging_left':
                return "I've added extra plus power to intentionally blur your left eye. Can you confirm everything looks blurry?";
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
            case 'fogging_right':
            case 'fogging_left':
                intents = ["Yes, it's blurry", 'No, I can still see clearly'];
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

    // ─── Phase Rationale (clinical reasoning + operator guide + validation) ──
    _getRationale() {
        const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
        const fmtEye = (e) => `${fmt(e.sph)}/${fmt(e.cyl)}x${e.axis}`;
        const ar = this.patientData.autorefraction;
        const p = this.getPower();
        const age = this.patientData.age || 30;
        const fc = this.lastFogCalc;

        switch (this.currentPhase) {
            case 'distance_vision':
                return {
                    phase: 'Baseline Distance Vision',
                    why: `AR loaded into phoropter: OD ${fmtEye(ar.OD)}, OS ${fmtEye(ar.OS)}. Checking if patient can see the largest chart (20/400 E) with AR as starting correction.`,
                    clinical: 'The auto-refractometer (AR) gives an objective measurement of refractive error. We use it as a starting point and refine subjectively. Binocular check first to verify AR gives functional distance vision.',
                    guide: 'Both eyes are open. A large "E" letter is displayed on the chart. Ask the patient if they can see the E. This is just a quick baseline check — not a precise measurement yet.',
                    expected: '"Able to read" (most common) — the AR values give enough correction to see the big E. We proceed to fogging.',
                    watchFor: 'If patient says "Unable to read" even with AR correction, we test with a pinhole. If pinhole doesn\'t help either, there may be a medical issue beyond just needing glasses — flag for optometrist.',
                    decisionLogic: `AR values applied: OD ${fmtEye(ar.OD)}, OS ${fmtEye(ar.OS)}. Binocular (both eyes open). Chart: 20/400 E. Next: Fog right eye.`,
                };

            case 'fogging_right': {
                const fogAmt = fc ? fc.amount : 0;
                return {
                    phase: 'Fogging — Right Eye',
                    why: `Right eye fogged: AR SPH ${fmt(ar.OD.sph)} + ${fmt(fogAmt)} fog = ${fmt(p.right.sph)}. Left eye occluded.`,
                    clinical: 'Fogging adds excess plus power to intentionally blur vision. This relaxes the ciliary muscle (accommodation), preventing over-minusing. Without fogging, the eye may accommodate (focus harder), making us prescribe too much minus.',
                    guide: 'The left eye is covered. The right eye has extra "plus" lens power added so everything looks blurry on purpose. Ask the patient to confirm they see blurry. If they can still see clearly, we need to add more fog.',
                    expected: '"Yes, it\'s blurry" — the fog is working, accommodation is relaxed. We then slowly reduce the fog to find the right prescription.',
                    watchFor: 'If the patient keeps saying "I can still see clearly" after 3+ fog additions (>3.50D total), this suggests unusually strong accommodation — may need cycloplegic drops. Flag for optometrist.',
                    decisionLogic: fc
                        ? `Fog calculation: ${fc.ageReason}. ${fc.arReason}. Formula: ${fc.formula}.${fc.lmNote ? ' ' + fc.lmNote : ''}`
                        : 'Dynamic fog calculation pending.',
                };
            }

            case 'right_eye_refraction':
                return {
                    phase: 'De-fogging / Monocular Refraction — Right Eye',
                    why: `Reducing SPH in -0.25D steps from fogged value. Current: OD SPH ${fmt(p.right.sph)} (AR was ${fmt(ar.OD.sph)}).`,
                    clinical: 'Each -0.25D step sharpens the retinal image. "Able to read" means this line is resolved — advance to smaller letters. "Unable to read" twice consecutively — move to astigmatism refinement (JCC).',
                    guide: 'The left eye is still covered. Show Snellen letter charts of decreasing size. Each time the patient says "Blurry" or "Unable to read", we add -0.25D (like a tiny glass lens adjustment). When they say "Able to read", we show smaller letters.',
                    expected: 'The patient will alternate between "Able to read" (advance chart) and "Blurry"/"Unable to read" (add -0.25D). We stop when they fail twice in a row, or reach 20/20.',
                    watchFor: `If SPH goes far beyond AR (more than 1.50D past ${fmt(ar.OD.sph)}), the patient may be over-accommodating or AR was inaccurate. Current SPH: ${fmt(p.right.sph)}.`,
                    decisionLogic: `Step: -0.25D per "Blurry"/"Unable". Exit rule: 2x consecutive "Unable to read" OR 20/20 reached. Unable count: ${this.unableReadCount}/2. Chart index: ${this.currentChartIndex}.`,
                };

            case 'jcc_axis_right':
                return {
                    phase: 'JCC Axis Refinement — Right Eye',
                    why: `Refining cylinder axis. Current: OD CYL ${fmt(p.right.cyl)} x ${p.right.axis}\u00B0 (AR was ${fmt(ar.OD.cyl)} x ${ar.OD.axis}\u00B0).`,
                    clinical: 'The JCC flips two cross-cylinder lens orientations (Flip 1 vs Flip 2). The clearer flip tells us which direction to rotate the astigmatism axis. Converges when both flips look the same.',
                    guide: 'A dot chart is shown. The machine automatically flips between two lens positions (Flip 1 and Flip 2). Ask the patient which flip looked clearer. The system adjusts the astigmatism angle based on their answer. We keep flipping until both look the same.',
                    expected: 'Patient picks Flip 1 or Flip 2 several times. After a few rounds, they\'ll say "Both Same" — that means we found the right astigmatism angle. A "reversal" (switching from one preference to the other) also signals convergence.',
                    watchFor: 'If axis shifts more than 30\u00B0 from AR, the astigmatism may be irregular. If patient consistently can\'t tell a difference, their astigmatism may be minimal — consider zeroing CYL.',
                    decisionLogic: `Flip choices tracked: last=${this.jccLastChoice || 'none'}, sameCount=${this.jccSameChoiceCount}. Reversal detection active. \u00B15\u00B0 per choice, \u00B110\u00B0 for "MUCH better".`,
                };

            case 'jcc_power_right':
                return {
                    phase: 'JCC Power Refinement — Right Eye',
                    why: `Refining cylinder power. Current: OD CYL ${fmt(p.right.cyl)} (AR was ${fmt(ar.OD.cyl)}).`,
                    clinical: 'Same JCC flip comparison, now adjusting the amount of cylinder correction (\u00B10.25D steps). SPH is compensated when CYL crosses 0.50D boundaries to maintain spherical equivalent.',
                    guide: 'Same flip comparison as before, but now we\'re adjusting the strength (power) of the astigmatism correction, not the angle. Patient picks which flip is clearer. We stop when both look the same.',
                    expected: 'Similar to axis test — a few rounds of choosing, then "Both Same". If CYL was 0 and patient picks Flip 1 twice, it means no significant astigmatism — we skip ahead.',
                    watchFor: `If CYL diverges significantly from AR (${fmt(ar.OD.cyl)}), verify with the patient. CYL change automatically adjusts SPH to keep the "spherical equivalent" balanced.`,
                    decisionLogic: `CYL-zero special: Flip1 count at CYL=0: ${this.jccPowerZeroFlip1Count}/2 (2 = exit). SPH compensation at 0.50D CYL boundaries. Reversal detection active.`,
                };

            case 'duochrome_right':
                return {
                    phase: 'Duochrome (Red/Green) — Right Eye',
                    why: `Verifying spherical endpoint. Current: OD SPH ${fmt(p.right.sph)} (AR was ${fmt(ar.OD.sph)}).`,
                    clinical: 'Red and green light focus at slightly different retinal points due to chromatic aberration. Red clearer = under-corrected (RAM: Red Add Minus). Green clearer = over-corrected (GAP: Green Add Plus). Equal = optimal.',
                    guide: 'A chart with letters on a split red/green background is shown. Ask the patient: "Are the letters on the RED side or GREEN side clearer, or are they the same?" Adjust based on their answer.',
                    expected: '"Both Same" means the sphere is perfect. Usually takes 1-3 rounds. Mnemonics: RAM (Red Add Minus), GAP (Green Add Plus).',
                    watchFor: 'If the patient oscillates between Red and Green more than 3 times, accept the current value — it\'s within tolerance. A reversal (switching from Red to Green or vice versa) signals we\'re at the endpoint.',
                    decisionLogic: `Duochrome tracking: last=${this.duochromeLastChoice || 'none'}, sameCount=${this.duochromeSameChoiceCount}. Red\u2192-0.25D SPH, Green\u2192+0.25D SPH. Reversal exits to next phase.`,
                };

            case 'fogging_left': {
                const fogAmt = fc ? fc.amount : 0;
                return {
                    phase: 'Fogging — Left Eye',
                    why: `Left eye fogged: AR SPH ${fmt(ar.OS.sph)} + ${fmt(fogAmt)} fog = ${fmt(p.left.sph)}. Right eye occluded.`,
                    clinical: 'Same fogging principle for the left eye. Relaxing accommodation before monocular refraction to prevent over-minusing.',
                    guide: 'Now the right eye is covered and we fog the left eye. Same process: confirm the patient sees blurry, then we\'ll de-fog step by step.',
                    expected: '"Yes, it\'s blurry" — proceed to left eye refraction.',
                    watchFor: 'Compare fog amount needed vs right eye. If significantly different, note it as unusual.',
                    decisionLogic: fc
                        ? `Fog calculation: ${fc.ageReason}. ${fc.arReason}. Formula: ${fc.formula}.${fc.lmNote ? ' ' + fc.lmNote : ''}`
                        : 'Dynamic fog calculation pending.',
                };
            }

            case 'left_eye_refraction':
                return {
                    phase: 'De-fogging / Monocular Refraction — Left Eye',
                    why: `Reducing SPH in -0.25D steps from fogged value. Current: OS SPH ${fmt(p.left.sph)} (AR was ${fmt(ar.OS.sph)}).`,
                    clinical: 'Same de-fogging process as right eye. Each -0.25D step tests if the image sharpens enough to read the next line.',
                    guide: 'Right eye is covered. Same de-fogging process: show letter charts, add -0.25D when blurry, advance chart when readable.',
                    expected: 'Same pattern as right eye. Typically the left eye takes a similar number of steps.',
                    watchFor: `If final SPH for left eye differs from right eye by more than 2.00D (anisometropia), flag it. Right eye ended at OD SPH ${fmt(p.right.sph)}.`,
                    decisionLogic: `Step: -0.25D per "Blurry"/"Unable". Exit rule: 2x consecutive "Unable" OR 20/20. Unable count: ${this.unableReadCount}/2. Chart index: ${this.currentChartIndex}.`,
                };

            case 'jcc_axis_left':
                return {
                    phase: 'JCC Axis Refinement — Left Eye',
                    why: `Refining cylinder axis. Current: OS CYL ${fmt(p.left.cyl)} x ${p.left.axis}\u00B0 (AR was ${fmt(ar.OS.cyl)} x ${ar.OS.axis}\u00B0).`,
                    clinical: 'Cross-cylinder axis test for the left eye. Same flip comparison to converge on the correct astigmatism axis.',
                    guide: 'Same JCC axis test as right eye. Dot chart, automatic flips, patient picks clearer one.',
                    expected: 'Patient picks flips until "Both Same" or a reversal is detected.',
                    watchFor: 'Compare final axis with AR and with right eye. Large asymmetry between eyes is uncommon but possible.',
                    decisionLogic: `Flip choices: last=${this.jccLastChoice || 'none'}, sameCount=${this.jccSameChoiceCount}. \u00B15\u00B0/\u00B110\u00B0 steps. Reversal detection active.`,
                };

            case 'jcc_power_left':
                return {
                    phase: 'JCC Power Refinement — Left Eye',
                    why: `Refining cylinder power. Current: OS CYL ${fmt(p.left.cyl)} (AR was ${fmt(ar.OS.cyl)}).`,
                    clinical: 'Cross-cylinder power test for the left eye. Adjusting cylinder in \u00B10.25D steps.',
                    guide: 'Same JCC power test as right eye. Adjusting astigmatism strength for the left eye.',
                    expected: 'Few rounds of flip comparison, then "Both Same".',
                    watchFor: `Compare with right eye CYL (${fmt(p.right.cyl)}). Large difference may warrant rechecking.`,
                    decisionLogic: `CYL-zero special: Flip1@CYL0 count: ${this.jccPowerZeroFlip1Count}/2. SPH compensation at 0.50D CYL boundaries. Reversal detection active.`,
                };

            case 'duochrome_left':
                return {
                    phase: 'Duochrome (Red/Green) — Left Eye',
                    why: `Verifying spherical endpoint. Current: OS SPH ${fmt(p.left.sph)} (AR was ${fmt(ar.OS.sph)}).`,
                    clinical: 'Duochrome test for left eye. Red clearer = add minus, Green clearer = add plus, Equal = done.',
                    guide: 'Same red/green test as right eye. Ask which side is clearer or if both are the same.',
                    expected: '"Both Same" in 1-3 rounds. RAM/GAP rules apply.',
                    watchFor: `Compare final SPH with right eye (${fmt(p.right.sph)}). Large difference = anisometropia.`,
                    decisionLogic: `Duochrome: last=${this.duochromeLastChoice || 'none'}, sameCount=${this.duochromeSameChoiceCount}. Red\u2192-0.25D, Green\u2192+0.25D. Reversal exits.`,
                };

            case 'binocular_balance':
                return {
                    phase: 'Binocular Balance',
                    why: `Equalizing both eyes. Current: OD SPH ${fmt(p.right.sph)}, OS SPH ${fmt(p.left.sph)}.`,
                    clinical: 'Both eyes view separate lines through prism dissociation. If one line is blurrier, that eye gets +0.25D to equalize. Goal: both eyes equally sharp for comfortable binocular vision.',
                    guide: 'Both eyes are now open. The patient sees two rows of letters (one per eye, separated by a prism). Ask which row is blurrier — top or bottom. We adjust until both look the same.',
                    expected: '"Both are same" means the eyes are balanced — exam is complete! Usually takes 1-3 adjustments.',
                    watchFor: 'If balance takes more than 5 adjustments, the monocular refraction may need rechecking. If one eye is significantly weaker, it may never fully balance — accept the best achievable.',
                    decisionLogic: `Top blurry (OD) \u2192 +0.25D OS SPH. Bottom blurry (OS) \u2192 +0.25D OD SPH. "Both same" \u2192 exam complete.`,
                };

            default:
                return { phase: this.currentPhase, why: '', clinical: '', guide: '', expected: '', watchFor: '', decisionLogic: '' };
        }
    }

    // ─── Action Rationale (why this specific action was taken) ──
    // Returns { summary, rule, delta } for structured JSON export
    _getActionRationale(intent) {
        const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
        const ar = this.patientData.autorefraction;
        const p = this.getPower();
        const fc = this.lastFogCalc;
        const fogAmt = fc ? fc.amount : 2.0;

        const _r = (summary, rule, delta) => ({ summary, rule, delta: delta || null });

        switch (this.currentPhase) {
            case 'distance_vision':
                if (intent === 'Able to read') return _r(
                    `Patient can see 20/400 E with AR correction (OD ${fmt(ar.OD.sph)}, OS ${fmt(ar.OS.sph)}). Baseline confirmed.`,
                    'Baseline OK → proceed to fogging', { next: 'fogging_right' });
                if (intent === 'Blurry') return _r(
                    'E is blurry but detectable with AR. Proceeding to fogging.',
                    'Blurry but visible → proceed to fogging', { next: 'fogging_right' });
                if (intent === 'Unable to read') return _r(
                    'Cannot read E with AR correction — activating pinhole to differentiate refractive error from pathology.',
                    'Unable → pinhole test (diagnostic branch)', { action: 'pinhole' });
                if (intent.includes('pinhole')) return _r(
                    intent.includes('Still')
                        ? 'Pinhole did not help — flagging possible pathology for optometrist review.'
                        : 'Pinhole improved vision — confirms refractive (optical) issue, not pathology.',
                    intent.includes('Still') ? 'Pinhole negative → flag pathology' : 'Pinhole positive → refractive issue confirmed',
                    { flag: intent.includes('Still') ? 'pinhole_no_improvement' : null });
                break;

            case 'fogging_right':
                if (intent.includes('blurry')) return _r(
                    `Fog confirmed at OD SPH ${fmt(p.right.sph)} (AR ${fmt(ar.OD.sph)} + ${fmt(fogAmt)} fog). Accommodation relaxed.`,
                    `Fog effective → begin de-fog in -0.25D steps`,
                    { fogApplied: fogAmt, next: 'right_eye_refraction' });
                if (intent.includes('see clearly')) return _r(
                    `Patient sees through ${fmt(fogAmt)} fog — accommodation still active. Adding +0.50D more.`,
                    'Fog insufficient → add +0.50D', { sph: +0.50 });
                break;

            case 'fogging_left':
                if (intent.includes('blurry')) return _r(
                    `Fog confirmed at OS SPH ${fmt(p.left.sph)} (AR ${fmt(ar.OS.sph)} + ${fmt(fogAmt)} fog). Accommodation relaxed.`,
                    `Fog effective → begin de-fog`, { fogApplied: fogAmt, next: 'left_eye_refraction' });
                if (intent.includes('see clearly')) return _r(
                    `Patient sees through fog — adding +0.50D more.`,
                    'Fog insufficient → add +0.50D', { sph: +0.50 });
                break;

            case 'right_eye_refraction':
            case 'left_eye_refraction': {
                const eye = this.currentPhase.includes('right') ? 'right' : 'left';
                const sph = eye === 'right' ? p.right.sph : p.left.sph;
                if (intent === 'Able to read') return _r(
                    `Patient reads this line at SPH ${fmt(sph)}. Advancing to smaller chart.`,
                    'Readable → next chart (smaller letters)', { chartAdvance: true });
                if (intent === 'Blurry') return _r(
                    `Blurry at SPH ${fmt(sph)} → ${fmt(sph - 0.25)}. De-fogging toward optimal.`,
                    'Blurry → -0.25D SPH (de-fog step)', { sph: -0.25 });
                if (intent === 'Unable to read') return _r(
                    `Cannot read at SPH ${fmt(sph)} → ${fmt(sph - 0.25)}. ${this.unableReadCount >= 1 ? 'Second consecutive failure → JCC.' : 'Continuing.'}`,
                    `Unable to read (${this.unableReadCount + 1}/2) → -0.25D SPH`,
                    { sph: -0.25, unableCount: this.unableReadCount + 1, exitToJcc: this.unableReadCount >= 1 });
                if (intent === 'Prev State') return _r(
                    'Reverting to previous power setting.',
                    'Operator undo → restore previous state', { undo: true });
                break;
            }

            case 'jcc_axis_right': case 'jcc_axis_left': {
                const eye = this.currentPhase.includes('right') ? 'right' : 'left';
                const axis = eye === 'right' ? p.right.axis : p.left.axis;
                if (intent === 'AUTO_FLIP') return _r('Auto-flipping Flip 1 → Flip 2.', 'Timer → auto-flip', { flip: '1→2' });
                if (intent.includes('Both Same')) return _r(`Axis locked at ${axis}\u00B0. Moving to power test.`, 'Both Same → exit axis, enter power', { next: 'jcc_power' });
                if (intent.includes('Flip 1') && intent.includes('MUCH')) return _r(`Flip 1 much clearer → axis +10\u00B0.`, 'GAP Axis MUCH → +10\u00B0', { axis: +10 });
                if (intent.includes('Flip 1') && intent.includes('better')) return _r(`Flip 1 clearer → axis +5\u00B0.`, 'GAP Axis → +5\u00B0', { axis: +5 });
                if (intent.includes('Flip 2') && intent.includes('MUCH')) return _r(`Flip 2 much clearer → axis -10\u00B0.`, 'RAM Axis MUCH → -10\u00B0', { axis: -10 });
                if (intent.includes('Flip 2') && intent.includes('better')) return _r(`Flip 2 clearer → axis -5\u00B0.`, 'RAM Axis → -5\u00B0', { axis: -5 });
                if (intent.includes('Repeat')) return _r('Repeating flip comparison.', 'Repeat requested', { repeat: true });
                break;
            }

            case 'jcc_power_right': case 'jcc_power_left': {
                const eye = this.currentPhase.includes('right') ? 'right' : 'left';
                const cyl = eye === 'right' ? p.right.cyl : p.left.cyl;
                if (intent === 'AUTO_FLIP') return _r('Auto-flipping Flip 1 → Flip 2.', 'Timer → auto-flip', { flip: '1→2' });
                if (intent.includes('Both Same')) return _r(`CYL locked at ${fmt(cyl)}. Moving to duochrome.`, 'Both Same → exit power, enter duochrome', { next: 'duochrome' });
                if (intent.includes('Flip 1') && intent.includes('MUCH')) return _r(`Flip 1 much clearer → CYL +0.50D.`, 'GAP Power MUCH → +0.50D CYL', { cyl: +0.50 });
                if (intent.includes('Flip 1') && intent.includes('better')) return _r(`Flip 1 clearer → CYL +0.25D.`, 'GAP Power → +0.25D CYL', { cyl: +0.25 });
                if (intent.includes('Flip 2') && intent.includes('MUCH')) return _r(`Flip 2 much clearer → CYL -0.50D.`, 'RAM Power MUCH → -0.50D CYL', { cyl: -0.50 });
                if (intent.includes('Flip 2') && intent.includes('better')) return _r(`Flip 2 clearer → CYL -0.25D.`, 'RAM Power → -0.25D CYL', { cyl: -0.25 });
                if (intent.includes('Repeat')) return _r('Repeating flip comparison.', 'Repeat requested', { repeat: true });
                break;
            }

            case 'duochrome_right': case 'duochrome_left': {
                const eye = this.currentPhase.includes('right') ? 'right' : 'left';
                const sph = eye === 'right' ? p.right.sph : p.left.sph;
                if (intent === 'Red') return _r(
                    `Red clearer — under-corrected. SPH ${fmt(sph)} → ${fmt(sph - 0.25)} (RAM: Red Add Minus).`,
                    'Red clearer → -0.25D SPH (RAM)', { sph: -0.25 });
                if (intent === 'Green') return _r(
                    `Green clearer — over-corrected. SPH ${fmt(sph)} → ${fmt(sph + 0.25)} (GAP: Green Add Plus).`,
                    'Green clearer → +0.25D SPH (GAP)', { sph: +0.25 });
                if (intent === 'Both Same') return _r(
                    `Red and green equal — spherical power optimized at ${fmt(sph)}.`,
                    'Both Same → SPH endpoint reached', { next: eye === 'right' ? 'fogging_left' : 'binocular_balance' });
                break;
            }

            case 'binocular_balance':
                if (intent.includes('Top') || intent.includes('Right Eye')) return _r(
                    `Top (OD) blurrier → +0.25D OS SPH. L SPH ${fmt(p.left.sph)} → ${fmt(p.left.sph + 0.25)}.`,
                    'Top blurry (OD weaker) → +0.25D OS SPH', { l_sph: +0.25 });
                if (intent.includes('Bottom') || intent.includes('Left Eye')) return _r(
                    `Bottom (OS) blurrier → +0.25D OD SPH. R SPH ${fmt(p.right.sph)} → ${fmt(p.right.sph + 0.25)}.`,
                    'Bottom blurry (OS weaker) → +0.25D OD SPH', { r_sph: +0.25 });
                if (intent.includes('same')) return _r(
                    'Both eyes balanced — exam complete.',
                    'Balanced → generate prescription', { next: 'complete' });
                if (intent === 'Prev State') return _r(
                    'Reverting to previous power.',
                    'Operator undo → restore previous state', { undo: true });
                break;
        }

        return _r(`${this.currentPhase}: ${intent}`, 'fallback', null);
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
            rationale: this._getActionRationale(intent),
            arReference: this.patientData.autorefraction,
        });

        switch (this.currentPhase) {
            case 'distance_vision':        return this._processDistanceVision(intent);
            case 'fogging_right':          return this._processFogging('right', intent);
            case 'right_eye_refraction':   return this._processRefraction('right', intent);
            case 'jcc_axis_right':         return this._processJCCAxis('right', intent);
            case 'jcc_power_right':        return this._processJCCPower('right', intent);
            case 'duochrome_right':        return this._processDuochrome('right', intent);
            case 'fogging_left':           return this._processFogging('left', intent);
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

        return this._transitionToFogging('right');
    }

    // ═══════════════════════════════════════════════
    // PHASE A2 & C2: Fogging (relax accommodation)
    // ═══════════════════════════════════════════════
    async _transitionToFogging(eye) {
        this.currentPhase = eye === 'right' ? 'fogging_right' : 'fogging_left';

        const occluder = eye === 'right' ? 'Left_Occluded' : 'Right_Occluded';
        const sphKey = eye === 'right' ? 'r_sph' : 'l_sph';

        this.currentRow = this._copyRowState();
        this.currentRow.occluder_state = occluder;

        // Dynamic fog: calculate based on age + AR
        const fogCalc = this._calculateFogAmount(eye);
        this.lastFogCalc = fogCalc;
        this.currentRow[sphKey] += fogCalc.amount;

        // Show a readable chart so patient can confirm blur
        this.currentRow.chart_display = this.cv5000.snellenCharts[0];

        await this.cv5000.setPower({
            r_sph: this.currentRow.r_sph, r_cyl: this.currentRow.r_cyl, r_axis: this.currentRow.r_axis,
            l_sph: this.currentRow.l_sph, l_cyl: this.currentRow.l_cyl, l_axis: this.currentRow.l_axis,
            occluder,
        });
        await this.cv5000.setChart(this.cv5000.snellenCharts[0]);

        this.emit('phase-change', this.getProgress());
        return this._buildResponse();
    }

    async _processFogging(eye, intent) {
        const sphKey = eye === 'right' ? 'r_sph' : 'l_sph';
        const auxLens = eye === 'right' ? 'AuxLensL' : 'AuxLensR';

        if (intent.includes('see clearly')) {
            // Not enough fog — add +0.50D more
            const prevSph = this.currentRow[sphKey];
            this.currentRow = this._copyRowState();
            this.currentRow[sphKey] = prevSph + 0.50;

            await this.cv5000.setPowerWithPrevState({
                prev_r_sph: eye === 'right' ? prevSph : this.currentRow.r_sph,
                prev_r_cyl: this.currentRow.r_cyl, prev_r_axis: this.currentRow.r_axis,
                prev_l_sph: eye === 'left' ? prevSph : this.currentRow.l_sph,
                prev_l_cyl: this.currentRow.l_cyl, prev_l_axis: this.currentRow.l_axis,
                r_sph: this.currentRow.r_sph, r_cyl: this.currentRow.r_cyl, r_axis: this.currentRow.r_axis,
                l_sph: this.currentRow.l_sph, l_cyl: this.currentRow.l_cyl, l_axis: this.currentRow.l_axis,
                prev_aux_lens: auxLens, aux_lens: auxLens,
            });

            return this._buildResponse();
        }

        // "Yes, it's blurry" — fog confirmed, proceed to refraction (de-fogging)
        return this._transitionToRefraction(eye);
    }

    // ═══════════════════════════════════════════════
    // PHASE B & D: Eye Refraction / De-fog (shared logic)
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
            ? () => this._transitionToFogging('left')
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
