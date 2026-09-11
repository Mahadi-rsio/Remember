"""Memory engine package: delta detection + deterministic canonical updates."""

from app.memory.delta import DeltaResult, detect_delta
from app.memory.engine import MemoryUpdateResult, process_memory_delta
from app.memory.ids import normalize_message, normalize_messages
from app.memory.interrogative import is_interrogative
from app.memory.isolation import derive_isolation_keys
from app.memory.low_info import is_low_info_message

__all__ = [
    "DeltaResult",
    "MemoryUpdateResult",
    "detect_delta",
    "is_interrogative",
    "is_low_info_message",
    "normalize_message",
    "normalize_messages",
    "derive_isolation_keys",
    "process_memory_delta",
]
