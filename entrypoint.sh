#!/bin/bash
# OpenGrid entrypoint — switches between UI server and GRPO training
# based on the OPENGRID_MODE environment variable.
#
# OPENGRID_MODE=training  → runs GRPO training pipeline
# OPENGRID_MODE=server    → runs the FastAPI UI server (default)

set -e

MODE="${OPENGRID_MODE:-server}"

if [ "$MODE" = "training" ]; then
    echo "========================================"
    echo "  OpenGrid — GRPO Training Mode"
    echo "========================================"
    exec python run_training.py
else
    echo "========================================"
    echo "  OpenGrid — Control Room Server"
    echo "========================================"
    exec uvicorn app:app --host 0.0.0.0 --port 7860
fi
