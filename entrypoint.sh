#!/bin/bash
# OpenGrid entrypoint — switches between UI server and GRPO training

set -e

# Dynamically find all pip-installed NVIDIA library paths
NVIDIA_LIBS=$(python -c "
import glob, os
paths = glob.glob('/home/user/.local/lib/python3.10/site-packages/nvidia/*/lib')
print(':'.join(paths))
" 2>/dev/null || echo "")

if [ -n "$NVIDIA_LIBS" ]; then
    export LD_LIBRARY_PATH="${NVIDIA_LIBS}:${LD_LIBRARY_PATH}"
    echo "Set LD_LIBRARY_PATH with NVIDIA libs: $NVIDIA_LIBS"
fi

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
