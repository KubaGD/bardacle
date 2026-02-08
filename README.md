# 🐚 Bardacle

**A metacognitive layer for AI agents.**

Bardacle watches your agent's session transcript and maintains a real-time "session state" summary. When context gets compacted or sessions restart, your agent can read this state to pick up exactly where it left off.

Think of it as short-term memory that survives context loss.

---

## The Problem

AI agents forget. Long conversations get compacted, losing detail. Sessions restart with no memory. Multi-tasking fragments focus. Your agent asks "where were we?" and you have to re-explain everything.

## The Solution

Bardacle runs alongside your agent as a background daemon:

1. **Watches** your session transcript in real-time
2. **Summarizes** tool calls so the agent knows what it *did*, not just what it *said*
3. **Extracts** current goal, active tasks, blockers, next steps
4. **Writes** a session-state file your agent reads at each response

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Session Transcript                                    │
│            ↓                                                 │
│  Bardacle watches for new messages                          │
│            ↓                                                 │
│  Summarizes: [exec] script.py → ✓                           │
│            ↓                                                 │
│  Extracts: goal, tasks, decisions, blockers                 │
│            ↓                                                 │
│  Writes session-state.md                                    │
│            ↓                                                 │
│  Agent reads this → knows what it was doing                 │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

- **🧠 Metacognitive Awareness**: Tracks what the agent is working on, not just conversation history
- **🔧 Tool Awareness**: Summarizes tool calls (`[exec] deploy.sh → ✓`) so the agent knows what happened
- **🏠 Local-First**: Uses local LLMs (LM Studio, Ollama) by default
- **☁️ Cloud Fallback**: Falls back to Groq → OpenAI when local fails
- **⚡ Rate Limit Detection**: Skips rate-limited providers automatically
- **📊 Incremental Updates**: Updates existing state instead of regenerating
- **📈 Metrics Logging**: Tracks latency, model used, messages analyzed

---

## Quick Start

### Prerequisites

- Python 3.10+
- Local LLM server (LM Studio, Ollama) OR cloud API keys (Groq, OpenAI)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/bardacle.git
cd bardacle

# Install dependencies
pip install -r requirements.txt

# Copy example config
cp config.example.yaml config.yaml
```

### Configuration

Edit `config.yaml`:

```yaml
inference:
  # Local LLM (primary)
  local_url: "http://localhost:1234"
  local_model: "qwen2.5-coder-7b-instruct"
  
  # Cloud fallbacks (optional)
  groq_api_key: "${GROQ_API_KEY}"  # or set env var
  openai_api_key: "${OPENAI_API_KEY}"

transcripts:
  # Path to your agent's session transcripts
  dir: "~/.your-agent/sessions"
  pattern: "*.jsonl"

output:
  # Where to write the session state
  state_file: "~/.your-agent/session-state.md"
```

### Run

```bash
# Start the daemon
python -m bardacle start

# Check status
python -m bardacle status

# Force an update
python -m bardacle update

# Stop the daemon
python -m bardacle stop
```

---

## Session State Format

Bardacle generates a markdown file your agent can read:

```markdown
# Session State

*Auto-generated at 2026-02-07 21:30:15*
*Model: groq | Latency: 16.3s | Messages: 100*

## Current Goal
Implement user authentication for the web app

## Active Tasks
- [in progress] Set up OAuth2 with Google
- [blocked] Waiting for API credentials from client
- [done] Database schema for users

## Recent Decisions
- Using JWT tokens instead of sessions
- PostgreSQL over MongoDB for this project

## Blockers
- Need Google OAuth credentials from client

## Next Steps
1. Create OAuth callback endpoint
2. Test login flow locally
3. Deploy to staging

## Key Context
- Client: Acme Corp
- Deadline: Friday
- Repo: github.com/acme/webapp
```

---

## Transcript Format

Bardacle expects JSONL transcripts with this structure:

```jsonl
{"type": "message", "message": {"role": "user", "content": "Deploy the app"}}
{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Deploying now..."}]}}
{"type": "message", "message": {"role": "toolResult", "toolCallId": "123", "content": [{"type": "text", "text": "Deployed successfully"}]}}
```

For other formats, see [Transcript Adapters](docs/adapters.md).

---

## Fallback Chain

Bardacle tries inference in this order:

1. **Local LLM** (15s timeout) - Fast, free, private
2. **Groq** - Fast cloud, generous free tier
3. **OpenAI** - Reliable fallback
4. **Local 30B** - Smarter local model as last resort

If Groq returns 429 (rate limited), Bardacle skips it for 60 seconds.

---

## Integration Examples

### OpenClaw

```yaml
# In your AGENTS.md or startup instructions
"Read session-state.md at the start of each response for continuity."
```

### LangChain

```python
from langchain.memory import ReadOnlySharedMemory

# Point to Bardacle's output
state = open("~/.agent/session-state.md").read()
memory = ReadOnlySharedMemory(memory_key="session_state", value=state)
```

### Custom Agent

```python
# At the start of each agent turn
def get_context():
    state_file = Path("~/.agent/session-state.md")
    if state_file.exists():
        return state_file.read_text()
    return ""
```

---

## Why "Bardacle"?

- **Bard**: A keeper of stories and memory
- **Barnacle**: Attaches itself, persistent, goes where you go

It's also a nod to the crustacean theme of [OpenClaw](https://github.com/openclaw/openclaw) (claw → crab → barnacle).

---

## Research Background

Bardacle is a practical implementation of metacognitive AI patterns:

- **Microsoft's AI Agents for Beginners**: Metacognition as "thinking about thinking"
- **SOFAI Architecture**: Slow/fast/metacognitive reasoning layers
- **Letta/MemGPT**: Stateful agents with persistent memory
- **momentiq**: Plan-Learn-Reflect-Evolve cycles

The key insight: **Reasoning is about completing the task. Metacognition is about managing how the task is completed.**

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

MIT License. See [LICENSE](LICENSE).

---

## Credits

Created by Bob (an AI agent) with Blair at [OpenClaw](https://github.com/openclaw/openclaw).

*"The light is yours."* 💀
