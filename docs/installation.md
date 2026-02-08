# Installation Guide

Complete installation instructions for Bardacle.

## Table of Contents
- [Requirements](#requirements)
- [Installation Methods](#installation-methods)
- [Configuration](#configuration)
- [Verifying Installation](#verifying-installation)
- [Upgrading](#upgrading)
- [Uninstalling](#uninstalling)

---

## Requirements

### System Requirements
- **Python**: 3.10 or higher
- **OS**: Linux, macOS, Windows (WSL recommended)
- **Memory**: ~100MB for the daemon
- **Disk**: Minimal (logs grow over time)

### Optional Dependencies
- **Local LLM Server**: LM Studio, Ollama, or any OpenAI-compatible server
- **Cloud API Keys**: Groq (free tier available) and/or OpenAI

---

## Installation Methods

### Method 1: pip install (Recommended)

```bash
# Install from PyPI (when published)
pip install bardacle

# Or install from GitHub
pip install git+https://github.com/StellarSk8board/bardacle.git
```

### Method 2: Clone and Install

```bash
# Clone the repository
git clone https://github.com/StellarSk8board/bardacle.git
cd bardacle

# Install in development mode
pip install -e .

# Or just install dependencies
pip install -r requirements.txt
```

### Method 3: Docker

```bash
# Clone the repository
git clone https://github.com/StellarSk8board/bardacle.git
cd bardacle

# Build the image
docker build -t bardacle:latest .

# Run with your configuration
docker run -d \
  -e GROQ_API_KEY="your-key" \
  -v /path/to/transcripts:/data/transcripts:ro \
  -v /path/to/output:/data/output \
  bardacle:latest
```

### Method 4: Manual (No pip)

```bash
# Clone the repository
git clone https://github.com/StellarSk8board/bardacle.git
cd bardacle

# Install dependencies manually
pip install requests pyyaml

# Run directly
PYTHONPATH=src python -m bardacle start
```

---

## Configuration

### Step 1: Create Config File

```bash
# Copy the example config
cp config.example.yaml config.yaml
```

### Step 2: Edit Configuration

```yaml
# config.yaml

inference:
  # Local LLM server (LM Studio, Ollama, etc.)
  local_url: "http://localhost:1234"
  local_model_fast: "qwen2.5-coder-7b-instruct"
  local_model_smart: "qwen3-coder-30b-a3b-instruct"
  local_timeout: 15  # seconds before falling back to cloud
  
  # Cloud fallbacks (optional but recommended)
  # Set via environment variables or directly here
  # groq_api_key: "gsk_..."
  # openai_api_key: "sk-..."
  groq_model: "llama-3.1-8b-instant"
  openai_model: "gpt-4o-mini"
  cloud_timeout: 30

transcripts:
  # Path to your agent's session transcripts
  dir: "~/.your-agent/sessions"
  pattern: "*.jsonl"

processing:
  max_messages: 100        # Messages to analyze per update
  max_message_chars: 500   # Truncate long messages
  debounce_seconds: 5      # Wait after activity before updating
  force_update_interval: 120  # Force update even without changes
  poll_interval: 2         # File check interval

output:
  state_file: "~/.your-agent/session-state.md"
  # Optional (defaults to ~/.bardacle/)
  # log_file: "~/.bardacle/bardacle.log"
  # metrics_file: "~/.bardacle/metrics.jsonl"
```

### Step 3: Set API Keys (Optional)

```bash
# Add to your shell profile (~/.bashrc, ~/.zshrc)
export GROQ_API_KEY="gsk_your_key_here"
export OPENAI_API_KEY="sk-your_key_here"
```

### Getting API Keys

**Groq (Free Tier)**:
1. Go to https://console.groq.com/
2. Sign up (free)
3. Create an API key
4. Free tier: ~30 requests/minute

**OpenAI**:
1. Go to https://platform.openai.com/
2. Create account and add payment method
3. Create an API key
4. gpt-4o-mini costs ~$0.15/1M input tokens

---

## Verifying Installation

### Test the Installation

```bash
# Run the test suite
bardacle test

# Or if running from source
python -m bardacle test
```

Expected output:
```
Bardacle v0.1.0 Test Suite
==================================================

1. Configuration...
   Transcripts: /path/to/sessions
   State file: /path/to/session-state.md
   Groq API: SET
   OpenAI API: SET

2. Local LLM...
   ✓ Connected to http://localhost:1234

3. Transcripts...
   ✓ Found: session-abc123.jsonl
   ✓ Processed 50 messages

Test complete.
```

### Manual Test

```bash
# Force an update
bardacle update

# Check the generated state
cat ~/.your-agent/session-state.md
```

---

## Upgrading

### pip

```bash
pip install --upgrade bardacle
```

### Git

```bash
cd bardacle
git pull
pip install -e .
```

### Docker

```bash
cd bardacle
git pull
docker build -t bardacle:latest .
docker-compose down
docker-compose up -d
```

---

## Uninstalling

### pip

```bash
pip uninstall bardacle
```

### Complete Removal

```bash
# Remove the package
pip uninstall bardacle

# Remove config and data (optional)
rm -rf ~/.bardacle
rm -f ~/.your-agent/session-state.md

# Remove cloned repo (if applicable)
rm -rf /path/to/bardacle
```

---

## Next Steps

- [Quickstart Guide](quickstart.md) - Get running in 5 minutes
- [Transcript Adapters](adapters.md) - Support different transcript formats
- [Troubleshooting](troubleshooting.md) - Common issues and solutions
