"""
Logging utilities for Bus-Off attack simulation.
Outputs JSON Lines format for easy parsing with pandas.read_json(lines=True).
"""

import json
import os

# Ensure attack_logs directory exists
LOG_DIR = os.path.join(os.path.dirname(__file__), "attack_logs")
os.makedirs(LOG_DIR, exist_ok=True)


class JSONLinesLogger:
    """Simple logger that writes JSON Lines (one JSON object per line)."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._file = None

    def open(self, mode: str = "w"):
        """Open log file. Use 'w' to overwrite, 'a' to append."""
        self._file = open(self.filepath, mode, encoding="utf-8")

    def close(self):
        """Close the log file."""
        if self._file:
            self._file.close()
            self._file = None

    def log(self, data: dict):
        """Write a single JSON object as one line."""
        if self._file:
            self._file.write(json.dumps(data) + "\n")

    def __enter__(self):
        self.open("w")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


def get_log_path(filename: str) -> str:
    """Return full path for a log file in attack_logs/."""
    return os.path.join(LOG_DIR, filename)

