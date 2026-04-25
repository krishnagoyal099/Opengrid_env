# OpenGrid GRPO Training Space — Runs on A10G GPU
# After training completes, serves results on port 7860

FROM python:3.10-slim

LABEL org.opencontainers.image.title="OpenGrid GRPO Training"
LABEL org.opencontainers.image.description="GRPO training for power grid multi-agent controller"

RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Install training dependencies
COPY --chown=user requirements-training.txt .
RUN pip install --no-cache-dir --upgrade -r requirements-training.txt

# Copy application code
COPY --chown=user . /app

# Training entrypoint: runs GRPO then serves results
EXPOSE 7860
CMD ["python", "run_training.py"]
