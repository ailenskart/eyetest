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
        this.mode = new ModeManager();

        // ── UI state ──
        this.currentScreen = 'mode';
        this.autoFlipTimer = null;
        this.logEntries = [];
        this.voiceEnabled = true;

        this._init();
    }

    _init() {
        document.addEventListener('DOMContentLoaded', () => {
            this._bindModeEvents();
            this._bindIntakeEvents();
            this._bindExamEvents();
            this._bindResultsEvents();
            this._initVideoPanel();
            this._initComfortCheck();
            this._initCopilotControls();
            this._updateTimestamp();
            setInterval(() => this._updateTimestamp(), 1000);
        });

        // Release device on page unload
        window.addEventListener('beforeunload', () => {
            if (this.cv5000 && this.cv5000.connectionStatus === 'acquired') {
                this.cv5000.destroy();
            }
        });
    }

    // ════════════════════════════════════════════
    // MODE SELECTION
    // ════════════════════════════════════════════
    _bindModeEvents() {
        document.querySelectorAll('.mode-select-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const selectedMode = btn.dataset.mode;
                this.mode.setMode(selectedMode);
                this._showScreen('intake');
            });
        });

        const backBtn = document.getElementById('backToModeBtn');
        if (backBtn) {
            backBtn.addEventListener('click', () => this._showScreen('mode'));
        }
    }

    _initComfortCheck() {
        const comfortBtn = document.getElementById('comfortCheckBtn');
        if (comfortBtn) {
            comfortBtn.addEventListener('click', () => this.mode.showComfortCheck());
        }

        document.querySelectorAll('.comfort-resume-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.mode.hideComfortCheck();
            });
        });
        document.querySelectorAll('.comfort-water-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                if (this.ai) this.ai.speak('Take your time. Press continue when you\'re ready.');
            });
        });
        document.querySelectorAll('.comfort-stop-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                this.mode.hideComfortCheck();
                if (this.engine) {
                    const rx = this.engine.getFinalRx();
                    this._onExamComplete(rx);
                }
            });
        });
    }

    _initCopilotControls() {
        // Override steppers
        document.querySelectorAll('.cp-step-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const param = btn.dataset.param;
                const delta = parseFloat(btn.dataset.delta);
                const valEl = document.getElementById(`cpOvr${param.charAt(0).toUpperCase() + param.slice(1)}`);
                if (valEl) {
                    let val = parseFloat(valEl.textContent) || 0;
                    val += delta;
                    if (param === 'axis') val = ((val % 180) + 180) % 180 || 180;
                    valEl.textContent = param === 'axis' ? val : (val >= 0 ? '+' : '') + val.toFixed(2);
                }
            });
        });

        // Apply override
        const applyBtn = document.getElementById('cpApplyOverride');
        if (applyBtn) {
            applyBtn.addEventListener('click', () => this._applyCopilotOverride());
        }
    }

    _applyCopilotOverride() {
        if (!this.engine || !this.cv5000) return;

        const eye = document.getElementById('cpOvrEye').value;
        const sph = parseFloat(document.getElementById('cpOvrSph').textContent) || 0;
        const cyl = parseFloat(document.getElementById('cpOvrCyl').textContent) || 0;
        const axis = parseInt(document.getElementById('cpOvrAxis').textContent) || 180;

        const state = this.cv5000.state;
        if (eye === 'right') {
            state.r_sph = sph; state.r_cyl = cyl; state.r_axis = axis;
        } else {
            state.l_sph = sph; state.l_cyl = cyl; state.l_axis = axis;
        }

        this.cv5000.setPower(state.r_sph, state.r_cyl, state.r_axis, state.l_sph, state.l_cyl, state.l_axis);
        this._updatePowerDisplay({ OD: { sph: state.r_sph, cyl: state.r_cyl, axis: state.r_axis }, OS: { sph: state.l_sph, cyl: state.l_cyl, axis: state.l_axis } });
        this.mode.recordOverride();
        this._log('override', `Manual override: ${eye} → SPH:${sph} CYL:${cyl} AXIS:${axis}`);
    }

    // ════════════════════════════════════════════
    // INTAKE SCREEN
    // ════════════════════════════════════════════
    _bindIntakeEvents() {
        document.getElementById('startExamBtn').addEventListener('click', () => this._startExam());
        document.getElementById('hasOldRx').addEventListener('change', (e) => {
            document.getElementById('oldRxFields').classList.toggle('hidden', !e.target.checked);
        });
        document.getElementById('loadDevicesBtn').addEventListener('click', () => this._loadDevices());
        document.getElementById('simulatedMode').addEventListener('change', (e) => {
            if (!e.target.checked) this._loadDevices();
            else document.getElementById('deviceList').innerHTML = '<span class="device-placeholder">Enable real phoropter mode to see devices</span>';
        });
        document.getElementById('showAllDevices')?.addEventListener('change', () => this._loadDevices());
    }

    async _loadDevices() {
        const baseUrl = document.getElementById('cv5000Url').value.trim();
        const listEl = document.getElementById('deviceList');
        const showAll = document.getElementById('showAllDevices')?.checked ?? true;
        listEl.innerHTML = '<span class="device-placeholder">Loading phoropters...</span>';

        const tempProto = new CV5000Protocol({ baseUrl, simulatedMode: false });
        try {
            const data = await tempProto.listDevices(showAll);
            const arr = Array.isArray(data) ? data : (data.devices || []);
            if (!arr.length) {
                listEl.innerHTML = '<span class="device-placeholder">No phoropters found. Check the broker URL or try "Show all devices".</span>';
                return;
            }

            listEl.innerHTML = '';
            arr.forEach(d => {
                const id = d.id || d.device_id || d.phoropter_id || '';
                const name = d.name || id;
                const store = d.store || '';
                const status = (d.status || 'UNKNOWN').toUpperCase();
                const statusClass = status === 'AVAILABLE' ? 'available' : status === 'CONNECTED' ? 'connected' : 'offline';
                const isAvailable = status === 'AVAILABLE';

                const item = document.createElement('div');
                item.className = `device-item ${isAvailable ? 'device-available' : ''}`;
                item.dataset.deviceId = id;
                item.innerHTML = `
                    <div class="device-item-main">
                        <span class="device-name">${name}</span>
                        ${store ? `<span class="device-store">${store}</span>` : ''}
                        <span class="device-id">${id}</span>
                    </div>
                    <span class="device-status ${statusClass}">${status}</span>
                `;
                item.addEventListener('click', () => {
                    document.querySelectorAll('.device-item').forEach(el => el.classList.remove('selected'));
                    item.classList.add('selected');
                    document.getElementById('phoroptertId').value = id;
                });
                listEl.appendChild(item);
            });
        } catch (err) {
            listEl.innerHTML = `<span class="device-placeholder">Error: ${err.message}</span>`;
        }
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

        const phoroptertId = document.getElementById('phoroptertId').value.trim();
        const brainId = document.getElementById('brainId').value.trim() || `brain_${Date.now()}`;

        if (!simulated && !phoroptertId) {
            alert('Please select a phoropter device or enable Simulated Mode.');
            return;
        }

        // ── Initialize modules ──
        this.cv5000 = new CV5000Protocol({
            baseUrl: document.getElementById('cv5000Url').value.trim(),
            phoroptertId,
            brainId,
            brainName: 'AI Eye Test',
            simulatedMode: simulated,
        });

        // ── Acquire device if not simulated ──
        if (!simulated) {
            const result = await this.cv5000.acquireDevice(phoroptertId);
            if (result.status === 'FAILED' || result.reason === 'DEVICE_ALREADY_CONNECTED') {
                alert(`Cannot acquire device: ${result.reason || 'Unknown error'}.\nConnected brain: ${result.connected_brain || 'unknown'}`);
                return;
            }
        }

        // Always reset at exam start so machine + engine start from same baseline.
        const resetResult = await this.cv5000.resetPhoropter();
        if (!simulated && (resetResult?.status === 'FAILED' || resetResult?.success === false)) {
            alert(`Cannot reset phoropter: ${resetResult?.reason || 'Unknown error'}`);
            return;
        }

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

        // ── Start mode-aware features ──
        this.mode.startExamTimer();
        this._patientData = patientData; // Store for later use in results

        // ── Start ──
        this._log('system', `Exam started for ${patientData.name || 'Patient'} [${this.mode.currentMode} mode]`);
        this._log('system', `AR: OD ${patientData.autorefraction.OD.sph}/${patientData.autorefraction.OD.cyl}x${patientData.autorefraction.OD.axis} | OS ${patientData.autorefraction.OS.sph}/${patientData.autorefraction.OS.cyl}x${patientData.autorefraction.OS.axis}`);

        // Initialize copilot Rx comparison
        if (this.mode.isMode('copilot')) {
            this.mode.updateRxComparison(patientData.autorefraction, {
                OD: { sph: 0, cyl: 0, axis: 180 },
                OS: { sph: 0, cyl: 0, axis: 180 },
            });
        }

        // Greet patient
        if (this.voiceEnabled) {
            const greetings = {
                customer: patientData.name ? `Hello ${patientData.name}, welcome! I'll guide you through your eye test step by step. Just answer my questions naturally.` : 'Welcome! I\'ll guide you through your eye test. Just answer my questions naturally.',
                copilot: null, // Use default
                selftest: patientData.name ? `Hello ${patientData.name}! Let's check your vision. Please sit at arm's length from the screen in a well-lit room.` : 'Hello! Let\'s check your vision. Please sit at arm\'s length from the screen in a well-lit room.',
            };
            const greeting = greetings[this.mode.currentMode];
            if (greeting) {
                await this.ai.speak(greeting);
            } else {
                await this.ai.greetPatient(patientData.name);
            }
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
        this._initRationalePanel();
    }

    _bindResultsEvents() {
        document.getElementById('exportResultsBtn').addEventListener('click', () => this._exportFullReport());
        document.getElementById('printRxBtn').addEventListener('click', () => window.print());
        document.getElementById('newExamBtn').addEventListener('click', () => location.reload());

        // Self-test: shareable report
        const shareBtn = document.getElementById('shareResultsBtn');
        if (shareBtn) {
            shareBtn.addEventListener('click', () => this._shareReport());
        }

        // Self-test: book appointment
        const bookBtn = document.getElementById('bookApptBtn');
        if (bookBtn) {
            bookBtn.addEventListener('click', () => {
                window.open('https://www.lenskart.com/stores-near-me', '_blank');
            });
        }
    }

    _shareReport() {
        if (!this.engine) return;
        const rx = this.engine.getFinalRx();
        const report = this.mode.generateShareableReport(
            this._patientData || {},
            { OD: rx?.right, OS: rx?.left },
            rx?.flags
        );
        // Copy to clipboard
        navigator.clipboard.writeText(report).then(() => {
            const shareBtn = document.getElementById('shareResultsBtn');
            if (shareBtn) {
                const orig = shareBtn.textContent;
                shareBtn.textContent = 'Copied to clipboard!';
                setTimeout(() => { shareBtn.textContent = orig; }, 2000);
            }
        }).catch(() => {
            // Fallback: download as file
            const blob = new Blob([report], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'vision-report.json';
            a.click();
            URL.revokeObjectURL(url);
        });
    }

    // ════════════════════════════════════════════
    // VIDEO ANALYSIS / SLM PANEL
    // ════════════════════════════════════════════
    _initVideoPanel() {
        // Initialize SLM and Video Analyzer
        this.slm = new OptomSLM();
        this.videoAnalyzer = new VideoAnalyzer(this.slm);

        // Tab switching
        document.querySelectorAll('.rp-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.rp-tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.rp-tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                const targetId = tab.dataset.tab === 'log' ? 'logTab' : 'videoTab';
                document.getElementById(targetId).classList.add('active');
            });
        });

        // Video URL load
        document.getElementById('vaLoadBtn').addEventListener('click', () => this._vaLoadVideo());
        document.getElementById('vaVideoUrl').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') this._vaLoadVideo();
        });

        // File upload
        document.getElementById('vaFileInput').addEventListener('change', (e) => {
            if (e.target.files.length > 0) this._vaLoadVideoFile(e.target.files[0]);
        });

        // Analyze button
        document.getElementById('vaAnalyzeBtn').addEventListener('click', () => this._vaAnalyze());

        // Annotation buttons
        document.getElementById('vaMarkPhaseBtn').addEventListener('click', () => {
            const marker = document.getElementById('vaPhaseMarker');
            marker.classList.toggle('hidden');
            document.getElementById('vaPowerEntry').classList.toggle('hidden');
        });

        document.getElementById('vaPhaseStartBtn').addEventListener('click', () => this._vaMarkPhase('phase_start'));
        document.getElementById('vaPhaseEndBtn').addEventListener('click', () => this._vaMarkPhase('phase_end'));
        document.getElementById('vaMarkEventBtn').addEventListener('click', () => this._vaMarkEvent());

        // Submit / Validate / Reset
        document.getElementById('vaSubmitBtn').addEventListener('click', () => this._vaSubmitToSLM());
        document.getElementById('vaValidateBtn').addEventListener('click', () => this._vaValidate());
        document.getElementById('vaResetBtn').addEventListener('click', () => this._vaReset());

        // Wire analyzer events
        this.videoAnalyzer.on('video-loaded', (data) => {
            const player = document.getElementById('vaVideoPlayer');
            player.src = this.videoAnalyzer.videoUrl;
            document.getElementById('vaPlayerSection').classList.remove('hidden');
            document.getElementById('vaAnnotationSection').classList.remove('hidden');
            document.getElementById('vaPlayerStatus').textContent = `${this._vaFmtDuration(data.duration)}`;
            document.getElementById('vaSubmitBtn').disabled = false;
            document.getElementById('vaValidateBtn').disabled = false;
        });

        this.videoAnalyzer.on('analysis-progress', (data) => {
            document.getElementById('vaProgressBar').style.width = `${data.progress}%`;
            document.getElementById('vaProgressText').textContent = `${data.progress}%`;
        });

        this.videoAnalyzer.on('analysis-complete', () => {
            document.getElementById('vaProgressSection').classList.add('hidden');
        });

        this.videoAnalyzer.on('annotation-added', () => this._vaRenderTimeline());
        this.videoAnalyzer.on('annotation-removed', () => this._vaRenderTimeline());
        this.videoAnalyzer.on('phases-updated', () => {
            const count = this.videoAnalyzer.getExtractedPhases().length;
            document.getElementById('vaSubmitBtn').disabled = count === 0;
            document.getElementById('vaValidateBtn').disabled = count === 0;
        });

        this.videoAnalyzer.on('slm-updated', (data) => this._vaUpdateSLMDisplay(data));
        this.videoAnalyzer.on('validation-complete', (data) => this._vaShowFlags(data.flags));

        // Populate reference video dropdown
        const refSelect = document.getElementById('vaRefSelect');
        this.slm.referenceVideos.forEach((url, i) => {
            const opt = document.createElement('option');
            opt.value = url;
            // Extract a readable ID from the URL
            const parts = url.split('/');
            const id = parts[parts.length - 1].replace('.mp4', '').substring(0, 12);
            opt.textContent = `Session ${i + 1} (${id}...)`;
            refSelect.appendChild(opt);
        });
        refSelect.addEventListener('change', () => {
            if (refSelect.value) {
                document.getElementById('vaVideoUrl').value = refSelect.value;
            }
        });

        // Initial SLM display
        this._vaUpdateSLMStats();
    }

    async _vaLoadVideo() {
        const url = document.getElementById('vaVideoUrl').value.trim();
        if (!url) return;
        try {
            await this.videoAnalyzer.loadVideo(url);
        } catch (e) {
            document.getElementById('vaPlayerStatus').textContent = `Error: ${e.message}`;
        }
    }

    async _vaLoadVideoFile(file) {
        try {
            await this.videoAnalyzer.loadVideoFile(file);
        } catch (e) {
            document.getElementById('vaPlayerStatus').textContent = `Error: ${e.message}`;
        }
    }

    async _vaAnalyze() {
        document.getElementById('vaProgressSection').classList.remove('hidden');
        document.getElementById('vaProgressBar').style.width = '0%';
        try {
            await this.videoAnalyzer.analyzeVideo();
        } catch (e) {
            document.getElementById('vaPlayerStatus').textContent = `Error: ${e.message}`;
        }
    }

    _vaMarkPhase(type) {
        const player = document.getElementById('vaVideoPlayer');
        const phase = document.getElementById('vaPhaseSelect').value;
        const sph = parseFloat(document.getElementById('vaPowerSph').value) || 0;
        const cyl = parseFloat(document.getElementById('vaPowerCyl').value) || 0;
        const axis = parseFloat(document.getElementById('vaPowerAxis').value) || 180;

        this.videoAnalyzer.addAnnotation(player.currentTime, type, {
            phase,
            power: { sph, cyl, axis, add: 0 },
        });
    }

    _vaMarkEvent() {
        const player = document.getElementById('vaVideoPlayer');
        const phase = document.getElementById('vaPhaseSelect').value;
        this.videoAnalyzer.addAnnotation(player.currentTime, 'event', {
            phase,
            intent: 'manual_observation',
            note: `Event at ${this._vaFmtDuration(player.currentTime)}`,
        });
    }

    _vaRenderTimeline() {
        const container = document.getElementById('vaTimeline');
        const timeline = this.videoAnalyzer.getTimeline();

        if (timeline.length === 0) {
            container.innerHTML = '<span class="va-timeline-empty">No annotations yet</span>';
            return;
        }

        container.innerHTML = '';
        timeline.forEach((entry, i) => {
            const div = document.createElement('div');
            div.className = 'va-timeline-entry';

            const detail = entry.type === 'phase_start' || entry.type === 'phase_end'
                ? entry.data.phase.replace(/_/g, ' ')
                : entry.data.note || entry.data.intent || '';

            div.innerHTML = `
                <span class="va-tl-time">${this._vaFmtDuration(entry.timestamp)}</span>
                <span class="va-tl-type ${entry.type}">${entry.type.replace('_', ' ')}</span>
                <span class="va-tl-detail">${this._escapeHtml(detail)}</span>
                <button class="va-tl-remove" data-idx="${i}">&times;</button>
            `;

            div.querySelector('.va-tl-remove').addEventListener('click', () => {
                this.videoAnalyzer.removeAnnotation(i);
            });

            // Click to seek video
            div.addEventListener('click', (e) => {
                if (e.target.classList.contains('va-tl-remove')) return;
                const player = document.getElementById('vaVideoPlayer');
                if (player) player.currentTime = entry.timestamp;
            });

            container.appendChild(div);
        });
    }

    _vaSubmitToSLM() {
        try {
            const result = this.videoAnalyzer.submitToSLM({
                source: 'manual_annotation',
            });
            this._vaShowFlags(result.flags);
            this._vaUpdateSLMStats();
        } catch (e) {
            document.getElementById('vaPlayerStatus').textContent = e.message;
        }
    }

    _vaValidate() {
        const flags = this.videoAnalyzer.validateOnly();
        this._vaShowFlags(flags);
    }

    _vaShowFlags(flags) {
        const section = document.getElementById('vaFlagsSection');
        const list = document.getElementById('vaFlagsList');
        const badge = document.getElementById('vaFlagCount');

        if (!flags || flags.length === 0) {
            section.classList.add('hidden');
            return;
        }

        section.classList.remove('hidden');
        badge.textContent = flags.length;
        list.innerHTML = '';

        flags.forEach(flag => {
            const div = document.createElement('div');
            div.className = `va-flag-item ${flag.severity}`;
            div.textContent = flag.description;
            list.appendChild(div);
        });
    }

    _vaUpdateSLMDisplay(data) {
        this._vaUpdateSLMStats();
    }

    _vaUpdateSLMStats() {
        const summary = this.slm.getModelSummary();
        document.getElementById('vaSlmCount').textContent = `${summary.videosAnalyzed} video${summary.videosAnalyzed !== 1 ? 's' : ''}`;

        const statsEl = document.getElementById('vaSlmStats');
        if (summary.videosAnalyzed === 0) {
            statsEl.innerHTML = '<span class="va-stat">No data yet — submit videos to teach</span>';
        } else {
            let html = `<span class="va-stat">Phases learned: <span class="va-stat-value">${summary.phasesLearned}</span></span>`;
            html += `<span class="va-stat">Rules: <span class="va-stat-value">${summary.flagRuleCount}</span></span>`;
            if (summary.lastUpdated) {
                html += `<span class="va-stat">Last: ${new Date(summary.lastUpdated).toLocaleDateString()}</span>`;
            }
            // Timing summary
            const phases = Object.keys(summary.timingSummary);
            if (phases.length > 0) {
                html += '<span class="va-stat" style="margin-top:0.25rem;font-weight:600;color:var(--accent-cyan)">Avg Phase Timing:</span>';
                phases.slice(0, 6).forEach(p => {
                    const t = summary.timingSummary[p];
                    const shortName = p.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                    html += `<span class="va-stat">${shortName}: <span class="va-stat-value">${t.avgSeconds}s</span> <span style="color:var(--text-muted)">(n=${t.samples})</span></span>`;
                });
            }
            statsEl.innerHTML = html;
        }
    }

    _vaReset() {
        this.videoAnalyzer.reset();
        document.getElementById('vaVideoUrl').value = '';
        document.getElementById('vaPlayerSection').classList.add('hidden');
        document.getElementById('vaProgressSection').classList.add('hidden');
        document.getElementById('vaAnnotationSection').classList.add('hidden');
        document.getElementById('vaFlagsSection').classList.add('hidden');
        document.getElementById('vaTimeline').innerHTML = '<span class="va-timeline-empty">No annotations yet</span>';
        document.getElementById('vaSubmitBtn').disabled = true;
        document.getElementById('vaValidateBtn').disabled = true;
        document.getElementById('vaPlayerStatus').textContent = 'Ready';
    }

    _vaFmtDuration(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    // ════════════════════════════════════════════
    // ENGINE RESPONSE HANDLER
    // ════════════════════════════════════════════
    async _handleEngineResponse(response) {
        if (!response) return;

        // Update power display
        if (response.power) this._updatePowerDisplay(response.power);

        // Update CV-5000 panel (occluder, chart preview, eye toggle, etc.)
        this._updateCV5000Panel(response);

        // Update progress
        if (response.progress) this._updateProgress(response.progress);

        // Row counter
        document.getElementById('rowCounter').textContent = `Row: ${this.engine.rowCounter}`;

        // Chart selector
        this._updateChartSelector(response);

        // Flags
        this._updateFlags(response.progress?.flags);

        // Rationale
        this._updateRationale(response.rationale);

        // AR Reference
        this._updateARReference(response.arReference);

        // Handle exam complete
        if (response.phaseId === 'complete' || response.status === 'complete') {
            this._onExamComplete(response.prescription);
            return;
        }

        // Update self-test chart display
        if (this.mode.isMode('selftest') && response.chartIndex !== undefined) {
            const occluder = response.occluder || this.cv5000?.state?.aux_lens || 'BINO';
            this.mode.updateSelfTestChart(response.chartIndex, occluder);
        }
        if (this.mode.isMode('selftest') && response.phaseId) {
            if (response.phaseId.includes('duochrome')) this.mode.showDuochromeChart();
            else if (response.phaseId === 'binocular_balance') this.mode.showBinocularChart();
        }

        // Show question in chat (use friendly version for customer/selftest)
        if (response.question) {
            const displayQuestion = (this.mode.isMode('customer') || this.mode.isMode('selftest'))
                ? (this.mode.friendlyQuestions[response.phaseId] || response.question)
                : response.question;
            this._addChatMessage('system', displayQuestion);
            document.getElementById('currentQuestion').textContent = displayQuestion;
        }

        // Render intent buttons (with friendly labels for customer/selftest)
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
            btn.textContent = this.mode.translateIntentLabel(intent);
            btn.addEventListener('click', () => this._handleIntentClick(intent));
            container.appendChild(btn);
        });
    }

    async _handleIntentClick(intent) {
        this._clearAutoFlip();

        // Add patient response to chat
        const displayLabel = this.mode.translateIntentLabel(intent);
        this._addChatMessage('patient', displayLabel);
        this._log('intent', `Patient: "${intent}"`);

        // Update copilot confidence (button clicks = 100% confidence)
        this.mode.updateConfidence(1.0, intent, null);

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
            this.mode.updateConfidence(result.confidence, result.intent, transcript);

            const response = await this.engine.processResponse(result.intent);
            await this._handleEngineResponse(response);
        } else if (result.action === 'confirm') {
            this._addChatMessage('system', result.message);
            this.mode.updateConfidence(result.confidence, result.intent, transcript);
            // Show confirm/deny buttons
            this._renderIntentButtons([result.intent, 'Repeat question']);
        } else if (result.action === 'clarify') {
            this._addChatMessage('system', result.message);
            this._log('voice', `Low confidence: "${transcript}" (${(result.confidence * 100).toFixed(0)}%)`);
            this.mode.updateConfidence(result.confidence, null, transcript);
            this.mode.recordClarification();
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
        const screenMap = { mode: 'modeScreen', intake: 'intakeScreen', exam: 'examScreen', results: 'resultsScreen' };
        const el = document.getElementById(screenMap[name]);
        if (el) el.classList.add('active');
        this.currentScreen = name;
        if (name === 'intake') {
            const baseUrl = document.getElementById('cv5000Url')?.value?.trim() || '';
            const dash = document.getElementById('dashboardLink');
            if (dash && baseUrl) dash.href = baseUrl.replace(/\/$/, '') + '/dashboard';
            if (!document.getElementById('simulatedMode')?.checked) this._loadDevices();
        }
    }

    _updateConnectionBadge(simulated) {
        const badge = document.getElementById('connectionBadge');
        const cvDot = document.getElementById('cvConnectionDot');
        if (simulated) {
            badge.textContent = 'Simulated';
            badge.className = 'badge badge-warning';
            if (cvDot) cvDot.className = 'cv-connection-dot simulated';
        } else {
            badge.textContent = `Connected: ${this.cv5000.phoroptertId}`;
            badge.className = 'badge badge-success';
            if (cvDot) cvDot.className = 'cv-connection-dot';
        }
    }

    _updatePowerDisplay(power) {
        const fmt = (v) => (v >= 0 ? '+' : '') + v.toFixed(2);

        // Update S/C/A/ADD table values
        const rSph = document.getElementById('rSphDisplay');
        const lSph = document.getElementById('lSphDisplay');
        rSph.textContent = fmt(power.right.sph);
        document.getElementById('rCylDisplay').textContent = fmt(power.right.cyl);
        document.getElementById('rAxisDisplay').textContent = Math.round(power.right.axis);
        document.getElementById('rAddDisplay').textContent = fmt(power.right.add);
        lSph.textContent = fmt(power.left.sph);
        document.getElementById('lCylDisplay').textContent = fmt(power.left.cyl);
        document.getElementById('lAxisDisplay').textContent = Math.round(power.left.axis);
        document.getElementById('lAddDisplay').textContent = fmt(power.left.add);

        // Flash animation on changed values
        document.querySelectorAll('.cv-val').forEach(el => {
            el.classList.remove('highlight');
            void el.offsetWidth; // reflow
            el.classList.add('highlight');
        });
    }

    _updateCV5000Panel(response) {
        // ── Occluder state ──
        const occluder = response.occluder || 'BINO';
        const occR = document.getElementById('cvOccluderR');
        const occL = document.getElementById('cvOccluderL');

        // Reset all
        occR.className = 'cv-occluder-circle';
        occL.className = 'cv-occluder-circle';

        if (occluder === 'Left_Occluded' || occluder === 'LEFT') {
            occR.classList.add('active-eye');
            occR.classList.add('open');
            occL.classList.add('closed');
            // Gray out left column
            document.querySelectorAll('.cv-val-l').forEach(el => el.classList.add('occluded'));
            document.querySelectorAll('.cv-val-r').forEach(el => el.classList.remove('occluded'));
        } else if (occluder === 'Right_Occluded' || occluder === 'RIGHT') {
            occR.classList.add('closed');
            occL.classList.add('active-eye');
            occL.classList.add('open');
            document.querySelectorAll('.cv-val-r').forEach(el => el.classList.add('occluded'));
            document.querySelectorAll('.cv-val-l').forEach(el => el.classList.remove('occluded'));
        } else {
            // BINO
            occR.classList.add('active-eye');
            occR.classList.add('open');
            occL.classList.add('active-eye');
            occL.classList.add('open');
            document.querySelectorAll('.cv-val-r').forEach(el => el.classList.remove('occluded'));
            document.querySelectorAll('.cv-val-l').forEach(el => el.classList.remove('occluded'));
        }

        // Hidden compat fields
        document.getElementById('occluderDisplay').textContent = occluder;

        // ── Eye toggle ──
        document.querySelectorAll('.cv-eye-toggle-btn').forEach(btn => btn.classList.remove('active'));
        if (occluder === 'Left_Occluded' || occluder === 'LEFT') {
            document.getElementById('cvEyeR').classList.add('active');
        } else if (occluder === 'Right_Occluded' || occluder === 'RIGHT') {
            document.getElementById('cvEyeL').classList.add('active');
        } else {
            document.getElementById('cvEyeBino').classList.add('active');
        }

        // ── Header status text ──
        const phase = response.progress?.phaseName || '';
        const cvStatus = document.getElementById('cvHeaderStatus');
        if (phase) cvStatus.textContent = phase;

        // ── Chart preview ──
        if (response.chart || response.chartVA) {
            this._updateCVChartPreview(response.chart, response.chartVA);
        }

        // ── PD ──
        if (this.engine && this.engine.patientData) {
            document.getElementById('cvPdValue').textContent =
                (this.engine.patientData.pd || 63).toFixed(1);
        }

        // Hidden compat fields
        if (response.chart) document.getElementById('chartDisplay').textContent = response.chart;
        if (response.chartVA) document.getElementById('vaDisplay').textContent = response.chartVA;
    }

    _updateCVChartPreview(chartName, va) {
        const optotype = document.getElementById('cvChartDisplay');
        const nameEl = document.getElementById('cvChartName');
        const vaEl = document.getElementById('cvChartVA');

        const name = chartName || '';
        const vaText = va || '';

        nameEl.textContent = name.replace(/_/g, ' ');
        vaEl.textContent = vaText;

        // Reset classes
        optotype.className = 'cv-chart-optotype';

        // Determine optotype display based on chart type
        if (name.includes('duochrome')) {
            optotype.classList.add('duochrome');
            optotype.innerHTML = '<span class="duo-red">5 3 2</span><span class="duo-green">5 4 0</span>';
        } else if (name.includes('jcc') || name.includes('dot')) {
            optotype.classList.add('jcc-dots');
            optotype.textContent = '\u25CF \u25CB \u25CF\n\u25CB \u25CF \u25CB';
        } else if (name.includes('bino') || name.includes('balance')) {
            optotype.textContent = 'T O P\n\u2500\u2500\u2500\nB O T';
        } else if (name.includes('e_chart') || name.includes('echart') || name.includes('E_chart')) {
            // E-chart: show single large E
            const sizeMap = { '400': 3, '200': 2.5, '150': 2.25, '100': 2, '80': 1.75, '70': 1.5, '60': 1.35, '50': 1.2, '40': 1.1, '30': 1, '25': 0.9, '20': 0.8, '15': 0.7 };
            let fontSize = 2;
            for (const [sz, fs] of Object.entries(sizeMap)) {
                if (name.includes(sz) || vaText.includes(sz)) { fontSize = fs; break; }
            }
            optotype.style.fontSize = `${fontSize}rem`;
            optotype.textContent = '\u042E'; // Ш-like E character
        } else if (name.includes('snellen') || name.includes('alphabetic')) {
            // Snellen alphabetic
            const lines = [
                { va: '200', text: 'E' },
                { va: '100', text: 'F P' },
                { va: '70', text: 'T O Z' },
                { va: '50', text: 'L P E D' },
                { va: '40', text: 'P E C F D' },
                { va: '30', text: 'E D F C Z P' },
                { va: '25', text: 'F E L O P Z D' },
                { va: '20', text: 'D E F P O T E C' },
            ];
            // Show lines appropriate to current VA
            let showLines = 3;
            const vaNum = parseInt(vaText.replace(/[^0-9]/g, '')) || 200;
            const startIdx = lines.findIndex(l => parseInt(l.va) <= vaNum);
            const start = Math.max(0, startIdx >= 0 ? startIdx : 0);
            const end = Math.min(lines.length, start + showLines);
            const text = lines.slice(start, end).map(l => l.text).join('\n');
            optotype.textContent = text || 'E';
            optotype.style.fontSize = '';
        } else {
            // Default: show a large letter
            optotype.textContent = 'E';
            optotype.style.fontSize = '';
        }
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

    _updateRationale(rationale) {
        const area = document.getElementById('rationaleArea');
        if (!rationale || (!rationale.why && !rationale.clinical)) {
            area.classList.add('hidden');
            return;
        }

        area.classList.remove('hidden');
        document.getElementById('rationalePhase').textContent = rationale.phase || '';
        document.getElementById('rationaleWhy').textContent = rationale.why || '';
        document.getElementById('rationaleClinical').textContent = rationale.clinical || '';

        // Operator Guide section
        const guideSection = document.getElementById('rationaleGuideSection');
        const guideEl = document.getElementById('rationaleGuide');
        const expectedEl = document.getElementById('rationaleExpected');
        if (rationale.guide) {
            guideSection.classList.remove('hidden');
            guideEl.textContent = rationale.guide;
            expectedEl.textContent = rationale.expected || '';
        } else {
            guideSection.classList.add('hidden');
        }

        // Watch For section
        const watchSection = document.getElementById('rationaleWatchSection');
        const watchEl = document.getElementById('rationaleWatchFor');
        if (rationale.watchFor) {
            watchSection.classList.remove('hidden');
            watchEl.textContent = rationale.watchFor;
        } else {
            watchSection.classList.add('hidden');
        }

        // Decision Logic section (optometrist validation)
        const decisionSection = document.getElementById('rationaleDecisionSection');
        const decisionEl = document.getElementById('rationaleDecisionLogic');
        if (rationale.decisionLogic) {
            decisionSection.classList.remove('hidden');
            decisionEl.textContent = rationale.decisionLogic;
        } else {
            decisionSection.classList.add('hidden');
        }

        // Apply current view mode
        this._applyRationaleMode();
    }

    _initRationalePanel() {
        // Mode toggle: Operator (educational) vs Optometrist (validation)
        this._rationaleMode = 'operator'; // 'operator' or 'optometrist'

        const modeBtn = document.getElementById('rationaleModeBtn');
        if (modeBtn) {
            modeBtn.addEventListener('click', () => {
                this._rationaleMode = this._rationaleMode === 'operator' ? 'optometrist' : 'operator';
                modeBtn.textContent = this._rationaleMode === 'operator' ? 'Operator' : 'Optometrist';
                this._applyRationaleMode();
            });
        }

        // Collapsible section toggle
        document.querySelectorAll('.rationale-section-header').forEach(header => {
            header.addEventListener('click', () => {
                const targetId = header.getAttribute('data-toggle');
                const body = document.getElementById(targetId);
                if (body) {
                    body.classList.toggle('collapsed');
                    header.querySelector('.rationale-chevron').classList.toggle('collapsed');
                }
            });
        });
    }

    _applyRationaleMode() {
        const guideSection = document.getElementById('rationaleGuideSection');
        const watchSection = document.getElementById('rationaleWatchSection');
        const decisionSection = document.getElementById('rationaleDecisionSection');

        if (this._rationaleMode === 'operator') {
            // Operator mode: show guide + expected, show watch for, hide decision logic
            if (guideSection && !guideSection.classList.contains('no-data')) guideSection.classList.remove('hidden');
            if (watchSection && !watchSection.classList.contains('no-data')) watchSection.classList.remove('hidden');
            if (decisionSection) decisionSection.classList.add('hidden');
        } else {
            // Optometrist mode: show all sections including decision logic
            if (guideSection && !guideSection.classList.contains('no-data')) guideSection.classList.remove('hidden');
            if (watchSection && !watchSection.classList.contains('no-data')) watchSection.classList.remove('hidden');
            if (decisionSection && !decisionSection.classList.contains('no-data')) decisionSection.classList.remove('hidden');
        }
    }

    _updateARReference(arRef) {
        const card = document.getElementById('arReferenceCard');
        if (!arRef) return;

        const fmt = (v) => `${v >= 0 ? '+' : ''}${v.toFixed(2)}`;
        const fmtEye = (e) => `${fmt(e.sph)} / ${fmt(e.cyl)} x ${e.axis}\u00B0`;

        const hasData = arRef.OD.sph !== 0 || arRef.OD.cyl !== 0 || arRef.OS.sph !== 0 || arRef.OS.cyl !== 0;
        if (hasData) {
            card.classList.remove('hidden');
            document.getElementById('arRefOD').textContent = fmtEye(arRef.OD);
            document.getElementById('arRefOS').textContent = fmtEye(arRef.OS);
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

        // Update patient-friendly progress
        this.mode.updatePhaseProgress(progress.phaseId || progress.phaseName);

        if (this.voiceEnabled && this.ai) {
            this.ai.announcePhase(progress.phaseName);
        }

        // Update copilot Rx comparison on phase change
        if (this.mode.isMode('copilot') && this.engine && this._patientData) {
            const power = this.engine.getPower();
            if (power) {
                this.mode.updateRxComparison(this._patientData.autorefraction, {
                    OD: { sph: power.r_sph || 0, cyl: power.r_cyl || 0, axis: power.r_axis || 180 },
                    OS: { sph: power.l_sph || 0, cyl: power.l_cyl || 0, axis: power.l_axis || 180 },
                });
            }
        }
    }

    _onExamComplete(rx) {
        this._clearAutoFlip();
        this._log('system', 'Examination complete');
        this.mode.stopExamTimer();
        this.mode.markExamComplete();

        // Release device
        if (this.cv5000 && this.cv5000.connectionStatus === 'acquired') {
            this.cv5000.releaseDevice();
            this._log('system', 'Device released');
        }

        if (rx) {
            this._showResults(rx);

            // Patient-friendly results
            const rxForPatient = {
                OD: rx.right || { sph: 0, cyl: 0, axis: 180 },
                OS: rx.left || { sph: 0, cyl: 0, axis: 180 },
            };
            this.mode.showPatientResults(rxForPatient, rx.flags);

            // Copilot quality report
            if (this.mode.isMode('copilot')) {
                this.mode.showCopilotResults(this.mode.getQualityReport());
            }

            if (this.voiceEnabled && this.ai) {
                if (this.mode.isMode('customer') || this.mode.isMode('selftest')) {
                    this.ai.speak('Your eye test is complete! Your results are now on screen.');
                } else {
                    this.ai.announcePrescription(rx);
                }
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
