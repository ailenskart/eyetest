/**
 * Mode Manager — Persona-aware UI controller
 *
 * Three modes:
 *   customer  — Patient at a Lenskart store: friendly language, progress tracker, comfort checks
 *   copilot   — Licensed optometrist: full clinical controls, AI confidence, override, quality scoring
 *   selftest  — Home user: on-screen charts, no hardware, simplified flow, shareable report
 *
 * Controls:
 *   - Visibility of persona-specific elements (.customer-only, .copilot-only, .selftest-only)
 *   - Phase name translation (clinical → patient-friendly)
 *   - Intent button label translation
 *   - Exam timer
 *   - Copilot dashboard updates (confidence, Rx comparison, quality)
 *   - Self-test chart rendering
 *   - Comfort check flow
 */

class ModeManager {
    constructor() {
        this.currentMode = null; // 'customer' | 'copilot' | 'selftest'
        this.examStartTime = null;
        this.examTimerInterval = null;
        this.paused = false;
        this.pauseStartTime = null;
        this.totalPauseMs = 0;

        // Copilot tracking
        this.confidenceHistory = [];
        this.overrideCount = 0;
        this.clarificationCount = 0;
        this.responseCount = 0;

        // Self-test chart state
        this.currentChartLine = 0;
        this.chartLines = this._buildChartLines();

        // Friendly phase names for customers
        this.friendlyPhaseNames = {
            'distance_vision':       'Reading the chart with both eyes',
            'fogging_right':         'Relaxing your right eye',
            'right_eye_refraction':  'Testing your right eye',
            'jcc_axis_right':        'Fine-tuning right eye (part 1)',
            'jcc_power_right':       'Fine-tuning right eye (part 2)',
            'duochrome_right':       'Checking right eye balance',
            'fogging_left':          'Relaxing your left eye',
            'left_eye_refraction':   'Testing your left eye',
            'jcc_axis_left':         'Fine-tuning left eye (part 1)',
            'jcc_power_left':        'Fine-tuning left eye (part 2)',
            'duochrome_left':        'Checking left eye balance',
            'binocular_balance':     'Final check — both eyes together',
        };

        // Friendly intent labels for customers
        this.friendlyIntents = {
            "Able to read":              "Yes, I can read it",
            "Blurry but readable":       "It's a bit blurry",
            "Unable to read":            "I can't read it",
            "Flip 1 Better":             "First one was better",
            "Flip 1 MUCH Better":        "First one was much better",
            "Flip 2 Better":             "Second one was better",
            "Flip 2 MUCH Better":        "Second one was much better",
            "Both Same":                 "They look the same",
            "Repeat flips":              "Show me again",
            "Red":                       "Red is clearer",
            "Green":                     "Green is clearer",
            "Both Same (Red/Green)":     "They're the same",
            "Top is blurry":             "Top is blurry",
            "Bottom is blurry":          "Bottom is blurry",
            "Both equal":                "Both are equal",
            "It's blurry (fog confirmed)": "Yes, it's blurry",
            "Can still see clearly":     "I can still see clearly",
        };

        // Patient-friendly questions
        this.friendlyQuestions = {
            'distance_vision': 'Can you read the letters on the screen?',
            'fogging_right': 'We\'re going to blur your vision on purpose — this is normal. Is it blurry now?',
            'right_eye_refraction': 'Can you read this line?',
            'jcc_axis_right': 'I\'m going to show you two options. Which one looks clearer?',
            'jcc_power_right': 'Which lens makes the dots look rounder?',
            'duochrome_right': 'Which side is clearer — the red or the green?',
            'fogging_left': 'Now let\'s check your left eye. Is it blurry?',
            'left_eye_refraction': 'Can you read this line?',
            'jcc_axis_left': 'Which option looks clearer?',
            'jcc_power_left': 'Which lens makes the dots look rounder?',
            'duochrome_left': 'Which side is clearer — the red or the green?',
            'binocular_balance': 'Looking with both eyes — is the top or bottom line blurrier?',
        };

        // Phase → patient progress step mapping
        this.phaseToStep = {
            'distance_vision': 'setup',
            'fogging_right': 'right',
            'right_eye_refraction': 'right',
            'jcc_axis_right': 'right',
            'jcc_power_right': 'right',
            'duochrome_right': 'right',
            'fogging_left': 'left',
            'left_eye_refraction': 'left',
            'jcc_axis_left': 'left',
            'jcc_power_left': 'left',
            'duochrome_left': 'left',
            'binocular_balance': 'both',
        };
    }

    // ════════════════════════════════════════════
    // MODE SELECTION
    // ════════════════════════════════════════════

    setMode(mode) {
        this.currentMode = mode;
        document.body.setAttribute('data-mode', mode);

        // Show/hide persona-specific elements
        document.querySelectorAll('.customer-only').forEach(el => {
            el.classList.toggle('hidden', mode !== 'customer');
        });
        document.querySelectorAll('.copilot-only').forEach(el => {
            el.classList.toggle('hidden', mode !== 'copilot');
        });
        document.querySelectorAll('.selftest-only').forEach(el => {
            el.classList.toggle('hidden', mode !== 'selftest');
        });

        // Update badges
        const modeBadge = document.getElementById('examModeBadge');
        const intakeBadge = document.getElementById('intakeModeBadge');
        const modeLabels = { customer: 'Customer', copilot: 'Optometrist', selftest: 'Self-Test' };
        if (modeBadge) modeBadge.textContent = modeLabels[mode];
        if (intakeBadge) intakeBadge.textContent = modeLabels[mode] + ' Mode';

        // Mode-specific setup
        if (mode === 'customer' || mode === 'selftest') {
            this._showPatientProgress(true);
        } else {
            this._showPatientProgress(false);
        }

        if (mode === 'selftest') {
            // Auto-enable simulated mode for self-test
            const simCheckbox = document.getElementById('simulatedMode');
            if (simCheckbox) simCheckbox.checked = true;
            // Show self-test chart
            const stChart = document.getElementById('selfTestChart');
            if (stChart) stChart.classList.remove('hidden');
            // Hide phoropter connection card
            this._hideIntakeCards(['Phoropter Connection']);
        } else {
            const stChart = document.getElementById('selfTestChart');
            if (stChart) stChart.classList.add('hidden');
            this._showAllIntakeCards();
        }

        if (mode === 'customer') {
            // Simplify intake: hide technical fields
            this._hideIntakeCards(['Phoropter Connection']);
            // Auto-enable voice
            const voiceCheckbox = document.getElementById('voiceEnabled');
            if (voiceCheckbox) voiceCheckbox.checked = true;
        }

        if (mode === 'copilot') {
            // Show all clinical fields
            this._showAllIntakeCards();
            // Auto-select copilot tab
            const cpTab = document.getElementById('tabCopilotBtn');
            if (cpTab) cpTab.click();
        }

        // Update results screen title
        const resultsTitle = document.getElementById('resultsTitle');
        if (resultsTitle) {
            const titles = {
                customer: 'Your Eye Test Results',
                copilot: 'AI Eye Test — Clinical Results',
                selftest: 'Your Vision Report',
            };
            resultsTitle.textContent = titles[mode];
        }
    }

    isMode(mode) {
        return this.currentMode === mode;
    }

    // ════════════════════════════════════════════
    // PATIENT PROGRESS TRACKER
    // ════════════════════════════════════════════

    _showPatientProgress(show) {
        const pp = document.getElementById('patientProgress');
        const clinicalProgress = document.querySelector('.progress-bar-container');
        if (pp) pp.classList.toggle('hidden', !show);
        if (clinicalProgress) clinicalProgress.classList.toggle('hidden', show);
        // Show friendly phase name instead of clinical one
        const clinical = document.getElementById('currentPhaseName');
        const friendly = document.getElementById('friendlyPhaseName');
        if (clinical) clinical.classList.toggle('hidden', show);
        if (friendly) friendly.classList.toggle('hidden', !show);
    }

    updatePhaseProgress(phase) {
        if (this.currentMode === 'copilot') return;

        // Update friendly name
        const friendly = document.getElementById('friendlyPhaseName');
        if (friendly) {
            friendly.textContent = this.friendlyPhaseNames[phase] || phase;
        }

        // Update progress steps
        const stepName = this.phaseToStep[phase] || 'setup';
        const steps = ['setup', 'right', 'left', 'both', 'done'];
        const currentIdx = steps.indexOf(stepName);

        document.querySelectorAll('.pp-step').forEach(step => {
            const sn = step.dataset.step;
            const idx = steps.indexOf(sn);
            step.classList.remove('completed', 'active');
            if (idx < currentIdx) step.classList.add('completed');
            else if (idx === currentIdx) step.classList.add('active');
        });
    }

    markExamComplete() {
        document.querySelectorAll('.pp-step').forEach(step => {
            step.classList.remove('active');
            step.classList.add('completed');
        });
    }

    // ════════════════════════════════════════════
    // EXAM TIMER
    // ════════════════════════════════════════════

    startExamTimer() {
        this.examStartTime = Date.now();
        this.totalPauseMs = 0;
        this.paused = false;
        this._updateTimerDisplay();
        this.examTimerInterval = setInterval(() => this._updateTimerDisplay(), 1000);
    }

    stopExamTimer() {
        if (this.examTimerInterval) {
            clearInterval(this.examTimerInterval);
            this.examTimerInterval = null;
        }
    }

    pauseExam() {
        if (!this.paused) {
            this.paused = true;
            this.pauseStartTime = Date.now();
        }
    }

    resumeExam() {
        if (this.paused) {
            this.totalPauseMs += Date.now() - this.pauseStartTime;
            this.paused = false;
            this.pauseStartTime = null;
        }
    }

    getExamDuration() {
        if (!this.examStartTime) return 0;
        const raw = Date.now() - this.examStartTime;
        const pauseMs = this.paused ? (Date.now() - this.pauseStartTime) : 0;
        return Math.floor((raw - this.totalPauseMs - pauseMs) / 1000);
    }

    _updateTimerDisplay() {
        const el = document.getElementById('examTimer');
        if (!el) return;
        const secs = this.getExamDuration();
        const m = Math.floor(secs / 60);
        const s = secs % 60;
        el.textContent = `${m}:${s.toString().padStart(2, '0')}`;
    }

    // ════════════════════════════════════════════
    // INTENT LABEL TRANSLATION
    // ════════════════════════════════════════════

    translateIntentLabel(clinical) {
        if (this.currentMode === 'copilot') return clinical;
        return this.friendlyIntents[clinical] || clinical;
    }

    // ════════════════════════════════════════════
    // COPILOT: CONFIDENCE DASHBOARD
    // ════════════════════════════════════════════

    updateConfidence(confidence, intent, transcript) {
        if (this.currentMode !== 'copilot') return;

        this.responseCount++;
        this.confidenceHistory.push(confidence);

        const pct = Math.round(confidence * 100);
        const badge = document.getElementById('cpConfidenceScore');
        const bar = document.getElementById('cpConfidenceBar');
        const detail = document.getElementById('cpConfidenceDetail');

        if (badge) {
            badge.textContent = `${pct}%`;
            badge.className = 'cp-confidence-badge ' +
                (confidence >= 0.75 ? 'high' : confidence >= 0.4 ? 'medium' : 'low');
        }
        if (bar) {
            bar.style.width = `${pct}%`;
            bar.className = 'cp-confidence-bar ' +
                (confidence >= 0.75 ? 'high' : confidence >= 0.4 ? 'medium' : 'low');
        }
        if (detail) {
            detail.innerHTML = `<span class="cp-detail-intent">${intent || 'Unknown'}</span>` +
                (transcript ? `<span class="cp-detail-transcript">"${transcript}"</span>` : '');
        }

        this._updateQualityMetrics();
    }

    // ════════════════════════════════════════════
    // COPILOT: RX COMPARISON
    // ════════════════════════════════════════════

    updateRxComparison(ar, current) {
        if (this.currentMode !== 'copilot') return;

        const fmt = (v) => v !== null && v !== undefined ? (v >= 0 ? '+' : '') + v.toFixed(2) : '—';
        const fmtAxis = (v) => v !== null && v !== undefined ? v + '°' : '—';
        const delta = (a, b) => {
            if (a === null || a === undefined || b === null || b === undefined) return '—';
            const d = b - a;
            return (d >= 0 ? '+' : '') + d.toFixed(2);
        };

        const fields = [
            ['RSph', ar.OD.sph, current.OD.sph, fmt, delta],
            ['RCyl', ar.OD.cyl, current.OD.cyl, fmt, delta],
            ['RAxis', ar.OD.axis, current.OD.axis, fmtAxis, (a, b) => (b - a) + '°'],
            ['LSph', ar.OS.sph, current.OS.sph, fmt, delta],
            ['LCyl', ar.OS.cyl, current.OS.cyl, fmt, delta],
            ['LAxis', ar.OS.axis, current.OS.axis, fmtAxis, (a, b) => (b - a) + '°'],
        ];

        fields.forEach(([key, arVal, curVal, fmtFn, deltaFn]) => {
            const arEl = document.getElementById(`cpAr${key}`);
            const curEl = document.getElementById(`cpCur${key}`);
            const deltaEl = document.getElementById(`cpDelta${key}`);
            if (arEl) arEl.textContent = fmtFn(arVal);
            if (curEl) curEl.textContent = fmtFn(curVal);
            if (deltaEl) {
                const d = deltaFn(arVal, curVal);
                deltaEl.textContent = d;
                deltaEl.className = 'cp-delta ' +
                    (d === '—' || d === '0.00' || d === '+0.00' || d === '0°' ? '' : 'changed');
            }
        });
    }

    // ════════════════════════════════════════════
    // COPILOT: QUALITY SCORING
    // ════════════════════════════════════════════

    recordOverride() { this.overrideCount++; this._updateQualityMetrics(); }
    recordClarification() { this.clarificationCount++; this._updateQualityMetrics(); }

    _updateQualityMetrics() {
        const respEl = document.getElementById('cpQualResponses');
        const ovrEl = document.getElementById('cpQualOverrides');
        const clarEl = document.getElementById('cpQualClarifications');
        const confEl = document.getElementById('cpQualAvgConf');
        const scoreEl = document.getElementById('cpQualityScore');

        if (respEl) respEl.textContent = this.responseCount;
        if (ovrEl) ovrEl.textContent = this.overrideCount;
        if (clarEl) clarEl.textContent = this.clarificationCount;

        const avgConf = this.confidenceHistory.length > 0
            ? this.confidenceHistory.reduce((a, b) => a + b, 0) / this.confidenceHistory.length
            : 0;
        if (confEl) confEl.textContent = avgConf > 0 ? Math.round(avgConf * 100) + '%' : '—';

        // Quality score: based on avg confidence, override ratio, clarification ratio
        if (scoreEl && this.responseCount > 0) {
            let score = avgConf * 50; // 50% weight on confidence
            score += Math.max(0, 30 - (this.overrideCount * 5)); // penalty per override
            score += Math.max(0, 20 - (this.clarificationCount * 3)); // penalty per clarification
            score = Math.min(100, Math.max(0, Math.round(score)));
            scoreEl.textContent = score + '/100';
            scoreEl.className = 'cp-quality-badge ' +
                (score >= 80 ? 'good' : score >= 50 ? 'fair' : 'poor');
        }
    }

    getQualityReport() {
        const avgConf = this.confidenceHistory.length > 0
            ? this.confidenceHistory.reduce((a, b) => a + b, 0) / this.confidenceHistory.length
            : 0;
        return {
            responses: this.responseCount,
            overrides: this.overrideCount,
            clarifications: this.clarificationCount,
            avgConfidence: Math.round(avgConf * 100),
            duration: this.getExamDuration(),
        };
    }

    // ════════════════════════════════════════════
    // SELF-TEST: ON-SCREEN CHART
    // ════════════════════════════════════════════

    _buildChartLines() {
        return [
            { va: '20/200', letters: 'E', size: 72 },
            { va: '20/100', letters: 'F P', size: 56 },
            { va: '20/70',  letters: 'T O Z', size: 44 },
            { va: '20/50',  letters: 'L P E D', size: 36 },
            { va: '20/40',  letters: 'P E C F D', size: 28 },
            { va: '20/30',  letters: 'E D F C Z P', size: 22 },
            { va: '20/25',  letters: 'F E L O P Z D', size: 18 },
            { va: '20/20',  letters: 'D E F P O T E C', size: 15 },
            { va: '20/15',  letters: 'L E F O D P C T', size: 12 },
        ];
    }

    updateSelfTestChart(chartIndex, eye) {
        if (this.currentMode !== 'selftest') return;

        const stChart = document.getElementById('selfTestChart');
        const lettersEl = document.getElementById('stChartLetters');
        const labelEl = document.getElementById('stChartLabel');
        const eyeEl = document.getElementById('stEyeIndicator');

        if (!stChart || !lettersEl) return;
        stChart.classList.remove('hidden');

        const line = this.chartLines[Math.min(chartIndex, this.chartLines.length - 1)];
        this.currentChartLine = chartIndex;

        lettersEl.textContent = line.letters;
        lettersEl.style.fontSize = `${line.size}px`;

        if (labelEl) labelEl.textContent = `Line ${chartIndex + 1} — ${line.va}`;

        if (eyeEl) {
            const eyeLabels = {
                'BINO': 'Testing: Both Eyes',
                'AuxLensL': 'Testing: Right Eye (cover left)',
                'AuxLensR': 'Testing: Left Eye (cover right)',
            };
            eyeEl.textContent = eyeLabels[eye] || 'Testing: Both Eyes';
        }
    }

    showDuochromeChart() {
        if (this.currentMode !== 'selftest') return;
        const lettersEl = document.getElementById('stChartLetters');
        const labelEl = document.getElementById('stChartLabel');
        if (lettersEl) {
            lettersEl.innerHTML = '<span class="st-red">O X O</span><span class="st-green">X O X</span>';
            lettersEl.style.fontSize = '32px';
        }
        if (labelEl) labelEl.textContent = 'Red/Green Test';
    }

    showBinocularChart() {
        if (this.currentMode !== 'selftest') return;
        const lettersEl = document.getElementById('stChartLetters');
        const labelEl = document.getElementById('stChartLabel');
        if (lettersEl) {
            lettersEl.innerHTML = '<span class="st-bino-top">O X O</span><span class="st-bino-bottom">X O X</span>';
            lettersEl.style.fontSize = '28px';
        }
        if (labelEl) labelEl.textContent = 'Binocular Balance';
    }

    // ════════════════════════════════════════════
    // COMFORT CHECK
    // ════════════════════════════════════════════

    showComfortCheck() {
        const modal = document.getElementById('comfortModal');
        if (modal) {
            modal.classList.remove('hidden');
            this.pauseExam();
        }
    }

    hideComfortCheck() {
        const modal = document.getElementById('comfortModal');
        if (modal) {
            modal.classList.add('hidden');
            this.resumeExam();
        }
    }

    // ════════════════════════════════════════════
    // RESULTS: PATIENT-FRIENDLY SUMMARY
    // ════════════════════════════════════════════

    showPatientResults(rx, flags) {
        if (this.currentMode === 'copilot') return;

        const summary = document.getElementById('patientSummary');
        if (!summary) return;
        summary.classList.remove('hidden');

        // Determine approximate VA from SPH
        const approxVA = (sph) => {
            const absSph = Math.abs(sph || 0);
            if (absSph <= 0.25) return '20/20 (Excellent)';
            if (absSph <= 0.75) return '20/25 (Very Good)';
            if (absSph <= 1.50) return '20/40 (Good)';
            if (absSph <= 3.00) return '20/80 (Moderate)';
            if (absSph <= 5.00) return '20/200 (Needs correction)';
            return '20/400+ (Strong correction needed)';
        };

        const rVision = document.getElementById('psRightVision');
        const lVision = document.getElementById('psLeftVision');
        if (rVision && rx.OD) rVision.textContent = approxVA(rx.OD.sph);
        if (lVision && rx.OS) lVision.textContent = approxVA(rx.OS.sph);

        // Explanation
        const explEl = document.getElementById('psExplanation');
        if (explEl) {
            const rSph = rx.OD?.sph || 0;
            const lSph = rx.OS?.sph || 0;
            let explanation = '';

            if (Math.abs(rSph) <= 0.25 && Math.abs(lSph) <= 0.25) {
                explanation = 'Great news! Your vision is near perfect. You may not need glasses for distance.';
            } else if (rSph < -0.5 || lSph < -0.5) {
                explanation = 'You have some degree of near-sightedness (myopia). Objects far away may appear blurry. Glasses or contact lenses will help you see clearly at distance.';
            } else if (rSph > 0.5 || lSph > 0.5) {
                explanation = 'You have some degree of far-sightedness (hyperopia). You may experience eye strain with prolonged near work. Glasses can help reduce fatigue.';
            } else {
                explanation = 'Your prescription has been determined. The numbers below tell your optometrist exactly what lenses you need.';
            }

            if (flags && flags.length > 0) {
                explanation += ' Some items were flagged during your exam — your optometrist can discuss these with you.';
            }

            explEl.textContent = explanation;
        }

        // Summary text
        const summaryText = document.getElementById('psSummaryText');
        if (summaryText) {
            const duration = this.getExamDuration();
            const m = Math.floor(duration / 60);
            summaryText.textContent = m > 0
                ? `Your exam took ${m} minute${m !== 1 ? 's' : ''}. Here's what we found.`
                : 'Your results are ready. Here\'s what we found.';
        }
    }

    showCopilotResults(qualityReport) {
        if (this.currentMode !== 'copilot') return;

        const card = document.getElementById('rxQualityReport');
        if (card) card.classList.remove('hidden');

        const scoreEl = document.getElementById('rxQualScore');
        const stepsEl = document.getElementById('rxQualSteps');
        const confEl = document.getElementById('rxQualConf');
        const durEl = document.getElementById('rxQualDuration');

        if (stepsEl) stepsEl.textContent = qualityReport.responses;
        if (confEl) confEl.textContent = qualityReport.avgConfidence + '%';
        if (durEl) {
            const m = Math.floor(qualityReport.duration / 60);
            const s = qualityReport.duration % 60;
            durEl.textContent = `${m}:${s.toString().padStart(2, '0')}`;
        }
        if (scoreEl) {
            let score = qualityReport.avgConfidence * 0.5;
            score += Math.max(0, 30 - qualityReport.overrides * 5);
            score += Math.max(0, 20 - qualityReport.clarifications * 3);
            score = Math.min(100, Math.max(0, Math.round(score)));
            scoreEl.textContent = score + '/100';
        }
    }

    // ════════════════════════════════════════════
    // HELPERS
    // ════════════════════════════════════════════

    _hideIntakeCards(titles) {
        document.querySelectorAll('.intake-card h2').forEach(h2 => {
            if (titles.includes(h2.textContent)) {
                h2.closest('.intake-card').classList.add('hidden');
            }
        });
    }

    _showAllIntakeCards() {
        document.querySelectorAll('.intake-card').forEach(card => {
            card.classList.remove('hidden');
        });
    }

    generateShareableReport(patientData, rx, flags) {
        const report = {
            title: 'Vision Screening Report',
            date: new Date().toISOString().split('T')[0],
            patient: {
                name: patientData.name || 'Not provided',
                age: patientData.age || 'Not provided',
            },
            prescription: {
                rightEye: rx.OD,
                leftEye: rx.OS,
                pd: patientData.pd,
            },
            flags: (flags || []).map(f => f.description || f),
            duration: this.getExamDuration(),
            mode: this.currentMode,
            disclaimer: 'This is a preliminary screening result. Please visit a licensed optometrist for a comprehensive eye exam before ordering corrective lenses.',
        };

        return JSON.stringify(report, null, 2);
    }
}
