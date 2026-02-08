# Bardacle Docker Image
# A metacognitive layer for AI agents

FROM python:3.11-slim

LABEL maintainer="Bob & Blair"
LABEL description="Bardacle - A metacognitive layer for AI agents"
LABEL version="0.1.0"

# Set working directory
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY config.example.yaml ./config.example.yaml

# Create directories for runtime
RUN mkdir -p /data/transcripts /data/output /root/.bardacle

# Environment variables (can be overridden)
ENV BARDACLE_TRANSCRIPTS_DIR=/data/transcripts
ENV BARDACLE_STATE_FILE=/data/output/session-state.md
ENV PYTHONPATH=/app/src

# Default command
CMD ["python", "-m", "bardacle", "start"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -m bardacle status || exit 1
