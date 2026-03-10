# Eye Test Engine

Interactive eye test session orchestrator with frontend and backend API server.

## Overview

This engine provides an interactive eye test system that:
- Manages conversation flow with patients through a web interface
- Controls phoropter hardware via API calls
- Implements clinical phases (distance vision, refraction, JCC, duochrome, binocular balance)
- Tracks state transitions and power adjustments

## Architecture

```
eye_test_engine/
├── config/
│   ├── protocol.yaml          # Phase definitions and transition rules
│   └── thresholds.yaml        # Configurable thresholds
├── core/
│   ├── context.py             # Row-level context
│   └── state_machine.py       # Phase transition logic
├── frontend/
│   ├── index.html             # Web interface
│   └── app.js                 # Frontend logic
├── tests/
│   └── (test files)
├── interactive_session.py     # Session orchestrator
├── api_server.py              # Backend API server
└── start_frontend.sh          # Frontend launcher script
```

## Installation

### 1. Create and activate virtual environment

```bash
cd eye_test_engine
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
```

### 2. Install dependencies

```bash
pip install pyyaml flask flask-cors
```

## Usage

You can run the backend API and the frontend static server from a development virtualenv.

If you created a venv inside `eye_test_engine`:

```bash
cd eye_test_engine
source venv/bin/activate
# start backend (port 5050)
PYTHONPATH=.. python -m eye_test_engine.api_server
```

Or, if your project uses a workspace venv at the repository root (e.g. `.venv`):

```bash
# in one terminal
source .venv/bin/activate
cd eye_test_engine
PYTHONPATH=.. python -m eye_test_engine.api_server

# in another terminal
source .venv/bin/activate
cd eye_test_engine/frontend
python3 -m http.server 8080
```

Simpler: from the `eye_test_engine` folder you can run the launcher script which will try to activate a local venv or a parent `.venv` and start both servers:

```bash
cd eye_test_engine
./start_frontend.sh
```

The servers will be available at:

- Frontend: http://localhost:8080
- Backend API: http://localhost:5050

Open your browser to the frontend URL above.

## Phase Flow

```
Phase A: Distance Vision
    ↓
Phase B: Right Eye Refraction
    ↓
Phase E: JCC Axis Right (±5° or ±10°)
    ↓
Phase F: JCC Power Right (±0.25D or ±0.50D)
    ↓
Phase G: Duochrome Right
    ↓
Phase D: Left Eye Refraction
    ↓
Phase H: JCC Axis Left (±5° or ±10°)
    ↓
Phase I: JCC Power Left (±0.25D or ±0.50D)
    ↓
Phase J: Duochrome Left
    ↓
Phase K: Binocular Balance (BINO)
    ↓
Test Complete
```

## Features

### Interactive Session Management
- Real-time patient interaction through web interface
- Automatic phase transitions based on patient responses
- Power adjustment tracking with previous state support
- Chart selection and progression

### JCC Refinement
- Automatic flip timing (2 seconds)
- Standard adjustments: ±5° axis, ±0.25D cylinder
- Large adjustments: ±10° axis, ±0.50D cylinder
- Reversal detection for phase transitions
- Spherical equivalent compensation

### Binocular Balance
- Chart_20 (BINO chart) display
- Top/bottom line blur detection
- Iterative balancing until both eyes equal
- Previous state restoration

### Vision Correction API
- All power adjustments use Vision Correction API with Previous State
- Accurate click calculations with prev/current state tracking
- Aux lens state tracking (AuxLensL, AuxLensR, BINO)

## Configuration

### protocol.yaml

Defines:
- Phase triggers (occluder states, chart types)
- Questions and intents for each phase
- Exit conditions and transition rules
- Adjustment rules for JCC flips

### thresholds.yaml

Configurable parameters:
- `unable_read_threshold`: Number of "Unable to read" to exit sphere phase (default: 2)
- `axis_increment`: Degrees to adjust per JCC axis flip (default: 5)
- `power_increment`: Diopters to adjust per JCC power flip (default: 0.25)

## API Endpoints

### Backend API (Port 5050)

- `POST /api/session/start` - Start new test session
- `POST /api/session/<id>/respond` - Process patient response
- `POST /api/session/<id>/switch-chart` - Switch to different chart
- `POST /api/session/<id>/jump` - Jump to specific phase
- `GET /api/session/<id>/status` - Get current session state

### Phoropter API

All phoropter commands are sent to:
```
https://rajasthan-royals.preprod.lenskart.com/phoropter/phoropter-1/run-tests
```

See `../curl_API.md` for complete API documentation.

## Documentation

Detailed documentation is available in the `docs/` folder:

- **[docs/QUICK_START.md](docs/QUICK_START.md)** - Get started quickly
- **[docs/DEMO.md](docs/DEMO.md)** - Interactive walkthrough
- **[docs/FRONTEND_GUIDE.md](docs/FRONTEND_GUIDE.md)** - Frontend usage guide
- **[docs/API_USAGE.md](docs/API_USAGE.md)** - API endpoints and usage

See [docs/INDEX.md](docs/INDEX.md) for the complete documentation index.
