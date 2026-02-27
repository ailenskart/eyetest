/**
 * AI Eye Test — Main Application Controller
 *
 * Wires together:
 *   - CV5000Protocol (phoropter + chart control)
 *   - RefractionEngine (10-phase state machine)
 *   - AIOptometrist (conversation + voice I/O)
 *
 * Handles:
 *   - Patient intake → exam flow → results
 *   - Auto-flip timers for JCC phases
 *   - UI updates (power display, chat, progress, logs)
 *   - Session export
 */

class EyeTestApp {
    constructor() {
        this.cv5000 = null;
        this.engine = null;
        this.ai = null;

        // ── UI state ──
        this.currentScreen = 'intake';
        this.autoFlipTimer = null;
        this.logEntries = [];
        this.voiceEnabled = true;

        this._init();
    }

    _init() {
        document.addEventListener('DOMContentLoaded', () => {
            this._bindIntakeEvents();
            this._bindExamEvents();
            this._bindResultsEvents();
            this._updateTimestamp();
            setInterval(() => this._updateTimestamp(), 1000);
        });
    }

    // ════════════════════════════════════════════
    // INTAKE SCREEN
    // ════════════════════════════════════════════
    _bindIntakeEvents() {
        document.getElementById('startExamBtn').addEventListener('click', () => this._startExam());
        document.getElementById('hasOldRx').addEventListener('change', (e) => {
            document.getElementById('oldRxFields').classList.toggle('hidden', !e.target.checked);
        });
    }

    _collectPatientData() {
        const f = (id) => parseFloat(document.getElementById(id).value) || 0;
        const v = (id) => document.getElementById(id).value;

        return {
            name: v('patientName'),
            age: f('patientAge'),
            gender: v('patientGender'),
            pd: f('patientPD'),
            autorefraction: {
                OD: { sph: f('arOdSph'), cyl: f('arOdCyl'), axis: f('arOdAxis') },
                OS: { sph: f('arOsSph'), cyl: f('arOsCyl'), axis: f('arOsAxis') },
            },
            lensometry: {
                hasOldRx: document.getElementById('hasOldRx').checked,
                OD: { sph: f('oldOdSph'), cyl: f('oldOdCyl'), axis: f('oldOdAxis'), add: f('oldOdAdd') },
                OS: { sph: f('oldOsSph'), cyl: f('oldOsCyl'), axis: f('oldOsAxis'), add: f('oldOsAdd') },
            },
        };
    }

    async _startExam() {
        const patientData = this._collectPatientData();
        const simulated = document.getElementById('simulatedMode').checked;
        this.voiceEnabled = document.getElementById('voiceEnabled').checked;

        // ── Initialize modules ──
        this.cv5000 = new CV5000Protocol({
            baseUrl: document.getElementById('cv5000Url').value,
            phoroptertId: document.getElementById('phoroptertId').value,
        });
        this.cv5000.simulatedMode = simulated;

        this.engine = new RefractionEngine(this.cv5000);
        this.engine.setPatientData(patientData);

        this.ai = new AIOptometrist({ voiceEnabled: this.voiceEnabled });

        // ── Wire events ──
        this.engine.on('phase-change', (progress) => this._onPhaseChange(progress));
        this.engine.on('exam-complete', (rx) => this._onExamComplete(rx));

        this.ai.on('asr-start', () => this._onASRStart());
        this.ai.on('asr-result', (data) => this._onASRResult(data));
        this.ai.on('asr-interim', (data) => this._onASRInterim(data));
        this.ai.on('asr-end', () => this._onASREnd());
        this.ai.on('asr-error', (data) => this._onASRError(data));
        this.ai.on('tts-start', (data) => this._log('voice', `Speaking: "${data.text.substring(0, 60)}..."`));
        this.ai.on('log-entry', (entry) => this._onConversationLog(entry));

        this.cv5000.on('command', (cmd) => {
            this._log('power', `CV-5000: ${cmd.type} ${JSON.stringify(cmd.params || '').substring(0, 80)}`);
        });

        // ── Switch screen ──
        this._showScreen('exam');
        this._updateConnectionBadge(simulated);

        // ── Start ──
        this._log('system', `Exam started for ${patientData.name || 'Patient'}`);
        this._log('system', `AR: OD ${patientData.autorefraction.OD.sph}/${patientData.autorefraction.OD.cyl}x${patientData.autorefraction.OD.axis} | OS ${patientData.autorefraction.OS.sph}/${patientData.autorefraction.OS.cyl}x${patientData.autorefraction.OS.axis}`);

        // Greet patient
        if (this.voiceEnabled) {
            await this.ai.greetPatient(patientData.name);
        }

        const response = await this.engine.startExam();
        this._handleEngineResponse(response);
    }

    // ════════════════════════════════════════════
    // EXAM SCREEN EVENTS
    // ════════════════════════════════════════════
    _bindExamEvents() {
        document.getElementById('micBtn').addEventListener('click', () => this._toggleMic());
        document.getElementById('voiceToggleBtn').addEventListener('click', () => this._toggleVoice());
        document.getElementById('exportBtn').addEventListener('click', () => this._exportSession());
        document.getElementById('takeoverBtn').addEventListener('click', () => this._handleTakeover());
    }

    _bindResultsEvents() {
        document.getElementById('exportResultsBtn').addEventListener('click', () => this._exportFullReport());
        document.getElementById('printRxBtn').addEventListener('click', () => window.print());
        document.getElementById('newExamBtn').addEventListener('click', () => location.reload());
    }

    // ════════════════════════════════════════════
    // ENGINE RESPONSE HANDLER
    // ════════════════════════════════════════════
    async _handleEngineResponse(response) {
        if (!response) return;

        // Update power display
        if (response.power) this._updatePowerDisplay(response.power);

        // Update occluder/chart
        if (response.occluder) document.getElementById('occluderDisplay').textContent = response.occluder;
        if (response.chart) document.getElementById('chartDisplay').textContent = response.chart;
        if (response.chartVA) document.getElementById('vaDisplay').textContent = response.chartVA;

        // Update progress
        if (response.progress) this._updateProgress(response.progress);

        // Row counter
        document.getElementById('rowCounter').textContent = `Row: ${this.engine.rowCounter}`;

        // Chart selector
        this._updateChartSelector(response);

        // Flags
        this._updateFlags(response.progress?.flags);

        // Handle exam complete
        if (response.phaseId === 'complete' || response.status === 'complete') {
            this._onExamComplete(response.prescription);
            return;
        }

        // Show question in chat
        if (response.question) {
            this._addChatMessage('system', response.question);
            document.getElementById('currentQuestion').textContent = response.question;
        }

        // Render intent buttons
        this._renderIntentButtons(response.intents || []);

        // Auto-flip handling
        if (response.auto_flip) {
            this._startAutoFlip(response.flip_wait_seconds || 2);
        } else {
            this._clearAutoFlip();
        }

        // Speak question
        if (this.voiceEnabled && response.question && !response.auto_flip) {
            await this.ai.askQuestion(response.question, response.intents || [], response.phaseId);
        }
    }

    // ════════════════════════════════════════════
    // INTENT HANDLING
    // ════════════════════════════════════════════
    _renderIntentButtons(intents) {
        const container = document.getElementById('intentButtons');
        container.innerHTML = '';

        intents.forEach(intent => {
            const btn = document.createElement('button');
            btn.className = 'intent-btn';
            btn.textContent = intent;
            btn.addEventListener('click', () => this._handleIntentClick(intent));
            container.appendChild(btn);
        });
    }

    async _handleIntentClick(intent) {
        this._clearAutoFlip();

        // Add patient response to chat
        this._addChatMessage('patient', intent);
        this._log('intent', `Patient: "${intent}"`);

        // Process through AI (for logging)
        if (this.ai) {
            this.ai.processPatientInput(intent, false);
        }

        // Process through engine
        const response = await this.engine.processResponse(intent);
        await this._handleEngineResponse(response);
    }

    async _handleVoiceIntent(transcript) {
        if (!this.ai || !this.engine) return;

        const currentIntents = this.engine._getIntents();
        const result = this.ai.processPatientInput(transcript, true);

        if (result.action === 'proceed' && result.intent) {
            this._addChatMessage('patient', `"${transcript}" → ${result.intent}`);
            this._log('voice', `Classified: "${transcript}" → ${result.intent} (${(result.confidence * 100).toFixed(0)}%)`);

            const response = await this.engine.processResponse(result.intent);
            await this._handleEngineResponse(response);
        } else if (result.action === 'confirm') {
            this._addChatMessage('system', result.message);
            // Show confirm/deny buttons
            this._renderIntentButtons([result.intent, 'Repeat question']);
        } else if (result.action === 'clarify') {
            this._addChatMessage('system', result.message);
            this._log('voice', `Low confidence: "${transcript}" (${(result.confidence * 100).toFixed(0)}%)`);
            if (this.voiceEnabled) {
                await this.ai.speak(result.message);
            }
        } else if (result.action === 'show_buttons') {
            this._addChatMessage('system', result.message);
            this._renderIntentButtons(currentIntents);
        }
    }

    // ════════════════════════════════════════════
    // AUTO-FLIP (JCC)
    // ════════════════════════════════════════════
    _startAutoFlip(seconds) {
        this._clearAutoFlip();

        const indicator = document.getElementById('autoFlipIndicator');
        const bar = document.getElementById('flipProgressBar');
        const countdown = document.getElementById('flipCountdown');

        indicator.classList.remove('hidden');
        countdown.textContent = seconds;
        bar.style.transition = 'none';
        bar.style.width = '0%';

        // Force reflow then animate
        bar.offsetHeight;
        bar.style.transition = `width ${seconds}s linear`;
        bar.style.width = '100%';

        let remaining = seconds;
        const countdownInterval = setInterval(() => {
            remaining--;
            countdown.textContent = Math.max(0, remaining);
        }, 1000);

        this.autoFlipTimer = setTimeout(async () => {
            clearInterval(countdownInterval);
            indicator.classList.add('hidden');

            // Send AUTO_FLIP to engine
            this._log('system', 'Auto-flip triggered');
            const response = await this.engine.processResponse('AUTO_FLIP');
            await this._handleEngineResponse(response);
        }, seconds * 1000);
    }

    _clearAutoFlip() {
        if (this.autoFlipTimer) {
            clearTimeout(this.autoFlipTimer);
            this.autoFlipTimer = null;
        }
        const indicator = document.getElementById('autoFlipIndicator');
        if (indicator) indicator.classList.add('hidden');
    }

    // ════════════════════════════════════════════
    // UI UPDATES
    // ════════════════════════════════════════════
    _showScreen(name) {
        document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
        const screenMap = { intake: 'intakeScreen', exam: 'examScreen', results: 'resultsScreen' };
        const el = document.getElementById(screenMap[name]);
        if (el) el.classList.add('active');
        this.currentScreen = name;
    }

    _updateConnectionBadge(simulated) {
        const badge = document.getElementById('connectionBadge');
        if (simulated) {
            badge.textContent = 'Simulated';
            badge.className = 'badge badge-warning';
        } else {
            badge.textContent = 'Connected';
            badge.className = 'badge badge-success';
        }
    }

    _updatePowerDisplay(power) {
        const fmt = (v) => (v >= 0 ? '+' : '') + v.toFixed(2);
        document.getElementById('rSphDisplay').textContent = fmt(power.right.sph);
        document.getElementById('rCylDisplay').textContent = fmt(power.right.cyl);
        document.getElementById('rAxisDisplay').textContent = Math.round(power.right.axis);
        document.getElementById('rAddDisplay').textContent = fmt(power.right.add);
        document.getElementById('lSphDisplay').textContent = fmt(power.left.sph);
        document.getElementById('lCylDisplay').textContent = fmt(power.left.cyl);
        document.getElementById('lAxisDisplay').textContent = Math.round(power.left.axis);
        document.getElementById('lAddDisplay').textContent = fmt(power.left.add);
    }

    _updateProgress(progress) {
        // Phase name
        document.getElementById('currentPhaseName').textContent = progress.phaseName;

        // Progress bar
        document.getElementById('progressBar').style.width = `${progress.percent}%`;

        // Phase dots
        const container = document.getElementById('progressPhases');
        container.innerHTML = '';
        (progress.phases || []).forEach(p => {
            const dot = document.createElement('div');
            dot.className = `phase-dot ${p.status}`;

            const label = p.id.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            const shortLabel = label.length > 12 ? label.substring(0, 10) + '..' : label;

            dot.innerHTML = `<span class="dot"></span><span>${shortLabel}</span>`;
            container.appendChild(dot);
        });
    }

    _updateChartSelector(response) {
        const selector = document.getElementById('chartSelector');
        const buttonsContainer = document.getElementById('chartButtons');

        if (response.chart_info) {
            selector.classList.remove('hidden');
            buttonsContainer.innerHTML = '';

            response.chart_info.available_charts.forEach((chart, i) => {
                const btn = document.createElement('button');
                btn.className = `chart-btn${i === response.chart_info.current_index ? ' active' : ''}`;

                const va = this.cv5000.getChartVA(chart);
                btn.textContent = va ? `${chart.replace(/_/g, ' ')} (${va})` : chart.replace(/_/g, ' ');

                btn.addEventListener('click', async () => {
                    const resp = await this.engine.switchChart(i);
                    await this._handleEngineResponse(resp);
                });
                buttonsContainer.appendChild(btn);
            });
        } else {
            selector.classList.add('hidden');
        }
    }

    _updateFlags(flags) {
        const panel = document.getElementById('flagsPanel');
        const list = document.getElementById('flagsList');

        if (flags && flags.length > 0) {
            panel.classList.remove('hidden');
            list.innerHTML = '';
            flags.forEach(f => {
                const div = document.createElement('div');
                div.className = 'flag-item';
                div.textContent = f.detail || f.type;
                list.appendChild(div);
            });
        }
    }

    // ── Chat ──
    _addChatMessage(type, text) {
        const container = document.getElementById('chatContainer');
        const msg = document.createElement('div');
        msg.className = `chat-msg ${type}`;

        const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        msg.innerHTML = `${this._escapeHtml(text)}<div class="msg-meta">${time}</div>`;

        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
    }

    _addPhaseChangeMessage(phaseName) {
        const container = document.getElementById('chatContainer');
        const msg = document.createElement('div');
        msg.className = 'chat-msg phase-change';
        msg.textContent = phaseName;
        container.appendChild(msg);
        container.scrollTop = container.scrollHeight;
    }

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ── Logging ──
    _log(type, message) {
        const time = new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
        const entry = { time, type, message };
        this.logEntries.push(entry);

        const container = document.getElementById('logContainer');
        if (container) {
            const div = document.createElement('div');
            div.className = 'log-entry';
            div.innerHTML = `
                <span class="log-time">${time}</span>
                <span class="log-type ${type}">${type}</span>
                <span class="log-message">${this._escapeHtml(message)}</span>
            `;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        const counter = document.getElementById('logCount');
        if (counter) counter.textContent = this.logEntries.length;
    }

    _updateTimestamp() {
        const el = document.getElementById('examTimestamp');
        if (el) {
            el.textContent = new Date().toLocaleString('en-US', {
                year: 'numeric', month: 'short', day: 'numeric',
                hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
            });
        }
    }

    // ════════════════════════════════════════════
    // VOICE CONTROLS
    // ════════════════════════════════════════════
    _toggleMic() {
        if (!this.ai) return;
        if (this.ai.isListening) {
            this.ai.stopListening();
        } else {
            this.ai.startListening();
        }
    }

    _toggleVoice() {
        this.voiceEnabled = !this.voiceEnabled;
        if (this.ai) this.ai.voiceEnabled = this.voiceEnabled;

        const btn = document.getElementById('voiceToggleBtn');
        btn.textContent = `Voice: ${this.voiceEnabled ? 'ON' : 'OFF'}`;
    }

    _onASRStart() {
        const mic = document.getElementById('micBtn');
        mic.classList.add('listening');
        document.getElementById('voiceTranscript').innerHTML = '<span class="interim">Listening...</span>';
    }

    _onASRResult(data) {
        const mic = document.getElementById('micBtn');
        mic.classList.remove('listening');
        document.getElementById('voiceTranscript').innerHTML = `<span class="final">${this._escapeHtml(data.transcript)}</span>`;
        this._log('voice', `Heard: "${data.transcript}"`);

        // Process voice input
        this._handleVoiceIntent(data.transcript);
    }

    _onASRInterim(data) {
        document.getElementById('voiceTranscript').innerHTML = `<span class="interim">${this._escapeHtml(data.transcript)}</span>`;
    }

    _onASREnd() {
        document.getElementById('micBtn').classList.remove('listening');
    }

    _onASRError(data) {
        document.getElementById('micBtn').classList.remove('listening');
        this._log('error', `ASR Error: ${data.error}`);
    }

    // ════════════════════════════════════════════
    // EVENT HANDLERS
    // ════════════════════════════════════════════
    _onPhaseChange(progress) {
        this._addPhaseChangeMessage(progress.phaseName);
        this._log('phase', `→ ${progress.phaseName}`);

        if (this.voiceEnabled && this.ai) {
            this.ai.announcePhase(progress.phaseName);
        }
    }

    _onExamComplete(rx) {
        this._clearAutoFlip();
        this._log('system', 'Examination complete');

        if (rx) {
            this._showResults(rx);
            if (this.voiceEnabled && this.ai) {
                this.ai.announcePrescription(rx);
            }
        }
    }

    _onConversationLog(entry) {
        // Additional logging from AI module — already tracked via _log
    }

    _showResults(rx) {
        const fmt = (v) => (v >= 0 ? '+' : '') + v.toFixed(2);

        if (rx.right) {
            document.getElementById('rxRSph').textContent = fmt(rx.right.sph);
            document.getElementById('rxRCyl').textContent = fmt(rx.right.cyl);
            document.getElementById('rxRAxis').textContent = `${rx.right.axis}\u00B0`;
            document.getElementById('rxRAdd').textContent = fmt(rx.right.add);
        }
        if (rx.left) {
            document.getElementById('rxLSph').textContent = fmt(rx.left.sph);
            document.getElementById('rxLCyl').textContent = fmt(rx.left.cyl);
            document.getElementById('rxLAxis').textContent = `${rx.left.axis}\u00B0`;
            document.getElementById('rxLAdd').textContent = fmt(rx.left.add);
        }
        if (rx.pd) {
            document.getElementById('rxPD').textContent = rx.pd;
        }

        if (rx.flags && rx.flags.length > 0) {
            const flagsPanel = document.getElementById('rxFlags');
            flagsPanel.classList.remove('hidden');
            const list = document.getElementById('rxFlagsList');
            list.innerHTML = '';
            rx.flags.forEach(f => {
                const li = document.createElement('li');
                li.textContent = f.detail || f.type;
                list.appendChild(li);
            });
        }

        this._showScreen('results');
    }

    // ════════════════════════════════════════════
    // TAKEOVER & EXPORT
    // ════════════════════════════════════════════
    _handleTakeover() {
        this._clearAutoFlip();
        this._log('system', 'Manual takeover activated — optometrist control');
        this._addChatMessage('system', 'Manual takeover activated. The optometrist is now in control.');
        document.getElementById('statusMessage').textContent = 'Manual Takeover Mode';
    }

    _exportSession() {
        const data = {
            exportTime: new Date().toISOString(),
            patientData: this.engine ? this.engine.patientData : null,
            currentPower: this.engine ? this.engine.getPower() : null,
            progress: this.engine ? this.engine.getProgress() : null,
            sessionHistory: this.engine ? this.engine.sessionHistory : [],
            conversationLog: this.ai ? this.ai.getConversationLog() : [],
            eventLog: this.logEntries,
            flags: this.engine ? this.engine.flags : [],
        };

        this._downloadJSON(data, `eye-test-session-${Date.now()}.json`);
    }

    _exportFullReport() {
        const data = this.engine ? this.engine.exportExamData() : {};
        data.conversationLog = this.ai ? this.ai.exportSession() : {};
        data.eventLog = this.logEntries;
        this._downloadJSON(data, `eye-test-report-${Date.now()}.json`);
    }

    _downloadJSON(data, filename) {
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    }
}

// ── Initialize ──
const app = new EyeTestApp();
