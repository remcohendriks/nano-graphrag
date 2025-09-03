"""Test chunking operations."""

import pytest
from nano_graphrag._chunking import (
    chunking_by_token_size,
    chunking_by_separators,
    get_chunks,
    get_chunks_v2
)
from nano_graphrag._utils import TokenizerWrapper


@pytest.fixture
def tokenizer():
    """Create tokenizer fixture."""
    return TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4o")


class TestChunking:
    @pytest.mark.asyncio
    async def test_chunk_text_basic(self, tokenizer):
        """Test basic text chunking."""
        text = "This is a test. " * 100
        tokens = [tokenizer.encode(text)]
        doc_keys = ["doc-1"]
        
        chunks = chunking_by_token_size(
            tokens, doc_keys, tokenizer, 
            overlap_token_size=10, max_token_size=50
        )
        
        assert len(chunks) > 1
        assert all(c["tokens"] <= 50 for c in chunks)
        assert all(c["full_doc_id"] == "doc-1" for c in chunks)
        
    def test_chunk_overlap(self, tokenizer):
        """Test chunk overlap is maintained."""
        text = " ".join([f"word{i}" for i in range(100)])
        tokens = [tokenizer.encode(text)]
        doc_keys = ["doc-1"]
        
        chunks = chunking_by_token_size(
            tokens, doc_keys, tokenizer,
            overlap_token_size=5, max_token_size=20
        )
        
        # Check chunks have correct ordering
        for i, chunk in enumerate(chunks):
            assert chunk["chunk_order_index"] == i
            
    def test_chunking_by_separators(self, tokenizer):
        """Test separator-based chunking."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        tokens = [tokenizer.encode(text)]
        doc_keys = ["doc-1"]
        
        chunks = chunking_by_separators(
            tokens, doc_keys, tokenizer,
            overlap_token_size=5, max_token_size=50
        )
        
        assert len(chunks) > 0
        assert all(c["full_doc_id"] == "doc-1" for c in chunks)
        
    def test_get_chunks(self, tokenizer):
        """Test get_chunks function."""
        docs = {
            "doc-1": {"content": "This is document one. " * 50},
            "doc-2": {"content": "This is document two. " * 50}
        }
        
        chunks = get_chunks(
            docs, 
            chunking_by_token_size,
            tokenizer_wrapper=tokenizer,
            overlap_token_size=10,
            max_token_size=50
        )
        
        assert len(chunks) > 2  # Should have multiple chunks
        # Check chunk IDs are hashed
        assert all(k.startswith("chunk-") for k in chunks.keys())
        
    @pytest.mark.asyncio
    async def test_get_chunks_v2_single_text(self, tokenizer):
        """Test get_chunks_v2 with single text."""
        text = "This is a test text. " * 100
        
        chunks = await get_chunks_v2(
            text, tokenizer,
            chunking_by_token_size,
            size=50, overlap=10
        )
        
        assert len(chunks) > 1
        assert all("content" in c for c in chunks)
        assert all("tokens" in c for c in chunks)
        
    @pytest.mark.asyncio
    async def test_get_chunks_v2_multiple_texts(self, tokenizer):
        """Test get_chunks_v2 with multiple texts."""
        texts = [
            "First document. " * 50,
            "Second document. " * 50,
            "Third document. " * 50
        ]
        
        chunks = await get_chunks_v2(
            texts, tokenizer,
            chunking_by_token_size,
            size=50, overlap=10
        )
        
        # Should have chunks from all documents
        doc_ids = set(c["full_doc_id"] for c in chunks)
        assert len(doc_ids) == 3
        assert "doc-0" in doc_ids
        assert "doc-1" in doc_ids
        assert "doc-2" in doc_ids
        
    def test_empty_document(self, tokenizer):
        """Test handling of empty documents."""
        docs = {
            "doc-1": {"content": ""}
        }
        
        chunks = get_chunks(
            docs,
            chunking_by_token_size,
            tokenizer_wrapper=tokenizer
        )
        
        # Should handle empty content gracefully
        assert len(chunks) == 0 or all(c["content"] == "" for c in chunks.values())
        
    def test_chunk_size_boundaries(self, tokenizer):
        """Test chunking with exact size boundaries."""
        # Create text with known token count
        text = "word " * 100  # Approximately 100 tokens
        tokens = [tokenizer.encode(text)]
        doc_keys = ["doc-1"]
        
        # Chunk with size 25 and no overlap
        chunks = chunking_by_token_size(
            tokens, doc_keys, tokenizer,
            overlap_token_size=0, max_token_size=25
        )
        
        # Should create approximately 4 chunks
        assert 3 <= len(chunks) <= 5
        # Each chunk should be at most 25 tokens
        assert all(c["tokens"] <= 25 for c in chunks)