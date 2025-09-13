"""Examples of different entity extraction strategies in nano-graphrag."""

import asyncio
import os
from pathlib import Path
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, EntityExtractionConfig, StorageConfig
from nano_graphrag.entity_extraction.base import BaseEntityExtractor, ExtractionResult
import re

# Sample text for extraction
SAMPLE_TEXT = """
Steve Jobs co-founded Apple Inc. with Steve Wozniak in 1976 in Cupertino, California.
Apple revolutionized personal computing with the Macintosh in 1984 and later dominated
the mobile market with the iPhone in 2007. Under Jobs' leadership, Apple became one of
the most valuable companies in the world. Tim Cook succeeded Jobs as CEO in 2011.
"""

def setup_test_env(strategy_name: str):
    """Setup a test environment with temporary storage."""
    import tempfile
    temp_dir = tempfile.mkdtemp(prefix=f"nano_graphrag_{strategy_name}_")
    return temp_dir


async def example_llm_extraction():
    """Example using LLM-based extraction with gleaning."""
    print("=" * 60)
    print("LLM-BASED EXTRACTION EXAMPLE")
    print("=" * 60)

    # Setup temporary storage
    working_dir = setup_test_env("llm")

    # Configure LLM extraction
    config = GraphRAGConfig(
        storage=StorageConfig(working_dir=working_dir),
        entity_extraction=EntityExtractionConfig(
            strategy="llm",
            max_gleaning=1,  # Use 1 gleaning iteration for better results
            summary_max_tokens=300
        )
    )

    # Initialize GraphRAG
    rag = GraphRAG(config)

    # Insert sample text
    print(f"\nInserting text ({len(SAMPLE_TEXT)} chars)...")
    await rag.ainsert(SAMPLE_TEXT)

    # Query the knowledge graph
    print("\nQuerying: 'Who founded Apple?'")
    result = await rag.aquery("Who founded Apple?")
    print(f"Result: {result}")

    print("\nQuerying: 'Who is the current CEO?'")
    result = await rag.aquery("Who is the current CEO of Apple?")
    print(f"Result: {result}")

    print(f"\nWorking directory: {working_dir}")
    print("(Graph and entities saved here)")


async def example_dspy_extraction():
    """Example using DSPy extraction (requires dspy-ai package)."""
    print("\n" + "=" * 60)
    print("DSPY-BASED EXTRACTION EXAMPLE")
    print("=" * 60)

    try:
        import dspy
    except ImportError:
        print("DSPy not installed. Install with: pip install dspy-ai")
        return

    # Setup temporary storage
    working_dir = setup_test_env("dspy")

    # Configure DSPy extraction
    config = GraphRAGConfig(
        storage=StorageConfig(working_dir=working_dir),
        entity_extraction=EntityExtractionConfig(
            strategy="dspy",
            max_gleaning=0  # DSPy handles its own refinement
        )
    )

    # Initialize GraphRAG
    rag = GraphRAG(config)

    # Insert sample text
    print(f"\nInserting text ({len(SAMPLE_TEXT)} chars)...")
    await rag.ainsert(SAMPLE_TEXT)

    # Query the knowledge graph
    print("\nQuerying: 'What products did Apple create?'")
    result = await rag.aquery("What products did Apple create?")
    print(f"Result: {result}")

    print(f"\nWorking directory: {working_dir}")


async def example_custom_extraction():
    """Example using custom extraction logic for domain-specific patterns."""
    print("\n" + "=" * 60)
    print("CUSTOM EXTRACTION EXAMPLE")
    print("=" * 60)

    # Define a custom extractor for tech domain
    class TechDomainExtractor(BaseEntityExtractor):
        """Custom extractor for technology domain entities."""

        async def _initialize_impl(self):
            """Initialize any resources (models, regex patterns, etc.)."""
            # Define patterns for tech entities
            self.company_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Inc\.|Corp\.|LLC|Company))\b')
            self.product_pattern = re.compile(r'\b(iPhone|iPad|MacBook|Macintosh|Apple Watch|AirPods)\b', re.I)
            self.year_pattern = re.compile(r'\b(19|20)\d{2}\b')
            self.person_pattern = re.compile(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b')

        async def extract_single(self, text: str, chunk_id: str = None):
            """Extract entities using regex patterns."""
            nodes = {}
            edges = []

            # Extract companies
            companies = self.company_pattern.findall(text)
            for company in companies:
                node_id = company.upper()
                nodes[node_id] = {
                    "entity_name": node_id,
                    "entity_type": "ORGANIZATION",
                    "description": f"Technology company: {company}",
                    "source_id": chunk_id
                }

            # Extract products
            products = self.product_pattern.findall(text)
            for product in products:
                node_id = product.upper()
                nodes[node_id] = {
                    "entity_name": node_id,
                    "entity_type": "PRODUCT",
                    "description": f"Technology product: {product}",
                    "source_id": chunk_id
                }

            # Extract people (simple heuristic)
            people = self.person_pattern.findall(text)
            for person in people:
                # Filter out common non-person matches
                if person not in companies and not any(word in person for word in ['Apple', 'Microsoft', 'Google']):
                    node_id = person.upper()
                    nodes[node_id] = {
                        "entity_name": node_id,
                        "entity_type": "PERSON",
                        "description": f"Person: {person}",
                        "source_id": chunk_id
                    }

            # Extract years as events
            years = self.year_pattern.findall(text)
            for year in years:
                node_id = f"YEAR_{year}"
                nodes[node_id] = {
                    "entity_name": node_id,
                    "entity_type": "EVENT",
                    "description": f"Year: {year}",
                    "source_id": chunk_id
                }

            # Create relationships between companies and products
            for company in companies:
                for product in products:
                    edges.append((
                        company.upper(),
                        product.upper(),
                        {
                            "weight": 1.0,
                            "description": "produces",
                            "source_id": chunk_id
                        }
                    ))

            # Create relationships between people and companies
            for person in people:
                if person not in companies:
                    for company in companies:
                        if person in text and company in text:
                            edges.append((
                                person.upper(),
                                company.upper(),
                                {
                                    "weight": 1.0,
                                    "description": "associated with",
                                    "source_id": chunk_id
                                }
                            ))

            return ExtractionResult(
                nodes=nodes,
                edges=edges,
                metadata={"chunk_id": chunk_id, "method": "custom_regex"}
            )

        async def extract(self, chunks, storage=None):
            """Extract from multiple chunks."""
            results = []
            for chunk_id, chunk_data in chunks.items():
                result = await self.extract_single(chunk_data.get("content", ""), chunk_id)
                results.append(result)
            return self.deduplicate_entities(results)

    # Setup temporary storage
    working_dir = setup_test_env("custom")

    # Create the custom extractor instance
    from nano_graphrag.entity_extraction.factory import create_extractor
    from nano_graphrag.entity_extraction.base import ExtractorConfig

    # Register the custom extractor
    import sys
    sys.modules['__main__'].TechDomainExtractor = TechDomainExtractor

    # Use factory to create with custom class
    config = GraphRAGConfig(
        storage=StorageConfig(working_dir=working_dir),
        entity_extraction=EntityExtractionConfig(
            strategy="llm"  # Will be overridden by custom
        )
    )

    # Initialize GraphRAG with custom extractor
    rag = GraphRAG(config)

    # Override with custom extractor
    custom_config = ExtractorConfig()
    rag.entity_extractor = TechDomainExtractor(custom_config)
    await rag.entity_extractor.initialize()

    # Insert sample text
    print(f"\nInserting text ({len(SAMPLE_TEXT)} chars)...")
    await rag.ainsert(SAMPLE_TEXT)

    print("\nExtracted entities using custom patterns:")
    # Read the graph to show what was extracted
    graph = rag.chunk_entity_relation_graph
    nodes = await graph.nodes()
    print(f"- Found {len(nodes)} entities")
    for node in sorted(nodes)[:10]:  # Show first 10
        node_data = await graph.get_node(node)
        print(f"  - {node}: {node_data.get('entity_type', 'UNKNOWN')}")

    print(f"\nWorking directory: {working_dir}")


async def compare_strategies():
    """Compare extraction results across different strategies."""
    print("\n" + "=" * 60)
    print("STRATEGY COMPARISON")
    print("=" * 60)

    strategies = ["llm"]  # Start with LLM

    # Add DSPy if available
    try:
        import dspy
        strategies.append("dspy")
    except ImportError:
        print("(DSPy not available for comparison)")

    results_summary = {}

    for strategy in strategies:
        print(f"\n--- Testing {strategy.upper()} strategy ---")

        working_dir = setup_test_env(f"compare_{strategy}")

        config = GraphRAGConfig(
            storage=StorageConfig(working_dir=working_dir),
            entity_extraction=EntityExtractionConfig(
                strategy=strategy,
                max_gleaning=1 if strategy == "llm" else 0
            )
        )

        rag = GraphRAG(config)

        # Insert and extract
        await rag.ainsert(SAMPLE_TEXT)

        # Count entities and relationships
        graph = rag.chunk_entity_relation_graph
        nodes = await graph.nodes()
        edges = await graph.edges()

        results_summary[strategy] = {
            "entities": len(nodes),
            "relationships": len(edges)
        }

        print(f"  Entities: {len(nodes)}")
        print(f"  Relationships: {len(edges)}")

    print("\n--- Summary ---")
    for strategy, counts in results_summary.items():
        print(f"{strategy.upper()}: {counts['entities']} entities, {counts['relationships']} relationships")


async def main():
    """Run all examples."""
    print("NANO-GRAPHRAG ENTITY EXTRACTION EXAMPLES")
    print("=" * 60)

    # Run examples
    await example_llm_extraction()
    await example_dspy_extraction()
    await example_custom_extraction()
    await compare_strategies()

    print("\n" + "=" * 60)
    print("All examples completed!")
    print("Check the temporary directories for generated graphs.")


if __name__ == "__main__":
    # Ensure we have an API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable")
        exit(1)

    # Run examples
    asyncio.run(main())