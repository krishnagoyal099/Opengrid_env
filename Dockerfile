# Hugging Face Docker Space — OpenGrid
# Docs: https://huggingface.co/docs/hub/spaces-sdks-docker

FROM python:3.10-slim

LABEL org.opencontainers.image.title="OpenGrid"
LABEL org.opencontainers.image.description="Renewable energy grid load-balancing environment"
LABEL openenv="true"

# Create non-root user required by HF Spaces
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Install dependencies
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy application code
COPY --chown=user . /app

# Expose HF Spaces default port
EXPOSE 7860

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import httpx; httpx.get('http://localhost:7860/health').raise_for_status()" || exit 1

# Run the server
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
