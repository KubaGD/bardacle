# Transcript Adapters

Bardacle expects session transcripts in JSONL (JSON Lines) format. This document describes the expected format and how to adapt other formats.

## Default Format (OpenClaw/Claude)

```jsonl
{"type": "message", "message": {"role": "user", "content": "Hello"}}
{"type": "message", "message": {"role": "assistant", "content": [{"type": "text", "text": "Hi there!"}]}}
{"type": "message", "message": {"role": "assistant", "content": [{"type": "toolCall", "name": "exec", "id": "123", "arguments": {"command": "ls"}}]}}
{"type": "message", "message": {"role": "toolResult", "toolCallId": "123", "content": [{"type": "text", "text": "file1.txt\nfile2.txt"}]}}
```

### Message Structure

Each line is a JSON object with:
- `type`: "message"
- `message`: Object containing:
  - `role`: "user", "assistant", or "toolResult"
  - `content`: String or array of content blocks

### Content Blocks

Content can be:
- A plain string: `"Hello world"`
- An array of blocks:
  ```json
  [
    {"type": "text", "text": "Some text"},
    {"type": "toolCall", "name": "exec", "id": "abc", "arguments": {...}},
    {"type": "thinking", "thinking": "Agent's internal reasoning"}
  ]
  ```

## Alternative Formats

### Simple Format

If your agent uses a simpler format:

```jsonl
{"role": "user", "content": "Hello"}
{"role": "assistant", "content": "Hi there!"}
```

Bardacle will automatically detect and handle this.

### LangChain Format

```jsonl
{"type": "human", "content": "Hello"}
{"type": "ai", "content": "Hi there!"}
{"type": "tool", "name": "search", "content": "results..."}
```

To use this format, create an adapter:

```python
# adapters/langchain.py

def convert_message(msg):
    role_map = {"human": "user", "ai": "assistant", "tool": "toolResult"}
    return {
        "role": role_map.get(msg["type"], msg["type"]),
        "content": msg["content"]
    }
```

### Custom Adapter

To support your own format:

1. Create `src/adapters/your_format.py`
2. Implement the conversion function
3. Register it in config:

```yaml
transcripts:
  adapter: "your_format"
```

## Tool Call Detection

Bardacle summarizes tool calls for awareness. It looks for:

- `toolCall` or `tool_use` blocks in content
- `toolResult` messages with matching `toolCallId`

If your format differs, you may need an adapter to normalize tool calls.

## Tips

- Keep transcripts append-only (don't modify old entries)
- Bardacle only reads the last N messages (configurable)
- Large files are fine - we seek to the end
