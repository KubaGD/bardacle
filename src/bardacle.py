#!/usr/bin/env python3
"""
Bardacle - A Metacognitive Layer for AI Agents

Watches agent session transcripts and maintains real-time session state
awareness, enabling agents to recover context after compaction or restart.

v0.2.0 - P0 Reliability Fixes:
- Atomic file writes (prevent corruption on crash)
- State file backups (rotating, with JSON structured backup)
- Pre-flight health checks (skip unavailable providers)
- Graceful crash handling (emergency state save)

Usage:
    python -m bardacle start   # Start daemon
    python -m bardacle stop    # Stop daemon
    python -m bardacle status  # Check status
    python -m bardacle update  # Force immediate update
    python -m bardacle test    # Test components
    python -m bardacle recover # Recover from backup
"""

import os
import sys
import json
import time
import signal
import hashlib
import argparse
import logging
import shutil
import atexit
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    import requests
except ImportError:
    print("Error: requests library required. Run: pip install requests")
    sys.exit(1)

__version__ = "0.2.0"
__author__ = "Bob & Blair"

# =============================================================================
# GLOBAL STATE (for crash recovery)
# =============================================================================

LAST_KNOWN_STATE: Optional[str] = None
LAST_STATE_METADATA: Optional[Dict] = None

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class InferenceConfig:
    local_url: str = "http://localhost:1234"
    ollama_url: str = "http://localhost:11434"
    local_model_fast: str = "qwen2.5-coder-7b-instruct"
    local_model_smart: str = "qwen3-coder-30b-a3b-instruct"
    ollama_model: str = "llama3.2"
    groq_model: str = "llama-3.1-8b-instant"
    openai_model: str = "gpt-4o-mini"
    local_timeout: int = 15
    cloud_timeout: int = 30
    health_check_timeout: int = 2  # NEW: Quick health check timeout
    groq_api_key: str = ""
    openai_api_key: str = ""

@dataclass
class TranscriptConfig:
    dir: str = ""
    pattern: str = "*.jsonl"

@dataclass
class ProcessingConfig:
    max_messages: int = 100
    max_message_chars: int = 500
    max_tool_summary_chars: int = 100
    debounce_seconds: int = 5
    force_update_interval: int = 120
    poll_interval: int = 2

@dataclass
class OutputConfig:
    state_file: str = ""
    log_file: str = ""
    metrics_file: str = ""
    pid_file: str = ""
    backup_count: int = 5  # NEW: Number of backups to keep

@dataclass
class Config:
    inference: InferenceConfig = field(default_factory=InferenceConfig)
    transcripts: TranscriptConfig = field(default_factory=TranscriptConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    output: OutputConfig = field(default_factory=OutputConfig)


def load_config(config_path: Optional[Path] = None) -> Config:
    """Load configuration from file and environment."""
    config = Config()
    
    # Try to find config file
    if config_path is None:
        search_paths = [
            Path.cwd() / "config.yaml",
            Path.cwd() / "bardacle.yaml",
            Path.home() / ".config" / "bardacle" / "config.yaml",
            Path.home() / ".bardacle" / "config.yaml",
        ]
        for path in search_paths:
            if path.exists():
                config_path = path
                break
    
    # Load from file if found
    if config_path and config_path.exists():
        with open(config_path) as f:
            if YAML_AVAILABLE:
                data = yaml.safe_load(f)
            elif config_path.suffix == '.json':
                data = json.load(f)
            else:
                log("YAML not available, skipping config file", "WARN")
                data = None
            if data:
                if "inference" in data:
                    for k, v in data["inference"].items():
                        if hasattr(config.inference, k):
                            setattr(config.inference, k, v)
                if "transcripts" in data:
                    for k, v in data["transcripts"].items():
                        if hasattr(config.transcripts, k):
                            setattr(config.transcripts, k, v)
                if "processing" in data:
                    for k, v in data["processing"].items():
                        if hasattr(config.processing, k):
                            setattr(config.processing, k, v)
                if "output" in data:
                    for k, v in data["output"].items():
                        if hasattr(config.output, k):
                            setattr(config.output, k, v)
    
    # Override with environment variables
    config.inference.groq_api_key = os.getenv("GROQ_API_KEY", config.inference.groq_api_key)
    config.inference.openai_api_key = os.getenv("OPENAI_API_KEY", config.inference.openai_api_key)
    config.inference.local_url = os.getenv("BARDACLE_LOCAL_URL", config.inference.local_url)
    config.inference.ollama_url = os.getenv("BARDACLE_OLLAMA_URL", config.inference.ollama_url)
    
    if os.getenv("BARDACLE_TRANSCRIPTS_DIR"):
        config.transcripts.dir = os.getenv("BARDACLE_TRANSCRIPTS_DIR")
    if os.getenv("BARDACLE_STATE_FILE"):
        config.output.state_file = os.getenv("BARDACLE_STATE_FILE")
    
    # Expand paths
    if config.transcripts.dir:
        config.transcripts.dir = os.path.expanduser(config.transcripts.dir)
    if config.output.state_file:
        config.output.state_file = os.path.expanduser(config.output.state_file)
    if config.output.log_file:
        config.output.log_file = os.path.expanduser(config.output.log_file)
    if config.output.metrics_file:
        config.output.metrics_file = os.path.expanduser(config.output.metrics_file)
    if config.output.pid_file:
        config.output.pid_file = os.path.expanduser(config.output.pid_file)
    
    # Set defaults for output paths
    bardacle_dir = Path.home() / ".bardacle"
    if not config.output.log_file:
        config.output.log_file = str(bardacle_dir / "bardacle.log")
    if not config.output.metrics_file:
        config.output.metrics_file = str(bardacle_dir / "metrics.jsonl")
    if not config.output.pid_file:
        config.output.pid_file = str(bardacle_dir / "bardacle.pid")
    
    return config


# Global config (loaded at runtime)
CONFIG: Optional[Config] = None

# =============================================================================
# PROVIDER HEALTH TRACKING (NEW - P0 Fix #3)
# =============================================================================

class ProviderHealth:
    """Track provider availability to skip failed providers quickly."""
    
    def __init__(self):
        self.status: Dict[str, Dict] = {}
        self.check_interval = 60  # Recheck every 60s
    
    def is_available(self, provider: str) -> bool:
        """Quick check if provider is likely available."""
        status = self.status.get(provider, {})
        now = time.time()
        
        # If recently verified as available, skip check
        if status.get("available") and now - status.get("last_check", 0) < self.check_interval:
            return True
        
        # If recently failed multiple times, skip for cooldown
        failures = status.get("failures", 0)
        if failures >= 3:
            cooldown = min(300, 30 * failures)  # Max 5 min cooldown
            if now - status.get("last_check", 0) < cooldown:
                return False
        
        # Perform quick ping
        available = self._ping(provider)
        self.status[provider] = {
            "available": available,
            "last_check": now,
            "failures": 0 if available else failures + 1
        }
        return available
    
    def _ping(self, provider: str) -> bool:
        """Quick health check ping."""
        if not CONFIG:
            return False
        
        timeout = CONFIG.inference.health_check_timeout
        
        try:
            if provider == "local":
                r = requests.get(f"{CONFIG.inference.local_url}/v1/models", timeout=timeout)
                return r.status_code == 200
            elif provider == "ollama":
                r = requests.get(f"{CONFIG.inference.ollama_url}/api/tags", timeout=timeout)
                return r.status_code == 200
            elif provider == "groq":
                if not CONFIG.inference.groq_api_key:
                    return False
                # Just check if key is set, actual health is verified on use
                return True
            elif provider == "openai":
                if not CONFIG.inference.openai_api_key:
                    return False
                return True
            return False
        except:
            return False
    
    def mark_failed(self, provider: str):
        """Mark a provider as having just failed."""
        status = self.status.get(provider, {})
        self.status[provider] = {
            "available": False,
            "last_check": time.time(),
            "failures": status.get("failures", 0) + 1
        }
    
    def mark_success(self, provider: str):
        """Mark a provider as having just succeeded."""
        self.status[provider] = {
            "available": True,
            "last_check": time.time(),
            "failures": 0
        }


# Global health tracker
HEALTH = ProviderHealth()

# =============================================================================
# RATE LIMIT TRACKING
# =============================================================================

_rate_limit_state = {
    "groq_limited_until": 0,
    "groq_cooldown_seconds": 60
}

def is_groq_rate_limited() -> bool:
    return time.time() < _rate_limit_state["groq_limited_until"]

def mark_groq_rate_limited():
    _rate_limit_state["groq_limited_until"] = time.time() + _rate_limit_state["groq_cooldown_seconds"]
    log(f"Groq rate limited, skipping for {_rate_limit_state['groq_cooldown_seconds']}s")

def get_groq_cooldown_remaining() -> int:
    remaining = _rate_limit_state["groq_limited_until"] - time.time()
    return max(0, int(remaining))

# =============================================================================
# LOGGING
# =============================================================================

def log(message: str, level: str = "INFO"):
    """Log with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    
    if CONFIG and CONFIG.output.log_file:
        log_path = Path(CONFIG.output.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(log_line + "\n")


def log_metrics(metrics: Dict):
    """Log metrics to JSONL file."""
    if not CONFIG or not CONFIG.output.metrics_file:
        return
    metrics["timestamp"] = datetime.now().isoformat()
    metrics_path = Path(CONFIG.output.metrics_file)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    with open(metrics_path, "a") as f:
        f.write(json.dumps(metrics) + "\n")

# =============================================================================
# ATOMIC FILE OPERATIONS (NEW - P0 Fix #1)
# =============================================================================

def write_atomic(content: str, target_path: Path) -> bool:
    """Write file atomically using temp file + rename.
    
    This prevents corruption if the process is killed mid-write.
    On POSIX systems, rename is atomic within the same filesystem.
    """
    temp_path = target_path.with_suffix('.tmp')
    
    try:
        # Ensure parent directory exists
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temp file
        temp_path.write_text(content, encoding='utf-8')
        
        # Atomic rename (on POSIX)
        temp_path.rename(target_path)
        return True
        
    except Exception as e:
        log(f"Atomic write failed: {e}", "ERROR")
        # Clean up temp file if it exists
        if temp_path.exists():
            try:
                temp_path.unlink()
            except:
                pass
        return False


def write_atomic_json(data: Dict, target_path: Path) -> bool:
    """Write JSON atomically."""
    try:
        content = json.dumps(data, indent=2, default=str)
        return write_atomic(content, target_path)
    except Exception as e:
        log(f"Atomic JSON write failed: {e}", "ERROR")
        return False

# =============================================================================
# STATE BACKUP (NEW - P0 Fix #2)
# =============================================================================

def get_backup_dir() -> Path:
    """Get the backup directory path."""
    if CONFIG and CONFIG.output.state_file:
        return Path(CONFIG.output.state_file).parent / "session-history"
    return Path.home() / ".bardacle" / "session-history"


def backup_state(state_path: Path) -> Optional[Path]:
    """Create a backup of the current state file.
    
    Returns the path to the backup file, or None if backup failed.
    """
    if not state_path.exists():
        return None
    
    backup_dir = get_backup_dir()
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{state_path.stem}-{timestamp}.md"
    
    try:
        shutil.copy2(state_path, backup_path)
        log(f"Backed up state to {backup_path.name}")
        
        # Prune old backups
        max_backups = CONFIG.output.backup_count if CONFIG else 5
        prune_backups(backup_dir, state_path.stem, max_backups)
        
        return backup_path
    except Exception as e:
        log(f"Backup failed: {e}", "ERROR")
        return None


def prune_backups(backup_dir: Path, stem: str, max_count: int):
    """Remove old backups keeping only the most recent max_count."""
    try:
        backups = sorted(backup_dir.glob(f"{stem}-*.md"), key=lambda p: p.stat().st_mtime)
        for old in backups[:-max_count]:
            old.unlink()
            log(f"Pruned old backup: {old.name}")
    except Exception as e:
        log(f"Backup pruning error: {e}", "WARN")


def list_backups() -> List[Path]:
    """List available backup files."""
    backup_dir = get_backup_dir()
    if not backup_dir.exists():
        return []
    return sorted(backup_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)


def recover_from_backup(backup_path: Optional[Path] = None) -> bool:
    """Recover state from a backup file.
    
    If backup_path is None, uses the most recent backup.
    """
    if backup_path is None:
        backups = list_backups()
        if not backups:
            log("No backups available", "ERROR")
            return False
        backup_path = backups[0]
    
    if not backup_path.exists():
        log(f"Backup not found: {backup_path}", "ERROR")
        return False
    
    if not CONFIG or not CONFIG.output.state_file:
        log("No state file configured", "ERROR")
        return False
    
    state_path = Path(CONFIG.output.state_file)
    
    try:
        # Read backup content
        content = backup_path.read_text()
        
        # Write to state file atomically
        if write_atomic(content, state_path):
            log(f"Recovered state from {backup_path.name}")
            return True
        return False
    except Exception as e:
        log(f"Recovery failed: {e}", "ERROR")
        return False

# =============================================================================
# CRASH HANDLING (NEW - P0 Fix #4)
# =============================================================================

def save_emergency_state():
    """Save emergency state on crash.
    
    Called via atexit or signal handler when process is shutting down unexpectedly.
    Saves whatever state we have to an emergency file.
    """
    global LAST_KNOWN_STATE, LAST_STATE_METADATA
    
    if not LAST_KNOWN_STATE:
        return
    
    if not CONFIG or not CONFIG.output.state_file:
        return
    
    emergency_path = Path(CONFIG.output.state_file).parent / "emergency-state.md"
    
    try:
        metadata = LAST_STATE_METADATA or {}
        content = f"""# Emergency State Save

*Saved: {datetime.now().isoformat()}*
*Reason: Unexpected shutdown*
*Original model: {metadata.get('model', 'unknown')}*
*Original messages: {metadata.get('msg_count', 'unknown')}*

---

{LAST_KNOWN_STATE}
"""
        # Use simple write here (can't guarantee atomic in crash scenario)
        emergency_path.write_text(content)
        log("Emergency state saved", "WARN")
    except Exception as e:
        # Last resort: try to log the error
        try:
            print(f"[EMERGENCY] Failed to save state: {e}", file=sys.stderr)
        except:
            pass


def setup_crash_handlers():
    """Set up handlers for graceful shutdown and crash recovery."""
    
    def graceful_shutdown(signum, frame):
        """Handle SIGTERM/SIGINT gracefully."""
        log(f"Received signal {signum}, shutting down gracefully...")
        save_emergency_state()
        remove_pid()
        sys.exit(0)
    
    def handle_sighup(signum, frame):
        """Handle SIGHUP - reload config (future use)."""
        log("Received SIGHUP, would reload config...")
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, graceful_shutdown)
    signal.signal(signal.SIGINT, graceful_shutdown)
    
    # SIGHUP for future config reload
    if hasattr(signal, 'SIGHUP'):
        signal.signal(signal.SIGHUP, handle_sighup)
    
    # atexit for Python-level crashes
    atexit.register(save_emergency_state)


def check_emergency_state() -> Optional[Path]:
    """Check if emergency state file exists (indicates previous crash)."""
    if not CONFIG or not CONFIG.output.state_file:
        return None
    
    emergency_path = Path(CONFIG.output.state_file).parent / "emergency-state.md"
    if emergency_path.exists():
        return emergency_path
    return None

# =============================================================================
# PROMPTS
# =============================================================================

SYSTEM_PROMPT = """You are a Session Shepherd - a metacognitive assistant that maintains awareness of an ongoing AI agent session.

Analyze the conversation and tool usage to extract:

1. **Current Goal**: The primary objective being worked toward
2. **Active Tasks**: Specific tasks in progress (bullet list with status)
3. **Recent Decisions**: Key decisions made
4. **Blockers**: Anything preventing progress (or "None")
5. **Next Steps**: Immediate actions planned
6. **Key Context**: Important details (paths, IDs, names, technical specifics)

Guidelines:
- Be concise but complete
- Focus on actionable state, not history
- Capture all active threads if multi-tasking
- PRESERVE specific paths, IDs, and technical details
- Tool summaries (format: [tool] action → result) show what actually happened
- If idle, say "Session idle - awaiting input"

Output: Clean markdown with section headers. 2-4 bullets per section max."""

INCREMENTAL_PROMPT = """Update the existing session state with new information.

Current state:
{current_state}

New messages:
{new_messages}

Preserve relevant context, update goals/tasks/steps based on new messages.
Output complete updated state in the same format."""

# =============================================================================
# TOOL SUMMARIZATION
# =============================================================================

def summarize_tool_call(tool_name: str, arguments: Dict, result: Any) -> str:
    """Generate one-line summary of tool call and result."""
    max_chars = CONFIG.processing.max_tool_summary_chars if CONFIG else 100
    
    try:
        if tool_name == "exec":
            cmd = str(arguments.get("command", ""))[:60]
            if isinstance(result, dict):
                exit_code = result.get("exitCode", "?")
                status = "✓" if exit_code == 0 else f"✗ (exit {exit_code})"
            else:
                status = "done"
            return f"[exec] {cmd} → {status}"
        
        elif tool_name in ("Write", "write"):
            path = arguments.get("path", arguments.get("file_path", "?"))
            return f"[Write] {Path(path).name if path else '?'} → created"
        
        elif tool_name in ("Read", "read"):
            path = arguments.get("path", arguments.get("file_path", "?"))
            return f"[Read] {Path(path).name if path else '?'}"
        
        elif tool_name in ("Edit", "edit"):
            path = arguments.get("path", arguments.get("file_path", "?"))
            return f"[Edit] {Path(path).name if path else '?'} → modified"
        
        elif tool_name == "web_search":
            query = str(arguments.get("query", ""))[:40]
            count = len(result.get("results", [])) if isinstance(result, dict) else "?"
            return f"[search] '{query}' → {count} results"
        
        elif tool_name == "web_fetch":
            url = str(arguments.get("url", ""))[:50]
            return f"[fetch] {url}"
        
        else:
            return f"[{tool_name}] executed"
    
    except Exception:
        return f"[{tool_name}] (error summarizing)"

# =============================================================================
# TRANSCRIPT READING
# =============================================================================

def find_active_transcript() -> Optional[Path]:
    """Find the most recent active session transcript."""
    if not CONFIG or not CONFIG.transcripts.dir:
        return None
    
    transcript_dir = Path(CONFIG.transcripts.dir)
    if not transcript_dir.exists():
        return None
    
    files = list(transcript_dir.glob(CONFIG.transcripts.pattern))
    if not files:
        return None
    
    return max(files, key=lambda p: p.stat().st_mtime)


def read_and_process_messages(transcript_path: Path, max_messages: int = 100) -> List[Dict]:
    """Read and preprocess messages from transcript JSONL."""
    raw_entries = []
    pending_tools = {}
    
    try:
        with open(transcript_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    if entry.get("type") == "message" and "message" in entry:
                        raw_entries.append(entry["message"])
                    elif "role" in entry:
                        raw_entries.append(entry)
                except json.JSONDecodeError:
                    continue
    except Exception as e:
        log(f"Error reading transcript: {e}", "ERROR")
        return []
    
    processed = []
    max_chars = CONFIG.processing.max_message_chars if CONFIG else 500
    
    for msg in raw_entries[-max_messages:]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        
        if role == "toolResult":
            tool_id = msg.get("toolCallId", "")
            if tool_id in pending_tools:
                tool_name, arguments = pending_tools[tool_id]
                result_text = ""
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            result_text = block.get("text", "")[:200]
                            break
                summary = summarize_tool_call(tool_name, arguments, {"text": result_text})
                processed.append({"role": "tool", "content": summary})
                del pending_tools[tool_id]
            continue
        
        if isinstance(content, list):
            text_parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block.get("text", ""))
                    elif block.get("type") == "thinking":
                        thinking = block.get("thinking", "")[:80]
                        if thinking:
                            text_parts.append(f"[thinking: {thinking}...]")
                    elif block.get("type") in ("toolCall", "tool_use"):
                        tool_name = block.get("name", "unknown")
                        tool_id = block.get("id", "")
                        arguments = block.get("arguments", block.get("input", {}))
                        pending_tools[tool_id] = (tool_name, arguments)
                        text_parts.append(f"[calling {tool_name}...]")
                elif isinstance(block, str):
                    text_parts.append(block)
            content = "\n".join(text_parts)
        
        if len(content) > max_chars:
            content = content[:max_chars] + "... [truncated]"
        
        if content.strip():
            processed.append({"role": role, "content": content})
    
    return processed

# =============================================================================
# INFERENCE (Updated with health checks)
# =============================================================================

def try_local(model: str, messages: List[Dict], timeout: int) -> Optional[str]:
    """Try inference with local LLM server."""
    if not CONFIG:
        return None
    
    url = f"{CONFIG.inference.local_url}/v1/chat/completions"
    
    try:
        response = requests.post(
            url,
            json={"model": model, "messages": messages, "temperature": 0.3, "max_tokens": 1500},
            timeout=timeout
        )
        response.raise_for_status()
        HEALTH.mark_success("local")
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        log(f"Local LLM timeout ({model})", "WARN")
        HEALTH.mark_failed("local")
        return None
    except requests.exceptions.ConnectionError:
        log("Local LLM not reachable", "WARN")
        HEALTH.mark_failed("local")
        return None
    except Exception as e:
        log(f"Local LLM error: {e}", "ERROR")
        HEALTH.mark_failed("local")
        return None


def try_ollama(model: str, messages: List[Dict], timeout: int) -> Optional[str]:
    """Try inference with Ollama."""
    if not CONFIG:
        return None
    
    url = f"{CONFIG.inference.ollama_url}/api/chat"
    
    try:
        response = requests.post(
            url,
            json={"model": model, "messages": messages, "stream": False},
            timeout=timeout
        )
        response.raise_for_status()
        HEALTH.mark_success("ollama")
        return response.json()["message"]["content"]
    except requests.exceptions.Timeout:
        log(f"Ollama timeout ({model})", "WARN")
        HEALTH.mark_failed("ollama")
        return None
    except requests.exceptions.ConnectionError:
        log("Ollama not reachable", "WARN")
        HEALTH.mark_failed("ollama")
        return None
    except Exception as e:
        log(f"Ollama error: {e}", "ERROR")
        HEALTH.mark_failed("ollama")
        return None


def try_groq(messages: List[Dict], timeout: int) -> Optional[str]:
    """Try inference with Groq API."""
    if not CONFIG or not CONFIG.inference.groq_api_key:
        return None
    
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {CONFIG.inference.groq_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": CONFIG.inference.groq_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1500
            },
            timeout=timeout
        )
        response.raise_for_status()
        HEALTH.mark_success("groq")
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response.status_code == 429:
            mark_groq_rate_limited()
        log(f"Groq error: {e}", "ERROR")
        HEALTH.mark_failed("groq")
        return None
    except Exception as e:
        log(f"Groq error: {e}", "ERROR")
        HEALTH.mark_failed("groq")
        return None


def try_openai(messages: List[Dict], timeout: int) -> Optional[str]:
    """Try inference with OpenAI API."""
    if not CONFIG or not CONFIG.inference.openai_api_key:
        return None
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {CONFIG.inference.openai_api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": CONFIG.inference.openai_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1500
            },
            timeout=timeout
        )
        response.raise_for_status()
        HEALTH.mark_success("openai")
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"OpenAI error: {e}", "ERROR")
        HEALTH.mark_failed("openai")
        return None


def call_llm_with_fallback(prompt_messages: List[Dict]) -> Tuple[Optional[str], str]:
    """Call LLM with fallback chain and health-aware provider selection."""
    if not CONFIG:
        return None, "none"
    
    local_timeout = CONFIG.inference.local_timeout
    cloud_timeout = CONFIG.inference.cloud_timeout
    
    # 1. Local fast model (with health check)
    if HEALTH.is_available("local"):
        log("Trying local LLM...")
        result = try_local(CONFIG.inference.local_model_fast, prompt_messages, local_timeout)
        if result:
            return result, "local"
    else:
        log("Skipping local LLM (health check failed)")
    
    # 2. Ollama (with health check)
    if HEALTH.is_available("ollama"):
        log("Trying Ollama...")
        result = try_ollama(CONFIG.inference.ollama_model, prompt_messages, local_timeout)
        if result:
            return result, "ollama"
    else:
        log("Skipping Ollama (not available)")
    
    # 3. Groq (skip if rate limited or health failed)
    if is_groq_rate_limited():
        log(f"Skipping Groq (rate limited, {get_groq_cooldown_remaining()}s remaining)")
    elif HEALTH.is_available("groq"):
        log("Trying Groq...")
        result = try_groq(prompt_messages, cloud_timeout)
        if result:
            return result, "groq"
    
    # 4. OpenAI
    if HEALTH.is_available("openai"):
        log("Trying OpenAI...")
        result = try_openai(prompt_messages, cloud_timeout)
        if result:
            return result, "openai"
    
    # 5. Local smart model (last resort, skip health check)
    log("Trying local smart model (last resort)...")
    result = try_local(CONFIG.inference.local_model_smart, prompt_messages, local_timeout + 15)
    if result:
        return result, "local-smart"
    
    return None, "none"

# =============================================================================
# STATE GENERATION
# =============================================================================

def format_messages_for_prompt(messages: List[Dict]) -> str:
    """Format messages for LLM prompt."""
    formatted = []
    for msg in messages:
        role = msg["role"].upper()
        content = msg["content"]
        if role == "TOOL":
            formatted.append(content)
        else:
            formatted.append(f"**{role}**: {content}")
    return "\n\n".join(formatted)


def get_current_state() -> Optional[str]:
    """Read current state file if exists."""
    if not CONFIG or not CONFIG.output.state_file:
        return None
    
    state_path = Path(CONFIG.output.state_file)
    if state_path.exists():
        content = state_path.read_text()
        if "---" in content:
            parts = content.split("---", 2)
            if len(parts) > 2:
                return parts[2].strip()
    return None


def generate_state(messages: List[Dict], incremental: bool = True) -> Tuple[Optional[str], str, float]:
    """Generate session state from messages."""
    start_time = time.time()
    messages_text = format_messages_for_prompt(messages)
    
    if incremental:
        current_state = get_current_state()
        if current_state and len(messages) > 10:
            recent = messages[-15:]
            recent_text = format_messages_for_prompt(recent)
            prompt_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": INCREMENTAL_PROMPT.format(
                    current_state=current_state, new_messages=recent_text
                )}
            ]
        else:
            prompt_messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Analyze and generate session state:\n\n{messages_text}"}
            ]
    else:
        prompt_messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze and generate session state:\n\n{messages_text}"}
        ]
    
    result, model = call_llm_with_fallback(prompt_messages)
    latency = time.time() - start_time
    return result, model, latency


def write_state_file(state_content: str, model: str, latency: float, msg_count: int):
    """Write session state to file with backup and atomic write."""
    global LAST_KNOWN_STATE, LAST_STATE_METADATA
    
    if not CONFIG or not CONFIG.output.state_file:
        return
    
    state_path = Path(CONFIG.output.state_file)
    
    # Create backup of existing state
    backup_state(state_path)
    
    # Prepare content
    header = f"""# Session State

*Auto-generated at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*Model: {model} | Latency: {latency:.1f}s | Messages: {msg_count}*

---

"""
    full_content = header + state_content
    
    # Store for crash recovery
    LAST_KNOWN_STATE = state_content
    LAST_STATE_METADATA = {"model": model, "latency": latency, "msg_count": msg_count}
    
    # Atomic write
    if write_atomic(full_content, state_path):
        log(f"Updated state ({len(state_content)} chars, {model}, {latency:.1f}s)")
        
        # Also write structured JSON backup
        json_path = state_path.with_suffix('.json')
        write_atomic_json({
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "latency": latency,
            "msg_count": msg_count,
            "content": state_content
        }, json_path)
    else:
        log("Failed to write state file", "ERROR")

# =============================================================================
# DAEMON
# =============================================================================

def get_pid() -> Optional[int]:
    if not CONFIG or not CONFIG.output.pid_file:
        return None
    pid_path = Path(CONFIG.output.pid_file)
    if pid_path.exists():
        try:
            return int(pid_path.read_text().strip())
        except:
            return None
    return None


def is_running() -> bool:
    pid = get_pid()
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write_pid():
    if CONFIG and CONFIG.output.pid_file:
        pid_path = Path(CONFIG.output.pid_file)
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text(str(os.getpid()))


def remove_pid():
    if CONFIG and CONFIG.output.pid_file:
        pid_path = Path(CONFIG.output.pid_file)
        if pid_path.exists():
            pid_path.unlink()


def get_file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except:
        return ""


def update_state(force_full: bool = False) -> bool:
    """Perform a state update."""
    transcript = find_active_transcript()
    if not transcript:
        log("No transcript found", "WARN")
        return False
    
    max_msgs = CONFIG.processing.max_messages if CONFIG else 100
    messages = read_and_process_messages(transcript, max_msgs)
    
    if not messages:
        log("No messages to analyze")
        return False
    
    log(f"Analyzing {len(messages)} messages...")
    state, model, latency = generate_state(messages, incremental=not force_full)
    
    if not state:
        log("Failed to generate state", "ERROR")
        return False
    
    write_state_file(state, model, latency, len(messages))
    log_metrics({"action": "update", "messages": len(messages), "model": model, "latency": latency})
    return True


def daemon_loop():
    """Main daemon loop."""
    log(f"Bardacle v{__version__} starting...")
    
    # Set up crash handlers
    setup_crash_handlers()
    
    # Write PID file
    write_pid()
    
    # Check for emergency state from previous crash
    emergency = check_emergency_state()
    if emergency:
        log(f"Found emergency state from previous crash: {emergency}", "WARN")
        log("Consider running 'bardacle recover' to restore")
    
    last_hash = ""
    last_update = 0
    last_change = 0
    
    while True:
        try:
            transcript = find_active_transcript()
            if transcript:
                current_hash = get_file_hash(transcript)
                now = time.time()
                
                if current_hash != last_hash:
                    last_hash = current_hash
                    last_change = now
                
                debounce = CONFIG.processing.debounce_seconds if CONFIG else 5
                force_interval = CONFIG.processing.force_update_interval if CONFIG else 120
                
                should_update = False
                if last_change > last_update and (now - last_change) >= debounce:
                    should_update = True
                if (now - last_update) >= force_interval:
                    should_update = True
                
                if should_update:
                    if update_state():
                        last_update = now
            
            poll = CONFIG.processing.poll_interval if CONFIG else 2
            time.sleep(poll)
            
        except Exception as e:
            log(f"Loop error: {e}", "ERROR")
            time.sleep(5)

# =============================================================================
# CLI
# =============================================================================

def cmd_start():
    if is_running():
        print("Bardacle is already running")
        return 1
    
    if os.fork() > 0:
        print("Bardacle started")
        return 0
    
    os.setsid()
    if os.fork() > 0:
        sys.exit(0)
    
    sys.stdin.close()
    if CONFIG and CONFIG.output.log_file:
        sys.stdout = open(CONFIG.output.log_file, "a")
        sys.stderr = sys.stdout
    
    daemon_loop()
    return 0


def cmd_stop():
    pid = get_pid()
    if pid and is_running():
        os.kill(pid, signal.SIGTERM)
        print("Bardacle stopped")
        remove_pid()
    else:
        print("Bardacle is not running")
        remove_pid()
    return 0


def cmd_status():
    if is_running():
        pid = get_pid()
        print(f"Bardacle is running (PID: {pid})")
        if CONFIG and CONFIG.output.state_file:
            state_path = Path(CONFIG.output.state_file)
            if state_path.exists():
                mtime = datetime.fromtimestamp(state_path.stat().st_mtime)
                print(f"Last update: {mtime.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Show provider health
        print("\nProvider Health:")
        for provider in ["local", "ollama", "groq", "openai"]:
            status = HEALTH.status.get(provider, {})
            avail = "✓" if status.get("available", False) else "✗"
            failures = status.get("failures", 0)
            print(f"  {provider}: {avail} (failures: {failures})")
    else:
        print("Bardacle is not running")
    
    # Check for emergency state
    emergency = check_emergency_state()
    if emergency:
        print(f"\n⚠️  Emergency state found: {emergency}")
        print("   Run 'bardacle recover' to restore from last good state")
    
    return 0


def cmd_update(full: bool = False):
    print("Updating state...")
    if update_state(force_full=full):
        print("State updated")
        if CONFIG and CONFIG.output.state_file:
            print(Path(CONFIG.output.state_file).read_text())
        return 0
    else:
        print("Update failed")
        return 1


def cmd_recover(backup_name: Optional[str] = None):
    """Recover state from backup."""
    backups = list_backups()
    
    if not backups:
        print("No backups available")
        return 1
    
    if backup_name:
        # Find specific backup
        backup_path = None
        for b in backups:
            if b.name == backup_name or backup_name in b.name:
                backup_path = b
                break
        if not backup_path:
            print(f"Backup not found: {backup_name}")
            print("\nAvailable backups:")
            for b in backups[:10]:
                print(f"  - {b.name}")
            return 1
    else:
        # List backups and ask user
        print("Available backups:")
        for i, b in enumerate(backups[:10]):
            mtime = datetime.fromtimestamp(b.stat().st_mtime)
            print(f"  {i+1}. {b.name} ({mtime.strftime('%Y-%m-%d %H:%M:%S')})")
        
        print("\nTo recover, run: bardacle recover <backup-name>")
        print("Or to recover latest: bardacle recover --latest")
        return 0
    
    if recover_from_backup(backup_path):
        print(f"Recovered from {backup_path.name}")
        
        # Remove emergency state if exists
        emergency = check_emergency_state()
        if emergency:
            emergency.unlink()
            print("Cleared emergency state")
        return 0
    else:
        print("Recovery failed")
        return 1


def cmd_test():
    print(f"Bardacle v{__version__} Test Suite")
    print("=" * 50)
    
    # Check config
    print("\n1. Configuration...")
    print(f"   Transcripts: {CONFIG.transcripts.dir or 'NOT SET'}")
    print(f"   State file: {CONFIG.output.state_file or 'NOT SET'}")
    print(f"   Groq API: {'SET' if CONFIG.inference.groq_api_key else 'NOT SET'}")
    print(f"   OpenAI API: {'SET' if CONFIG.inference.openai_api_key else 'NOT SET'}")
    
    # Check providers with health checks
    print("\n2. Provider Health Checks...")
    
    print("   Checking local LLM...", end=" ")
    if HEALTH._ping("local"):
        print(f"✓ Connected to {CONFIG.inference.local_url}")
    else:
        print("✗ Not reachable")
    
    print("   Checking Ollama...", end=" ")
    if HEALTH._ping("ollama"):
        print(f"✓ Connected to {CONFIG.inference.ollama_url}")
    else:
        print("✗ Not reachable")
    
    print("   Checking Groq...", end=" ")
    if CONFIG.inference.groq_api_key:
        print("✓ API key set")
    else:
        print("✗ No API key")
    
    print("   Checking OpenAI...", end=" ")
    if CONFIG.inference.openai_api_key:
        print("✓ API key set")
    else:
        print("✗ No API key")
    
    # Check transcript
    print("\n3. Transcripts...")
    transcript = find_active_transcript()
    if transcript:
        print(f"   ✓ Found: {transcript.name}")
        messages = read_and_process_messages(transcript, 20)
        print(f"   ✓ Processed {len(messages)} messages")
    else:
        print("   ✗ No transcript found")
    
    # Check backups
    print("\n4. Backups...")
    backups = list_backups()
    print(f"   {len(backups)} backup(s) available")
    if backups:
        latest = backups[0]
        mtime = datetime.fromtimestamp(latest.stat().st_mtime)
        print(f"   Latest: {latest.name} ({mtime.strftime('%Y-%m-%d %H:%M:%S')})")
    
    # Check emergency state
    print("\n5. Crash Recovery...")
    emergency = check_emergency_state()
    if emergency:
        print(f"   ⚠️  Emergency state found: {emergency}")
    else:
        print("   ✓ No emergency state (clean shutdown)")
    
    print("\nTest complete.")
    return 0


def main():
    global CONFIG
    
    parser = argparse.ArgumentParser(
        description="Bardacle - A Metacognitive Layer for AI Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=["start", "stop", "status", "update", "test", "recover"],
                       help="Action to perform")
    parser.add_argument("--config", "-c", type=Path, help="Config file path")
    parser.add_argument("--full", "-f", action="store_true", help="Force full (non-incremental) update")
    parser.add_argument("--latest", "-l", action="store_true", help="Recover from latest backup")
    parser.add_argument("--backup", "-b", type=str, help="Specific backup to recover from")
    parser.add_argument("--version", "-v", action="version", version=f"Bardacle {__version__}")
    
    args = parser.parse_args()
    
    # Load config
    CONFIG = load_config(args.config)
    
    # Run command
    if args.action == "start":
        return cmd_start()
    elif args.action == "stop":
        return cmd_stop()
    elif args.action == "status":
        return cmd_status()
    elif args.action == "update":
        return cmd_update(args.full)
    elif args.action == "test":
        return cmd_test()
    elif args.action == "recover":
        if args.latest:
            backups = list_backups()
            if backups:
                return 0 if recover_from_backup(backups[0]) else 1
            print("No backups available")
            return 1
        return cmd_recover(args.backup)


if __name__ == "__main__":
    sys.exit(main() or 0)
