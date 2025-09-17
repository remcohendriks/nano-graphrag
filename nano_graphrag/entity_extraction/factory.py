"""Factory for creating entity extractors based on strategy."""

import importlib
from typing import Optional, Any

from .base import BaseEntityExtractor, ExtractorConfig
from nano_graphrag._utils import logger


def create_extractor(
    strategy: str,
    model_func: Optional[Any] = None,
    model_name: Optional[str] = None,
    entity_types: Optional[list] = None,
    max_gleaning: int = 1,
    max_continuation_attempts: int = 5,
    summary_max_tokens: int = 500,
    custom_extractor_class: Optional[str] = None,
    **kwargs
) -> BaseEntityExtractor:
    """Create an entity extractor based on the specified strategy.

    Args:
        strategy: Extraction strategy ("llm", "dspy", or custom class path)
        model_func: LLM function for extraction
        model_name: Model name for DSPy
        entity_types: List of entity types to extract
        max_gleaning: Number of gleaning iterations for LLM
        max_continuation_attempts: Max attempts to continue truncated extraction
        summary_max_tokens: Max tokens for summaries
        custom_extractor_class: Import path for custom extractor
        **kwargs: Additional strategy-specific parameters

    Returns:
        Configured entity extractor instance
    """
    # Build config
    config = ExtractorConfig(
        entity_types=entity_types or [
            "PERSON", "ORGANIZATION", "LOCATION", "EVENT", "CONCEPT"
        ],
        max_gleaning=max_gleaning,
        max_continuation_attempts=max_continuation_attempts,
        summary_max_tokens=summary_max_tokens,
        model_func=model_func,
        model_name=model_name,
        strategy_params=kwargs
    )

    strategy = strategy.lower()

    if strategy == "llm":
        logger.info("Creating LLM entity extractor")
        from .llm import LLMEntityExtractor
        return LLMEntityExtractor(config)

    elif strategy == "dspy":
        logger.info("Creating DSPy entity extractor")
        from .dspy_extractor import DSPyEntityExtractor
        return DSPyEntityExtractor(config)

    elif custom_extractor_class:
        logger.info(f"Creating custom entity extractor: {custom_extractor_class}")
        # Import custom extractor
        try:
            module_path, class_name = custom_extractor_class.rsplit(".", 1)
            module = importlib.import_module(module_path)
            extractor_class = getattr(module, class_name)

            if not issubclass(extractor_class, BaseEntityExtractor):
                raise ValueError(
                    f"Custom extractor {custom_extractor_class} must inherit from BaseEntityExtractor"
                )

            return extractor_class(config)

        except (ImportError, AttributeError, ValueError) as e:
            raise ValueError(f"Failed to load custom extractor {custom_extractor_class}: {e}")

    else:
        raise ValueError(
            f"Unknown extraction strategy: {strategy}. "
            "Use 'llm', 'dspy', or provide custom_extractor_class"
        )