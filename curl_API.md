# 📡 Phoropter API Reference (Preprod)

This document provides complete `curl` commands for controlling the TOPCON phoropter remotely via the preprod broker.

**Base URL:** `https://rajasthan-royals.preprod.lenskart.com`
**Phoropter ID:** `lkst1782-1`

---

## 🔒 Device Management (Multi-Brain)

Before sending any phoropter commands, a Brain UI must **discover** available devices and **acquire** exclusive access.

### What is a Brain ID?

A `brain_id` is a **unique identifier** for each Brain UI (client application) that controls a TOPCON device. It is used to:

1. **Acquire** exclusive ownership of a device (only one brain can control a device at a time)
2. **Release** the device when done
3. **Keep the lock alive** via periodic heartbeats (auto-releases after 60s of silence)
4. **Reject** other brains from taking over your device

**Naming Convention:** Use any unique string — e.g. `brain_01`, `clinic_delhi_01`, `dr_sharma`.

**Lifecycle Flow:**
```
Brain UI starts
   │
   ▼
GET /devices          ← find available TOPCONs
   │
   ▼
POST /acquire         ← lock device with your brain_id
   │
   ▼
POST /heartbeat       ← send every 15s to keep lock alive
   │
   ▼
POST /run-tests       ← send phoropter commands (only owner can)
POST /reset           
   │
   ▼
POST /release         ← done → unlock device for others
```

#### Complete Example (End-to-End)
```bash
# 1. Find available devices
curl https://rajasthan-royals.preprod.lenskart.com/devices

# 2. Acquire a device (lock it to your brain)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}/acquire \
  -H "Content-Type: application/json" \
  -d '{"brain_id": "brain_01", "name": "Dr. Sharma Clinic"}'

# 3. Now you can send commands (only brain_01 can control this device)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/reset

curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{"test_cases": [{"case_id": 1, "right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90}, "left_eye": {"sph": -1.75, "cyl": -1.00, "axis": 180}}]}'

# 4. Keep sending heartbeat every 15s (or lock auto-releases after 300s)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"brain_id": "brain_01"}'

# 5. Release device when done
curl -X POST https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}/release \
  -H "Content-Type: application/json" \
  -d '{"brain_id": "brain_01"}'
```

> **If another brain tries to acquire the same device:**
> ```json
> {"status": "FAILED", "reason": "DEVICE_ALREADY_CONNECTED", "connected_brain": "brain_01"}
> ```

### List Available Devices
```bash
curl https://rajasthan-royals.preprod.lenskart.com/devices
```
Returns only `AVAILABLE` devices (ready to be acquired). To see all devices including `CONNECTED`, `OFFLINE`, `ERROR`:
```bash
curl https://rajasthan-royals.preprod.lenskart.com/devices?all=true
```

### Get Single Device
```bash
curl https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}
```

### Acquire Device (Lock for Exclusive Use)
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}/acquire \
  -H "Content-Type: application/json" \
  -d '{"brain_id": "brain_01", "name": "Dr. Sharma Clinic"}'
```

| Response | Meaning |
| :--- | :--- |
| `200 SUCCESS` | Device locked for this brain |
| `409 DEVICE_ALREADY_CONNECTED` | Another brain owns this device |
| `400 OFFLINE` | Agent not connected |

### Release Device
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}/release \
  -H "Content-Type: application/json" \
  -d '{"brain_id": "brain_01"}'
```

### Brain Heartbeat (Keep Lock Alive)
Send every 15s to prevent auto-release (timeout: 60s).
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/devices/{Phoropter-ID}/heartbeat \
  -H "Content-Type: application/json" \
  -d '{"brain_id": "brain_01"}'
```

### List Active Brains
```bash
curl https://rajasthan-royals.preprod.lenskart.com/brains
```

### View Connection Events (Audit Log)
```bash
curl https://rajasthan-royals.preprod.lenskart.com/events?limit=20
```

---

## 0. Preload AR / Lenso Values (Initial Reading)

Use this command to set the initial prescription values on the TOPCON from Auto-Refractor (AR) or Lensometer (Lenso) readings. This physically moves the phoropter to the specified values.

> [!IMPORTANT]
> **Always call `/reset` first** before preloading values to ensure the phoropter starts from a known 0/0/180 state.

```bash
# Step 1: Reset to zero
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/reset

# Step 2: Preload AR / Lenso values
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [
      {
        "case_id": 1,
        "aux_lens": "BINO",
        "right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90},
        "left_eye": {"sph": -1.75, "cyl": -1.00, "axis": 180}
      }
    ]
  }'
```

| Parameter | Description |
| :--- | :--- |
| **aux_lens** | Set to `"BINO"` for initial loading (both eyes visible) |
| **right_eye** | AR/Lenso values for right eye: `sph`, `cyl`, `axis` |
| **left_eye** | AR/Lenso values for left eye: `sph`, `cyl`, `axis` |

---

## 1. Vision Correction (Power Adjustments)

### Set Eyes & Occluder (Combined)
Use the `run-tests` endpoint to set power for both eyes and (optionally) an occluder in a single request.

```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [
      {
        "case_id": 1,
        "aux_lens": "AuxLensL",
        "right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90},
        "left_eye": {"sph": -1.75, "cyl": -1.00, "axis": 180}
      }
    ]
  }'
```

| Parameter | Description |
| :--- | :--- |
| **aux_lens** | (Optional) "AuxLensR" (occlude L), "AuxLensL" (occlude R), or "OFF" |
| **right_eye** / **left_eye** | Objects containing `sph`, `cyl`, and `axis` |

#### With Previous State (Recommended)
To ensure accurate click calculations, provide the **previous state** along with the target state. This is especially important when the agent's internal state might be out of sync.

```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [
      {
        "case_id": 1,
        "prev_aux_lens": "AuxLensL",
        "prev_right_eye": {"sph": 0.00, "cyl": 0.00, "axis": 180},
        "prev_left_eye": {"sph": 0.00, "cyl": 0.00, "axis": 180},
        "aux_lens": "AuxLensL",
        "right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90},
        "left_eye": {"sph": -1.75, "cyl": -1.00, "axis": 180}
      }
    ]
  }'
```

| Parameter | Description |
| :--- | :--- |
| **aux_lens** | (Optional) "AuxLensL" (JCC R mode), "AuxLensR" (JCC L mode), or "BINO" (binocular) |
| **right_eye** / **left_eye** | Objects containing `sph`, `cyl`, and `axis` |
| **prev_aux_lens** | (Optional) Previous occluder state - used as starting point for calculations |
| **prev_right_eye** / **prev_left_eye** | (Optional) Previous eye values - used as starting point for click calculations |

> **Note:** `aux_lens` values are mapped to JCC commands:
> - `"AuxLensL"` → JCC R mode (tests Right eye, occludes Left)
> - `"AuxLensR"` → JCC L mode (tests Left eye, occludes Right)
> - `"BINO"` → JCC BINO mode (binocular testing)

---

## 2. JCC & Auxiliary Controls
These commands utilize the `run-tests` endpoint to trigger specific UI interactions.

### JCC Operations (Handle, Toggle & Adjust)
| Action | Description |
| :--- | :--- |
| **JCC Handle** | Flip the JCC lens handle |
| **Power/Axis Switch** | Toggle between Power and Axis mode |
| **Increase** | Increase value in JCC mode |
| **Decrease** | Decrease value in JCC mode |

```bash
# JCC Handle
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "handle" }] }'

# Power/Axis Switch
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "power_axis_switch" }] }'

# Increase
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "increase" }] }'

# Decrease
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "decrease" }] }'
```

### JCC Eye Modes (L, R, BINO)
| Mode | Action |
| :--- | :--- |
| **R** | Test Right Eye (Occlude Left) |
| **L** | Test Left Eye (Occlude Right) |
| **BINO** | Binocular mode |

```bash
# Set mode to RIGHT
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "R" }] }'

# Set mode to LEFT
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "L" }] }'

# Set mode to BINO
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "jcc": "BINO" }] }'
```

---

## 3. Chart Controls
Individual commands for specific chart items on **Chart1** and **Chart2**.

### Chart 1: Visual Acuity & Tests
| Action | Item ID | Description |
| :--- | :--- | :--- |
| **echart_400** | chart_9 | E-Chart 400 |
| **snellen_chart_200_150** | chart_10 | Snellen 200/150 |
| **snellen_chart_100_90** | chart_11 | Snellen 100/90 |
| **snellen_chart_70_60_50** | chart_12 | Snellen 70/60/50 |
| **snellen_chart_40_30_25** | chart_13 | Snellen 40/30/25 |
| **snellen_chart_20_15_10** | chart_14 | Snellen 20/15/10 |
| **snellen_chart_20_20_20** | chart_15 | Snellen 20/20/20 |
| **snellen_chart_25_20_15** | chart_16 | Snellen 25/20/15 |
| **Duochrome** | chart_17 | Duochrome Test |
| **JCC Chart** | chart_19 | JCC Cross Cylinder Chart |

#### Individual Commands (Chart 1)

```bash
# echart_400
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_9"] } }] }'

# snellen_chart_200_150
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_10"] } }] }'

# snellen_chart_100_90
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_11"] } }] }'

# snellen_chart_70_60_50
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_12"] } }] }'

# snellen_chart_40_30_25
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_13"] } }] }'

# snellen_chart_20_15_10
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_14"] } }] }'

# snellen_chart_20_20_20
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_15"] } }] }'

# snellen_chart_25_20_15
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_16"] } }] }'

# Duochrome
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_17"] } }] }'

# JCC Chart
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_19"] } }] }'

# BINO Chart (chart_20)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_20"] } }] }'
```

### Chart 2: Miscellaneous
```bash
# Show chart_1, chart_2, and chart_3 from Chart2 tab
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{ "test_cases": [{ "chart": { "tab": "Chart2", "chart_items": ["chart_1", "chart_2", "chart_3"] } }] }'
```

### 3.1 Charts with VA (Size Selection)
You can now select specific optotypes/sizes for Snellen and E-Charts by providing the size value after the chart ID.

| Chart | Size Options |
| :--- | :--- |
| **chart_10** | 200, 150 |
| **chart_11** | 100, 80 |
| **chart_12** | 70, 60, 50 |
| **chart_13** | 40, 30, 25 |
| **chart_14** | 20, 15, 10 |
| **chart_15** | 20_1, 20_2, 20_3 |
| **chart_16** | 25, 20, 15 |
| **chart_20 (BINO)** | R, L |

#### Example: Show Snellen Chart 100/80 and select Size 100
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [
      { "chart": { "tab": "Chart1", "chart_items": ["chart_11", "100"] } }
    ]
  }'
```

#### Individual Commands for all VA Charts (Chart 1)

```bash
# chart_10 (200, 150)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_10", "200"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_10", "150"] } }] }'

# chart_11 (100, 80)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_11", "100"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_11", "80"] } }] }'

# chart_12 (70, 60, 50)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_12", "70"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_12", "60"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_12", "50"] } }] }'

# chart_13 (40, 30, 25)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_13", "40"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_13", "30"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_13", "25"] } }] }'

# chart_14 (20, 15, 10)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_14", "20"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_14", "15"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_14", "10"] } }] }'

# chart_15 (20_1, 20_2, 20_3) - Different columns for 20 VA
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_15", "20_1"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_15", "20_2"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_15", "20_3"] } }] }'

# chart_16 (25, 20, 15)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_16", "25"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_16", "20"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_16", "15"] } }] }'

# chart_20 (R, L selection)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_20", "R"] } }] }'
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests -H "Content-Type: application/json" -d '{ "test_cases": [{ "chart": { "tab": "Chart1", "chart_items": ["chart_20", "L"] } }] }'
```

---

### 3.2 Near Chart (Chart 5)
Switch to the Near Vision tab (Chart 5). This is required before adjusting **ADD** power.

```bash
curl -X POST "https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests" -H "Content-Type: application/json" -d '{"sessionId":"near_vision_test","phoropter_id":"CV-5000PC","test_cases":[{"case_id":1,"chart":{"tab":"Chart5","chart_items":["chart_5"]}}]}'
```

---

## 4. Specialized Lens States (Menu Shortcuts)

### Pinhole
Sets the pinhole via the software menu shortcuts (`Alt+V` sequence).
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/pinhole
```

### Occluder (Menu Shortcut)
Sets the occluder via the software menu shortcuts (`Alt+V` sequence).
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/occluder
```

---

## 5. Reset Operations

### Global Reset (To 0/0/180)
Resets all values (SPH, CYL, AXIS) to neutral and clears occluders.
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/reset
```

---

## 6. Internal State Synchronization

### Sync State (No Clicks)
Updates the agent's internal tracking of the phoropter state **without** triggering any physical interactions on the machine. This is useful for "telling" the agent the current starting point if it has drifted or if the brain knows the state better.

```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/sync-state \
  -H "Content-Type: application/json" \
  -d '{
    "right_eye": {"sph": -3.00, "cyl": -1.50, "axis": 45},
    "left_eye": {"sph": -2.50, "cyl": -1.25, "axis": 135},
    "aux_lens": "AuxLensR",
    "pd": 64.5
  }'
```

### Final Rx State Sync (Near Vision)
Sync the final state after Near Vision adjustments (including ADD) to the internal tracker.

```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/sync-state \
  -H "Content-Type: application/json" \
  -d '{
    "right_eye": { "sph": -2.00, "cyl": -1.00, "axis": 90, "add": 1.25 },
    "left_eye":  { "sph": -1.75, "cyl": -1.00, "axis": 180, "add": 1.25 },
    "aux_lens": "BINO",
    "pd": 64
  }'
```

---

## 7. Diagnostics & Verification

### Live Screenshot
Capture a live image of the agent's screen for visual verification. Returns a **raw base64-encoded JPEG string**.

```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/screenshot \
  -H "x-brain-id: brain_01"
```

**Response Example (Raw String):**
```text
/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL...
```

#### Technical Flow: How it works
This command uses a **request-response relay** to bridge the Brain (Web) and the Agent (Windows):

1. **Request (Brain → Broker)**: Brain sends a standard HTTP POST to the broker. The broker keeps this connection open (on "hold").
2. **Relay (Broker → Agent)**: Broker sends a WebSocket message to the Windows Agent with `action: "screenshot"`.
3. **Capture (Agent)**: The agent uses `pyautogui` to grab the screen, converts it to a **JPEG** (70% quality for speed), and encodes it to a **Base64 string**.
4. **Result (Agent → Broker)**: Agent sends the string back via WebSocket.
5. **Delivery (Broker → Brain)**: The broker returns the **raw string** directly as the response body.

**Frontend Usage (JavaScript):**
```javascript
// Display the image in a browser
const response = await fetch('/phoropter/lkst1782-1/screenshot', { method: 'POST' });
const base64Image = await response.text();
const imgElement = document.getElementById('screen-preview');
imgElement.src = "data:image/jpeg;base64," + base64Image;
```

---

---

## 7. Test Suite for State Management

These test cases demonstrate the dual-mode state management behavior.

### Test 1: Reset and Set with Correct Previous State
```bash
# Reset to 0/0/180
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/reset

# Set values with correct prev_state (0/0/180 after reset)
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [{
      "case_id": 1,
      "prev_aux_lens": "BINO",
      "prev_right_eye": {"sph": 0.00, "cyl": 0.00, "axis": 180},
      "prev_left_eye": {"sph": 0.00, "cyl": 0.00, "axis": 180},
      "aux_lens": "AuxLensL",
      "right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90},
      "left_eye": {"sph": -1.75, "cyl": -1.00, "axis": 180}
    }]
  }'
```
**Expected:** Should move from 0/0/180 to target values.

### Test 2: Incremental Change with Previous State
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [{
      "case_id": 2,
      "prev_aux_lens": "AuxLensL",
      "prev_right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90},
      "prev_left_eye": {"sph": -1.75, "cyl": -1.00, "axis": 180},
      "aux_lens": "AuxLensR",
      "right_eye": {"sph": -3.00, "cyl": -1.50, "axis": 45},
      "left_eye": {"sph": -2.50, "cyl": -1.25, "axis": 135}
    }]
  }'
```
**Expected:** Should calculate and execute the difference.

### Test 3: No Change (prev == target)
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [{
      "case_id": 3,
      "prev_aux_lens": "AuxLensR",
      "prev_right_eye": {"sph": -3.00, "cyl": -1.50, "axis": 45},
      "prev_left_eye": {"sph": -2.50, "cyl": -1.25, "axis": 135},
      "aux_lens": "AuxLensR",
      "right_eye": {"sph": -3.00, "cyl": -1.50, "axis": 45},
      "left_eye": {"sph": -2.50, "cyl": -1.25, "axis": 135}
    }]
  }'
```
**Expected:** Should skip JCC click and execute 0 eye adjustments.

### Test 4: Change Only AuxLens
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [{
      "case_id": 4,
      "prev_aux_lens": "AuxLensR",
      "prev_right_eye": {"sph": -3.00, "cyl": -1.50, "axis": 45},
      "prev_left_eye": {"sph": -2.50, "cyl": -1.25, "axis": 135},
      "aux_lens": "BINO",
      "right_eye": {"sph": -3.00, "cyl": -1.50, "axis": 45},
      "left_eye": {"sph": -2.50, "cyl": -1.25, "axis": 135}
    }]
  }'
```
**Expected:** Should only click JCC BINO, no eye adjustments.

### Test 5: Without prev_state (Internal Tracking)
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [{
      "case_id": 5,
      "aux_lens": "AuxLensL",
      "right_eye": {"sph": -1.00, "cyl": -0.50, "axis": 180},
      "left_eye": {"sph": -1.00, "cyl": -0.50, "axis": 180}
    }]
  }'
```
**Expected:** Uses agent's internal state tracking (may be inaccurate).

### Test 6: Partial Previous State
```bash
curl -X POST https://rajasthan-royals.preprod.lenskart.com/phoropter/{Phoropter-ID}/run-tests \
  -H "Content-Type: application/json" \
  -d '{
    "test_cases": [{
      "case_id": 6,
      "prev_right_eye": {"sph": -1.00, "cyl": -0.50, "axis": 180},
      "right_eye": {"sph": -2.00, "cyl": -1.00, "axis": 90},
      "left_eye": {"sph": -1.50, "cyl": -0.75, "axis": 180}
    }]
  }'
```
**Expected:** Right eye uses prev_state, left eye uses internal tracking.
