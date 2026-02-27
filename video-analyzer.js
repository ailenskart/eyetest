/**
 * Video Analyzer — Optometry Session Video Analysis
 *
 * Accepts video URLs or file uploads of eye test sessions.
 * Extracts structured session data by analyzing the CV-5000 UI
 * shown in the video (phase transitions, power changes, timing).
 *
 * Feeds extracted data into the OptomSLM for learning and validation.
 *
 * Architecture:
 *   Video URL → <video> element → frame sampling → ROI analysis →
 *   structured timeline → SLM.learnFromSession()
 *
 * For real deployment, frame analysis would use server-side OCR
 * (Tesseract/EasyOCR) on the CV-5000 ROIs. This client-side
 * implementation provides the UI framework and simulated analysis
 * for demonstration, with manual annotation support.
 */

class VideoAnalyzer {
    constructor(slm) {
        this.slm = slm;
        this.listeners = new Map();

        // Current analysis state
        this.videoUrl = null;
        this.videoElement = null;
        this.isAnalyzing = false;
        this.timeline = [];          // [{timestamp, phase, power, event, flags}]
        this.extractedPhases = [];   // [{name, startTime, endTime, steps, powerStart, powerEnd, decisions}]
        this.analysisFlags = [];
    }

    // ═══════════════════════════════════════════
    // EVENT SYSTEM
    // ═══════════════════════════════════════════

    on(event, callback) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(callback);
    }

    _emit(event, data) {
        (this.listeners.get(event) || []).forEach(cb => cb(data));
    }

    // ═══════════════════════════════════════════
    // VIDEO LOADING
    // ═══════════════════════════════════════════

    /**
     * Load a video from URL for analysis.
     */
    async loadVideo(url) {
        this.videoUrl = url;
        this.timeline = [];
        this.extractedPhases = [];
        this.analysisFlags = [];

        this._emit('status', { message: 'Loading video...', state: 'loading' });

        return new Promise((resolve, reject) => {
            const video = document.createElement('video');
            video.crossOrigin = 'anonymous';
            video.preload = 'metadata';
            video.src = url;

            video.addEventListener('loadedmetadata', () => {
                this.videoElement = video;
                this._emit('video-loaded', {
                    duration: video.duration,
                    width: video.videoWidth,
                    height: video.videoHeight,
                    url,
                });
                this._emit('status', { message: `Video loaded (${this._formatDuration(video.duration)})`, state: 'ready' });
                resolve({
                    duration: video.duration,
                    width: video.videoWidth,
                    height: video.videoHeight,
                });
            });

            video.addEventListener('error', () => {
                this._emit('status', { message: 'Failed to load video', state: 'error' });
                reject(new Error('Failed to load video'));
            });
        });
    }

    /**
     * Load video from file input.
     */
    loadVideoFile(file) {
        const url = URL.createObjectURL(file);
        return this.loadVideo(url);
    }

    // ═══════════════════════════════════════════
    // ANALYSIS
    // ═══════════════════════════════════════════

    /**
     * Run analysis on the loaded video.
     * In production, this would sample frames and run OCR on CV-5000 ROIs.
     * Here we provide the framework and support manual annotation.
     */
    async analyzeVideo() {
        if (!this.videoElement) throw new Error('No video loaded');
        if (this.isAnalyzing) return;

        this.isAnalyzing = true;
        this._emit('status', { message: 'Analyzing video...', state: 'analyzing' });
        this._emit('analysis-start', {});

        const duration = this.videoElement.duration;
        const sampleInterval = 2; // seconds between frame samples
        const totalSamples = Math.floor(duration / sampleInterval);

        // Sample frames at regular intervals
        for (let i = 0; i <= totalSamples; i++) {
            const timestamp = i * sampleInterval;
            this.videoElement.currentTime = timestamp;

            await new Promise(resolve => {
                this.videoElement.addEventListener('seeked', resolve, { once: true });
            });

            // In production: capture frame → send to ROI extraction → OCR
            // Here: emit progress for UI update
            const progress = Math.round((i / totalSamples) * 100);
            this._emit('analysis-progress', {
                progress,
                timestamp,
                frame: i,
                totalFrames: totalSamples,
            });
        }

        this.isAnalyzing = false;
        this._emit('status', { message: 'Analysis complete — annotate timeline to teach the SLM', state: 'complete' });
        this._emit('analysis-complete', { timeline: this.timeline, phases: this.extractedPhases });
    }

    // ═══════════════════════════════════════════
    // MANUAL ANNOTATION
    // ═══════════════════════════════════════════

    /**
     * Add a manual annotation to the timeline.
     * Used when automatic OCR is not available — the operator marks
     * phase transitions and key events while watching the video.
     */
    addAnnotation(timestamp, type, data) {
        const entry = {
            timestamp,
            type,         // 'phase_start', 'phase_end', 'power_change', 'event', 'flag'
            data,         // { phase, power: {sph,cyl,axis,add}, eye, intent, note }
            addedAt: Date.now(),
        };

        this.timeline.push(entry);
        this.timeline.sort((a, b) => a.timestamp - b.timestamp);

        this._emit('annotation-added', entry);
        this._rebuildPhasesFromTimeline();

        return entry;
    }

    /**
     * Remove an annotation by index.
     */
    removeAnnotation(index) {
        if (index >= 0 && index < this.timeline.length) {
            const removed = this.timeline.splice(index, 1)[0];
            this._emit('annotation-removed', removed);
            this._rebuildPhasesFromTimeline();
        }
    }

    /**
     * Rebuild extractedPhases from timeline annotations.
     */
    _rebuildPhasesFromTimeline() {
        const phases = [];
        let currentPhase = null;

        this.timeline.forEach(entry => {
            if (entry.type === 'phase_start') {
                if (currentPhase) {
                    currentPhase.endTime = entry.timestamp * 1000;
                    phases.push(currentPhase);
                }
                currentPhase = {
                    name: entry.data.phase,
                    startTime: entry.timestamp * 1000,
                    endTime: null,
                    steps: 0,
                    powerStart: entry.data.power ? { ...entry.data.power } : null,
                    powerEnd: null,
                    decisions: [],
                };
            } else if (entry.type === 'phase_end' && currentPhase) {
                currentPhase.endTime = entry.timestamp * 1000;
                currentPhase.powerEnd = entry.data.power ? { ...entry.data.power } : currentPhase.powerStart;
                phases.push(currentPhase);
                currentPhase = null;
            } else if (entry.type === 'power_change' && currentPhase) {
                currentPhase.steps++;
                currentPhase.powerEnd = entry.data.power ? { ...entry.data.power } : null;
            } else if (entry.type === 'event' && currentPhase && entry.data.intent) {
                currentPhase.decisions.push({
                    intent: entry.data.intent,
                    action: entry.data.action || 'unknown',
                });
                currentPhase.steps++;
            }
        });

        // Close last phase if still open
        if (currentPhase) {
            currentPhase.endTime = (this.videoElement ? this.videoElement.duration : 0) * 1000;
            phases.push(currentPhase);
        }

        this.extractedPhases = phases;
        this._emit('phases-updated', phases);
    }

    // ═══════════════════════════════════════════
    // SLM INTEGRATION
    // ═══════════════════════════════════════════

    /**
     * Submit the analyzed/annotated session to the SLM for learning.
     */
    submitToSLM(metadata = {}) {
        if (this.extractedPhases.length === 0) {
            throw new Error('No phases extracted — annotate the timeline first');
        }

        const sessionData = {
            phases: this.extractedPhases,
            metadata: {
                ...metadata,
                videoUrl: this.videoUrl,
                duration: this.videoElement ? this.videoElement.duration : 0,
                analyzedAt: new Date().toISOString(),
                annotationCount: this.timeline.length,
            },
        };

        // Validate
        this.analysisFlags = this.slm.validateSession(sessionData);

        // Learn
        const sessionRecord = this.slm.learnFromSession(sessionData);

        this._emit('slm-updated', {
            session: sessionRecord,
            flags: this.analysisFlags,
            modelSummary: this.slm.getModelSummary(),
        });

        return { session: sessionRecord, flags: this.analysisFlags };
    }

    /**
     * Validate current annotations against SLM without learning.
     */
    validateOnly() {
        if (this.extractedPhases.length === 0) return [];

        this.analysisFlags = this.slm.validateSession({
            phases: this.extractedPhases,
            metadata: {},
        });

        this._emit('validation-complete', { flags: this.analysisFlags });
        return this.analysisFlags;
    }

    // ═══════════════════════════════════════════
    // HELPERS
    // ═══════════════════════════════════════════

    _formatDuration(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${m}:${s.toString().padStart(2, '0')}`;
    }

    getTimeline() {
        return [...this.timeline];
    }

    getExtractedPhases() {
        return [...this.extractedPhases];
    }

    reset() {
        this.videoUrl = null;
        this.videoElement = null;
        this.isAnalyzing = false;
        this.timeline = [];
        this.extractedPhases = [];
        this.analysisFlags = [];
        this._emit('reset', {});
    }
}
