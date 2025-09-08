"""Storage module with lazy loading support."""

from typing import TYPE_CHECKING

# Always import factory and registration (lightweight)
from .factory import StorageFactory, _register_backends

# Type checking imports (no runtime cost)
if TYPE_CHECKING:
    from .gdb_networkx import NetworkXStorage
    from .gdb_neo4j import Neo4jStorage
    from .vdb_hnswlib import HNSWVectorStorage
    from .vdb_nanovectordb import NanoVectorDBStorage
    from .kv_json import JsonKVStorage


def __getattr__(name):
    """Lazy import storage backends for backward compatibility."""
    if name == "NetworkXStorage":
        from .gdb_networkx import NetworkXStorage
        return NetworkXStorage
    elif name == "Neo4jStorage":
        from .gdb_neo4j import Neo4jStorage
        return Neo4jStorage
    elif name == "HNSWVectorStorage":
        from .vdb_hnswlib import HNSWVectorStorage
        return HNSWVectorStorage
    elif name == "NanoVectorDBStorage":
        from .vdb_nanovectordb import NanoVectorDBStorage
        return NanoVectorDBStorage
    elif name == "JsonKVStorage":
        from .kv_json import JsonKVStorage
        return JsonKVStorage
    else:
        raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "StorageFactory",
    "_register_backends",
    "NetworkXStorage",
    "Neo4jStorage", 
    "HNSWVectorStorage",
    "NanoVectorDBStorage",
    "JsonKVStorage",
]