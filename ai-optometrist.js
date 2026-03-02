/**
 * AI Optometrist — Conversation Controller with Voice I/O
 *
 * Handles:
 *   Output 1: System Response → Voice (TTS to patient)
 *   Input  2: Patient Response → Voice (ASR from patient)
 *   Intent classification from free-form speech to constrained intent sets
 *   Clarification questions for low-confidence responses
 *   Session logging of every question, raw transcript, intent, and action
 *
 * Uses Web Speech API (SpeechSynthesis + SpeechRecognition)
 */

class AIOptometrist {
    constructor(config = {}) {
        this.listeners = new Map();

        // ── Voice config ──
        this.voiceEnabled = config.voiceEnabled !== false;
        this.ttsRate = config.ttsRate || 0.9;
        this.ttsPitch = config.ttsPitch || 1.0;
        this.ttsVoice = config.ttsVoice || null;
        this.language = config.language || 'en-US';
        this.autoListen = config.autoListen !== false;

        // ── ASR state ──
        this.recognition = null;
        this.isListening = false;
        this.lastTranscript = '';

        // ── Conversation state ──
        this.currentIntents = [];
        this.currentQuestion = '';
        this.currentPhaseId = '';
        this.clarificationMode = false;
        this.clarificationCount = 0;
        this.maxClarifications = 2;

        // ── Session log ──
        this.conversationLog = [];
        this.logCounter = 0;

        // ── Confidence thresholds ──
        this.highConfidence = config.highConfidence || 0.75;
        this.lowConfidence = config.lowConfidence || 0.40;

        // ── Init speech engines ──
        this._initTTS();
        this._initASR();
    }

    // ─── Event System ──────────────────────────────
    on(event, cb) {
        if (!this.listeners.has(event)) this.listeners.set(event, []);
        this.listeners.get(event).push(cb);
    }
    emit(event, data) {
        (this.listeners.get(event) || []).forEach(cb => cb(data));
    }

    // ─── TTS (Output 1) ───────────────────────────
    _initTTS() {
        this.synth = window.speechSynthesis || null;
        this.voices = [];
        if (this.synth) {
            this.voices = this.synth.getVoices();
            this.synth.onvoiceschanged = () => {
                this.voices = this.synth.getVoices();
            };
        }
    }

    getAvailableVoices() {
        return this.voices.map((v, i) => ({
            index: i,
            name: v.name,
            lang: v.lang,
            default: v.default,
        }));
    }

    setVoice(voiceIndex) {
        if (voiceIndex >= 0 && voiceIndex < this.voices.length) {
            this.ttsVoice = this.voices[voiceIndex];
        }
    }

    speak(text) {
        return new Promise((resolve, reject) => {
            if (!this.synth || !this.voiceEnabled) {
                this.emit('tts-text', { text });
                resolve();
                return;
            }

            // Cancel any ongoing speech
            this.synth.cancel();

            const utterance = new SpeechSynthesisUtterance(text);
            utterance.rate = this.ttsRate;
            utterance.pitch = this.ttsPitch;
            utterance.lang = this.language;

            if (this.ttsVoice) {
                utterance.voice = this.ttsVoice;
            } else {
                // Pick a good English voice
                const preferred = this.voices.find(v =>
                    v.lang.startsWith('en') && v.name.includes('Google')
                ) || this.voices.find(v => v.lang.startsWith('en'));
                if (preferred) utterance.voice = preferred;
            }

            utterance.onend = () => {
                this.emit('tts-end', { text });
                resolve();
            };
            utterance.onerror = (e) => {
                this.emit('tts-error', { error: e.error, text });
                reject(e);
            };

            this.emit('tts-start', { text });
            this.synth.speak(utterance);
        });
    }

    stopSpeaking() {
        if (this.synth) this.synth.cancel();
    }

    // ─── ASR (Input 2) ────────────────────────────
    _initASR() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            this.recognition = null;
            return;
        }

        this.recognition = new SpeechRecognition();
        this.recognition.continuous = false;
        this.recognition.interimResults = true;
        this.recognition.lang = this.language;
        this.recognition.maxAlternatives = 3;

        this.recognition.onresult = (event) => {
            let finalTranscript = '';
            let interimTranscript = '';

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const result = event.results[i];
                if (result.isFinal) {
                    finalTranscript += result[0].transcript;
                } else {
                    interimTranscript += result[0].transcript;
                }
            }

            if (interimTranscript) {
                this.emit('asr-interim', { transcript: interimTranscript });
            }

            if (finalTranscript) {
                this.lastTranscript = finalTranscript.trim();
                this.isListening = false;
                this.emit('asr-result', {
                    transcript: this.lastTranscript,
                    alternatives: Array.from(event.results)
                        .filter(r => r.isFinal)
                        .flatMap(r => Array.from(r).map(a => ({
                            transcript: a.transcript,
                            confidence: a.confidence,
                        }))),
                });
            }
        };

        this.recognition.onerror = (event) => {
            this.isListening = false;
            this.emit('asr-error', { error: event.error });
        };

        this.recognition.onend = () => {
            this.isListening = false;
            this.emit('asr-end', {});
        };
    }

    startListening() {
        if (!this.recognition) {
            this.emit('asr-error', { error: 'Speech recognition not supported' });
            return;
        }
        if (this.isListening) return;

        this.isListening = true;
        this.lastTranscript = '';
        this.emit('asr-start', {});

        try {
            this.recognition.start();
        } catch (e) {
            this.isListening = false;
            this.emit('asr-error', { error: e.message });
        }
    }

    stopListening() {
        if (this.recognition && this.isListening) {
            this.recognition.stop();
            this.isListening = false;
        }
    }

    // ─── Intent Classification ─────────────────────
    classifyIntent(transcript, availableIntents, phaseId) {
        if (!transcript || !availableIntents.length) {
            return { intent: null, confidence: 0, rawTranscript: transcript };
        }

        const text = transcript.toLowerCase().trim();
        const scores = [];

        for (const intent of availableIntents) {
            const score = this._scoreIntent(text, intent, phaseId);
            scores.push({ intent, score });
        }

        scores.sort((a, b) => b.score - a.score);
        const best = scores[0];
        const secondBest = scores[1] || { score: 0 };

        // Confidence = best score, reduced if close to second best
        let confidence = best.score;
        if (secondBest.score > 0 && best.score - secondBest.score < 0.15) {
            confidence *= 0.7; // Reduce confidence if ambiguous
        }

        return {
            intent: best.score > 0.1 ? best.intent : null,
            confidence: Math.min(1.0, confidence),
            rawTranscript: transcript,
            scores: scores.slice(0, 3),
        };
    }

    _scoreIntent(text, intent, phaseId) {
        const intentLower = intent.toLowerCase();

        // ── Exact match ──
        if (text === intentLower) return 1.0;

        // ── Phase-specific keyword matching ──

        // Fogging phases
        if (intentLower.includes("it's blurry")) {
            if (this._matchesAny(text, ['blurry', 'blur', 'yes', 'blurred', 'can\'t see', 'foggy', 'everything blurry', 'yes blurry', 'it is blurry'])) return 0.9;
        }
        if (intentLower.includes('can still see clearly')) {
            if (this._matchesAny(text, ['clear', 'can see', 'still see', 'not blurry', 'i can read', 'sharp', 'can still see', 'no it\'s clear'])) return 0.9;
        }

        // Refraction phases
        if (intentLower.includes('able to read')) {
            if (this._matchesAny(text, ['able to read', 'can read', 'i can see', 'yes', 'clear', 'readable', 'can see it', 'yes i can'])) return 0.9;
        }
        if (intentLower.includes('blurry')) {
            if (this._matchesAny(text, ['blurry', 'blur', 'blurred', 'fuzzy', 'hazy', 'not clear', 'little blurry', 'a bit blurry'])) return 0.9;
        }
        if (intentLower.includes('unable to read')) {
            if (this._matchesAny(text, ['unable', 'can\'t read', 'cannot read', 'can\'t see', 'cannot see', 'no', 'nothing', 'i can\'t', 'too blurry'])) return 0.9;
        }

        // JCC phases
        if (intentLower.includes('flip 1') && intentLower.includes('much better')) {
            if (this._matchesAny(text, ['first much better', 'one much better', 'first way better', 'first is way better', 'definitely first', 'one was much'])) return 0.9;
        }
        if (intentLower.includes('flip 1') && intentLower.includes('better') && !intentLower.includes('much')) {
            if (this._matchesAny(text, ['first better', 'first one', 'one better', 'first was better', 'number one', 'the first', 'one is better', 'prefer first'])) return 0.85;
        }
        if (intentLower.includes('flip 2') && intentLower.includes('much better')) {
            if (this._matchesAny(text, ['second much better', 'two much better', 'second way better', 'second is way better', 'definitely second', 'two was much'])) return 0.9;
        }
        if (intentLower.includes('flip 2') && intentLower.includes('better') && !intentLower.includes('much')) {
            if (this._matchesAny(text, ['second better', 'second one', 'two better', 'second was better', 'number two', 'the second', 'two is better', 'prefer second'])) return 0.85;
        }
        if (intentLower.includes('both same')) {
            if (this._matchesAny(text, ['same', 'both same', 'no difference', 'equal', 'both are same', 'they\'re the same', 'identical', 'about the same', 'similar'])) return 0.9;
        }
        if (intentLower.includes('repeat')) {
            if (this._matchesAny(text, ['repeat', 'again', 'show again', 'one more time', 'not sure', 'show me again'])) return 0.85;
        }

        // Duochrome
        if (intentLower === 'red') {
            if (this._matchesAny(text, ['red', 'red side', 'red is clearer', 'the red', 'red one'])) return 0.9;
        }
        if (intentLower === 'green') {
            if (this._matchesAny(text, ['green', 'green side', 'green is clearer', 'the green', 'green one'])) return 0.9;
        }

        // Binocular balance
        if (intentLower.includes('top is blurry') || intentLower.includes('right eye')) {
            if (this._matchesAny(text, ['top', 'top blurry', 'top is blurry', 'upper', 'top one', 'the top'])) return 0.9;
        }
        if (intentLower.includes('bottom is blurry') || intentLower.includes('left eye')) {
            if (this._matchesAny(text, ['bottom', 'bottom blurry', 'bottom is blurry', 'lower', 'bottom one', 'the bottom'])) return 0.9;
        }
        if (intentLower.includes('both are same')) {
            if (this._matchesAny(text, ['same', 'both same', 'both are same', 'equal', 'no difference'])) return 0.9;
        }

        // Prev State
        if (intentLower.includes('prev state')) {
            if (this._matchesAny(text, ['undo', 'go back', 'previous', 'prev', 'revert', 'the previous one', 'before'])) return 0.85;
        }

        // ── Generic fuzzy match ──
        const intentWords = intentLower.split(/\s+/).filter(w => w.length > 2);
        const textWords = text.split(/\s+/);
        let matchCount = 0;
        for (const iw of intentWords) {
            if (textWords.some(tw => tw.includes(iw) || iw.includes(tw))) {
                matchCount++;
            }
        }
        if (intentWords.length > 0) {
            return (matchCount / intentWords.length) * 0.6;
        }

        return 0;
    }

    _matchesAny(text, keywords) {
        return keywords.some(kw => text.includes(kw));
    }

    // ─── Conversation Flow ─────────────────────────

    /**
     * Ask a question: speak it, show it, prepare for response.
     * @param {string} question - The question text
     * @param {string[]} intents - Available intents
     * @param {string} phaseId - Current phase ID
     */
    async askQuestion(question, intents, phaseId) {
        this.currentQuestion = question;
        this.currentIntents = intents;
        this.currentPhaseId = phaseId;
        this.clarificationMode = false;
        this.clarificationCount = 0;

        this.emit('question', { question, intents, phaseId });

        // Speak the question (Output 1)
        if (this.voiceEnabled) {
            try {
                await this.speak(question);
            } catch (e) {
                // TTS failed, continue silently
            }
        }

        // Start listening for response (Input 2)
        if (this.autoListen && intents.length > 0) {
            // Small delay after TTS
            setTimeout(() => this.startListening(), 300);
        }
    }

    /**
     * Process a raw transcript or button-selected intent.
     * Returns classified intent or triggers clarification.
     */
    processPatientInput(input, isVoice = false) {
        this.logCounter++;
        let classified;

        if (isVoice) {
            classified = this.classifyIntent(input, this.currentIntents, this.currentPhaseId);
        } else {
            // Button press — exact intent match, full confidence
            classified = {
                intent: input,
                confidence: 1.0,
                rawTranscript: input,
                scores: [],
            };
        }

        // Log conversation entry
        const logEntry = {
            id: this.logCounter,
            timestamp: new Date().toISOString(),
            phase: this.currentPhaseId,
            question: this.currentQuestion,
            rawTranscript: isVoice ? input : null,
            classifiedIntent: classified.intent,
            confidence: classified.confidence,
            isVoice,
            isClarification: this.clarificationMode,
        };
        this.conversationLog.push(logEntry);
        this.emit('log-entry', logEntry);

        // ── Confidence handling ──
        if (classified.confidence < this.lowConfidence && classified.intent !== null) {
            return this._handleLowConfidence(classified, input);
        }

        if (classified.confidence < this.highConfidence && classified.confidence >= this.lowConfidence) {
            return this._handleMediumConfidence(classified, input);
        }

        if (classified.intent === null) {
            return this._handleNoMatch(input);
        }

        // High confidence — return intent
        this.clarificationMode = false;
        this.clarificationCount = 0;

        return {
            intent: classified.intent,
            confidence: classified.confidence,
            rawTranscript: input,
            action: 'proceed',
        };
    }

    _handleLowConfidence(classified, rawInput) {
        this.clarificationCount++;
        if (this.clarificationCount > this.maxClarifications) {
            // Too many clarifications — present buttons
            return {
                intent: null,
                confidence: classified.confidence,
                rawTranscript: rawInput,
                action: 'show_buttons',
                message: "I'm having trouble understanding. Please select one of the options.",
            };
        }

        this.clarificationMode = true;
        const clarifyText = this._getClarificationQuestion(classified, rawInput);

        return {
            intent: null,
            confidence: classified.confidence,
            rawTranscript: rawInput,
            action: 'clarify',
            message: clarifyText,
            suggestedIntents: classified.scores
                ? classified.scores.filter(s => s.score > 0.1).map(s => s.intent)
                : [],
        };
    }

    _handleMediumConfidence(classified, rawInput) {
        // Medium confidence: confirm with patient
        this.clarificationMode = true;
        const confirmText = `I heard "${rawInput}". Did you mean: ${classified.intent}?`;

        return {
            intent: classified.intent,
            confidence: classified.confidence,
            rawTranscript: rawInput,
            action: 'confirm',
            message: confirmText,
        };
    }

    _handleNoMatch(rawInput) {
        this.clarificationCount++;
        if (this.clarificationCount > this.maxClarifications) {
            return {
                intent: null,
                confidence: 0,
                rawTranscript: rawInput,
                action: 'show_buttons',
                message: "I couldn't understand your response. Please select from the options below.",
            };
        }

        return {
            intent: null,
            confidence: 0,
            rawTranscript: rawInput,
            action: 'clarify',
            message: "I didn't quite catch that. Could you please repeat your answer?",
        };
    }

    _getClarificationQuestion(classified, rawInput) {
        const phase = this.currentPhaseId;

        if (phase.includes('jcc')) {
            return 'Was the first or second option clearer, or were they the same?';
        }
        if (phase.includes('duochrome')) {
            return 'Is the red side or green side clearer, or are they the same?';
        }
        if (phase.includes('binocular_balance')) {
            return 'Is the top or bottom line blurrier, or are they the same?';
        }
        if (phase.includes('refraction') || phase === 'distance_vision') {
            return 'Can you read the letters on the chart, are they blurry, or can you not see them at all?';
        }

        return "Could you please repeat that? Try saying it differently.";
    }

    // ─── Greeting & Instructions ───────────────────
    async greetPatient(patientName) {
        const greeting = patientName
            ? `Hello ${patientName}, welcome to your eye examination. I'll be guiding you through the test today. Please look straight ahead and follow my instructions.`
            : `Hello, welcome to your eye examination. I'll be guiding you through the test today. Please look straight ahead and follow my instructions.`;

        await this.speak(greeting);
        return greeting;
    }

    async announcePhase(phaseName) {
        const text = `Moving to: ${phaseName}`;
        this.emit('phase-announce', { text, phaseName });
        if (this.voiceEnabled) {
            await this.speak(text);
        }
        return text;
    }

    async announcePrescription(rx) {
        const lines = [];
        lines.push('Your eye test is now complete. Here are your results:');
        lines.push(`Right eye: sphere ${rx.right.sph.toFixed(2)}, cylinder ${rx.right.cyl.toFixed(2)}, axis ${rx.right.axis} degrees.`);
        lines.push(`Left eye: sphere ${rx.left.sph.toFixed(2)}, cylinder ${rx.left.cyl.toFixed(2)}, axis ${rx.left.axis} degrees.`);
        if (rx.pd) lines.push(`Pupillary distance: ${rx.pd} millimeters.`);

        const text = lines.join(' ');
        await this.speak(text);
        return text;
    }

    // ─── Session Export ────────────────────────────
    getConversationLog() {
        return [...this.conversationLog];
    }

    exportSession() {
        return {
            exportTime: new Date().toISOString(),
            totalInteractions: this.conversationLog.length,
            voiceInteractions: this.conversationLog.filter(e => e.isVoice).length,
            buttonInteractions: this.conversationLog.filter(e => !e.isVoice).length,
            clarifications: this.conversationLog.filter(e => e.isClarification).length,
            log: this.conversationLog,
        };
    }

    // ─── Capabilities Check ────────────────────────
    getCapabilities() {
        return {
            tts: !!this.synth,
            asr: !!this.recognition,
            voiceEnabled: this.voiceEnabled,
            language: this.language,
            voiceCount: this.voices.length,
        };
    }
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = AIOptometrist;
}
