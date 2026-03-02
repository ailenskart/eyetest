# AI Eye Test System — Product Documentation

**Version:** 1.0
**Last Updated:** February 2026
**Product:** AI-Powered Subjective Refraction System for Topcon CV-5000
**Built for:** Lenskart

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [System Architecture](#2-system-architecture)
3. [User Personas & Modes](#3-user-personas--modes)
4. [User Flows](#4-user-flows)
5. [Clinical Protocol — 12-Phase State Machine](#5-clinical-protocol--12-phase-state-machine)
6. [Hardware Integration — CV-5000 Protocol](#6-hardware-integration--cv-5000-protocol)
7. [AI & Voice System](#7-ai--voice-system)
8. [Statistical Learning Model (SLM)](#8-statistical-learning-model-slm)
9. [Video Analysis System](#9-video-analysis-system)
10. [UI/UX Design System](#10-uiux-design-system)
11. [Module Reference](#11-module-reference)
12. [Configuration & Deployment](#12-configuration--deployment)
13. [Data & Privacy](#13-data--privacy)
14. [Glossary](#14-glossary)

---

## 1. Product Overview

### 1.1 What It Is

The AI Eye Test System is a browser-based application that automates subjective refraction — the part of an eye exam where the optometrist asks "Which is better, one or two?" It connects to a **Topcon CV-5000 phoropter** via a cloud broker and guides the patient through the entire exam using AI-driven conversation, voice interaction, and automated lens adjustments.

### 1.2 The Problem

Traditional subjective refraction:
- Requires a trained optometrist for the entire 10–15 minute procedure
- Quality depends heavily on practitioner experience
- No standardisation of protocol — steps get skipped under time pressure
- No audit trail of clinical decisions
- Cannot scale with patient demand at retail optometry chains

### 1.3 The Solution

This system acts as an **AI optometrist** that:
- Follows a clinically validated 12-phase refraction protocol every time
- Communicates with the patient via voice and on-screen buttons
- Controls the phoropter hardware directly — no manual dial adjustment
- Learns from real optometrist sessions to improve its clinical patterns
- Provides three modes: assisted store visit, optometrist copilot, and home self-test

### 1.4 Key Differentiators

| Capability | Traditional | AI Eye Test |
|---|---|---|
| Protocol compliance | Variable | 100% — 12 phases every time |
| Exam consistency | Practitioner-dependent | Standardised |
| Audit trail | None | Full session log with rationale |
| Patient experience | Passive | Active — voice interaction, progress tracking |
| Learning | Per-practitioner experience | Statistical learning from all sessions |
| Scalability | 1 optometrist : 1 patient | 1 optometrist can supervise multiple AI exams |

---

## 2. System Architecture

### 2.1 High-Level Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    BROWSER (Brain UI)                    │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ ModeManager  │  │    App.js    │  │ AI Optometrist │ │
│  │  (persona)   │  │ (controller) │  │  (voice I/O)   │ │
│  └──────┬───────┘  └──────┬───────┘  └───────┬────────┘ │
│         │                 │                   │          │
│  ┌──────┴─────────────────┴───────────────────┴───────┐ │
│  │              RefractionEngine                       │ │
│  │           (12-phase state machine)                  │ │
│  └─────────────────────┬───────────────────────────────┘ │
│                        │                                 │
│  ┌─────────────────────┴───────────────────────────────┐ │
│  │            CV5000Protocol                           │ │
│  │     (device management + command dispatch)           │ │
│  └─────────────────────┬───────────────────────────────┘ │
│                        │                                 │
│  ┌───────────┐  ┌──────┴───────┐                        │
│  │ OptomSLM  │  │VideoAnalyzer │                        │
│  │ (learning) │  │ (training)   │                        │
│  └───────────┘  └──────────────┘                        │
└────────────────────────┬────────────────────────────────┘
                         │ HTTPS
                         ▼
              ┌─────────────────────┐
              │   Broker (preprod)   │
              │  rajasthan-royals.   │
              │ preprod.lenskart.com │
              └──────────┬──────────┘
                         │ WebSocket
                         ▼
              ┌─────────────────────┐
              │    Agent (Windows)   │
              │   Native CV-5000    │
              │   desktop control    │
              └──────────┬──────────┘
                         │ Serial/USB
                         ▼
              ┌─────────────────────┐
              │   Topcon CV-5000    │
              │    Phoropter        │
              └─────────────────────┘
```

### 2.2 Communication Flow

1. **Brain → Broker**: HTTP POST requests with JSON payloads
2. **Broker → Agent**: WebSocket relay to Windows desktop agent
3. **Agent → CV-5000**: Native automation (keyboard/mouse) of the CV-5000 desktop software
4. **Patient → Brain**: Voice (Web Speech API) or button clicks
5. **Brain → Patient**: Voice (TTS) and on-screen UI updates

### 2.3 Module Dependency Graph

```
index.html
  └── styles.css
  └── cv5000-protocol.js    (no dependencies)
  └── refraction-engine.js  (depends on cv5000-protocol)
  └── ai-optometrist.js     (no dependencies)
  └── optom-slm.js          (no dependencies)
  └── video-analyzer.js     (depends on optom-slm)
  └── mode-manager.js       (no dependencies)
  └── app.js                (orchestrates all modules)
```

### 2.4 Technology Stack

| Layer | Technology |
|---|---|
| UI | Vanilla HTML/CSS/JS — no framework |
| Voice Output | Web Speech API `SpeechSynthesis` |
| Voice Input | Web Speech API `SpeechRecognition` |
| Hardware Comm | Fetch API (HTTP REST) |
| Data Persistence | `localStorage` (SLM model) |
| Server | Static file server (any HTTP server) |
| Browser Support | Chrome/Edge (Speech API requires Chromium) |

---

## 3. User Personas & Modes

The system supports three distinct user personas, each with a tailored UI experience. Mode is selected at launch on Screen 0 and controls all downstream behaviour.

### 3.1 Customer Mode

**Who:** A patient visiting a Lenskart store for an eye test.

**Experience:**
- Friendly, non-clinical language throughout
- Progress tracker: Setup → Right Eye → Left Eye → Both → Done
- Comfort check modal: pause exam, take a break, get tips
- Voice-guided interaction with patient-friendly intent buttons
- Results screen with plain-language vision explanation
- No hardware configuration visible — auto-connects

**UI Adaptations:**
- Clinical phase names hidden; friendly names shown (e.g., "jcc_axis_right" → "Fine-tuning right eye (part 1)")
- Intent buttons use plain language ("Unable to read" → "I can't read it")
- Technical panels (phoropter connection, clinical log) hidden
- Patient progress bar replaces clinical progress bar
- Results show approximate VA description ("20/20 — Excellent") instead of raw numbers
- Voice auto-enabled

**Key Features:**
- Comfort check button in exam header
- Exam timer display
- Patient-friendly results with vision explanation
- Share report / Book appointment buttons

### 3.2 Optometrist Copilot Mode

**Who:** A licensed optometrist using the AI as an assistant during the exam.

**Experience:**
- Full clinical interface — all technical details visible
- AI Confidence Dashboard showing real-time classification accuracy
- Live Rx comparison: AR baseline vs. current prescription with deltas
- Quick Override controls: SPH/CYL/AXIS stepper buttons for manual intervention
- Exam Quality Score: weighted metric tracking confidence, overrides, and clarifications
- Session log with rationale for every AI decision

**UI Adaptations:**
- All clinical controls visible
- Copilot tab added to right panel with dashboard sections
- Clinical phase names shown in full
- Intent buttons show clinical labels
- Results include quality report (score/100, steps, avg confidence, duration)
- No comfort check — optometrist handles patient comfort directly

**Copilot Dashboard Sections:**

| Section | Description |
|---|---|
| AI Confidence | Real-time confidence bar + percentage badge (green ≥75%, amber ≥40%, red <40%) |
| Rx Comparison | 6-row table: R/L × SPH/CYL/AXIS showing AR, Current, and Delta columns |
| Quick Override | Eye selector (R/L) + SPH/CYL/AXIS stepper controls + Apply button |
| Exam Quality | Response count, override count, clarification count, avg confidence, quality score |

**Quality Score Formula:**
```
score = (avgConfidence × 50) + max(0, 30 − overrides × 5) + max(0, 20 − clarifications × 3)
```
- Maximum: 100 points
- 50 points from average classification confidence
- 30 points base, minus 5 per manual override
- 20 points base, minus 3 per clarification request

### 3.3 Self-Test Mode

**Who:** A home user performing a basic vision screening without hardware.

**Experience:**
- On-screen Snellen chart rendered in the browser
- No phoropter hardware required — simulated mode auto-enabled
- Patient-friendly language (same as Customer)
- Progress tracker and comfort check available
- Shareable report for bringing to an optometrist
- Disclaimer: "This is a preliminary screening — visit a licensed optometrist"

**On-Screen Chart System:**
- 9 Snellen lines rendered with decreasing font sizes:

| Line | VA | Letters | Font Size |
|---|---|---|---|
| 1 | 20/200 | E | 72px |
| 2 | 20/100 | F P | 56px |
| 3 | 20/70 | T O Z | 44px |
| 4 | 20/50 | L P E D | 36px |
| 5 | 20/40 | P E C F D | 28px |
| 6 | 20/30 | E D F C Z P | 22px |
| 7 | 20/25 | F E L O P Z D | 18px |
| 8 | 20/20 | D E F P O T E C | 15px |
| 9 | 20/15 | L E F O D P C T | 12px |

- Duochrome chart: Red/Green split display
- Binocular balance chart: Top/Bottom split display
- Eye indicator shows which eye is being tested ("Cover your left eye")

**UI Adaptations:**
- Phoropter connection card hidden on intake screen
- Simulated mode checkbox auto-checked
- Self-test chart panel visible in conversation area
- On mobile: phoropter panel hidden entirely

### 3.4 Visibility Control System

Mode-specific elements use CSS class annotations:

```html
<div class="customer-only">Only visible in Customer mode</div>
<div class="copilot-only">Only visible in Copilot mode</div>
<div class="selftest-only">Only visible in Self-Test mode</div>
```

The `ModeManager.setMode()` method:
1. Sets `data-mode` attribute on `<body>`
2. Toggles `.hidden` class on all mode-specific elements
3. Updates mode badges across screens
4. Configures mode-specific defaults (voice, simulation, visible cards)

---

## 4. User Flows

### 4.1 Complete Flow — Customer Mode

```
Screen 0: Mode Selection
  │  User clicks "Customer" card
  ▼
Screen 1: Patient Intake
  │  ├── Patient name (optional)
  │  ├── Age
  │  ├── AR readings (SPH/CYL/AXIS per eye)
  │  ├── Old Rx (optional)
  │  ├── PD
  │  └── Voice enabled (auto-on)
  │  Phoropter connection auto-handled
  │  User clicks "Start Eye Test"
  ▼
Screen 2: Exam
  │  AI speaks greeting
  │  Progress: ● Setup → ○ Right → ○ Left → ○ Both → ○ Done
  │
  │  ┌─── Phase Loop ───────────────────────────┐
  │  │  AI asks question (voice + on-screen)     │
  │  │  Patient responds (voice or button)       │
  │  │  Engine processes response                │
  │  │  Phoropter adjusts automatically          │
  │  │  → Next question or next phase            │
  │  └──────────────────────────────────────────┘
  │
  │  [Comfort Check] available at any time
  │  │  ├── Resume exam
  │  │  ├── Take a break (30s/60s)
  │  │  └── Stop exam early
  │
  │  After binocular balance phase completes
  ▼
Screen 3: Results
  ├── Patient Summary Hero
  │   ├── "Your exam took 8 minutes. Here's what we found."
  │   ├── Right Eye: 20/25 (Very Good)
  │   ├── Left Eye: 20/40 (Good)
  │   └── Plain-language explanation
  ├── Full Prescription Table (SPH/CYL/AXIS/ADD per eye)
  ├── Clinical Flags (if any)
  ├── Share Report button
  ├── Book Appointment button
  └── Start New Test button
```

### 4.2 Complete Flow — Optometrist Copilot

```
Screen 0: Mode Selection
  │  Optometrist clicks "Optometrist Copilot" card
  ▼
Screen 1: Patient Intake
  │  All clinical fields visible
  │  Connect to phoropter hardware
  │  Enter AR readings, old Rx, PD
  │  Select operator/optometrist mode
  │  Click "Start Eye Test"
  ▼
Screen 2: Exam
  │  ┌─────────────────────┬──────────────────────┐
  │  │   Conversation       │   Right Panel         │
  │  │   Panel              │   ├── Phoropter       │
  │  │   ├── AI questions   │   │   ├── Live state  │
  │  │   ├── Patient voice  │   │   ├── Controls    │
  │  │   ├── Intent buttons │   │   └── Panel       │
  │  │   └── Clinical log   │   ├── Copilot Tab     │
  │  │                      │   │   ├── Confidence   │
  │  │                      │   │   ├── Rx Compare   │
  │  │                      │   │   ├── Override     │
  │  │                      │   │   └── Quality      │
  │  │                      │   ├── Rationale Tab    │
  │  │                      │   └── Log Tab          │
  │  └─────────────────────┴──────────────────────┘
  │
  │  Optometrist can:
  │  ├── Monitor AI confidence in real time
  │  ├── See AR vs Current Rx comparison with deltas
  │  ├── Override Rx values via stepper controls
  │  ├── Let AI handle the conversation or intervene
  │  └── Review full rationale for each decision
  ▼
Screen 3: Results
  ├── Clinical Prescription Table
  ├── Quality Report (score/100, steps, confidence, duration)
  ├── Session Flags
  ├── Export Session button
  └── Start New Test button
```

### 4.3 Complete Flow — Self-Test

```
Screen 0: Mode Selection
  │  User clicks "Self Eye Test" card
  ▼
Screen 1: Patient Intake
  │  Phoropter connection hidden (not needed)
  │  Simulated mode auto-enabled
  │  Enter name, age
  │  AR readings optional (defaults to 0)
  │  Click "Start Eye Test"
  ▼
Screen 2: Exam
  │  On-screen Snellen chart displayed
  │  ┌─────────────────────────────────────┐
  │  │         ┌───────────────┐            │
  │  │         │    E          │  ← Chart   │
  │  │         │  Line 1 — 20/200           │
  │  │         │  Testing: Right Eye        │
  │  │         └───────────────┘            │
  │  │                                      │
  │  │  "Can you read the letters?"         │
  │  │  [Yes, I can read it] [I can't]      │
  │  └─────────────────────────────────────┘
  │
  │  Chart progresses through 9 Snellen lines
  │  Duochrome and binocular charts rendered on screen
  │  Progress tracker shows current step
  ▼
Screen 3: Results
  ├── "Your Vision Report"
  ├── Patient Summary (approximate VA per eye)
  ├── Explanation (myopia/hyperopia/normal)
  ├── Disclaimer: "Visit a licensed optometrist"
  ├── Share Report (JSON — copy or download)
  ├── Book Appointment
  └── Start New Test
```

---

## 5. Clinical Protocol — 12-Phase State Machine

### 5.1 Phase Sequence

The refraction engine implements the standard clinical subjective refraction protocol in 12 sequential phases:

| # | Phase ID | Clinical Name | Eye | Chart | Occluder |
|---|---|---|---|---|---|
| A | `distance_vision` | Distance Vision | BINO | E-chart (20/400) | None (BINO) |
| A2 | `fogging_right` | Fogging Right | Right | — | Left occluded |
| B | `right_eye_refraction` | Right Eye Refraction | Right | Snellen | Left occluded |
| E | `jcc_axis_right` | JCC Axis Right | Right | JCC chart | Left occluded |
| F | `jcc_power_right` | JCC Power Right | Right | JCC chart | Left occluded |
| G | `duochrome_right` | Duochrome Right | Right | Duochrome | Left occluded |
| C2 | `fogging_left` | Fogging Left | Left | — | Right occluded |
| D | `left_eye_refraction` | Left Eye Refraction | Left | Snellen | Right occluded |
| H | `jcc_axis_left` | JCC Axis Left | Left | JCC chart | Right occluded |
| I | `jcc_power_left` | JCC Power Left | Left | JCC chart | Right occluded |
| J | `duochrome_left` | Duochrome Left | Left | Duochrome | Right occluded |
| K | `binocular_balance` | Binocular Balance | Both | Binocular chart | None (BINO) |

### 5.2 Phase Details

#### Phase A: Distance Vision
- **Purpose:** Establish baseline visual acuity with both eyes open
- **Chart:** E-chart at 20/400
- **Intents:** "Able to read" / "Unable to read"
- **Logic:** If readable, present progressively smaller charts. Records best binocular VA.

#### Phase A2 & C2: Fogging
- **Purpose:** Relax accommodation to prevent over-minusing
- **Method:** Add positive sphere power to intentionally blur vision
- **Fog Calculation:**
  ```
  baseFog = +2.00D (standard)
  ageFactor = (age < 20) ? +0.50 : (age > 50) ? -0.25 : 0
  arFactor = (|AR_SPH| > 4) ? +0.50 : 0
  totalFog = baseFog + ageFactor + arFactor
  ```
- **Intents:** "It's blurry (fog confirmed)" / "Can still see clearly"
- **Logic:** Keep adding +0.25D until patient confirms blur. Maximum 8 attempts.

#### Phase B & D: Monocular Refraction (De-fog)
- **Purpose:** Find best sphere power for each eye
- **Method:** Progressively reduce plus (add minus) until best VA achieved
- **Step Size:** -0.25D per step
- **Intents:** "Able to read" / "Blurry but readable" / "Unable to read"
- **Exit Conditions:**
  - 20/20 (or 20/15) reached
  - 2 consecutive "Unable to read" responses with SPH changes
- **Chart Progression:** Start at largest unread chart, move to smaller on "Able to read"

#### Phases E, F, H, I: JCC (Jackson Cross-Cylinder)
- **Purpose:** Refine astigmatism axis (E/H) and power (F/I)
- **Method:** Present two lens options (Flip 1 and Flip 2) in rapid sequence
- **Timing:** Each flip shown for 2 seconds, then patient chooses
- **Intents:** "Flip 1 Better" / "Flip 1 MUCH Better" / "Flip 2 Better" / "Flip 2 MUCH Better" / "Both Same" / "Repeat flips"
- **Adjustments:**
  - Axis: ±5° for "Better", ±10° for "MUCH Better"
  - Power: ±0.25D CYL for "Better"
- **Exit:** "Both Same" or reversal detected (oscillating between same two values)

#### Phases G & J: Duochrome
- **Purpose:** Verify sphere endpoint — avoid over-minusing
- **Clinical Rule:** RAM-GAP (Red Add Minus, Green Add Plus)
- **Intents:** "Red" / "Green" / "Both Same (Red/Green)"
- **Adjustments:**
  - Red clearer → Add -0.25D SPH (under-corrected)
  - Green clearer → Add +0.25D SPH (over-corrected)
  - Same → Endpoint reached
- **Maximum:** 4 adjustments

#### Phase K: Binocular Balance
- **Purpose:** Equalise both eyes so neither dominates
- **Chart:** Binocular balance chart (top = right eye view, bottom = left eye view)
- **Intents:** "Top is blurry" / "Bottom is blurry" / "Both equal"
- **Adjustments:**
  - Top blurry → +0.25D to LEFT eye SPH
  - Bottom blurry → +0.25D to RIGHT eye SPH
- **Maximum:** 4 adjustments

### 5.3 Clinical Rationale System

Every AI decision produces a 7-field rationale object:

```json
{
  "phase": "right_eye_refraction",
  "why": "Patient reported 'Able to read' — advancing to next smaller chart",
  "clinical": "Snellen 20/40 achieved, progressing toward 20/20",
  "guide": "Presenting 20/30 chart. Patient should attempt to read smaller letters.",
  "expected": "Patient will either read the line (advance) or report blur (add -0.25D)",
  "watchFor": "Squinting, head tilt, or long hesitation may indicate struggling",
  "decisionLogic": "chartIndex++ because intent === 'Able to read' && currentVA !== '20/20'"
}
```

These rationales are visible in the Rationale tab (all modes) and provide full transparency into every clinical decision.

### 5.4 AR Reference Integration

Auto-Refractor (AR) readings entered during intake are used to:
- Set initial phoropter power as a starting point
- Calculate fogging amount (stronger prescriptions need more fog)
- Display as baseline comparison in copilot mode
- Validate final Rx against AR (flag if SPH delta > 2.00D)

---

## 6. Hardware Integration — CV-5000 Protocol

### 6.1 Connection Architecture

```
Brain UI  ──HTTP POST──▶  Broker Server  ──WebSocket──▶  Agent  ──▶  CV-5000
```

- **Base URL:** `https://rajasthan-royals.preprod.lenskart.com`
- **Dashboard:** `https://rajasthan-royals.preprod.lenskart.com/dashboard`

### 6.2 Device Management API

Multi-brain architecture allows multiple UIs to share a pool of phoropters. Exclusive locking prevents conflicts.

| Endpoint | Method | Description |
|---|---|---|
| `/devices` | GET | List available phoropter devices |
| `/devices?all=true` | GET | List all devices including acquired |
| `/devices/{id}` | GET | Get single device info |
| `/devices/{id}/acquire` | POST | Lock device for exclusive use |
| `/devices/{id}/release` | POST | Release device lock |
| `/devices/{id}/heartbeat` | POST | Keep lock alive (every 15s, auto-release after 60s) |

**Acquire Request:**
```json
{
  "brain_id": "brain_1709123456789",
  "name": "AI Eye Test"
}
```

### 6.3 Phoropter Control API

All phoropter commands go through the `run-tests` endpoint with different payload structures.

| Endpoint | Method | Description |
|---|---|---|
| `/phoropter/{id}/run-tests` | POST | Execute test cases (power, JCC, chart) |
| `/phoropter/{id}/reset` | POST | Reset to 0/0/180 |
| `/phoropter/{id}/pinhole` | POST | Activate pinhole |
| `/phoropter/{id}/occluder` | POST | Set occluder |
| `/phoropter/{id}/sync-state` | POST | Sync internal state (no clicks) |
| `/phoropter/{id}/screenshot` | POST | Capture agent screen (base64 JPEG) |

### 6.4 Payload Formats

**Power Control:**
```json
{
  "test_cases": [{
    "case_id": 1,
    "aux_lens": "AuxLensL",
    "right_eye": { "sph": -2.50, "cyl": -0.75, "axis": 170 },
    "left_eye": { "sph": -3.00, "cyl": -0.50, "axis": 15 }
  }]
}
```

**Power Control with Previous State (recommended — enables accurate delta click calculation):**
```json
{
  "test_cases": [{
    "case_id": 1,
    "prev_right_eye": { "sph": -2.25, "cyl": -0.50, "axis": 175 },
    "prev_left_eye": { "sph": -2.75, "cyl": -0.50, "axis": 15 },
    "prev_aux_lens": "AuxLensL",
    "right_eye": { "sph": -2.50, "cyl": -0.75, "axis": 170 },
    "left_eye": { "sph": -3.00, "cyl": -0.50, "axis": 15 },
    "aux_lens": "AuxLensL"
  }]
}
```

**JCC Control:**
```json
{
  "test_cases": [{ "jcc": "handle" }]
}
```

JCC actions: `handle` | `increase` | `decrease` | `power_axis_switch` | `R` | `L` | `BINO`

**Chart Control:**
```json
{
  "test_cases": [{
    "chart": {
      "tab": "Chart1",
      "chart_items": ["chart_13", "30"]
    }
  }]
}
```

### 6.5 Aux Lens / Occluder Mapping

| aux_lens Value | What It Does | Use Case |
|---|---|---|
| `AuxLensL` | Occludes left eye | Testing right eye (JCC R mode) |
| `AuxLensR` | Occludes right eye | Testing left eye (JCC L mode) |
| `BINO` | Both eyes open | Distance vision, binocular balance |
| `OFF` | Clear all occluders | — |

### 6.6 Chart ID Mapping

| Logical Name | CV-5000 ID | VA Range |
|---|---|---|
| `echart_400` | `chart_9` | 20/400 |
| `snellen_chart_200_150` | `chart_10` | 20/200 – 20/150 |
| `snellen_chart_100_80` | `chart_11` | 20/100 – 20/80 |
| `snellen_chart_70_60_50` | `chart_12` | 20/70 – 20/50 |
| `snellen_chart_40_30_25` | `chart_13` | 20/40 – 20/25 |
| `snellen_chart_20_15_10` | `chart_14` | 20/20 – 20/15 |
| `snellen_chart_20_20_20` | `chart_15` | 20/20 (alt) |
| `snellen_chart_25_20_15` | `chart_16` | 20/25 – 20/15 (alt) |
| `duochrome` | `chart_17` | — |
| `jcc_chart` | `chart_19` | — |
| `bino_chart` | `chart_20` | R/L rows |
| `near_chart` | `chart_5` | Near vision |

### 6.7 Simulated Mode

When `simulatedMode: true` (default for development and self-test):
- All API calls return `{ success: true, simulated: true }` without HTTP requests
- Internal state tracking still works — SPH/CYL/AXIS values updated locally
- Event system still fires — UI responds normally
- No heartbeat sent

### 6.8 Heartbeat & Device Lifecycle

```
acquire() ──▶ heartbeat every 15s ──▶ release()
                                        ▲
                  auto-release after 60s of no heartbeat
```

- `_startHeartbeat()`: Starts 15-second interval
- `_stopHeartbeat()`: Clears interval
- `destroy()`: Stops heartbeat + releases device (called on page unload)

---

## 7. AI & Voice System

### 7.1 Architecture

The `AIOptometrist` class handles all patient communication:

```
                     ┌──────────────┐
                     │ AIOptometrist │
                     └──────┬───────┘
                            │
               ┌────────────┼────────────┐
               ▼            ▼            ▼
          ┌────────┐  ┌──────────┐  ┌──────────┐
          │  TTS   │  │   ASR    │  │  Intent  │
          │ Output │  │  Input   │  │ Classify │
          └────────┘  └──────────┘  └──────────┘
```

### 7.2 Text-to-Speech (TTS) — Output

- **API:** `window.speechSynthesis`
- **Voice Selection:** Prefers Google English voices, falls back to any English voice
- **Configuration:**
  - Rate: 0.9 (slightly slower for clarity)
  - Pitch: 1.0 (natural)
  - Language: en-US (configurable)
- **Behaviour:** Cancels any ongoing speech before starting new utterance
- **Events:** `tts-start`, `tts-end`, `tts-error`, `tts-text` (when TTS disabled)

### 7.3 Automatic Speech Recognition (ASR) — Input

- **API:** `window.SpeechRecognition` / `webkitSpeechRecognition`
- **Configuration:**
  - Continuous: false (single utterance)
  - Interim results: true (real-time feedback)
  - Max alternatives: 3 (for confidence comparison)
  - Language: en-US
- **Flow:** After TTS finishes speaking the question, ASR starts after 300ms delay
- **Events:** `asr-start`, `asr-interim`, `asr-result`, `asr-end`, `asr-error`

### 7.4 Intent Classification

Converts free-form speech to structured clinical intents.

**Algorithm:**
1. Exact match → confidence 1.0
2. Phase-specific keyword matching → confidence 0.85–0.9
3. Generic fuzzy word overlap → confidence 0.0–0.6
4. Ambiguity penalty: if top 2 scores within 0.15, multiply best by 0.7

**Keyword Maps by Phase Type:**

| Phase Type | Intent | Keywords |
|---|---|---|
| Fogging | "It's blurry" | blurry, blur, yes, can't see, foggy |
| Fogging | "Can still see clearly" | clear, can see, not blurry, sharp |
| Refraction | "Able to read" | able to read, can read, yes, clear |
| Refraction | "Blurry" | blurry, blur, fuzzy, hazy, not clear |
| Refraction | "Unable to read" | unable, can't read, cannot see, no |
| JCC | "Flip 1 Better" | first better, first one, number one |
| JCC | "Flip 1 MUCH Better" | first much better, definitely first |
| JCC | "Flip 2 Better" | second better, second one, number two |
| JCC | "Both Same" | same, no difference, equal, identical |
| Duochrome | "Red" | red, red side, red is clearer |
| Duochrome | "Green" | green, green side, green is clearer |
| Binocular | "Top is blurry" | top, top blurry, upper |
| Binocular | "Bottom is blurry" | bottom, bottom blurry, lower |

### 7.5 Confidence Handling

Three tiers with different behaviours:

| Confidence | Range | Action |
|---|---|---|
| High | ≥ 0.75 | Accept intent, proceed |
| Medium | 0.40 – 0.74 | Confirm with patient ("I heard X. Did you mean Y?") |
| Low | < 0.40 | Request clarification (max 2 times, then show buttons) |

### 7.6 Clarification Flow

```
Low confidence detected
  ▼
Clarification question (phase-aware)
  ▼
Patient responds again
  ▼
Still low confidence?
  ├── Yes (< 2 attempts) → Ask again with different phrasing
  └── Yes (≥ 2 attempts) → Show button options for manual selection
```

### 7.7 Session Logging

Every interaction is logged:
```json
{
  "id": 1,
  "timestamp": "2026-02-28T10:30:00.000Z",
  "phase": "right_eye_refraction",
  "question": "Can you read the letters on this line?",
  "rawTranscript": "yes I can read them",
  "classifiedIntent": "Able to read",
  "confidence": 0.92,
  "isVoice": true,
  "isClarification": false
}
```

---

## 8. Statistical Learning Model (SLM)

### 8.1 Purpose

The OptomSLM learns patterns from real optometrist sessions (via video analysis or live exam data) and uses those patterns to flag deviations in new sessions.

### 8.2 What It Learns

| Pattern Type | Data Stored |
|---|---|
| Phase Sequences | Ordered list of phases observed in each session |
| Phase Timing | Duration distribution per phase (mean, stddev, min, max) |
| Step Counts | Number of interactions per phase |
| Power Patterns | SPH/CYL/AXIS deltas per phase |
| Decision Patterns | Intent → action transition frequencies |

### 8.3 Canonical Protocol

The "golden path" that every session is compared against:
```
distance_vision → fogging_right → right_eye_refraction →
jcc_axis_right → jcc_power_right → duochrome_right →
fogging_left → left_eye_refraction →
jcc_axis_left → jcc_power_left → duochrome_left →
binocular_balance
```

### 8.4 Flag Rules

8 built-in flag rules detecting common clinical issues:

| Rule ID | Severity | Description |
|---|---|---|
| `missing_fogging` | Critical | Fogging phase skipped — risk of over-minusing |
| `wrong_eye_order` | Warning | Left eye tested before right — non-standard |
| `no_jcc` | Warning | JCC astigmatism refinement skipped |
| `no_duochrome` | Warning | Duochrome endpoint verification skipped |
| `no_binocular_balance` | Warning | Binocular balance not performed |
| `excessive_sph_change` | Warning | SPH changed >2.00D from AR in single phase |
| `phase_too_fast` | Info | Phase completed in <5 seconds |
| `phase_too_slow` | Info | Phase took >300 seconds |

### 8.5 Statistical Anomaly Detection

After 3+ sessions, the SLM performs z-score analysis:
- Flag phases where duration deviates >2.5 standard deviations from learned mean
- Detect out-of-order phases compared to canonical sequence
- Flag unknown phases not in the standard protocol

### 8.6 Data Persistence

- **Storage:** `localStorage` under key `optom_slm_model`
- **Format:** JSON with version field for migration
- **Operations:** `exportModel()`, `importModel()`, `resetModel()`

### 8.7 Reference Video Library

14 reference optometry session videos available for training:
```
https://optometry.lenskart.com/ENGAGEMENT_VIDEOS/{session_id}/{video_id}.mp4
```

---

## 9. Video Analysis System

### 9.1 Purpose

The `VideoAnalyzer` allows operators to load optometry session recordings, annotate them with phase transitions and power changes, and feed the structured data into the SLM for learning.

### 9.2 Architecture

```
Video URL/File
  ▼
<video> element
  ▼
Frame sampling (every 2 seconds)
  ▼
Manual annotation by operator
  ├── Phase start/end markers
  ├── Power change events
  ├── Intent/action events
  └── Flag markers
  ▼
Structured timeline
  ▼
Phase extraction
  ▼
SLM.learnFromSession()
```

### 9.3 Annotation Types

| Type | Fields | Description |
|---|---|---|
| `phase_start` | phase, power | Mark beginning of a clinical phase |
| `phase_end` | phase, power | Mark end of a clinical phase |
| `power_change` | power (sph/cyl/axis) | Record lens power adjustment |
| `event` | intent, action | Record patient response and action taken |
| `flag` | note | Mark a notable event or issue |

### 9.4 SLM Integration

- `submitToSLM(metadata)`: Validates + learns from annotated session
- `validateOnly()`: Validates against learned patterns without learning
- Events: `slm-updated`, `validation-complete`

### 9.5 Production Roadmap

Current implementation provides the UI framework with manual annotation support. Production deployment would add:
- Server-side OCR (Tesseract/EasyOCR) on CV-5000 ROI regions
- Automatic phase detection from power display changes
- Automatic intent extraction from audio track
- Batch processing of video libraries

---

## 10. UI/UX Design System

### 10.1 Design Tokens

The system uses a dark clinical theme optimised for clinical environments (low ambient light, high contrast for readability).

**Colours:**

| Token | Value | Usage |
|---|---|---|
| `--bg-primary` | `#0f1119` | Page background |
| `--bg-secondary` | `#171b26` | Header, sidebars |
| `--bg-card` | `#1c2133` | Card backgrounds |
| `--bg-input` | `#232940` | Input fields |
| `--bg-hover` | `#2a3352` | Hover states |
| `--border-color` | `#2e3650` | Default borders |
| `--border-active` | `#4a7dff` | Active/focused borders |
| `--text-primary` | `#e4e8f1` | Primary text |
| `--text-secondary` | `#8891a8` | Secondary text |
| `--text-muted` | `#5a6380` | Muted text |
| `--accent-blue` | `#4a7dff` | Primary actions, links |
| `--accent-green` | `#34d399` | Success, positive |
| `--accent-red` | `#f87171` | Error, destructive |
| `--accent-amber` | `#fbbf24` | Warning, caution |
| `--accent-purple` | `#a78bfa` | Info, secondary accent |
| `--accent-cyan` | `#22d3ee` | Highlights, mode selection |

**Border Radius:**

| Token | Value |
|---|---|
| `--radius-sm` | `4px` |
| `--radius` | `8px` |
| `--radius-lg` | `12px` |

**Typography:**
- Font stack: `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', Roboto, sans-serif`
- Line height: 1.5
- Chart font: `'Courier New', Courier, monospace` (self-test Snellen display)

### 10.2 Screen Layout

```
┌──────────────────────────────────────────────────┐
│  Header (app-header)                             │
├──────────────────────────────────────────────────┤
│                                                  │
│  Screen Content                                  │
│  ├── Screen 0: Mode Selection (mode-main)        │
│  ├── Screen 1: Intake (intake-scroll)            │
│  ├── Screen 2: Exam (exam-layout)                │
│  │   ├── Left: Conversation Panel (60%)          │
│  │   └── Right: Control Panel (40%)              │
│  └── Screen 3: Results (results-scroll)          │
│                                                  │
└──────────────────────────────────────────────────┘
```

### 10.3 Component Catalogue

**Mode Selection Cards** (`.mode-card`)
- 3-column grid layout
- Hover: transform scale(1.03) + cyan border glow
- Icon: 64px circle with SVG icon
- Features list with checkmarks
- Single column on mobile

**Patient Progress Tracker** (`.patient-progress`)
- Horizontal flex bar with 5 steps
- Each step: dot + label + connecting line
- States: default (grey), active (cyan pulse), completed (green checkmark)
- Overflow-x scrollable on mobile

**Comfort Check Modal** (`.comfort-modal`)
- Fixed overlay with centered card
- Three options: Resume, Take a break, Stop early
- Tips section with relaxation suggestions

**Conversation Panel** (`.conversation-panel`)
- Chat-style message display
- AI messages: left-aligned, blue accent
- Patient messages: right-aligned, green accent
- Intent buttons: grid of action buttons
- Voice indicator: animated pulsing dot

**Phoropter Panel** (`.phoropter-panel`)
- Real-time power display for both eyes
- SPH/CYL/AXIS values in monospace font
- Phase name and chart display
- CV-5000 visual emulation panel

**Copilot Dashboard** (`.cp-section`)
- Confidence bar: full-width progress bar with colour coding
- Rx comparison table: monospace, delta highlighting
- Stepper controls: ± buttons for manual adjustment
- Quality score badge: good (green), fair (amber), poor (red)

**Self-Test Chart** (`.self-test-chart`)
- White background (#fff) for maximum contrast
- Black text, centered letters
- Decreasing font sizes (72px → 12px)
- Red/green coloured blocks for duochrome
- Eye indicator label

**Results Cards** (`.ps-vision-cards`)
- 2-column grid (right eye, left eye)
- Approximate VA in large text
- Explanation text below

### 10.4 Responsive Design

- Mode cards: 3-column → 1-column below 768px
- Exam layout: side-by-side → stacked on mobile
- Self-test mode on mobile: hides phoropter panel entirely
- Progress tracker: horizontal scroll on small screens
- Font sizes scale proportionally

---

## 11. Module Reference

### 11.1 `app.js` — Application Controller

**Class:** `EyeTestApp`

The central orchestrator that wires all modules together and handles UI interaction.

| Method | Description |
|---|---|
| `constructor()` | Initialises CV5000Protocol, ModeManager; sets initial screen to 'mode' |
| `_init()` | Binds all event handlers on DOMContentLoaded |
| `_bindModeEvents()` | Mode card click → setMode() → show intake |
| `_bindIntakeEvents()` | Form submission, phoropter connection, AR input |
| `_bindExamEvents()` | Voice toggle, intent buttons, manual controls |
| `_bindResultsEvents()` | Export, new test, share report, book appointment |
| `_initComfortCheck()` | Comfort button, resume/break/stop handlers |
| `_initCopilotControls()` | SPH/CYL/AXIS stepper buttons, apply override |
| `_startExam()` | Creates engine + AI instances, starts exam timer, mode-aware greeting |
| `_handleEngineResponse()` | Processes engine output, updates charts, renders intents |
| `_renderIntentButtons()` | Creates intent buttons with translated labels |
| `_handleIntentClick()` | Processes button press, updates confidence |
| `_handleVoiceIntent()` | Processes voice input, handles clarification flow |
| `_onPhaseChange()` | Updates progress tracker, Rx comparison, phase display |
| `_onExamComplete()` | Shows results, quality report, patient summary |
| `_applyCopilotOverride()` | Reads stepper values, sends to CV5000, records override |
| `_showScreen(name)` | Screen navigation (mode/intake/exam/results) |
| `_shareReport()` | Generates JSON report, copies to clipboard or downloads |

### 11.2 `cv5000-protocol.js` — Hardware Protocol

**Class:** `CV5000Protocol`

| Method | Params | Description |
|---|---|---|
| `listDevices(showAll)` | boolean | GET /devices — returns device array |
| `getDevice(deviceId)` | string | GET /devices/{id} |
| `acquireDevice(deviceId)` | string | POST acquire + start heartbeat |
| `releaseDevice()` | — | POST release + stop heartbeat |
| `sendHeartbeat()` | — | POST heartbeat (called every 15s) |
| `setChart(chartName, size, tab)` | string, number, string | Display chart on phoropter |
| `setPower(params)` | object | Set power + aux_lens |
| `setPowerWithPrevState(params)` | object | Set power with prev state for delta |
| `jccControl(action)` | string | JCC operation |
| `setPinhole()` | — | Activate pinhole lens |
| `setOccluder()` | — | Set occluder via menu |
| `resetPhoropter()` | — | Reset to 0/0/180 |
| `syncState(state)` | object | Sync internal state |
| `captureScreenshot()` | — | Get base64 JPEG of agent screen |
| `getState()` | — | Returns current machine state |
| `destroy()` | — | Stop heartbeat + release device |

### 11.3 `refraction-engine.js` — Clinical State Machine

**Class:** `RefractionEngine`

| Method | Description |
|---|---|
| `startExam(patientData)` | Initialise exam state, load AR/old Rx, begin phase A |
| `processResponse(intent)` | Route intent to current phase handler |
| `getCurrentPhase()` | Returns current phase ID |
| `getState()` | Returns full engine state (Rx, chart, phase, step count) |
| `getRx()` | Returns current prescription { OD, OS, pd } |
| `getSessionLog()` | Returns all phase transitions and decisions |

**Events emitted:**
- `phase-change`: `{ phase, name, question, intents, rationale }`
- `exam-complete`: `{ rx, flags, sessionLog }`
- `chart-change`: `{ chart, va }`
- `power-change`: `{ eye, sph, cyl, axis }`
- `jcc-flip`: `{ flip, timing }`

### 11.4 `ai-optometrist.js` — Voice & Conversation

**Class:** `AIOptometrist`

| Method | Description |
|---|---|
| `speak(text)` | Speak text via TTS (returns Promise) |
| `stopSpeaking()` | Cancel ongoing TTS |
| `startListening()` | Begin ASR capture |
| `stopListening()` | Stop ASR |
| `askQuestion(question, intents, phaseId)` | Full flow: speak → listen |
| `processPatientInput(input, isVoice)` | Classify intent, handle confidence |
| `classifyIntent(transcript, intents, phaseId)` | Score all intents, return best match |
| `greetPatient(name)` | Speak greeting |
| `announcePhase(name)` | Speak phase transition |
| `announcePrescription(rx)` | Speak final results |
| `getCapabilities()` | Check TTS/ASR availability |
| `exportSession()` | Export conversation log |

### 11.5 `mode-manager.js` — Persona Controller

**Class:** `ModeManager`

| Method | Description |
|---|---|
| `setMode(mode)` | Set active mode, toggle visibility, configure defaults |
| `isMode(mode)` | Check current mode |
| `translateIntentLabel(clinical)` | Translate clinical → friendly label |
| `updatePhaseProgress(phase)` | Update 5-step progress tracker |
| `markExamComplete()` | Mark all progress steps as completed |
| `startExamTimer()` | Start elapsed time counter |
| `stopExamTimer()` | Stop timer |
| `pauseExam() / resumeExam()` | Pause/resume with accurate timing |
| `getExamDuration()` | Get elapsed seconds (excluding pauses) |
| `updateConfidence(conf, intent, transcript)` | Update copilot confidence dashboard |
| `updateRxComparison(ar, current)` | Update AR vs Current Rx table |
| `recordOverride() / recordClarification()` | Track quality metrics |
| `getQualityReport()` | Return quality metrics object |
| `updateSelfTestChart(chartIndex, eye)` | Render Snellen line on screen |
| `showDuochromeChart()` | Render red/green chart |
| `showBinocularChart()` | Render binocular balance chart |
| `showComfortCheck() / hideComfortCheck()` | Show/hide comfort modal |
| `showPatientResults(rx, flags)` | Render patient-friendly results |
| `showCopilotResults(qualityReport)` | Render quality report |
| `generateShareableReport(data, rx, flags)` | Generate JSON report |

### 11.6 `optom-slm.js` — Statistical Learning Model

**Class:** `OptomSLM`

| Method | Description |
|---|---|
| `learnFromSession(sessionData)` | Ingest session: sequence, timing, steps, power, decisions |
| `validateSession(sessionData)` | Check against flag rules + statistical anomaly detection |
| `getModelSummary()` | Summary stats: videos analysed, timing, flag count |
| `getPhaseExpectations(phase)` | Expected timing, steps, power deltas for a phase |
| `getAllSessions()` | Return archived session summaries |
| `resetModel()` | Clear all learned data |
| `exportModel() / importModel()` | Export/import model JSON |

### 11.7 `video-analyzer.js` — Video Training

**Class:** `VideoAnalyzer`

| Method | Description |
|---|---|
| `loadVideo(url)` | Load video from URL into `<video>` element |
| `loadVideoFile(file)` | Load from File input |
| `analyzeVideo()` | Sample frames at 2s intervals (production: OCR) |
| `addAnnotation(timestamp, type, data)` | Add manual annotation to timeline |
| `removeAnnotation(index)` | Remove annotation |
| `submitToSLM(metadata)` | Validate + learn from annotated session |
| `validateOnly()` | Validate without learning |
| `reset()` | Clear all analysis state |

---

## 12. Configuration & Deployment

### 12.1 Project Structure

```
eyetest/
├── index.html              Main HTML (910 lines)
├── styles.css              All styles (2829 lines)
├── app.js                  Application controller (1434 lines)
├── cv5000-protocol.js      Hardware protocol (571 lines)
├── refraction-engine.js    Clinical state machine (1362 lines)
├── ai-optometrist.js       Voice & AI (574 lines)
├── mode-manager.js         Persona controller (630 lines)
├── optom-slm.js            Statistical learning model (479 lines)
├── video-analyzer.js       Video analysis (311 lines)
├── .gitignore              Excludes node_modules, logs
└── Logging_PhoropterUI/    Reference logging UI
```

### 12.2 Dependencies

**Runtime:** None — pure vanilla JS, no npm packages required at runtime.

**Development:**
- `jsdom` (dev dependency) — for headless DOM testing

### 12.3 Running the Application

**Local Development:**
```bash
# Any static HTTP server works
python3 -m http.server 8765
# Open http://localhost:8765 in Chrome/Edge
```

**Browser Requirements:**
- Chrome 80+ or Edge 80+ (required for Web Speech API)
- Microphone permission (for voice input)
- Speaker/headphone output (for voice output)

### 12.4 Configuration Options

All configuration is done through the intake form and mode selection. No config files needed.

**Intake Form Fields:**

| Field | Required | Default | Description |
|---|---|---|---|
| Patient Name | No | — | For greeting and report |
| Age | Yes | — | Used in fog calculation |
| AR Right SPH/CYL/AXIS | Yes | 0/0/180 | Auto-refractor reading |
| AR Left SPH/CYL/AXIS | Yes | 0/0/180 | Auto-refractor reading |
| Old Rx Right SPH/CYL/AXIS | No | — | Previous prescription |
| Old Rx Left SPH/CYL/AXIS | No | — | Previous prescription |
| PD | No | 63mm | Pupillary distance |
| Simulated Mode | No | true | Use simulated or real hardware |
| Phoropter ID | Conditional | — | Required for real hardware mode |
| Voice Enabled | No | true | Enable/disable TTS+ASR |

### 12.5 Broker Connection

For real hardware deployment:
1. Ensure the Windows agent is running on a machine connected to the CV-5000
2. Agent registers with the broker via WebSocket
3. Set `Simulated Mode` to unchecked in the intake form
4. Enter the Phoropter ID from the broker dashboard
5. Click "Connect" to acquire the device
6. Verify connection status shows "Connected"

---

## 13. Data & Privacy

### 13.1 Data Storage

| Data Type | Storage | Retention |
|---|---|---|
| Exam session data | In-memory only | Lost on page refresh |
| SLM learned patterns | localStorage | Until browser data cleared |
| Conversation logs | In-memory | Lost on page refresh |
| Exported session JSON | User's filesystem | User-controlled |
| Shareable reports | Clipboard / download | User-controlled |

### 13.2 Data Transmitted

| Destination | Data Sent | When |
|---|---|---|
| Broker API | Phoropter commands (power, chart, JCC) | During exam (real mode only) |
| Broker API | Device acquire/release/heartbeat | Connection lifecycle |
| No external servers | Patient data never leaves the browser | — |

### 13.3 Privacy Notes

- Patient data (name, age, prescription) exists only in the browser's memory
- No analytics or tracking is included
- Voice processing happens entirely in the browser (Web Speech API)
- No data is sent to any AI/ML cloud service
- The SLM model stored in localStorage contains only statistical patterns (timing, step counts), not patient-identifiable information

---

## 14. Glossary

| Term | Definition |
|---|---|
| **AR** | Auto-Refractor — machine measurement of eye's refractive error (objective, not subjective) |
| **Axis** | The angle (0–180°) of astigmatism correction in the lens |
| **BINO** | Binocular — both eyes open |
| **CYL** | Cylinder power — corrects astigmatism (measured in diopters) |
| **Duochrome** | Red/green test to verify sphere endpoint (RAM-GAP rule) |
| **Fogging** | Adding plus power to blur vision, relaxing accommodation before refraction |
| **GAP** | Green Add Plus — if green is clearer, add +0.25D SPH |
| **JCC** | Jackson Cross-Cylinder — technique for refining astigmatism axis and power |
| **OD** | Oculus Dexter — right eye |
| **OS** | Oculus Sinister — left eye |
| **PD** | Pupillary Distance — distance between pupils in mm |
| **RAM** | Red Add Minus — if red is clearer, add -0.25D SPH |
| **Rx** | Prescription |
| **SLM** | Statistical Learning Model — learns patterns from optometrist sessions |
| **Snellen** | Standard eye chart with letters of decreasing size |
| **SPH** | Sphere power — corrects myopia (negative) or hyperopia (positive) |
| **Subjective Refraction** | Eye test requiring patient responses (vs. objective auto-refractor) |
| **VA** | Visual Acuity — measured as Snellen fraction (e.g., 20/20) |

---

*This documentation covers the AI Eye Test System v1.0. For questions or contributions, contact the Lenskart Optometry Technology team.*
