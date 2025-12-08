# CAN Bus-Off Attack Simulation

**Cyber-Physical Systems and IoT Security Course Project**  
*MSc in ICT for Internet and Multimedia — University of Padova*

---

## Overview

This repository simulates a **Bus-Off attack** on a Controller Area Network (CAN) bus. The attack exploits the CAN error-handling mechanism to force a victim ECU (Electronic Control Unit) into the Bus-Off state, effectively silencing it from the network.

The simulation demonstrates:
- CAN arbitration and collision behavior
- Transmit Error Counter (TEC) dynamics
- Phase 1 (Error-Active) and Phase 2 (Error-Passive) attack patterns
- Attack timing across different bus speeds (250, 500, 1000 kbps)

---

## Repository Structure

```
├── Simulation/
│   ├── main.py           # Main simulation entry point
│   ├── can_bus.py        # CAN bus model (arbitration, collisions)
│   ├── ecu.py            # Base ECU class (TEC, state management)
│   ├── victim_ecu.py     # Victim ECU (periodic transmissions)
│   ├── attacker_ecu.py   # Attacker ECU (pattern detection, attack)
│   ├── setup_logger.py   # JSON Lines logging utilities
│   └── attack_logs/      # Generated log files (after running)
│       ├── single_run.log
│       ├── attack_250kbps.log
│       ├── attack_500kbps.log
│       └── attack_1000kbps.log
├── Notebook/
│   └── attack_graphPlots.ipynb   # Analysis and visualization notebook
└── README.md             # This file
```

### Key Files

| File | Purpose |
|------|---------|
| `main.py` | Orchestrates simulation, runs trials, generates logs |
| `can_bus.py` | Simulates bus arbitration, collision resolution, error flags |
| `ecu.py` | Base class for ECU state (Error-Active → Error-Passive → Bus-Off) |
| `victim_ecu.py` | Sends periodic/preceded/non-periodic frames |
| `attacker_ecu.py` | Observes patterns, times attack frames |
| `attack_graphPlots.ipynb` | Loads logs, generates all plots, contains analysis |

---

## Requirements

- **Python 3.8+**
- **Dependencies**: `pandas`, `numpy`, `matplotlib`, `seaborn`

Install dependencies:
```bash
pip install pandas numpy matplotlib seaborn
```

For the notebook, also install:
```bash
pip install jupyter
```

---

## Running the Simulation

### Step 1: Generate Log Files

```bash
cd Simulation
python main.py
```

This runs:
- 1 detailed trial at 500 kbps → `single_run.log`
- 1000 trials each at 250, 500, 1000 kbps → `attack_*.log`

Runtime: ~30–60 seconds depending on hardware.

### Step 2: Visualize Results

Open the notebook:
```bash
cd Notebook
jupyter notebook attack_graphPlots.ipynb
```

Then: **Kernel → Run All**

---

## Log File Formats

All logs use **JSON Lines** format (one JSON object per line, `.log` extension).

### `single_run.log` — Detailed Timeline

Step-by-step record of one attack at 500 kbps.

| Field | Type | Description |
|-------|------|-------------|
| `time_ms` | float | Elapsed time in milliseconds |
| `victim_tec` | int | Victim Transmit Error Counter |
| `attacker_tec` | int | Attacker Transmit Error Counter |
| `victim_state` | str | `EA` (Error-Active), `EP` (Error-Passive), `BO` (Bus-Off) |
| `attacker_state` | str | Attacker state (usually stays `EA`) |
| `phase` | str | `analysis`, `attack_phase1`, or `attack_phase2` |

**Example line:**
```json
{"time_ms": 77.70, "victim_tec": 128, "attacker_tec": 105, "victim_state": "EP", "attacker_state": "EA", "phase": "attack_phase2"}
```

### `attack_*kbps.log` — Aggregated Trials

One row per trial (1000 rows per file).

| Field | Type | Description |
|-------|------|-------------|
| `bus_speed_kbps` | int | CAN bus speed (250, 500, or 1000) |
| `step_ms` | float | Time per simulation step |
| `time_to_error_passive_ms` | float | Time until victim TEC ≥ 128 |
| `time_to_bus_off_ms` | float | Time until victim TEC ≥ 256 |
| `victim_final_tec` | int | Victim TEC at end (256 if Bus-Off) |
| `attacker_final_tec` | int | Attacker TEC at end |
| `victim_bus_off` | int | 1 if attack succeeded, 0 otherwise |
| `trial` | int | Trial number (1–1000) |

**Example line:**
```json
{"bus_speed_kbps": 500, "step_ms": 0.222, "time_to_error_passive_ms": 8.10, "time_to_bus_off_ms": 84.15, "victim_final_tec": 256, "attacker_final_tec": 72, "victim_bus_off": 1, "trial": 1}
```

---

## Using the Notebook

### Changing Log File Locations

The notebook reads logs from `LOG_DIR`, defined in the **first code cell**:

```python
from pathlib import Path
import os

LOG_DIR = Path(os.getenv("ATTACK_LOG_DIR", Path.cwd().parent / "Simulation" / "attack_logs"))

FILES = {
    "single": LOG_DIR / "single_run.log",
    "250":    LOG_DIR / "attack_250kbps.log",
    "500":    LOG_DIR / "attack_500kbps.log",
    "1000":   LOG_DIR / "attack_1000kbps.log",
}
```

**To change the log directory:**
1. Edit `LOG_DIR` directly in the cell, OR
2. Set the environment variable `ATTACK_LOG_DIR` before launching Jupyter

### Plots Generated

1. **TEC vs Time** — Single attack trace showing victim/attacker TEC progression
2. **Phase 1 vs Phase 2** — Side-by-side comparison of staircase vs sawtooth patterns
3. **Time to Error-Passive** — Box plot across bus speeds
4. **Time to Bus-Off** — Box plot across bus speeds
5. **Success/Failure counts** — Bar charts per bus speed

---

## Troubleshooting

### "File not found" errors

**Cause**: Log files don't exist or `LOG_DIR` points to wrong location.

**Fix**:
1. Run `python Simulation/main.py` to generate logs
2. Verify files exist in `Simulation/attack_logs/`
3. Check `LOG_DIR` in the notebook points to correct path

### Empty or invalid logs

**Cause**: Simulation was interrupted or failed.

**Fix**:
1. Delete contents of `Simulation/attack_logs/`
2. Re-run `python main.py`

### Plotting errors (missing columns)

**Cause**: Log schema mismatch (old logs with different format).

**Fix**:
1. Regenerate logs with current `main.py`
2. Ensure notebook uses `pd.read_json(..., lines=True)` to load

### Notebook won't find files when run from different directory

**Cause**: Relative path resolution depends on working directory.

**Fix**: Use absolute path in `LOG_DIR`:
```python
LOG_DIR = Path(r"C:\full\path\to\Simulation\attack_logs")
```

---

## Attack Mechanics

### CAN Error States
| State | TEC Range | Behavior |
|-------|-----------|----------|
| Error-Active | 0–127 | Transmits Active Error Flag (disrupts others) |
| Error-Passive | 128–255 | Transmits Passive Error Flag (doesn't disrupt) |
| Bus-Off | ≥256 | ECU stops all communication |

### Attack Phases
1. **Pattern Analysis**: Attacker observes traffic to identify periodic frame timing
2. **Phase 1**: Attacker causes collisions; both TECs increase (+8 per collision)
3. **Phase 2**: After victim enters Error-Passive, its error flags no longer disrupt attacker; victim TEC continues rising while attacker TEC decreases

### TEC Dynamics
- **Collision (loser)**: TEC += 8
- **Successful transmission**: TEC -= 1
- **Phase 2 sawtooth**: +8 (collision) then −1, −1, −1... (successful TXs) = net +5 per cycle

---

## References

- Cho, K.-T., & Shin, K. G. (2016). *Error Handling of In-vehicle Networks Makes Them Vulnerable*. CCS '16.
- CAN Specification 2.0, Bosch (https://en.wikipedia.org/wiki/CAN_bus#Base_frame_format)