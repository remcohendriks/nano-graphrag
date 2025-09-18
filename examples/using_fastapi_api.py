#!/usr/bin/env python
"""Example of using the nano-graphrag FastAPI REST API."""

import httpx
import asyncio
import json


async def main():
    """Demonstrate API usage."""
    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        # Check health
        print("Checking health...")
        response = await client.get(f"{base_url}/health")
        print(f"Health: {response.json()}")

        # Insert a document
        print("\nInserting document...")
        doc_response = await client.post(
            f"{base_url}/documents",
            json={"content": "The quick brown fox jumps over the lazy dog. This is a test document about animals."}
        )
        print(f"Document inserted: {doc_response.json()}")

        # Batch insert
        print("\nBatch inserting documents...")
        batch_response = await client.post(
            f"{base_url}/documents/batch",
            json={
                "documents": [
                    {"content": "Python is a high-level programming language."},
                    {"content": "FastAPI is a modern web framework for building APIs."},
                    {"content": "GraphRAG combines graphs with retrieval augmented generation."}
                ]
            }
        )
        print(f"Batch result: {batch_response.json()}")

        # Wait a bit for processing
        await asyncio.sleep(2)

        # Query in different modes
        for mode in ["local", "global", "naive"]:
            print(f"\nQuerying in {mode} mode...")
            query_response = await client.post(
                f"{base_url}/query",
                json={
                    "question": "What programming concepts are mentioned?",
                    "mode": mode
                }
            )
            result = query_response.json()
            print(f"Mode: {result['mode']}")
            print(f"Answer: {result['answer'][:200]}...")
            print(f"Latency: {result['latency_ms']:.2f}ms")

        # Stream a query
        print("\nStreaming query...")
        async with client.stream(
            "POST",
            f"{base_url}/query/stream",
            json={"question": "Tell me about the documents", "mode": "local"}
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    if data["event"] == "chunk":
                        print(data["content"], end="", flush=True)
                    elif data["event"] == "complete":
                        print(f"\n\nStreaming complete. Latency: {data['latency_ms']:.2f}ms")

        # Get statistics
        print("\nGetting statistics...")
        stats_response = await client.get(f"{base_url}/stats")
        print(f"Stats: {stats_response.json()}")

        # Get system info
        print("\nGetting system info...")
        info_response = await client.get(f"{base_url}/info")
        info = info_response.json()
        print(f"Version: {info['nano_graphrag_version']}")
        print(f"Backends: {info['backends']}")


if __name__ == "__main__":
    asyncio.run(main())