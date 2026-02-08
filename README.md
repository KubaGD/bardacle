# 🐚 Bardacle

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

**A metacognitive layer for AI agents.**

Bardacle watches your agent's session transcript and maintains a real-time "session state" summary. When context gets compacted or sessions restart, your agent can read this state to pick up exactly where it left off.

Think of it as **short-term memory that survives context loss**.

<p align="center">
  <img src="assets/logo.svg" alt="Bardacle Logo" width="150">
</p>

---

## ✨ Features

- **🧠 Metacognitive Awareness** — Tracks what the agent is working on, not just conversation history
- **🔧 Tool Awareness** — Summarizes tool calls (`[exec] deploy.sh → ✓`) so the agent knows what happened
- **🏠 Local-First** — Uses local LLMs (LM Studio, Ollama) by default, keeping your data private
- **☁️ Cloud Fallback** — Falls back to Groq → OpenAI when local fails
- **⚡ Rate Limit Detection** — Automatically skips rate-limited providers
- **📊 Incremental Updates** — Updates existing state instead of regenerating from scratch
- **📈 Metrics Logging** — Tracks latency, model used, messages analyzed
- **🐳 Docker Ready** — Run containerized with one command

---

## 🚀 Quick Start

### Install

```bash
# Clone the repository
git clone https://github.com/StellarSk8board/bardacle.git
cd bardacle

# Install
pip install -e .
```

### Configure

```bash
# Copy example config
cp config.example.yaml config.yaml

# Edit with your paths
nano config.yaml
```

Minimal config:
```yaml
transcripts:
  dir: "~/.your-agent/sessions"
  pattern: "*.jsonl"

output:
  state_file: "~/.your-agent/session-state.md"
```

### Run

```bash
# Test the setup
bardacle test

# Start the daemon
bardacle start

# Check status
bardacle status
```

### Integrate with Your Agent

Add to your agent's instructions:
```
"At the start of each response, read session-state.md for current context."
```

That's it! Your agent now has persistent short-term memory.

---

## 📖 How It Works

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Session                                               │
│  ┌─────────────────────────────────────────────────────────┐│
│  │ User: Help me deploy my app                             ││
│  │ Agent: Sure! Let me check the config... [exec] cat...   ││
│  │ Agent: Found an issue. Fixing now... [Write] config.yml ││
│  │ User: Great, now run the tests                          ││
│  └─────────────────────────────────────────────────────────┘│
│                            │                                 │
│                            ▼                                 │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  📝 Transcript (JSONL)                                  ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────────│──────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  🐚 Bardacle                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │ Watch          │→ │ Summarize      │→ │ Extract State  │ │
│  │ Transcript     │  │ Tool Calls     │  │ via LLM        │ │
│  └────────────────┘  └────────────────┘  └────────────────┘ │
│                                                    │         │
│                                                    ▼         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  session-state.md                                       ││
│  │  ─────────────────                                      ││
│  │  Current Goal: Deploy the application                   ││
│  │  Active Tasks: Run tests (in progress)                  ││
│  │  Recent: Fixed config issue                             ││
│  │  Next: Execute test suite                               ││
│  └─────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│  Agent reads session-state.md → Knows what it was doing     │
└──────────────────────────────────────────────────────────────┘
```

---

## 🔧 Configuration

### Environment Variables

```bash
# Cloud API keys (optional but recommended for fallback)
export GROQ_API_KEY="gsk_..."
export OPENAI_API_KEY="sk-..."

# Override config paths
export BARDACLE_TRANSCRIPTS_DIR="/path/to/sessions"
export BARDACLE_STATE_FILE="/path/to/session-state.md"
export BARDACLE_LOCAL_URL="http://localhost:1234"
```

### Full Config Example

```yaml
inference:
  local_url: "http://localhost:1234"
  local_model_fast: "qwen2.5-coder-7b-instruct"
  local_model_smart: "qwen3-coder-30b-a3b-instruct"
  local_timeout: 15
  groq_model: "llama-3.1-8b-instant"
  openai_model: "gpt-4o-mini"
  cloud_timeout: 30

transcripts:
  dir: "~/.agent/sessions"
  pattern: "*.jsonl"

processing:
  max_messages: 100
  max_message_chars: 500
  debounce_seconds: 5
  force_update_interval: 120
  poll_interval: 2

output:
  state_file: "~/.agent/session-state.md"
  log_file: "~/.bardacle/bardacle.log"
  metrics_file: "~/.bardacle/metrics.jsonl"
```

---

## 📊 Fallback Chain

Bardacle tries inference in this order:

```
1. Local LLM (15s timeout)     ─── Fast, free, private
         │
         ▼ (timeout/error)
2. Groq Cloud                  ─── Fast, free tier
         │
         ▼ (rate limit/error)
3. OpenAI                      ─── Reliable fallback
         │
         ▼ (error)
4. Local Smart Model           ─── Last resort
```

Rate limit detection: When Groq returns 429, Bardacle skips it for 60 seconds.

---

## 🐳 Docker

### Quick Start

```bash
docker run -d \
  -e GROQ_API_KEY="your-key" \
  -v /path/to/transcripts:/data/transcripts:ro \
  -v /path/to/output:/data/output \
  ghcr.io/stellarsk8board/bardacle:latest
```

### With Docker Compose

```yaml
version: '3.8'
services:
  bardacle:
    image: ghcr.io/stellarsk8board/bardacle:latest
    environment:
      - GROQ_API_KEY=${GROQ_API_KEY}
      - BARDACLE_LOCAL_URL=http://host.docker.internal:1234
    volumes:
      - ./transcripts:/data/transcripts:ro
      - ./output:/data/output
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

---

## 📄 Session State Format

Bardacle generates a markdown file:

```markdown
# Session State

*Auto-generated at 2026-02-07 21:30:15*
*Model: groq | Latency: 0.4s | Messages: 50*

---

## Current Goal
Deploy the web application to production

## Active Tasks
- [done] Fix configuration issue
- [in progress] Run test suite
- [pending] Deploy to production

## Recent Decisions
- Using Docker for deployment
- PostgreSQL over MySQL for the database

## Blockers
None

## Next Steps
1. Wait for tests to complete
2. Review test results
3. Deploy if all tests pass

## Key Context
- App: FastAPI web service
- Environment: Production
- Deployment target: AWS ECS
```

---

## 📚 Documentation

- **[Installation Guide](docs/installation.md)** — Detailed setup instructions
- **[Quickstart](docs/quickstart.md)** — Get running in 5 minutes
- **[Transcript Adapters](docs/adapters.md)** — Support different formats
- **[Troubleshooting](docs/troubleshooting.md)** — Common issues and solutions
- **[FAQ](docs/faq.md)** — Frequently asked questions

---

## 🧪 Development

```bash
# Clone
git clone https://github.com/StellarSk8board/bardacle.git
cd bardacle

# Install dev dependencies
pip install -e ".[dev]"

# Run tests
python -m bardacle test

# Run with local changes
PYTHONPATH=src python -m bardacle update
```

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

- 🐛 [Report bugs](https://github.com/StellarSk8board/bardacle/issues)
- 💡 [Request features](https://github.com/StellarSk8board/bardacle/issues)
- 🔧 [Submit pull requests](https://github.com/StellarSk8board/bardacle/pulls)

---

## 📜 License

MIT License. See [LICENSE](LICENSE).

---

## 🙏 Credits

Created by **Bob** (an AI agent) with **Blair** at [OpenClaw](https://github.com/openclaw/openclaw).

Built on research from:
- Microsoft's AI Agents metacognition patterns
- SOFAI (Slow/Fast AI) architecture
- Letta/MemGPT stateful agents
- momentiq's Plan-Learn-Reflect-Evolve cycles

---

<p align="center">
  <i>"The bard remembers, so you don't have to."</i> 🐚
</p>
