#!/usr/bin/env python
"""Run the FastAPI server."""

import uvicorn
import sys
import os

# Add parent directory to path for development
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """Run the FastAPI application."""
    uvicorn.run(
        "nano_graphrag.api.app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()