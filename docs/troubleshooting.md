# Troubleshooting Guide

Common issues and their solutions.

## Table of Contents
- [Installation Issues](#installation-issues)
- [Configuration Issues](#configuration-issues)
- [Runtime Issues](#runtime-issues)
- [Inference Issues](#inference-issues)
- [Transcript Issues](#transcript-issues)
- [Docker Issues](#docker-issues)

---

## Installation Issues

### "No module named 'yaml'"

**Problem**: PyYAML is not installed.

**Solution**:
```bash
pip install pyyaml
```

If you can't install packages (externally managed environment):
```bash
# Create a virtual environment
python -m venv ~/.bardacle-venv
source ~/.bardacle-venv/bin/activate
pip install bardacle
```

Or Bardacle will work without YAML - just use environment variables for configuration.

### "No module named 'requests'"

**Problem**: requests library is not installed.

**Solution**:
```bash
pip install requests
```

### Permission Denied

**Problem**: Can't write to installation directory.

**Solution**:
```bash
# Install for current user only
pip install --user bardacle

# Or use a virtual environment
python -m venv ~/.bardacle-venv
source ~/.bardacle-venv/bin/activate
pip install bardacle
```

---

## Configuration Issues

### "No transcript found"

**Problem**: Bardacle can't find your agent's transcript files.

**Solutions**:

1. Check the path in config:
```yaml
transcripts:
  dir: "/absolute/path/to/sessions"  # Use absolute path
  pattern: "*.jsonl"
```

2. Verify the path exists:
```bash
ls -la /path/to/sessions/
```

3. Check file permissions:
```bash
chmod -R 755 /path/to/sessions/
```

4. Use environment variable:
```bash
export BARDACLE_TRANSCRIPTS_DIR="/path/to/sessions"
```

### "State file not being created"

**Problem**: Bardacle runs but doesn't create session-state.md.

**Solutions**:

1. Check the output path:
```yaml
output:
  state_file: "/absolute/path/to/session-state.md"
```

2. Verify parent directory exists:
```bash
mkdir -p /path/to/output/directory/
```

3. Check logs for errors:
```bash
tail -f ~/.bardacle/bardacle.log
```

### Config File Not Found

**Problem**: Bardacle isn't reading your config.yaml.

**Solution**: Bardacle searches these paths in order:
1. `./config.yaml` (current directory)
2. `./bardacle.yaml`
3. `~/.config/bardacle/config.yaml`
4. `~/.bardacle/config.yaml`

Specify explicitly:
```bash
bardacle --config /path/to/config.yaml start
```

---

## Runtime Issues

### "Bardacle is already running"

**Problem**: Trying to start when already running.

**Solution**:
```bash
# Check status
bardacle status

# Stop existing instance
bardacle stop

# Start fresh
bardacle start
```

### Daemon Dies Silently

**Problem**: Bardacle starts but then stops.

**Solutions**:

1. Check logs:
```bash
tail -100 ~/.bardacle/bardacle.log
```

2. Run in foreground for debugging:
```bash
# Instead of starting as daemon
PYTHONPATH=src python -c "
from bardacle import load_config, update_state
load_config()
update_state()
"
```

3. Check for Python errors:
```bash
python -m bardacle test
```

### High CPU Usage

**Problem**: Bardacle using too much CPU.

**Solution**: Increase poll interval in config:
```yaml
processing:
  poll_interval: 5  # Check every 5 seconds instead of 2
  debounce_seconds: 10  # Wait longer before processing
```

### Memory Growing Over Time

**Problem**: Log files getting too large.

**Solution**: Set up log rotation:
```bash
# Create logrotate config
sudo cat > /etc/logrotate.d/bardacle << EOF
~/.bardacle/bardacle.log {
    daily
    rotate 7
    compress
    missingok
    notifempty
}
EOF
```

---

## Inference Issues

### "Local LLM not reachable"

**Problem**: Can't connect to LM Studio or Ollama.

**Solutions**:

1. Verify the server is running:
```bash
curl http://localhost:1234/v1/models
```

2. Check the correct port:
   - LM Studio default: 1234
   - Ollama default: 11434

3. Update config:
```yaml
inference:
  local_url: "http://localhost:1234"  # or 11434 for Ollama
```

4. If using Docker, use host networking:
```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```
And set:
```yaml
local_url: "http://host.docker.internal:1234"
```

### "Groq rate limited"

**Problem**: Getting 429 errors from Groq.

**Solution**: This is normal. Bardacle automatically:
1. Detects the 429 error
2. Skips Groq for 60 seconds
3. Falls back to OpenAI

To reduce rate limit hits:
```yaml
processing:
  debounce_seconds: 10  # Update less frequently
  force_update_interval: 300  # 5 minutes instead of 2
```

### "All inference methods failed"

**Problem**: No LLM responded.

**Solutions**:

1. Check at least one is configured:
```bash
# Test Groq
curl -X POST "https://api.groq.com/openai/v1/chat/completions" \
  -H "Authorization: Bearer $GROQ_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.1-8b-instant","messages":[{"role":"user","content":"test"}]}'
```

2. Verify API keys are set:
```bash
echo $GROQ_API_KEY
echo $OPENAI_API_KEY
```

3. Check for network issues:
```bash
ping api.groq.com
ping api.openai.com
```

### Slow Inference (>30 seconds)

**Problem**: State updates taking too long.

**Solutions**:

1. Reduce message window:
```yaml
processing:
  max_messages: 50  # Instead of 100
```

2. Increase truncation:
```yaml
processing:
  max_message_chars: 300  # Instead of 500
```

3. Use faster local model:
```yaml
inference:
  local_model_fast: "qwen2.5-coder-3b-instruct"  # Smaller = faster
```

---

## Transcript Issues

### "Processed 0 messages"

**Problem**: Transcript exists but no messages parsed.

**Solutions**:

1. Check transcript format. Expected:
```jsonl
{"type": "message", "message": {"role": "user", "content": "Hello"}}
```

2. Verify valid JSON:
```bash
head -1 /path/to/transcript.jsonl | python -m json.tool
```

3. Check for encoding issues:
```bash
file /path/to/transcript.jsonl
# Should say: UTF-8 Unicode text
```

### Tool Calls Not Summarized

**Problem**: Tool summaries showing as "[unknown] executed".

**Solution**: Your transcript format may differ. Check the tool call structure:
```jsonl
{"type": "toolCall", "name": "exec", "id": "123", "arguments": {...}}
```

If your format differs, you may need a custom adapter. See [adapters.md](adapters.md).

### Transcript Too Large

**Problem**: Very large transcript files slowing things down.

**Solution**: Bardacle only reads the last N lines. This is efficient even for large files. If still slow:

1. Archive old sessions:
```bash
# Move old transcripts
mv old-session-*.jsonl archive/
```

2. Reduce message window:
```yaml
processing:
  max_messages: 50
```

---

## Docker Issues

### "Connection refused" to Local LLM

**Problem**: Container can't reach host's LM Studio.

**Solution**: Use host networking:
```yaml
# docker-compose.yml
services:
  bardacle:
    extra_hosts:
      - "host.docker.internal:host-gateway"
    environment:
      - BARDACLE_LOCAL_URL=http://host.docker.internal:1234
```

### Volume Mount Permission Denied

**Problem**: Container can't read/write mounted volumes.

**Solutions**:

1. Check permissions on host:
```bash
chmod -R 755 /path/to/transcripts
chmod -R 777 /path/to/output
```

2. Run container as current user:
```bash
docker run --user $(id -u):$(id -g) ...
```

### Container Exits Immediately

**Problem**: Container starts then stops.

**Solution**: Check logs:
```bash
docker logs bardacle
```

Common causes:
- Missing config
- Invalid API keys
- No transcripts found

---

## Still Having Issues?

1. **Check the logs**: `~/.bardacle/bardacle.log`
2. **Run tests**: `bardacle test`
3. **Run in verbose mode**: Edit source to add more logging
4. **Open an issue**: https://github.com/StellarSk8board/bardacle/issues

Include:
- Bardacle version: `bardacle --version`
- Python version: `python --version`
- OS: `uname -a`
- Config (redact API keys)
- Relevant log output
