"""
Bardacle - A Metacognitive Layer for AI Agents

Watches agent session transcripts and maintains real-time session state
awareness, enabling agents to recover context after compaction or restart.
"""

from .bardacle import (
    __version__,
    Config,
    load_config,
    update_state,
    find_active_transcript,
    read_and_process_messages,
)

__all__ = [
    "__version__",
    "Config",
    "load_config",
    "update_state",
    "find_active_transcript",
    "read_and_process_messages",
]
