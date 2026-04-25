# Hugging Face Docker Space — OpenGrid
# Docs: https://huggingface.co/docs/hub/spaces-sdks-docker
#
# This Dockerfile serves both the UI Space and the Training Space.
# Set OPENGRID_MODE=training to run GRPO training instead of the server.

FROM python:3.10-slim

LABEL org.opencontainers.image.title="OpenGrid"
LABEL org.opencontainers.image.description="Renewable energy grid load-balancing environment"
LABEL openenv="true"

# Create non-root user required by HF Spaces
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Install dependencies (both server and training)
COPY --chown=user requirements.txt .
COPY --chown=user requirements-training.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt \
    && pip install --no-cache-dir --upgrade -r requirements-training.txt

# Copy application code
COPY --chown=user . /app

# Make entrypoint executable
RUN chmod +x entrypoint.sh

# Default to server mode (override with OPENGRID_MODE=training)
ENV OPENGRID_MODE=server

# Expose HF Spaces default port
EXPOSE 7860

# Healthcheck (only applies in server mode)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import httpx; httpx.get('http://localhost:7860/health').raise_for_status()" || exit 1

# Entrypoint switches between server and training
CMD ["./entrypoint.sh"]
