"""Global pytest configuration and fixtures."""

import pytest
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import fixtures from storage base to make them globally available
from tests.storage.base.fixtures import (
    temp_storage_dir,
    mock_global_config,
    standard_test_dataset,
    mock_embedding_func,
    deterministic_embedding_func
)

# Re-export fixtures for global use
__all__ = [
    "temp_storage_dir",
    "mock_global_config",
    "standard_test_dataset",
    "mock_embedding_func",
    "deterministic_embedding_func"
]