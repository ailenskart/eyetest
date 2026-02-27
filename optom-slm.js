/**
 * Optometrist Statistical Learning Model (SLM)
 *
 * Learns patterns from optometrist eye test videos:
 *   - Standard protocol sequence (phase order + timing)
 *   - Power change patterns (SPH/CYL/AXIS/ADD deltas per phase)
 *   - Decision patterns (what action follows what response)
 *   - Timing distributions per phase
 *
 * Flags deviations from learned patterns when validating new sessions.
 *
 * Storage: localStorage for persistence across sessions.
 */

class OptomSLM {
    constructor() {
        this.storageKey = 'optom_slm_model';
        this.model = this._loadModel();

        // Reference video library (known good optometry sessions)
        this.referenceVideos = [
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/ocQ7zmkARmenS-do64ZwrA/EDw3B-XPSLqO9GfIQzQksg.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/8ffQRG3mTI268sHa3N5DVQ/CNNeuSTRQ7Wxp8MBCDWkWw.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/CnoARwgNRYClHTTd-5ccsA/lqjIinaUQKKQQowYC1hqbw.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/o3CPho2gSvKZguWWD5M6sg/Hkdr2hmHSIuR61ybdm-DqA.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/ROp98XdsTzCbPv-fFDfqZw/c74yS0wLSM2xcOEnQAvJnw.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/1dumhM-RRQKEggsHCaJoNw/KJcy7AFITWKNFO8mtJVTAA.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/ojL6XTfRQHm_eVlRF1EYVA/FZO28Wt2TjKrOe-jzN0lLg.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/pKluRUOySNONM2S1BO_cvA/MMDchBMvR5OL2LmXPlecug.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/9T8wsfQxQsuwRnDaSFM6WQ/fDMWmkogTmeoMnuRllhBpA.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/BLdcMf5mSKCo4KMgFljDMA/971yoyY5SriaxIEMA7mnkg.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/o3PSID3OS6uVXtkf54x1uA/m_IXynCZRGGdcKbD7q_i-w.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/VAmqx7uoQ5u0-wZMqY3XBg/QXBM2CbWQxWrsOnvD8lioQ.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/5nO6VcNRTcut8MjN-SsbwQ/WiJ0SOXqT0GdakubIyLbIg.mp4',
            'https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/PJy8TZcrQ7e1ZbqeEcUV3g/IA1eP7C1RLqvK6HrZP7GBw.mp4',
        ];
    }

    // ═══════════════════════════════════════════
    // MODEL STRUCTURE
    // ═══════════════════════════════════════════

    _createEmptyModel() {
        return {
            version: 1,
            videosAnalyzed: 0,
            lastUpdated: null,

            // ── Protocol sequence (ordered phases observed) ──
            phaseSequences: [],        // Array of observed phase-order arrays
            canonicalSequence: [        // The "golden path" (expected protocol)
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
            ],

            // ── Timing distribution per phase (seconds) ──
            phaseTiming: {},           // { phaseName: { samples: [], mean: 0, stddev: 0, min: 0, max: 0 } }

            // ── Power change patterns ──
            powerPatterns: {},         // { phaseName: { sph_deltas: [], cyl_deltas: [], axis_deltas: [] } }

            // ── Step counts per phase ──
            stepCounts: {},            // { phaseName: { samples: [], mean: 0, min: 0, max: 0 } }

            // ── Decision patterns (intent → action transitions) ──
            decisionPatterns: {},      // { phaseName: { intent: { nextAction: count, ... } } }

            // ── Flag rules (learned from correct sessions) ──
            flagRules: this._getDefaultFlagRules(),

            // ── Session archive (summary of all analyzed sessions) ──
            sessions: [],
        };
    }

    _getDefaultFlagRules() {
        return [
            {
                id: 'missing_fogging',
                severity: 'critical',
                description: 'Fogging phase was skipped — risk of over-minusing due to uncontrolled accommodation',
                check: 'sequence',
                condition: 'phase_missing',
                phases: ['fogging_right', 'fogging_left'],
            },
            {
                id: 'wrong_eye_order',
                severity: 'warning',
                description: 'Left eye was tested before right eye — non-standard order',
                check: 'sequence',
                condition: 'order_violation',
                before: 'right_eye_refraction',
                after: 'left_eye_refraction',
            },
            {
                id: 'no_jcc',
                severity: 'warning',
                description: 'JCC astigmatism refinement was skipped',
                check: 'sequence',
                condition: 'phase_missing',
                phases: ['jcc_axis_right', 'jcc_power_right', 'jcc_axis_left', 'jcc_power_left'],
            },
            {
                id: 'no_duochrome',
                severity: 'warning',
                description: 'Duochrome endpoint verification was skipped',
                check: 'sequence',
                condition: 'phase_missing',
                phases: ['duochrome_right', 'duochrome_left'],
            },
            {
                id: 'no_binocular_balance',
                severity: 'warning',
                description: 'Binocular balance was not performed — eyes may not be equalized',
                check: 'sequence',
                condition: 'phase_missing',
                phases: ['binocular_balance'],
            },
            {
                id: 'excessive_sph_change',
                severity: 'warning',
                description: 'SPH changed by more than 2.00D from AR in a single phase — verify accuracy',
                check: 'power',
                condition: 'delta_exceeds',
                param: 'sph',
                threshold: 2.0,
            },
            {
                id: 'phase_too_fast',
                severity: 'info',
                description: 'Phase completed unusually fast — may indicate rushed examination',
                check: 'timing',
                condition: 'below_threshold',
                thresholdSeconds: 5,
            },
            {
                id: 'phase_too_slow',
                severity: 'info',
                description: 'Phase took unusually long — patient may need additional assistance',
                check: 'timing',
                condition: 'above_threshold',
                thresholdSeconds: 300,
            },
        ];
    }

    // ═══════════════════════════════════════════
    // LEARNING (ingest session data)
    // ═══════════════════════════════════════════

    /**
     * Learn from a completed session's data.
     * @param {Object} sessionData - { phases: [{name, startTime, endTime, steps, powerStart, powerEnd}], metadata }
     */
    learnFromSession(sessionData) {
        const { phases, metadata } = sessionData;

        // Record sequence
        const sequence = phases.map(p => p.name);
        this.model.phaseSequences.push(sequence);

        // Record timing per phase
        phases.forEach(phase => {
            if (!this.model.phaseTiming[phase.name]) {
                this.model.phaseTiming[phase.name] = { samples: [], mean: 0, stddev: 0, min: Infinity, max: 0 };
            }
            const timing = this.model.phaseTiming[phase.name];
            const duration = (phase.endTime - phase.startTime) / 1000; // seconds
            if (duration > 0 && duration < 600) { // sanity check
                timing.samples.push(duration);
                this._recalcStats(timing);
            }
        });

        // Record step counts
        phases.forEach(phase => {
            if (!this.model.stepCounts[phase.name]) {
                this.model.stepCounts[phase.name] = { samples: [], mean: 0, min: Infinity, max: 0 };
            }
            const sc = this.model.stepCounts[phase.name];
            sc.samples.push(phase.steps || 0);
            this._recalcStats(sc);
        });

        // Record power patterns
        phases.forEach(phase => {
            if (!this.model.powerPatterns[phase.name]) {
                this.model.powerPatterns[phase.name] = { sph_deltas: [], cyl_deltas: [], axis_deltas: [] };
            }
            const pp = this.model.powerPatterns[phase.name];
            if (phase.powerStart && phase.powerEnd) {
                pp.sph_deltas.push(phase.powerEnd.sph - phase.powerStart.sph);
                pp.cyl_deltas.push(phase.powerEnd.cyl - phase.powerStart.cyl);
                pp.axis_deltas.push(phase.powerEnd.axis - phase.powerStart.axis);
            }
        });

        // Record decision patterns
        phases.forEach(phase => {
            if (phase.decisions) {
                if (!this.model.decisionPatterns[phase.name]) {
                    this.model.decisionPatterns[phase.name] = {};
                }
                const dp = this.model.decisionPatterns[phase.name];
                phase.decisions.forEach(d => {
                    if (!dp[d.intent]) dp[d.intent] = {};
                    dp[d.intent][d.action] = (dp[d.intent][d.action] || 0) + 1;
                });
            }
        });

        // Archive session summary
        this.model.sessions.push({
            id: `session_${Date.now()}`,
            timestamp: new Date().toISOString(),
            phaseCount: phases.length,
            sequence,
            metadata: metadata || {},
            flags: this.validateSession(sessionData),
        });

        this.model.videosAnalyzed++;
        this.model.lastUpdated = new Date().toISOString();
        this._saveModel();

        return this.model.sessions[this.model.sessions.length - 1];
    }

    _recalcStats(obj) {
        const s = obj.samples;
        if (s.length === 0) return;
        obj.mean = s.reduce((a, b) => a + b, 0) / s.length;
        obj.min = Math.min(...s);
        obj.max = Math.max(...s);
        if (s.length > 1) {
            const variance = s.reduce((sum, v) => sum + Math.pow(v - obj.mean, 2), 0) / (s.length - 1);
            obj.stddev = Math.sqrt(variance);
        } else {
            obj.stddev = 0;
        }
    }

    // ═══════════════════════════════════════════
    // VALIDATION (flag deviations)
    // ═══════════════════════════════════════════

    /**
     * Validate a session against learned patterns and flag deviations.
     * @param {Object} sessionData
     * @returns {Array} flags - [{ ruleId, severity, description, detail }]
     */
    validateSession(sessionData) {
        const flags = [];
        const { phases } = sessionData;
        const sequence = phases.map(p => p.name);

        this.model.flagRules.forEach(rule => {
            switch (rule.check) {
                case 'sequence':
                    this._checkSequenceRule(rule, sequence, flags);
                    break;
                case 'power':
                    this._checkPowerRule(rule, phases, flags);
                    break;
                case 'timing':
                    this._checkTimingRule(rule, phases, flags);
                    break;
            }
        });

        // ── Statistical anomaly detection (learned patterns) ──
        // If we have enough data, flag phases that deviate >2 stddev from learned timing
        phases.forEach(phase => {
            const learned = this.model.phaseTiming[phase.name];
            if (learned && learned.samples.length >= 3 && learned.stddev > 0) {
                const duration = (phase.endTime - phase.startTime) / 1000;
                const zScore = Math.abs(duration - learned.mean) / learned.stddev;
                if (zScore > 2.5) {
                    flags.push({
                        ruleId: 'statistical_timing_anomaly',
                        severity: 'info',
                        description: `${phase.name}: duration ${duration.toFixed(0)}s is ${zScore.toFixed(1)} stddev from mean ${learned.mean.toFixed(0)}s`,
                        detail: { phase: phase.name, duration, mean: learned.mean, stddev: learned.stddev },
                    });
                }
            }
        });

        // ── Sequence deviation from canonical ──
        const canonical = this.model.canonicalSequence;
        let lastCanonicalIdx = -1;
        sequence.forEach((phaseName, i) => {
            const canonIdx = canonical.indexOf(phaseName);
            if (canonIdx === -1) {
                flags.push({
                    ruleId: 'unknown_phase',
                    severity: 'info',
                    description: `Unknown phase "${phaseName}" not in standard protocol`,
                    detail: { phase: phaseName, position: i },
                });
            } else if (canonIdx < lastCanonicalIdx) {
                flags.push({
                    ruleId: 'out_of_order',
                    severity: 'warning',
                    description: `Phase "${phaseName}" appears out of standard order (expected after index ${lastCanonicalIdx})`,
                    detail: { phase: phaseName, position: i, expectedAfter: canonical[lastCanonicalIdx] },
                });
            } else {
                lastCanonicalIdx = canonIdx;
            }
        });

        return flags;
    }

    _checkSequenceRule(rule, sequence, flags) {
        if (rule.condition === 'phase_missing') {
            rule.phases.forEach(phase => {
                if (!sequence.includes(phase)) {
                    flags.push({
                        ruleId: rule.id,
                        severity: rule.severity,
                        description: rule.description,
                        detail: { missingPhase: phase },
                    });
                }
            });
        } else if (rule.condition === 'order_violation') {
            const beforeIdx = sequence.indexOf(rule.before);
            const afterIdx = sequence.indexOf(rule.after);
            if (beforeIdx >= 0 && afterIdx >= 0 && afterIdx < beforeIdx) {
                flags.push({
                    ruleId: rule.id,
                    severity: rule.severity,
                    description: rule.description,
                    detail: { before: rule.before, after: rule.after },
                });
            }
        }
    }

    _checkPowerRule(rule, phases, flags) {
        if (rule.condition === 'delta_exceeds') {
            phases.forEach(phase => {
                if (phase.powerStart && phase.powerEnd) {
                    const delta = Math.abs(phase.powerEnd[rule.param] - phase.powerStart[rule.param]);
                    if (delta > rule.threshold) {
                        flags.push({
                            ruleId: rule.id,
                            severity: rule.severity,
                            description: `${phase.name}: ${rule.param.toUpperCase()} changed by ${delta.toFixed(2)}D (threshold: ${rule.threshold}D)`,
                            detail: { phase: phase.name, param: rule.param, delta, threshold: rule.threshold },
                        });
                    }
                }
            });
        }
    }

    _checkTimingRule(rule, phases, flags) {
        phases.forEach(phase => {
            const duration = (phase.endTime - phase.startTime) / 1000;
            if (rule.condition === 'below_threshold' && duration < rule.thresholdSeconds && duration > 0) {
                flags.push({
                    ruleId: rule.id,
                    severity: rule.severity,
                    description: `${phase.name}: ${rule.description} (${duration.toFixed(0)}s < ${rule.thresholdSeconds}s)`,
                    detail: { phase: phase.name, duration, threshold: rule.thresholdSeconds },
                });
            } else if (rule.condition === 'above_threshold' && duration > rule.thresholdSeconds) {
                flags.push({
                    ruleId: rule.id,
                    severity: rule.severity,
                    description: `${phase.name}: ${rule.description} (${duration.toFixed(0)}s > ${rule.thresholdSeconds}s)`,
                    detail: { phase: phase.name, duration, threshold: rule.thresholdSeconds },
                });
            }
        });
    }

    // ═══════════════════════════════════════════
    // MODEL STATS / QUERIES
    // ═══════════════════════════════════════════

    getModelSummary() {
        const m = this.model;
        const phaseNames = Object.keys(m.phaseTiming);
        const timingSummary = {};
        phaseNames.forEach(name => {
            const t = m.phaseTiming[name];
            timingSummary[name] = {
                avgSeconds: t.mean.toFixed(1),
                samples: t.samples.length,
                range: `${t.min.toFixed(0)}–${t.max.toFixed(0)}s`,
            };
        });

        return {
            videosAnalyzed: m.videosAnalyzed,
            lastUpdated: m.lastUpdated,
            phasesLearned: phaseNames.length,
            timingSummary,
            totalSessions: m.sessions.length,
            flagRuleCount: m.flagRules.length,
        };
    }

    getPhaseExpectations(phaseName) {
        const timing = this.model.phaseTiming[phaseName];
        const steps = this.model.stepCounts[phaseName];
        const power = this.model.powerPatterns[phaseName];
        const decisions = this.model.decisionPatterns[phaseName];

        return {
            timing: timing ? { mean: timing.mean, stddev: timing.stddev, samples: timing.samples.length } : null,
            steps: steps ? { mean: steps.mean, min: steps.min, max: steps.max } : null,
            power: power ? {
                avgSphDelta: power.sph_deltas.length ? (power.sph_deltas.reduce((a, b) => a + b, 0) / power.sph_deltas.length).toFixed(2) : null,
                avgCylDelta: power.cyl_deltas.length ? (power.cyl_deltas.reduce((a, b) => a + b, 0) / power.cyl_deltas.length).toFixed(2) : null,
            } : null,
            decisions: decisions || null,
        };
    }

    getAllSessions() {
        return this.model.sessions;
    }

    // ═══════════════════════════════════════════
    // PERSISTENCE
    // ═══════════════════════════════════════════

    _loadModel() {
        try {
            const saved = localStorage.getItem(this.storageKey);
            if (saved) {
                const parsed = JSON.parse(saved);
                if (parsed.version === 1) return parsed;
            }
        } catch (e) {
            console.warn('SLM: failed to load model from localStorage', e);
        }
        return this._createEmptyModel();
    }

    _saveModel() {
        try {
            localStorage.setItem(this.storageKey, JSON.stringify(this.model));
        } catch (e) {
            console.warn('SLM: failed to save model to localStorage', e);
        }
    }

    resetModel() {
        this.model = this._createEmptyModel();
        this._saveModel();
    }

    exportModel() {
        return JSON.parse(JSON.stringify(this.model));
    }

    importModel(modelData) {
        if (modelData && modelData.version === 1) {
            this.model = modelData;
            this._saveModel();
        }
    }
}
