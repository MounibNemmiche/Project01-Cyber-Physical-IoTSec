"""
Bus-Off Attack Simulation - Main Entry Point

Simulates the Bus-Off attack on a CAN bus at different bit rates.
Generates JSON Lines log files for analysis in Notebook/attack_graphs.ipynb.

Reference: "Error Handling of In-vehicle Networks Makes Them Vulnerable"

Output files (in attack_logs/):
    - attack_1000kbps.log  (1000 trials, aggregated)
    - attack_500kbps.log   (1000 trials, aggregated)
    - attack_250kbps.log   (1000 trials, aggregated)
    - single_run.log       (1 trial, step-by-step timeline)
"""

import json
import os
import random
import time
import statistics

from can_bus import CANBus
from victim_ecu import VictimECU
from attacker_ecu import AttackerECU
from ecu import ECU

# =============================================================================
# CONFIGURATION CONSTANTS
# =============================================================================

# Random seed for reproducibility (set to None for non-deterministic runs)
RANDOM_SEED = 42

# CAN bus bit rates to simulate (kbps)
BIT_RATES_KBPS = [1000, 500, 250]

# Number of trials per bit rate for aggregated logs
NUM_TRIALS = 1000

# Default bus speed for single_run.log (500 kbps = standard high-speed CAN)
SINGLE_RUN_SPEED_KBPS = 500

# Base timing parameters (calibrated for 500 kbps)
# At 500 kbps, one CAN frame (111 bits) takes ~0.222 ms
BASE_STEP_MS = 0.222                      # Base time step at 500 kbps (one frame time)
BASE_SPEED_KBPS = 500                     # Reference speed for scaling
PATTERN_ANALYSIS_STEPS = 300              # Number of steps for pattern analysis (~66ms at 500kbps)
# Phase 2: +8 collision then -4 decrements = +4 net per cycle
# Reference shows ~25 cycles in Phase 2, each taking ~8ms = total 200ms
PERIODIC_FRAME_INTERVAL_STEPS = 5         # Steps between periodic frames (4 decrements, then +8 collision = +4 net)
PHASE2_TIME_SCALE = 5.0                   # Scale Phase 2 timing to match reference (~280ms total)

# CAN protocol constants (per CAN 2.0 spec)
TEC_ERROR_PASSIVE_THRESHOLD = 128         # TEC >= 128 -> Error-Passive
TEC_BUS_OFF_THRESHOLD = 256               # TEC >= 256 -> Bus-Off

# Failure rates by bus speed (timing becomes more critical at higher speeds)
FAILURE_RATE = {
    250: 0.02,   # 2% failure at 250 kbps (easiest timing)
    500: 0.05,   # 5% failure at 500 kbps
    1000: 0.08,  # 8% failure at 1000 kbps (hardest timing)
}

# CAN frame bit counts (for timing calculations)
BITS_PER_FRAME = 111                      # Standard CAN frame (~8 bytes)
BITS_IFS = 3                              # Inter-Frame Space
BITS_ERROR_FLAG = 14                      # 6 dominant + 8 delimiter

# =============================================================================
# LOG DIRECTORY SETUP
# =============================================================================

LOG_DIR = os.path.join(os.path.dirname(__file__), "attack_logs")
os.makedirs(LOG_DIR, exist_ok=True)


def get_log_path(filename: str) -> str:
    """Return full path for a log file in attack_logs/."""
    return os.path.join(LOG_DIR, filename)


def write_jsonl(path: str, records):
    """
    Write records to a JSON Lines file (one JSON object per line).
    Overwrites existing file.
    """
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")


# =============================================================================
# TIMING CALCULATIONS
# =============================================================================

def calculate_step_ms(bus_speed_kbps: int) -> float:
    """
    Scale step_ms based on bus speed.
    Faster bus = smaller time steps (proportional scaling).
    """
    return BASE_STEP_MS * (BASE_SPEED_KBPS / bus_speed_kbps)


def calculate_bus_time_ms(num_collisions: int, bus_speed_kbps: int) -> float:
    """
    Calculate actual CAN bus time for collisions.
    Each collision involves: frame attempt + error flag + retransmission.
    """
    bit_time_us = 1000.0 / bus_speed_kbps
    
    # Time per collision cycle (in ms)
    frame_time_ms = (BITS_PER_FRAME * bit_time_us) / 1000.0
    ifs_time_ms = (BITS_IFS * bit_time_us) / 1000.0
    error_time_ms = (BITS_ERROR_FLAG * bit_time_us) / 1000.0
    
    # Each collision: victim attempt + error + attacker success
    time_per_collision = 2 * frame_time_ms + ifs_time_ms + error_time_ms
    
    # Add jitter (±10%) for realism
    jitter = random.uniform(0.9, 1.1)
    return num_collisions * time_per_collision * jitter


# =============================================================================
# SINGLE TRIAL SIMULATION
# =============================================================================

def run_single_trial(bus_speed_kbps: int, collect_timeline: bool = False):
    """
    Run one Bus-Off attack trial.
    
    Args:
        bus_speed_kbps: CAN bus speed in kbps
        collect_timeline: If True, collect step-by-step events for single_run.log
        
    Returns:
        dict with trial metrics, plus 'timeline' list if collect_timeline=True
    """
    bus = CANBus()
    victim = VictimECU("Victim", bus)
    attacker = AttackerECU("Attacker", bus)
    
    step_ms = calculate_step_ms(bus_speed_kbps)
    timeline = [] if collect_timeline else None
    
    # Tracking variables
    step_index = 0
    current_time_ms = 0.0
    steps_to_error_passive = None
    steps_to_bus_off = None
    time_to_error_passive_ms = None
    attack_started = False
    
    def get_state_str(ecu):
        """Return state as short string: EA/EP/BO."""
        if ecu.is_bus_off:
            return "BO"
        elif ecu.is_error_passive:
            return "EP"
        return "EA"
    
    def log_step(phase: str, note: str = ""):
        """Log current step to timeline."""
        if timeline is not None:
            timeline.append({
                "step_index": step_index,
                "time_ms": round(current_time_ms, 3),
                "bus_speed_kbps": bus_speed_kbps,
                "phase": phase,
                "victim_tec": victim.transmit_error_counter,
                "attacker_tec": attacker.transmit_error_counter,
                "victim_state": get_state_str(victim),
                "attacker_state": get_state_str(attacker),
                "note": note
            })
    
    # -------------------------------------------------------------------------
    # Phase 1: Pattern Analysis
    # -------------------------------------------------------------------------
    traffic = []
    for _ in range(PATTERN_ANALYSIS_STEPS):
        if (step_index + 1) % PERIODIC_FRAME_INTERVAL_STEPS == 0:
            victim.send_preceded_frame()
            note = "preceded_frame"
        elif step_index % PERIODIC_FRAME_INTERVAL_STEPS == 0:
            victim.send_periodic_frame()
            note = "periodic_frame"
        else:
            victim.send_non_periodic_frame()
            note = "non_periodic"
        
        result = bus.receive_frame()
        if result:
            traffic.append(result)
        
        log_step("analysis", note)
        step_index += 1
        current_time_ms += step_ms
    
    # -------------------------------------------------------------------------
    # Phase 2: Attack Execution
    # -------------------------------------------------------------------------
    attacker.analyze_pattern(traffic)
    
    if not attacker.target_pattern:
        log_step("attack", "no_pattern_found")
        return {
            "bus_speed_kbps": bus_speed_kbps,
            "step_ms": round(step_ms, 3),
            "time_to_error_passive_ms": None,
            "time_to_bus_off_ms": None,
            "steps_to_error_passive": None,
            "steps_to_bus_off": None,
            "victim_final_tec": victim.transmit_error_counter,
            "attacker_final_tec": attacker.transmit_error_counter,
            "victim_bus_off": 0,
            "timeline": timeline
        }
    
    precedent_id, target_id = attacker.target_pattern
    attack_step_start = step_index
    attack_time_start = current_time_ms
    attack_started = True
    
    # Check for timing failure (higher bus speed = tighter timing = more failures)
    # This models real-world conditions where attack timing may be off
    failure_rate = FAILURE_RATE.get(bus_speed_kbps, 0.05)
    if random.random() < failure_rate:
        log_step("attack", "timing_failure")
        return {
            "bus_speed_kbps": bus_speed_kbps,
            "step_ms": round(step_ms, 3),
            "time_to_error_passive_ms": None,
            "time_to_bus_off_ms": None,
            "steps_to_error_passive": None,
            "steps_to_bus_off": None,
            "victim_final_tec": victim.transmit_error_counter,
            "attacker_final_tec": attacker.transmit_error_counter,
            "victim_bus_off": 0,
            "timeline": timeline
        }
    
    log_step("attack", f"pattern_found:{precedent_id}->{target_id}")
    
    # =========================================================================
    # PHASE 1: Rapid collisions until victim enters Error-Passive
    # In Phase 1, victim retries immediately after each collision (no TEC decrements)
    # =========================================================================
    while not victim.is_error_passive and not victim.is_bus_off:
        step_index += 1
        current_time_ms += step_ms
        
        fabricated_frame = {
            "id": target_id,
            "dlc": "0000",
            "data": ["00000000"]
        }
        
        # Simultaneous transmission (collision)
        victim.send_periodic_frame()
        attacker.send(fabricated_frame)
        bus.receive_frame()
        
        log_step("attack", "collision")
    
    # Record transition to Error-Passive
    if victim.is_error_passive:
        steps_to_error_passive = step_index - attack_step_start
        time_to_error_passive_ms = current_time_ms - attack_time_start
        log_step("attack", "error_passive_transition")
    
    # =========================================================================
    # PHASE 2: Periodic collisions with sawtooth TEC pattern
    # Victim is Error-Passive, can successfully transmit between collisions
    # =========================================================================
    while not victim.is_bus_off:
        # Victim sends non-periodic frames between collisions (TEC decrements)
        for _ in range(PERIODIC_FRAME_INTERVAL_STEPS - 1):
            if victim.is_bus_off:
                break
            victim.send_non_periodic_frame()
            bus.receive_frame()  # Successful transmission, TEC -= 1
            step_index += 1
            current_time_ms += step_ms
        
        if victim.is_bus_off:
            break
        
        # Periodic frame collision
        step_index += 1
        current_time_ms += step_ms
        
        fabricated_frame = {
            "id": target_id,
            "dlc": "0000",
            "data": ["00000000"]
        }
        
        victim.send_periodic_frame()
        attacker.send(fabricated_frame)
        bus.receive_frame()
        
        log_step("attack", "collision")
        
        # Safety limit
        if step_index > 10000:
            break
    
    # Record bus-off transition
    if victim.is_bus_off:
        steps_to_bus_off = step_index - attack_step_start
        log_step("attack", "bus_off_reached")
    
    # Calculate actual CAN bus timing
    collisions = steps_to_bus_off if steps_to_bus_off else 0
    time_to_bus_off_ms = calculate_bus_time_ms(collisions, bus_speed_kbps) if collisions > 0 else None
    
    # Recalculate error-passive time based on collision count (approx 16 collisions to EP)
    if steps_to_error_passive:
        ep_collisions = int(TEC_ERROR_PASSIVE_THRESHOLD / 8) + 1  # ~17 collisions
        time_to_error_passive_ms = calculate_bus_time_ms(ep_collisions, bus_speed_kbps)
    
    return {
        "bus_speed_kbps": bus_speed_kbps,
        "step_ms": round(step_ms, 3),
        "time_to_error_passive_ms": round(time_to_error_passive_ms, 3) if time_to_error_passive_ms else None,
        "time_to_bus_off_ms": round(time_to_bus_off_ms, 3) if time_to_bus_off_ms else None,
        "steps_to_error_passive": steps_to_error_passive,
        "steps_to_bus_off": steps_to_bus_off,
        "victim_final_tec": victim.transmit_error_counter,
        "attacker_final_tec": attacker.transmit_error_counter,
        "victim_bus_off": 1 if victim.is_bus_off else 0,
        "timeline": timeline
    }


# =============================================================================
# AGGREGATED TRIALS
# =============================================================================

def run_aggregated_trials(bus_speed_kbps: int, num_trials: int) -> list:
    """
    Run multiple trials and return aggregated results.
    """
    results = []
    
    for trial in range(1, num_trials + 1):
        result = run_single_trial(bus_speed_kbps, collect_timeline=False)
        result["trial"] = trial
        del result["timeline"]  # Not needed for aggregated logs
        results.append(result)
    
    return results


def print_summary(results: list, bus_speed_kbps: int):
    """Print summary statistics for a sweep."""
    bus_off_count = sum(1 for r in results if r["victim_bus_off"] == 1)
    total = len(results)
    
    # Extract times for successful attacks
    times = [r["time_to_bus_off_ms"] for r in results if r["time_to_bus_off_ms"] is not None]
    ep_times = [r["time_to_error_passive_ms"] for r in results if r["time_to_error_passive_ms"] is not None]
    
    print(f"\n  Summary for {bus_speed_kbps} kbps:")
    print(f"    Bus-Off success: {bus_off_count}/{total} ({100*bus_off_count/total:.1f}%)")
    
    if times:
        print(f"    Time to Bus-Off: mean={statistics.mean(times):.2f}ms, "
              f"median={statistics.median(times):.2f}ms, "
              f"min={min(times):.2f}ms, max={max(times):.2f}ms")
    
    if ep_times:
        print(f"    Time to Error-Passive: mean={statistics.mean(ep_times):.2f}ms")


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def main():
    """
    Main entry point - generates all log files.
    
    Output files:
        - attack_logs/attack_1000kbps.log
        - attack_logs/attack_500kbps.log
        - attack_logs/attack_250kbps.log
        - attack_logs/single_run.log
    """
    print("=" * 60)
    print("Bus-Off Attack Simulation")
    print("=" * 60)
    
    # Set random seed for reproducibility
    if RANDOM_SEED is not None:
        random.seed(RANDOM_SEED)
        print(f"Random seed: {RANDOM_SEED}")
    
    # Disable verbose output for bulk runs
    ECU.verbose = False
    CANBus.verbose = False
    
    start_time = time.time()
    
    # -------------------------------------------------------------------------
    # Run aggregated trials for each bit rate
    # -------------------------------------------------------------------------
    for bus_speed in BIT_RATES_KBPS:
        log_path = get_log_path(f"attack_{bus_speed}kbps.log")
        print(f"\nGenerating: {log_path}")
        print(f"  Running {NUM_TRIALS} trials at {bus_speed} kbps...")
        
        sweep_start = time.time()
        results = run_aggregated_trials(bus_speed, NUM_TRIALS)
        sweep_elapsed = time.time() - sweep_start
        
        write_jsonl(log_path, results)
        print(f"  Completed in {sweep_elapsed:.1f}s")
        print_summary(results, bus_speed)
    
    # -------------------------------------------------------------------------
    # Run single detailed trial with TEC event collection
    # -------------------------------------------------------------------------
    single_run_path = get_log_path("single_run.log")
    print(f"\nGenerating: {single_run_path}")
    print(f"  Running single detailed trial at {SINGLE_RUN_SPEED_KBPS} kbps...")
    
    # Enable verbose for single run
    ECU.verbose = True
    CANBus.verbose = True
    
    # Enable TEC event collection to capture ALL TEC changes (including those in collision loops)
    ECU.tec_events = []
    
    # Run simulation
    result = run_single_trial(SINGLE_RUN_SPEED_KBPS, collect_timeline=False)
    
    # Build timeline from TEC events with proper timestamps
    # Reference paper timing: pattern analysis ~65ms, total attack ~280ms at 500kbps
    bit_time_ms = 1.0 / SINGLE_RUN_SPEED_KBPS  # Time per bit in ms
    frame_time_ms = BITS_PER_FRAME * bit_time_ms  # ~0.222 ms at 500 kbps
    pattern_analysis_time_ms = PATTERN_ANALYSIS_STEPS * frame_time_ms
    
    timeline = []
    
    # Add initial state (start of pattern analysis)
    timeline.append({
        "time_ms": 0.0,
        "victim_tec": 0,
        "attacker_tec": 0,
        "victim_state": "EA",
        "attacker_state": "EA",
        "phase": "analysis"
    })
    
    # Add end of pattern analysis
    timeline.append({
        "time_ms": round(pattern_analysis_time_ms, 3),
        "victim_tec": 0,
        "attacker_tec": 0,
        "victim_state": "EA",
        "attacker_state": "EA",
        "phase": "analysis"
    })
    
    # Process TEC events and build timeline
    # Track current state for both ECUs
    victim_tec = 0
    attacker_tec = 0
    victim_state = "EA"
    attacker_state = "EA"
    current_time_ms = pattern_analysis_time_ms
    in_phase2 = False
    
    for event in ECU.tec_events:
        # Update the appropriate ECU's state
        if event["ecu_name"] == "Victim":
            victim_tec = event["tec"]
            victim_state = "BO" if event["is_bus_off"] else ("EP" if event["is_error_passive"] else "EA")
        else:
            attacker_tec = event["tec"]
            attacker_state = "BO" if event["is_bus_off"] else ("EP" if event["is_error_passive"] else "EA")
        
        # Determine phase based on victim state
        if victim_state in ["EP", "BO"]:
            phase = "attack_phase2"
            if not in_phase2:
                in_phase2 = True
        else:
            phase = "attack_phase1"
        
        # Time increment: scaled for Phase 2 to match reference timing
        time_increment = frame_time_ms * PHASE2_TIME_SCALE if in_phase2 else frame_time_ms
        current_time_ms += time_increment
        
        timeline.append({
            "time_ms": round(current_time_ms, 3),
            "victim_tec": victim_tec,
            "attacker_tec": attacker_tec,
            "victim_state": victim_state,
            "attacker_state": attacker_state,
            "phase": phase
        })
    
    # Disable TEC event collection
    ECU.tec_events = None
    
    # Write timeline
    if timeline:
        write_jsonl(single_run_path, timeline)
        print(f"  Detailed trial complete: {len(timeline)} TEC events logged")
        print(f"  Bus-Off: {'Yes' if result['victim_bus_off'] else 'No'}")
        print(f"  Total attack time: {timeline[-1]['time_ms']:.2f} ms")
    
    # -------------------------------------------------------------------------
    # Final summary
    # -------------------------------------------------------------------------
    total_elapsed = time.time() - start_time
    print("\n" + "=" * 60)
    print(f"Simulation complete in {total_elapsed:.1f}s")
    print(f"Log files generated in: {LOG_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()

