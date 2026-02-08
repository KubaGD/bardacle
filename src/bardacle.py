#!/usr/bin/env python3
"""
Bardacle - A Metacognitive Layer for AI Agents

Watches agent session transcripts and maintains real-time session state
awareness, enabling agents to recover context after compaction or restart.

Usage:
    python -m bardacle start   # Start daemon
    python -m bardacle stop    # Stop daemon
    python -m bardacle status  # Check status
    python -m bardacle update  # Force immediate update
    python -m bardacle test    # Test components
"""

import os
import sys
import json
import time
import signal
import hashlib
import argparse
import logging
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

__version__ = "0.1.0"
__author__ = "Bob & Blair"

# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class InferenceConfig:
    local_url: str = "http://localhost:1234"
    local_model_fast: str = "qwen2.5-coder-7b-instruct"
    local_model_smart: str = "qwen3-coder-30b-a3b-instruct"
    groq_model: str = "llama-3.1-8b-instant"
    openai_model: str = "gpt-4o-mini"
    local_timeout: int = 15
    cloud_timeout: int = 30
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
# INFERENCE
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
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        log(f"Local LLM timeout ({model})", "WARN")
        return None
    except requests.exceptions.ConnectionError:
        log("Local LLM not reachable", "WARN")
        return None
    except Exception as e:
        log(f"Local LLM error: {e}", "ERROR")
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
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.HTTPError as e:
        if hasattr(e, 'response') and e.response.status_code == 429:
            mark_groq_rate_limited()
        log(f"Groq error: {e}", "ERROR")
        return None
    except Exception as e:
        log(f"Groq error: {e}", "ERROR")
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
        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log(f"OpenAI error: {e}", "ERROR")
        return None


def call_llm_with_fallback(prompt_messages: List[Dict]) -> Tuple[Optional[str], str]:
    """Call LLM with fallback chain."""
    if not CONFIG:
        return None, "none"
    
    local_timeout = CONFIG.inference.local_timeout
    cloud_timeout = CONFIG.inference.cloud_timeout
    
    # 1. Local fast model
    log("Trying local LLM...")
    result = try_local(CONFIG.inference.local_model_fast, prompt_messages, local_timeout)
    if result:
        return result, "local"
    
    # 2. Groq (skip if rate limited)
    if is_groq_rate_limited():
        log(f"Skipping Groq (rate limited, {get_groq_cooldown_remaining()}s remaining)")
    else:
        log("Trying Groq...")
        result = try_groq(prompt_messages, cloud_timeout)
        if result:
            return result, "groq"
    
    # 3. OpenAI
    log("Trying OpenAI...")
    result = try_openai(prompt_messages, cloud_timeout)
    if result:
        return result, "openai"
    
    # 4. Local smart model (last resort)
    log("Trying local smart model...")
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
    """Write session state to file."""
    if not CONFIG or not CONFIG.output.state_file:
        return
    
    state_path = Path(CONFIG.output.state_file)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    
    header = f"""# Session State

*Auto-generated at {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*
*Model: {model} | Latency: {latency:.1f}s | Messages: {msg_count}*

---

"""
    state_path.write_text(header + state_content)
    log(f"Updated state ({len(state_content)} chars, {model}, {latency:.1f}s)")

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
    write_pid()
    
    last_hash = ""
    last_update = 0
    last_change = 0
    
    def shutdown(signum, frame):
        log("Shutting down...")
        remove_pid()
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    
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
    else:
        print("Bardacle is not running")
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


def cmd_test():
    print(f"Bardacle v{__version__} Test Suite")
    print("=" * 50)
    
    # Check config
    print("\n1. Configuration...")
    print(f"   Transcripts: {CONFIG.transcripts.dir or 'NOT SET'}")
    print(f"   State file: {CONFIG.output.state_file or 'NOT SET'}")
    print(f"   Groq API: {'SET' if CONFIG.inference.groq_api_key else 'NOT SET'}")
    print(f"   OpenAI API: {'SET' if CONFIG.inference.openai_api_key else 'NOT SET'}")
    
    # Check local LLM
    print("\n2. Local LLM...")
    try:
        resp = requests.get(f"{CONFIG.inference.local_url}/v1/models", timeout=5)
        if resp.ok:
            print(f"   ✓ Connected to {CONFIG.inference.local_url}")
        else:
            print(f"   ✗ Error response")
    except Exception as e:
        print(f"   ✗ Not reachable: {e}")
    
    # Check transcript
    print("\n3. Transcripts...")
    transcript = find_active_transcript()
    if transcript:
        print(f"   ✓ Found: {transcript.name}")
        messages = read_and_process_messages(transcript, 20)
        print(f"   ✓ Processed {len(messages)} messages")
    else:
        print("   ✗ No transcript found")
    
    print("\nTest complete.")
    return 0


def main():
    global CONFIG
    
    parser = argparse.ArgumentParser(
        description="Bardacle - A Metacognitive Layer for AI Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=["start", "stop", "status", "update", "test"],
                       help="Action to perform")
    parser.add_argument("--config", "-c", type=Path, help="Config file path")
    parser.add_argument("--full", "-f", action="store_true", help="Force full (non-incremental) update")
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


if __name__ == "__main__":
    sys.exit(main() or 0)
