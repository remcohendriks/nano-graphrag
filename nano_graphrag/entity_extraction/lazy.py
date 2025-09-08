"""Lazy loading wrapper for entity extraction module.

This module provides lazy loading of DSPy-dependent entity extraction functionality.
"""

from typing import TYPE_CHECKING, Optional, Any
from nano_graphrag._utils import ensure_dependency

if TYPE_CHECKING:
    from .module import TypedEntityRelationshipExtractor


class LazyEntityExtractor:
    """Lazy loader for TypedEntityRelationshipExtractor.
    
    This wrapper defers the import of DSPy until the extractor is actually used,
    improving import times when entity extraction is not needed.
    """
    
    def __init__(self, **kwargs):
        """Initialize with parameters to pass to the actual extractor.
        
        Args:
            **kwargs: Arguments to pass to TypedEntityRelationshipExtractor
        """
        self._kwargs = kwargs
        self._extractor: Optional[Any] = None
        
    @property
    def extractor(self):
        """Get the actual extractor, loading DSPy if needed."""
        if self._extractor is None:
            # Check for dspy dependency
            ensure_dependency(
                "dspy",
                "dspy",  # Correct package name per official docs
                "typed entity extraction"
            )
            # Now safe to import
            from .module import TypedEntityRelationshipExtractor
            self._extractor = TypedEntityRelationshipExtractor(**self._kwargs)
        return self._extractor
    
    def forward(self, input_text: str) -> Any:
        """Forward pass through the extractor.
        
        Args:
            input_text: Text to extract entities from
            
        Returns:
            dspy.Prediction with entities and relationships
        """
        return self.extractor.forward(input_text)
    
    def __getattr__(self, name):
        """Delegate attribute access to the actual extractor."""
        return getattr(self.extractor, name)


def get_entity_extractor(**kwargs) -> LazyEntityExtractor:
    """Factory function to create a lazy entity extractor.
    
    Args:
        **kwargs: Arguments for TypedEntityRelationshipExtractor
        
    Returns:
        LazyEntityExtractor that will load DSPy when needed
    """
    return LazyEntityExtractor(**kwargs)