"""Base test suites for all storage types."""

from .vector_suite import BaseVectorStorageTestSuite, VectorStorageContract
from .graph_suite import BaseGraphStorageTestSuite, GraphStorageContract
from .kv_suite import BaseKVStorageTestSuite, KVStorageContract
from .fixtures import (
    mock_embedding_func,
    deterministic_embedding_func,
    standard_test_dataset,
    temp_storage_dir,
    mock_global_config
)

__all__ = [
    "BaseVectorStorageTestSuite",
    "BaseGraphStorageTestSuite",
    "BaseKVStorageTestSuite",
    "VectorStorageContract",
    "GraphStorageContract",
    "KVStorageContract",
    "mock_embedding_func",
    "deterministic_embedding_func",
    "standard_test_dataset",
    "temp_storage_dir",
    "mock_global_config"
]