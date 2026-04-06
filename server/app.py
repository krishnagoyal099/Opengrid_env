"""
OpenGrid server entry point — used by openenv for multi-mode deployment.
Re-exports the FastAPI app from the root app module.
"""
import sys
import os
import uvicorn

# Add parent directory to path so we can import from the root package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app  # noqa: E402, F401


def main():
    """Entry point for openenv server mode."""
    uvicorn.run(app, host="0.0.0.0", port=7860)


if __name__ == "__main__":
    main()
