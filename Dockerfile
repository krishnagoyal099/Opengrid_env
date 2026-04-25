# Hugging Face Docker Space — OpenGrid
# Serves both the UI dashboard AND GRPO training.
# Set env OPENGRID_MODE=training for training mode.

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

LABEL org.opencontainers.image.title="OpenGrid"
LABEL org.opencontainers.image.description="Renewable energy grid load-balancing environment"
LABEL openenv="true"

# Install Python 3.10 and build tools (needed by Triton/Unsloth)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-venv build-essential && \
    ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip && \
    rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# --- Dependencies ---
# Install server deps first (cached across builds)
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Install PyTorch with CUDA support (must come before training deps)
RUN pip install --no-cache-dir torch==2.5.1 --extra-index-url https://download.pytorch.org/whl/cu121

# Install training deps (only re-runs if training reqs change)
COPY --chown=user requirements-training.txt .
RUN pip install --no-cache-dir --upgrade --no-deps -r requirements-training.txt

# --- Application code (selective COPY for lean images) ---
# Core Python modules
COPY --chown=user src/ /app/src/
COPY --chown=user training/ /app/training/

# Entry points
COPY --chown=user app.py /app/
COPY --chown=user run_training.py /app/
COPY --chown=user inference.py /app/
COPY --chown=user entrypoint.sh /app/

# Frontend (small, needed for server mode)
COPY --chown=user static/ /app/static/

# Config
COPY --chown=user pyproject.toml /app/
COPY --chown=user openenv.yaml /app/

RUN chmod +x entrypoint.sh

# Default mode controlled by OPENGRID_MODE env var (set via HF secrets)
# server = FastAPI UI, training = GRPO pipeline
EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=10s --start-period=600s \
    CMD python -c "import httpx; httpx.get('http://localhost:7860/health').raise_for_status()" || exit 1

CMD ["./entrypoint.sh"]
