class CANBus:
    """Simulates a CAN bus with arbitration and error handling."""

    # Class-level flag to suppress print output during bulk runs
    verbose = True

    def __init__(self):
        self.current_transmissions = []  # Tracks ongoing transmissions on the bus

    def _print(self, msg: str):
        """Print only if verbose mode is enabled."""
        if CANBus.verbose:
            print(msg)

    def send_frame(self, frame, ecu):
        """Place a frame on the CAN bus."""
        self.current_transmissions.append((frame, ecu))  # Add frame to the queue


    def handle_arbitration(self):
        error_found = False
        winner_frame, winner_ecu = self.current_transmissions[0]

        for frame, ecu in self.current_transmissions:
            # Check if IDs are identical, then compare DLC
            if frame['id'] == winner_frame['id']:
                # Compare DLC (dominant bit wins)
                for bit_a, bit_b in zip(frame['dlc'], winner_frame['dlc']):
                    if bit_a != bit_b:
                        if bit_a == '0' and bit_b == '1':
                            error_found = True
                            winner_frame, winner_ecu = frame, ecu #switch to atker winner frame and ecu
                        break
        
        return winner_frame, winner_ecu, error_found


    def resolve_collisions(self):
        """
        Handle collision between frames on the bus.
        
        CAN Bus-Off Attack collision model:
        - When same ID but different DLC: dominant bit (0) wins
        - Loser (victim, recessive DLC '0001') gets TEC += 8
        - Winner (attacker, dominant DLC '0000') transmits successfully, TEC -= 1
        - In Phase 1 (both Error-Active): rapid collision retransmissions
        - In Phase 2 (victim Error-Passive): single collision per periodic frame
        """
        if len(self.current_transmissions) > 1:
            self._print(f"[CANBus] Collision detected among {len(self.current_transmissions)} nodes.")

            # Determine winner by arbitration (dominant DLC wins when IDs match)
            winner_frame, winner_ecu, error_found = self.handle_arbitration()
            
            # Find the loser (the other ECU)
            loser_frame, loser_ecu = None, None
            for frame, ecu in self.current_transmissions:
                if ecu != winner_ecu:
                    loser_frame, loser_ecu = frame, ecu
                    break
            
            if error_found and loser_ecu:
                # Bus-Off Attack collision handling:
                # Phase 1 (both Error-Active): Both TECs increase
                # Phase 2 (victim Error-Passive): Only victim TEC increases
                
                # Loser (victim) always gets TEC += 8
                loser_ecu.increment_error_counter(is_transmit_error=True)
                self._print(f"[{loser_ecu.name}] Incremented Transmit Error Counter. TEC: {loser_ecu.transmit_error_counter}")
                
                # Winner (attacker) only gets TEC += 8 in Phase 1 (when loser is Error-Active)
                # In Phase 2, attacker doesn't increment (passive error flag doesn't cause error)
                if not loser_ecu.is_error_passive:
                    winner_ecu.increment_error_counter(is_transmit_error=True)
            
            # Winner transmits successfully, TEC -= 1
            self._print(f"[CANBus] Frame successfully transmitted: {winner_frame['id']} by {winner_ecu.name}")
            winner_ecu.decrement_error_counters()
            
            self.current_transmissions.clear()
            return winner_frame

        elif self.current_transmissions:
            frame, sender = self.current_transmissions.pop(0)
            self._print(f"[CANBus] Frame successfully transmitted: {frame['id']} by {sender.name}")
            sender.decrement_error_counters()
            return frame
        
    def receive_frame(self):
        """Retrieve and process the next frame."""
        if not self.current_transmissions:  # Check if there are frames to process
            return None
        return self.resolve_collisions()  # Resolve any collisions
