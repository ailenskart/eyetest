/**
 * Foropter Scanner Tool
 * Tracks all annotations and screen changes in the Foropter interface
 */

class ForopterScanner {
    constructor() {
        this.logs = [];
        this.screenNumber = 1;
        this.annotations = new Map();
        this.previousState = null;
        this.autoScroll = true;

        this.state = {
            eye: 'OD',
            sphere: 0.00,
            cylinder: 0.00,
            axis: 0,
            add: 0.00,
            pd: 63,
            testType: 'snellen',
            lenses: {
                red: false,
                green: false,
                polarized: false,
                occluder: false,
                pinhole: false
            }
        };

        this.init();
    }

    init() {
        this.scanAnnotations();
        this.bindEvents();
        this.updateScreenState();
        this.updateTimestamp();
        this.log('system', 'Foropter Scanner initialized');
        this.log('screen', `Screen ${this.screenNumber} loaded`);

        // Update timestamp every second
        setInterval(() => this.updateTimestamp(), 1000);
    }

    // Scan all data-annotation attributes in the DOM
    scanAnnotations() {
        const elements = document.querySelectorAll('[data-annotation]');
        const listContainer = document.getElementById('annotationsList');
        listContainer.innerHTML = '';

        elements.forEach((element, index) => {
            const annotation = element.getAttribute('data-annotation');
            this.annotations.set(annotation, {
                element: element,
                index: index,
                scanned: new Date().toISOString()
            });

            // Create annotation tag
            const tag = document.createElement('span');
            tag.className = 'annotation-tag';
            tag.textContent = annotation;
            tag.addEventListener('click', () => this.highlightAnnotation(annotation));
            listContainer.appendChild(tag);
        });

        this.log('state', `Scanned ${this.annotations.size} annotations`);
    }

    highlightAnnotation(annotation) {
        const data = this.annotations.get(annotation);
        if (data) {
            // Remove previous highlights
            document.querySelectorAll('.annotation-tag').forEach(tag => {
                tag.classList.remove('highlighted');
            });
            document.querySelectorAll('.control-group').forEach(group => {
                group.style.borderLeftColor = '';
            });

            // Highlight current
            const tags = document.querySelectorAll('.annotation-tag');
            tags.forEach(tag => {
                if (tag.textContent === annotation) {
                    tag.classList.add('highlighted');
                }
            });

            data.element.style.borderLeftColor = '#ff9800';
            data.element.scrollIntoView({ behavior: 'smooth', block: 'center' });

            this.log('action', `Focused on annotation: ${annotation}`);
        }
    }

    bindEvents() {
        // Eye selection buttons
        document.querySelectorAll('.eye-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                document.querySelectorAll('.eye-btn').forEach(b => b.classList.remove('active'));
                e.target.classList.add('active');
                const eye = e.target.dataset.eye;
                this.updateState('eye', eye);
            });
        });

        // Dial buttons (increase/decrease)
        document.querySelectorAll('.dial-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const action = e.target.dataset.action;
                const target = e.target.dataset.target;
                const input = document.getElementById(target);
                const step = parseFloat(input.step) || 1;
                let value = parseFloat(input.value) || 0;

                if (action === 'increase') {
                    value = Math.min(parseFloat(input.max), value + step);
                } else {
                    value = Math.max(parseFloat(input.min), value - step);
                }

                input.value = value.toFixed(step < 1 ? 2 : 0);
                this.updateState(target, value);
            });
        });

        // Direct input changes
        ['sphere', 'cylinder', 'axis', 'add', 'pd'].forEach(id => {
            const input = document.getElementById(id);
            input.addEventListener('change', (e) => {
                const value = parseFloat(e.target.value) || 0;
                this.updateState(id, value);
            });
        });

        // Test type selection
        document.getElementById('testType').addEventListener('change', (e) => {
            this.updateState('testType', e.target.value);
        });

        // Lens checkboxes
        document.querySelectorAll('[data-lens]').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const lens = e.target.dataset.lens;
                this.state.lenses[lens] = e.target.checked;
                this.log('value', `Lens ${lens}: ${e.target.checked ? 'ON' : 'OFF'}`);
                this.updateScreenState();
            });
        });

        // Action buttons
        document.getElementById('resetValues').addEventListener('click', () => this.resetValues());
        document.getElementById('captureReading').addEventListener('click', () => this.captureReading());
        document.getElementById('switchScreen').addEventListener('click', () => this.switchScreen());

        // Header controls
        document.getElementById('clearLogs').addEventListener('click', () => this.clearLogs());
        document.getElementById('exportLogs').addEventListener('click', () => this.exportLogs());
        document.getElementById('autoScroll').addEventListener('change', (e) => {
            this.autoScroll = e.target.checked;
        });
    }

    updateState(key, value) {
        const oldValue = this.state[key];
        this.state[key] = value;

        this.log('value', `${key}: ${oldValue} → ${value}`);
        this.updateScreenState();
        this.setStatus(`Updated ${key} to ${value}`);
    }

    updateScreenState() {
        const stateDisplay = document.getElementById('screenState');
        const formattedState = JSON.stringify(this.state, null, 2);
        stateDisplay.textContent = formattedState;

        // Check for state changes
        if (this.previousState) {
            const changes = this.detectChanges(this.previousState, this.state);
            if (changes.length > 0) {
                this.log('state', `State changed: ${changes.join(', ')}`);
            }
        }

        this.previousState = JSON.parse(JSON.stringify(this.state));
    }

    detectChanges(oldState, newState) {
        const changes = [];

        for (const key in newState) {
            if (key === 'lenses') {
                for (const lens in newState.lenses) {
                    if (oldState.lenses[lens] !== newState.lenses[lens]) {
                        changes.push(`lenses.${lens}`);
                    }
                }
            } else if (oldState[key] !== newState[key]) {
                changes.push(key);
            }
        }

        return changes;
    }

    resetValues() {
        this.state = {
            eye: 'OD',
            sphere: 0.00,
            cylinder: 0.00,
            axis: 0,
            add: 0.00,
            pd: 63,
            testType: 'snellen',
            lenses: {
                red: false,
                green: false,
                polarized: false,
                occluder: false,
                pinhole: false
            }
        };

        // Update UI
        document.querySelectorAll('.eye-btn').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.eye === 'OD');
        });
        document.getElementById('sphere').value = '0.00';
        document.getElementById('cylinder').value = '0.00';
        document.getElementById('axis').value = '0';
        document.getElementById('add').value = '0.00';
        document.getElementById('pd').value = '63';
        document.getElementById('testType').value = 'snellen';
        document.querySelectorAll('[data-lens]').forEach(cb => cb.checked = false);

        this.log('action', 'All values reset to defaults');
        this.updateScreenState();
        this.setStatus('Values reset');
    }

    captureReading() {
        const reading = {
            timestamp: new Date().toISOString(),
            screen: this.screenNumber,
            ...this.state
        };

        this.log('action', `Reading captured for ${this.state.eye}`);
        this.log('state', `Captured: SPH ${this.state.sphere} CYL ${this.state.cylinder} x ${this.state.axis}`);

        // Store reading (could be sent to server)
        console.log('Captured Reading:', reading);
        this.setStatus(`Reading captured for ${this.state.eye}`);
    }

    switchScreen() {
        this.screenNumber++;
        document.getElementById('screenCounter').textContent = `Screen: ${this.screenNumber}`;

        this.log('screen', `Switched to Screen ${this.screenNumber}`);
        this.log('state', `Previous screen completed with ${this.logs.length} log entries`);
        this.setStatus(`Screen ${this.screenNumber} active`);
    }

    log(type, message) {
        const timestamp = new Date().toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            fractionalSecondDigits: 3
        });

        const entry = {
            time: timestamp,
            type: type,
            message: message,
            screen: this.screenNumber
        };

        this.logs.push(entry);
        this.renderLogEntry(entry);
        this.updateLogCount();
    }

    renderLogEntry(entry) {
        const container = document.getElementById('logContainer');
        const div = document.createElement('div');
        div.className = 'log-entry';
        div.innerHTML = `
            <span class="log-time">${entry.time}</span>
            <span class="log-type ${entry.type}">${entry.type}</span>
            <span class="log-message">${entry.message}</span>
        `;
        container.appendChild(div);

        if (this.autoScroll) {
            container.scrollTop = container.scrollHeight;
        }
    }

    updateLogCount() {
        document.getElementById('logCount').textContent = this.logs.length;
    }

    clearLogs() {
        this.logs = [];
        document.getElementById('logContainer').innerHTML = '';
        this.updateLogCount();
        this.log('system', 'Logs cleared');
    }

    exportLogs() {
        const exportData = {
            exportTime: new Date().toISOString(),
            totalEntries: this.logs.length,
            annotations: Array.from(this.annotations.keys()),
            currentState: this.state,
            logs: this.logs
        };

        const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `foropter-log-${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);

        this.log('action', `Exported ${this.logs.length} log entries`);
        this.setStatus('Logs exported');
    }

    setStatus(message) {
        document.getElementById('statusMessage').textContent = message;
    }

    updateTimestamp() {
        const now = new Date().toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        });
        document.getElementById('timestamp').textContent = now;
    }
}

// Initialize the scanner when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.foropterScanner = new ForopterScanner();
});
