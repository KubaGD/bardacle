# Contributing to Bardacle

Thanks for your interest in contributing! 🐚

## Ways to Contribute

### Bug Reports
- Use GitHub Issues
- Include: Python version, OS, config, steps to reproduce
- Paste relevant logs (redact sensitive info)

### Feature Requests
- Open an issue with `[Feature]` prefix
- Describe the use case and proposed solution

### Code Contributions
1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Test locally: `python -m bardacle test`
5. Submit a pull request

## Code Style

- Python 3.10+
- Type hints where practical
- Docstrings for public functions
- Keep it simple

## Testing

```bash
# Run the test suite
python -m bardacle test

# Manual testing
python -m bardacle update --full
```

## Transcript Adapters

Want to support a new agent framework? Create an adapter:

1. Add a new file in `src/adapters/`
2. Implement `read_transcript(path) -> List[Dict]`
3. Document the expected format
4. Submit a PR

## Questions?

Open an issue or reach out!

---

*Created with 💀 by Bob*
