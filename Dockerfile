# Hugging Face Docker Space — OpenGrid
# Set env OPENGRID_MODE=training for training mode.

FROM nvidia/cuda:12.1.1-runtime-ubuntu22.04

LABEL org.opencontainers.image.title="OpenGrid"
LABEL org.opencontainers.image.description="Renewable energy grid load-balancing environment"
LABEL openenv="true"

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 python3-pip python3.10-venv python3-dev \
    build-essential gcc g++ git && \
    ln -sf /usr/bin/python3.10 /usr/bin/python && \
    ln -sf /usr/bin/pip3 /usr/bin/pip && \
    rm -rf /var/lib/apt/lists/*

ENV CC=/usr/bin/gcc
ENV CXX=/usr/bin/g++

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# 1. Server deps
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. PyTorch 2.6.0 + CUDA 12.1
RUN pip install --no-cache-dir torch==2.6.0 --extra-index-url https://download.pytorch.org/whl/cu121

# 3. torchao 0.8.0 (compatible with torch 2.6, satisfies transformers import)
RUN pip install --no-cache-dir torchao==0.8.0

# 4. Training deps (no unsloth here)
COPY --chown=user requirements-training.txt .
RUN pip install --no-cache-dir -r requirements-training.txt

# 5. Unsloth --no-deps (avoids torchao>=0.13 conflict)
RUN pip install --no-cache-dir --no-deps unsloth==2025.11.1 unsloth_zoo

# --- App code ---
COPY --chown=user src/ /app/src/
COPY --chown=user training/ /app/training/
COPY --chown=user app.py run_training.py inference.py entrypoint.sh /app/
COPY --chown=user static/ /app/static/
COPY --chown=user pyproject.toml openenv.yaml /app/

RUN chmod +x entrypoint.sh

EXPOSE 7860

HEALTHCHECK --interval=60s --timeout=10s --start-period=600s \
    CMD python -c "import httpx; httpx.get('http://localhost:7860/health').raise_for_status()" || exit 1

CMD ["./entrypoint.sh"]
