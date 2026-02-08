# Frequently Asked Questions

## General

### What is Bardacle?

Bardacle is a **metacognitive layer** for AI agents. It watches your agent's conversation transcript and maintains a real-time summary of what the agent is working on. When context gets compacted or the session restarts, the agent can read this summary to pick up where it left off.

Think of it as short-term memory that survives context loss.

### Why is it called Bardacle?

- **Bard**: A keeper of stories and memory (like the poets of old)
- **Barnacle**: Attaches itself and goes wherever you go

It's also a nod to the crustacean theme of [OpenClaw](https://github.com/openclaw/openclaw) (claw → crab → barnacle).

### Who made this?

Bardacle was created by **Bob** (an AI agent) with **Blair** at OpenClaw. Yes, an AI built a tool to help other AIs remember things. Very meta.

### Is it free?

Yes! Bardacle is open source under the MIT license. You can:
- Use it for any purpose
- Modify it
- Distribute it
- Use it commercially

The only costs are from the LLM inference:
- **Local LLMs**: Free (you provide the hardware)
- **Groq**: Free tier available (~30 req/min)
- **OpenAI**: ~$0.15 per million tokens (very cheap)

---

## How It Works

### How does Bardacle know what my agent is doing?

Bardacle reads your agent's session transcript (a JSONL file of messages). It analyzes the conversation and tool usage to extract:
- Current goal
- Active tasks
- Recent decisions
- Blockers
- Next steps
- Key context

### What's a "session transcript"?

A session transcript is a log file containing all messages in a conversation. Most agent frameworks write these automatically. Format example:

```jsonl
{"type": "message", "message": {"role": "user", "content": "Hello"}}
{"type": "message", "message": {"role": "assistant", "content": "Hi!"}}
```

### How often does it update?

By default:
- **On change**: 5 seconds after the last message (debounced)
- **Forced**: Every 2 minutes even without changes

Both are configurable in `config.yaml`.

### Does it work offline?

Yes, if you have a local LLM running (LM Studio, Ollama). Bardacle will use local inference with no internet required.

### What LLMs does it support?

**Local** (any OpenAI-compatible API):
- LM Studio
- Ollama
- vLLM
- llama.cpp server
- Text Generation WebUI

**Cloud**:
- Groq (llama-3.1-8b-instant)
- OpenAI (gpt-4o-mini)

---

## Usage

### My agent doesn't use JSONL transcripts. Can I still use Bardacle?

Yes! You can write a custom adapter to convert your format. See [adapters.md](adapters.md).

Alternatively, you could:
1. Write a script that converts your format to JSONL
2. Point Bardacle at the converted file

### Can I use Bardacle with multiple agents?

Yes! Run multiple Bardacle instances with different configs:

```bash
# Agent 1
bardacle --config agent1.yaml start

# Agent 2  
bardacle --config agent2.yaml start
```

Or use different environment variables for each.

### Does the agent need to do anything special?

Just add to your agent's instructions:
```
"At the start of each response, read session-state.md for current context."
```

The agent should then check the file to see what it was working on.

### Can I run it as a cron job instead of a daemon?

Yes! Instead of running as a daemon, just call update:

```bash
# Add to crontab
*/5 * * * * python -m bardacle update
```

This updates every 5 minutes.

---

## Performance

### How much does it cost?

**Local inference**: $0 (your electricity)

**Groq**: Free tier is generous (~30 requests/minute). At 1 update every 2 minutes, you'll never hit it in normal use.

**OpenAI**: gpt-4o-mini costs ~$0.15/million input tokens. A typical update uses ~2000 tokens, so:
- 1 update = ~$0.0003
- 100 updates/day = ~$0.03/day
- 30 days = ~$1/month

### How fast is it?

Typical latency:
- **Local 7B model**: 3-15 seconds
- **Groq cloud**: 0.4-2 seconds
- **OpenAI**: 2-5 seconds

The fallback chain tries local first, then cloud if local fails.

### Does it slow down my agent?

No. Bardacle runs as a separate process and only reads the transcript. It doesn't intercept or modify agent messages.

### How much memory does it use?

The daemon uses ~50-100MB. Logs and metrics grow over time but can be rotated.

---

## Security & Privacy

### Does my data go to the cloud?

**Only if you configure cloud fallback**. If you use only local LLMs, your data never leaves your machine.

When using cloud (Groq/OpenAI):
- Your last ~100 messages are sent for analysis
- They process it and return a summary
- Standard API privacy policies apply

### Are my API keys safe?

API keys are:
- Stored in environment variables (recommended) or config file
- Never logged
- Never included in the session state output

Best practice: Use environment variables, not config files.

### Can I redact sensitive information?

Bardacle doesn't have built-in redaction, but you can:
1. Filter your transcript before Bardacle reads it
2. Post-process the session-state.md output
3. Modify the source to add redaction patterns

---

## Troubleshooting

### Why isn't it updating?

Check:
1. Is the daemon running? `bardacle status`
2. Are there new messages in the transcript?
3. Check logs: `tail ~/.bardacle/bardacle.log`

### Why is inference failing?

The fallback chain is: Local → Groq → OpenAI → Local Smart

If all fail:
1. Is your local LLM running?
2. Are API keys set correctly?
3. Is there network connectivity?

Run `bardacle test` to diagnose.

### Why is the summary inaccurate?

The LLM might:
- Hallucinate details (rare but possible)
- Miss context from earlier in the conversation
- Misinterpret tool calls

Try:
- Increasing `max_messages` to give more context
- Using a smarter model
- Reducing `max_message_chars` to avoid noise

---

## Advanced

### Can I customize the summary format?

Yes! Edit the `SYSTEM_PROMPT` in `bardacle.py`. The default extracts:
- Current Goal
- Active Tasks
- Recent Decisions
- Blockers
- Next Steps
- Key Context

You can change these categories or add new ones.

### Can I use a different LLM for different tasks?

Currently, Bardacle uses the same prompt for all updates. For different models per task, you'd need to modify the source.

### Can I integrate with my own database?

Bardacle writes to a markdown file by default, but you could:
1. Modify `write_state_file()` to write to a database
2. Add a post-processing script that reads the file and syncs to a DB

### How do I contribute?

See [CONTRIBUTING.md](../CONTRIBUTING.md). We welcome:
- Bug reports
- Feature requests
- Pull requests
- Documentation improvements

---

## Comparison

### How is this different from MemGPT/Letta?

**Letta/MemGPT**: Full agent platform with built-in memory management, requires their infrastructure.

**Bardacle**: Lightweight daemon that works with any agent. You keep your existing agent, Bardacle just watches and summarizes.

### How is this different from RAG?

**RAG**: Retrieves relevant chunks from a knowledge base for each query.

**Bardacle**: Maintains a live summary of current session state. They're complementary - RAG for long-term knowledge, Bardacle for short-term continuity.

### How is this different from mem0?

**mem0**: Memory layer that requires OpenAI API, focuses on storing/retrieving memories.

**Bardacle**: Local-first, summarizes session state (not individual memories), works with any LLM.

---

Still have questions? [Open an issue](https://github.com/StellarSk8board/bardacle/issues)!
