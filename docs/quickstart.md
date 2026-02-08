# Quickstart Guide

Get Bardacle running in 5 minutes.

## Prerequisites

- Python 3.10+
- An AI agent that writes session transcripts to JSONL files
- Local LLM (LM Studio, Ollama) OR cloud API keys

## Step 1: Install

```bash
git clone https://github.com/yourusername/bardacle.git
cd bardacle
pip install -e .
```

Or directly:
```bash
pip install bardacle
```

## Step 2: Configure

Copy the example config:
```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:
```yaml
transcripts:
  dir: "/path/to/your/agent/sessions"
  pattern: "*.jsonl"

output:
  state_file: "/path/to/session-state.md"
```

Set API keys (if using cloud fallback):
```bash
export GROQ_API_KEY="your-key"
export OPENAI_API_KEY="your-key"
```

## Step 3: Test

```bash
python -m bardacle test
```

You should see:
```
Bardacle v0.1.0 Test Suite
==================================================

1. Configuration...
   Transcripts: /path/to/sessions
   State file: /path/to/session-state.md
   Groq API: SET

2. Local LLM...
   ✓ Connected to http://localhost:1234

3. Transcripts...
   ✓ Found: session-abc123.jsonl
   ✓ Processed 50 messages

Test complete.
```

## Step 4: Run

```bash
# Start the daemon
python -m bardacle start

# Check it's running
python -m bardacle status
```

## Step 5: Integrate

Tell your agent to read the session state:

```markdown
# In your agent's instructions:
"At the start of each response, read session-state.md for current context."
```

## That's it!

Bardacle will now:
- Watch your agent's transcript
- Update session-state.md every few minutes
- Help your agent remember what it's doing

## Next Steps

- [Configure transcript adapters](adapters.md)
- [Tune performance settings](performance.md)
- [Set up cloud fallback](cloud-fallback.md)
