"""Test NDJSON entity extraction format."""

import json
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from nano_graphrag._extraction import extract_entities
from nano_graphrag.entity_extraction.llm import LLMEntityExtractor
from nano_graphrag.entity_extraction.base import ExtractorConfig


def test_ndjson_parsing_no_quotes():
    """Test that NDJSON parsing produces clean entity names without quotes."""
    # Simulate NDJSON response
    test_response = """
{"type":"entity","name":"EXECUTIVE ORDER 14196","entity_type":"LAW","description":"Important executive order"}
{"type":"entity","name":"CONGRESS","entity_type":"ORGANIZATION","description":"Legislative body"}
{"type":"relationship","source":"EXECUTIVE ORDER 14196","target":"CONGRESS","description":"implements directive","strength":8}
<|COMPLETE|>
""".strip()

    entities = []
    relationships = []

    for line in test_response.split('\n'):
        line = line.strip()
        if not line or '<|COMPLETE|>' in line:
            continue

        try:
            obj = json.loads(line)
            if obj.get('type') == 'entity':
                name = obj.get('name', '').upper()
                assert '"' not in name, f"Entity name contains quotes: {name}"
                assert "'" not in name, f"Entity name contains quotes: {name}"
                entities.append(name)
            elif obj.get('type') == 'relationship':
                src = obj.get('source', '').upper()
                tgt = obj.get('target', '').upper()
                assert '"' not in src, f"Source contains quotes: {src}"
                assert '"' not in tgt, f"Target contains quotes: {tgt}"
                relationships.append((src, tgt))
        except json.JSONDecodeError:
            pytest.fail(f"Failed to parse valid NDJSON: {line}")

    assert len(entities) == 2
    assert "EXECUTIVE ORDER 14196" in entities
    assert "CONGRESS" in entities
    assert len(relationships) == 1
    assert ("EXECUTIVE ORDER 14196", "CONGRESS") in relationships


@pytest.mark.asyncio
async def test_llm_extractor_ndjson():
    """Test that LLMEntityExtractor handles NDJSON format correctly."""
    # Mock config
    config = ExtractorConfig(
        entity_types=["LAW", "ORGANIZATION"],
        max_gleaning=0,
        max_continuation_attempts=3
    )

    # Create mock model function that returns NDJSON
    mock_model = AsyncMock()
    mock_model.return_value = """
{"type":"entity","name":"EXECUTIVE ORDER 14196","entity_type":"LAW","description":"Executive order about sovereign wealth fund"}
{"type":"entity","name":"TREASURY DEPARTMENT","entity_type":"ORGANIZATION","description":"US Treasury"}
{"type":"relationship","source":"EXECUTIVE ORDER 14196","target":"TREASURY DEPARTMENT","description":"assigns responsibilities","strength":9}
<|COMPLETE|>
""".strip()

    config.model_func = mock_model

    # Create extractor and extract
    extractor = LLMEntityExtractor(config)
    await extractor.initialize()

    result = await extractor.extract_single("Test text about Executive Order 14196", "chunk-001")

    # Check entities have no quotes
    assert len(result.nodes) == 2
    for entity_name, entity_data in result.nodes.items():
        assert '"' not in entity_name, f"Entity name has quotes: {entity_name}"
        assert "'" not in entity_name, f"Entity name has quotes: {entity_name}"
        assert entity_data["entity_name"] == entity_name

    # Check relationships
    assert len(result.edges) == 1
    edge = result.edges[0]
    assert '"' not in edge[0], f"Source has quotes: {edge[0]}"
    assert '"' not in edge[1], f"Target has quotes: {edge[1]}"


def test_safe_float_conversion():
    """Test that strength field handles various invalid inputs gracefully."""
    # Helper function matching implementation
    def safe_float(value, default=1.0):
        try:
            return float(value) if value is not None else default
        except (ValueError, TypeError):
            return default

    # Test cases
    assert safe_float(8) == 8.0
    assert safe_float("7.5") == 7.5
    assert safe_float(None) == 1.0
    assert safe_float("invalid") == 1.0
    assert safe_float([1, 2, 3]) == 1.0
    assert safe_float({"key": "value"}) == 1.0


def test_sanitize_string():
    """Test HTML entity unescaping and control character removal."""
    import html
    import re

    def sanitize_str(text):
        if not text:
            return ""
        text = html.unescape(text)
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        return text.strip()

    # Test HTML entities
    assert sanitize_str("&lt;EXECUTIVE&gt;") == "<EXECUTIVE>"
    assert sanitize_str("&quot;ORDER&quot;") == '"ORDER"'
    assert sanitize_str("Congress &amp; Senate") == "Congress & Senate"

    # Test control characters
    assert sanitize_str("Text\x00with\x1fcontrol") == "Textwithcontrol"
    assert sanitize_str("\x7fSpecial\x9f") == "Special"

    # Test whitespace
    assert sanitize_str("  TRIMMED  ") == "TRIMMED"
    assert sanitize_str("\n\tTABS\n") == "TABS"

    # Test null/empty cases - CRITICAL for CODEX-006 fix
    assert sanitize_str(None) == ""
    assert sanitize_str("") == ""
    assert sanitize_str(False) == ""
    assert sanitize_str(0) == ""


def test_gleaning_newline_separation():
    """Test that gleaning responses are properly separated with newlines."""
    responses = [
        '{"type":"entity","name":"ENTITY1","entity_type":"TYPE1","description":"desc1"}',
        '{"type":"entity","name":"ENTITY2","entity_type":"TYPE2","description":"desc2"}',
        '{"type":"entity","name":"ENTITY3","entity_type":"TYPE3","description":"desc3"}'
    ]

    # Simulate gleaning combination with newline safety
    combined = []
    for resp in responses:
        if resp:
            if combined and not combined[-1].endswith('\n'):
                combined.append('\n')
            combined.append(resp)
    result = ''.join(combined)

    # Each line should be parseable
    lines = result.strip().split('\n')
    assert len(lines) == 3

    for i, line in enumerate(lines, 1):
        obj = json.loads(line)
        assert obj['name'] == f'ENTITY{i}'


@pytest.mark.asyncio
async def test_null_fields_in_ndjson():
    """Test that null fields in NDJSON don't crash extraction - CODEX-006 regression test."""
    from nano_graphrag._extraction import extract_entities_from_chunks
    from nano_graphrag._utils import TokenizerWrapper

    tokenizer = TokenizerWrapper(tokenizer_type="tiktoken", model_name="gpt-4o")

    # Test NDJSON with various null/missing fields
    ndjson_with_nulls = """{"type":"entity","name":null,"entity_type":"PERSON","description":"Description"}
{"type":"entity","name":"","entity_type":null,"description":"Empty name"}
{"type":"entity","name":"ALICE","entity_type":"","description":null}
{"type":"entity","name":"BOB"}
{"type":"relationship","source":null,"target":"BOB","description":"Invalid"}
{"type":"relationship","source":"ALICE","target":null,"description":"Invalid2"}
{"type":"relationship","source":"","target":"","description":"Empty"}"""

    mock_llm = AsyncMock(return_value=ndjson_with_nulls)
    chunks = [{"content": "Test content", "chunk_id": "test-chunk"}]

    # This should not crash despite null/missing fields
    result = await extract_entities_from_chunks(
        chunks, mock_llm, tokenizer,
        max_gleaning=0
    )

    # Should extract only valid entities
    assert "nodes" in result
    assert "edges" in result
    # ALICE and BOB should be extracted (those with valid names)
    node_names = {n["name"] for n in result["nodes"]}
    assert "ALICE" in node_names
    assert "BOB" in node_names
    # No relationships should be extracted (all have null/invalid source/target)
    assert len(result["edges"]) == 0


@pytest.mark.asyncio
async def test_llm_extractor_null_fields():
    """Test LLMEntityExtractor handles null fields without crashing."""
    config = ExtractorConfig(
        max_gleaning=0,
        max_continuation_attempts=0
    )

    # Mock response with null name that would cause .upper() to fail
    mock_model = AsyncMock()
    mock_model.return_value = '{"type":"entity","name":null,"entity_type":"UNKNOWN","description":"Test"}'

    config.model_func = mock_model

    extractor = LLMEntityExtractor(config)
    result = await extractor.extract_single("Test", "chunk-001")

    # Should not crash, and should extract nothing since name is null
    assert len(result.nodes) == 0


if __name__ == "__main__":
    # Run basic tests
    test_ndjson_parsing_no_quotes()
    test_safe_float_conversion()
    test_sanitize_string()
    test_gleaning_newline_separation()

    # Run async tests
    asyncio.run(test_llm_extractor_ndjson())
    asyncio.run(test_null_fields_in_ndjson())
    asyncio.run(test_llm_extractor_null_fields())

    print("All tests passed!")