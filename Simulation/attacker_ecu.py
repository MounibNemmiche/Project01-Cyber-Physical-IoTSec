from ecu import ECU

class AttackerECU(ECU):
    def __init__(self, name, bus):
        super().__init__(name, bus)
        self.observed_patterns = {}  # Tracks periodic messages and precedents
        self.target_pattern = None  # Stores identified target pattern (if found)

    def analyze_pattern(self, traffic):
        """Identify a pattern of periodic messages preceded by a specific message."""
        potential_patterns = {}

        for i in range(len(traffic) - 1):
            # Extract current and next frames
            current_frame = traffic[i]
            next_frame = traffic[i + 1]

            # Check if the next frame is periodic
            next_id = next_frame['id']
            if next_id not in potential_patterns:
                potential_patterns[next_id] = {}

            # Increment the count of this current_frame -> next_frame sequence
            current_id = current_frame['id']
            if current_id not in potential_patterns[next_id]:
                potential_patterns[next_id][current_id] = 0

            potential_patterns[next_id][current_id] += 1

        # Find the most frequent precedents for the periodic message
        target_pattern = None
        max_count = 0

        for periodic_id, precedents in potential_patterns.items():
            for precedent_id, count in precedents.items():
                if count > max_count:
                    max_count = count
                    target_pattern = (precedent_id, periodic_id)

        # Assign the identified pattern if it is consistent
        if target_pattern and max_count > 1:  # Require the pattern to appear at least twice
            self.target_pattern = target_pattern
            precedent_id, periodic_id = target_pattern
            self._print(f"\n[Attacker] Identified pattern: Precedent ID {precedent_id} followed by Periodic ID {periodic_id}\n")
        else:
            self._print("\n[Attacker] No valid pattern identified.\n")

    def execute_attack(self, victim):
        """Execute the Bus-Off attack by exploiting arbitration."""
        if not self.target_pattern:
            self._print(f"[{self.name}] No pattern identified, no attack launched.")
            return

        precedent_id, target_id = self.target_pattern

        """Tx parameters"""
        current_time_ms = 0
        step = 100
        periodic_frame_interval = 500

        while not victim.is_bus_off:
            """Victim normal Tx behaviour"""
            if (current_time_ms + step) % periodic_frame_interval == 0:
                victim.send_preceded_frame()  # Send the preceded frame
            else:
                victim.send_non_periodic_frame()  # Send a non-periodic frame

            # Attacker listens for the precedent frame
            frame = self.bus.receive_frame()

            if frame and frame["id"] == precedent_id:
                self._print(f"\n[{self.name}] Detected preceded frame: {precedent_id}. Preparing attack frame.\n")

                # Fabricate the attack frame with a dominant DLC
                fabricated_frame = {
                    "id": target_id,
                    "dlc": "0000",
                    "data": frame["data"]
                }

                # Reach the time on which victim periodic transmission is planned
                current_time_ms += step
                
                # Simultaneous transmission of victim's and attacker's messages
                victim.send_periodic_frame()
                self.send(fabricated_frame)

                # Resolve collisions using the CAN bus logic
                self.bus.receive_frame()

            current_time_ms += step 
