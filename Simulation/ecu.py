class ECU:
    """Base class for CAN bus Electronic Control Units."""

    # Class-level flag to suppress print output during bulk runs
    verbose = True
    
    # Class-level list to collect TEC events for single_run.log
    # Set to a list to enable collection, None to disable
    tec_events = None

    def __init__(self, name, bus):
        self.name = name
        self.bus = bus
        self.transmit_error_counter = 0
        self.is_error_passive = False
        self.is_bus_off = False

    def get_state(self) -> dict:
        """Return current ECU state as a dictionary."""
        return {
            "name": self.name,
            "tec": self.transmit_error_counter,
            "is_error_passive": self.is_error_passive,
            "is_bus_off": self.is_bus_off,
        }

    def _print(self, msg: str):
        """Print only if verbose mode is enabled."""
        if ECU.verbose:
            print(msg)

    def send(self, frame):
        """Transmit a CAN frame."""
        if self.is_bus_off:
            self._print(f"[{self.name}] Cannot send; ECU is in Bus-off state!")
            return

        self._print(f"[{self.name}] Sending frame: {frame}")
        self.bus.send_frame(frame, self)

    def listen(self):
        """Listen for a frame on the CAN bus."""
        if self.is_bus_off:
            return

        result = self.bus.receive_frame()
        if result:
            frame, sender = result
            if sender != self:
                self._print(f"[{self.name}] Received frame: {frame}")

    def increment_error_counter(self, is_transmit_error):
        """Increment the error counter by 8 for transmit errors (per CAN spec)."""
        increment = 8 if is_transmit_error else 0
        self.transmit_error_counter += increment

        self._print(f"[{self.name}] Incremented {'Transmit' if is_transmit_error else 'Receive'} Error Counter. "
                    f"TEC: {self.transmit_error_counter}")

        if not self.is_error_passive and self.transmit_error_counter > 127:
            self.is_error_passive = True
            self._print(f"[{self.name}] Entered Error-Passive state.")
        if self.transmit_error_counter > 255:
            self.is_bus_off = True
            self._print(f"[{self.name}] Entered Bus-Off state!")
        
        # Log TEC event if collection is enabled
        if ECU.tec_events is not None:
            ECU.tec_events.append({
                "ecu_name": self.name,
                "tec": self.transmit_error_counter,
                "is_error_passive": self.is_error_passive,
                "is_bus_off": self.is_bus_off,
            })

    def decrement_error_counters(self):
        """Reduce TEC by 1 after successful transmission (per CAN spec)."""
        old_tec = self.transmit_error_counter
        self.transmit_error_counter = max(0, self.transmit_error_counter - 1)

        if self.is_error_passive and self.transmit_error_counter <= 127:
            self.is_error_passive = False
            self._print(f"[{self.name}] Entered Error-Active state.")
        
        # Log TEC event only if TEC actually changed (was > 0 before)
        if ECU.tec_events is not None and old_tec > 0:
            ECU.tec_events.append({
                "ecu_name": self.name,
                "tec": self.transmit_error_counter,
                "is_error_passive": self.is_error_passive,
                "is_bus_off": self.is_bus_off,
            })
