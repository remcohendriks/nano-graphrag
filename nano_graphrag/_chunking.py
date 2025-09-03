"""Text chunking operations for nano-graphrag."""

from typing import Union
from ._splitter import SeparatorSplitter
from ._utils import compute_mdhash_id, TokenizerWrapper
from .base import TextChunkSchema
from .prompt import PROMPTS


def chunking_by_token_size(
    tokens_list: list[list[int]],
    doc_keys,
    tokenizer_wrapper: TokenizerWrapper, 
    overlap_token_size=128,
    max_token_size=1024,
):
    results = []
    for index, tokens in enumerate(tokens_list):
        chunk_token = []
        lengths = []
        for start in range(0, len(tokens), max_token_size - overlap_token_size):
            chunk_token.append(tokens[start : start + max_token_size])
            lengths.append(min(max_token_size, len(tokens) - start))


        chunk_texts = tokenizer_wrapper.decode_batch(chunk_token)

        for i, chunk in enumerate(chunk_texts):
            results.append(
                {
                    "tokens": lengths[i],
                    "content": chunk.strip(),
                    "chunk_order_index": i,
                    "full_doc_id": doc_keys[index],
                }
            )
    return results


def chunking_by_separators(
    tokens_list: list[list[int]],
    doc_keys,
    tokenizer_wrapper: TokenizerWrapper,
    overlap_token_size=128,
    max_token_size=1024,
):
    # *** Modified ***: Use wrapper encoding directly instead of getting underlying tokenizer
    separators = [tokenizer_wrapper.encode(s) for s in PROMPTS["default_text_separator"]]
    splitter = SeparatorSplitter(
        separators=separators,
        chunk_size=max_token_size,
        chunk_overlap=overlap_token_size,
    )
    results = []
    for index, tokens in enumerate(tokens_list):
        chunk_tokens = splitter.split_tokens(tokens)
        lengths = [len(c) for c in chunk_tokens]

        decoded_chunks = tokenizer_wrapper.decode_batch(chunk_tokens)
        for i, chunk in enumerate(decoded_chunks):
            results.append(
                {
                    "tokens": lengths[i],
                    "content": chunk.strip(),
                    "chunk_order_index": i,
                    "full_doc_id": doc_keys[index],
                }
            )
    return results


def get_chunks(new_docs, chunk_func=chunking_by_token_size, tokenizer_wrapper: TokenizerWrapper = None, **chunk_func_params):
    inserting_chunks = {}
    new_docs_list = list(new_docs.items())
    docs = [new_doc[1]["content"] for new_doc in new_docs_list]
    doc_keys = [new_doc[0] for new_doc in new_docs_list]

    tokens = [tokenizer_wrapper.encode(doc) for doc in docs]
    chunks = chunk_func(
        tokens, doc_keys=doc_keys, tokenizer_wrapper=tokenizer_wrapper, overlap_token_size=chunk_func_params.get("overlap_token_size", 128), max_token_size=chunk_func_params.get("max_token_size", 1024)
    )
    for chunk in chunks:
        # Include doc_id in hash to prevent cross-document chunk collisions
        chunk_id_content = f"{chunk['full_doc_id']}::{chunk['content']}"
        inserting_chunks.update(
            {compute_mdhash_id(chunk_id_content, prefix="chunk-"): chunk}
        )
    return inserting_chunks


async def get_chunks_v2(
    text_or_texts: Union[str, list[str]],
    tokenizer_wrapper: TokenizerWrapper,
    chunk_func=chunking_by_token_size,
    size: int = 1200,
    overlap: int = 100
) -> list[TextChunkSchema]:
    """Get chunks from text(s) - clean API for new config system.
    
    Args:
        text_or_texts: Single text or list of texts to chunk
        tokenizer_wrapper: Tokenizer for encoding
        chunk_func: Function to perform chunking
        size: Maximum token size per chunk
        overlap: Token overlap between chunks
        
    Returns:
        List of chunk dictionaries with content and metadata
    """
    texts = [text_or_texts] if isinstance(text_or_texts, str) else list(text_or_texts)
    tokens = [tokenizer_wrapper.encode(t) for t in texts]
    doc_keys = [f"doc-{i}" for i in range(len(texts))]
    
    chunks = chunk_func(
        tokens,
        doc_keys=doc_keys,
        tokenizer_wrapper=tokenizer_wrapper,
        overlap_token_size=overlap,
        max_token_size=size
    )
    return chunks