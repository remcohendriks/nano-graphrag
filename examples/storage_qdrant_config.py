"""
Example: Using Qdrant Vector Storage with GraphRAGConfig

This example demonstrates how to use Qdrant as the vector storage backend
with the new GraphRAGConfig configuration system.

Requirements:
- qdrant-client: pip install qdrant-client
- Running Qdrant instance: docker run -p 6333:6333 qdrant/qdrant

Environment variables (optional):
- QDRANT_URL: URL of Qdrant instance (default: http://localhost:6333)
- QDRANT_API_KEY: API key for Qdrant Cloud (optional)
"""

import asyncio
import os
from nano_graphrag import GraphRAG
from nano_graphrag.config import GraphRAGConfig, StorageConfig

# Optional: Set environment variables
# os.environ["QDRANT_URL"] = "http://localhost:6333"
# os.environ["OPENAI_API_KEY"] = "your-key-here"


async def main():
    """Main example function demonstrating Qdrant usage."""
    
    print("🚀 Initializing GraphRAG with Qdrant vector storage...")
    
    # Configure GraphRAG with Qdrant
    config = GraphRAGConfig(
        storage=StorageConfig(
            vector_backend="qdrant",  # Use Qdrant for vector storage
            qdrant_url="http://localhost:6333",  # Qdrant server URL
            # qdrant_api_key="your-api-key",  # Optional: for Qdrant Cloud
            # qdrant_collection_params={  # Optional: collection configuration
            #     "on_disk": True,  # Store vectors on disk for large datasets
            # }
        ),
        working_dir="./qdrant_graphrag_cache"  # Local cache directory
    )
    
    # Initialize GraphRAG
    rag = GraphRAG(config)
    
    print("📝 Inserting sample documents...")
    
    # Sample documents about technology companies
    documents = [
        "Apple Inc. is an American multinational technology company headquartered in Cupertino, California. "
        "It was founded by Steve Jobs, Steve Wozniak, and Ronald Wayne in 1976.",
        
        "Microsoft Corporation is an American multinational technology company headquartered in Redmond, Washington. "
        "It was founded by Bill Gates and Paul Allen in 1975.",
        
        "Google LLC is an American multinational technology company focusing on search engine technology, "
        "online advertising, cloud computing, and artificial intelligence. It was founded by Larry Page and Sergey Brin in 1998.",
        
        "Amazon.com, Inc. is an American multinational technology company focusing on e-commerce, cloud computing, "
        "and artificial intelligence. It was founded by Jeff Bezos in 1994.",
        
        "Tesla, Inc. is an American multinational automotive and clean energy company. "
        "It was founded by Martin Eberhard and Marc Tarpenning in 2003, with Elon Musk joining as an investor and chairman in 2004."
    ]
    
    # Insert documents
    for doc in documents:
        await rag.ainsert(doc)
        print(f"  ✓ Inserted: {doc[:50]}...")
    
    print("\n🔍 Querying the knowledge graph...\n")
    
    # Example queries
    queries = [
        "Who founded Apple?",
        "When was Microsoft founded?",
        "What companies did Elon Musk found or join?",
        "Which tech companies were founded in the 1990s?"
    ]
    
    for query in queries:
        print(f"❓ Question: {query}")
        
        # Query using local mode (searches within specific communities)
        answer = await rag.aquery(query, mode="local")
        print(f"💡 Answer: {answer}\n")
        print("-" * 50 + "\n")
    
    print("✅ Example complete!")
    print("\nNote: The Qdrant collection persists between runs.")
    print("To view your data, visit http://localhost:6333/dashboard")


async def test_connection():
    """Test if Qdrant is accessible."""
    try:
        from qdrant_client import AsyncQdrantClient
        client = AsyncQdrantClient(url="http://localhost:6333")
        await client.get_collections()
        await client.close()
        return True
    except Exception as e:
        print(f"❌ Could not connect to Qdrant: {e}")
        print("\n📋 To run Qdrant locally:")
        print("   docker run -p 6333:6333 qdrant/qdrant")
        return False


if __name__ == "__main__":
    # Check for required environment variables
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  Warning: OPENAI_API_KEY not set. Using mock mode or set your key:")
        print("   export OPENAI_API_KEY='your-key-here'")
        print()
    
    # Test Qdrant connection first
    print("🔌 Testing Qdrant connection...")
    if asyncio.run(test_connection()):
        print("✓ Qdrant is running!\n")
        # Run the main example
        asyncio.run(main())
    else:
        print("\n⚠️  Please start Qdrant before running this example.")