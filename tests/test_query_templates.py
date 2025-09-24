"""Test configurable query response templates."""

import pytest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from nano_graphrag._query import _load_template, _validate_template, local_query, global_query
from nano_graphrag.config import QueryConfig
from nano_graphrag.base import QueryParam


class TestTemplateUtilities:
    def test_load_template_none(self):
        """Test loading with None returns None."""
        assert _load_template(None) is None

    def test_load_template_inline(self):
        """Test inline template returns as-is."""
        template = "Test template with {placeholder}"
        assert _load_template(template) == template

    def test_load_template_from_file(self, tmp_path):
        """Test loading template from file."""
        template_content = "File template with {context_data} and {response_type}"
        template_file = tmp_path / "template.txt"
        template_file.write_text(template_content)

        result = _load_template(str(template_file))
        assert result == template_content

    def test_load_template_file_not_found(self):
        """Test loading non-existent file returns None with warning."""
        with patch('nano_graphrag._query.logger') as mock_logger:
            result = _load_template("./nonexistent.txt")
            assert result is None
            mock_logger.warning.assert_called()

    def test_validate_template_valid(self):
        """Test validation with all required placeholders."""
        template = "Context: {context_data}\nType: {response_type}"
        assert _validate_template(template, ['context_data', 'response_type']) is True

    def test_validate_template_missing_placeholder(self):
        """Test validation fails when placeholder missing."""
        template = "Only has {context_data}"
        with patch('nano_graphrag._query.logger') as mock_logger:
            assert _validate_template(template, ['context_data', 'response_type']) is False
            mock_logger.warning.assert_called()

    def test_validate_template_extra_placeholders(self):
        """Test validation passes with extra placeholders."""
        template = "Has {context_data}, {response_type}, and {extra}"
        assert _validate_template(template, ['context_data', 'response_type']) is True

    def test_template_format_with_extra_placeholders(self):
        """Test that format fails with KeyError when extra placeholders present."""
        template = "Context: {context_data}\nType: {response_type}\nExtra: {undefined_var}"

        assert _validate_template(template, ['context_data', 'response_type']) is True

        with pytest.raises(KeyError):
            template.format(context_data="test", response_type="test")


@pytest.mark.asyncio
class TestLocalQueryTemplates:
    async def test_local_query_default_template(self):
        """Test local query uses default template when no custom configured."""
        mock_kg = AsyncMock()
        mock_entities_vdb = AsyncMock()
        mock_community_reports = AsyncMock()
        mock_text_chunks = AsyncMock()
        mock_tokenizer = MagicMock()

        with patch('nano_graphrag._query._build_local_query_context') as mock_build:
            mock_build.return_value = "Test context"

            global_config = {
                'best_model_func': AsyncMock(return_value="Response"),
                'query_config': QueryConfig()
            }

            result = await local_query(
                "test query",
                mock_kg,
                mock_entities_vdb,
                mock_community_reports,
                mock_text_chunks,
                QueryParam(),
                mock_tokenizer,
                global_config
            )

            global_config['best_model_func'].assert_called_once()
            call_args = global_config['best_model_func'].call_args
            assert 'You are a helpful assistant' in call_args[1]['system_prompt']

    async def test_local_query_custom_inline_template(self):
        """Test local query uses custom inline template."""
        custom_template = "Custom prompt: {context_data}\nFormat: {response_type}"

        mock_kg = AsyncMock()
        mock_entities_vdb = AsyncMock()
        mock_community_reports = AsyncMock()
        mock_text_chunks = AsyncMock()
        mock_tokenizer = MagicMock()

        with patch('nano_graphrag._query._build_local_query_context') as mock_build:
            mock_build.return_value = "Test context"

            global_config = {
                'best_model_func': AsyncMock(return_value="Response"),
                'query_config': QueryConfig(local_template=custom_template)
            }

            result = await local_query(
                "test query",
                mock_kg,
                mock_entities_vdb,
                mock_community_reports,
                mock_text_chunks,
                QueryParam(),
                mock_tokenizer,
                global_config
            )

            global_config['best_model_func'].assert_called_once()
            call_args = global_config['best_model_func'].call_args
            expected_prompt = custom_template.format(
                context_data="Test context",
                response_type="Multiple Paragraphs"
            )
            assert call_args[1]['system_prompt'] == expected_prompt

    async def test_local_query_custom_file_template(self, tmp_path):
        """Test local query uses custom file template."""
        template_content = "File-based template\nContext: {context_data}\nType: {response_type}"
        template_file = tmp_path / "local.txt"
        template_file.write_text(template_content)

        mock_kg = AsyncMock()
        mock_entities_vdb = AsyncMock()
        mock_community_reports = AsyncMock()
        mock_text_chunks = AsyncMock()
        mock_tokenizer = MagicMock()

        with patch('nano_graphrag._query._build_local_query_context') as mock_build:
            mock_build.return_value = "Test context"

            global_config = {
                'best_model_func': AsyncMock(return_value="Response"),
                'query_config': QueryConfig(local_template=str(template_file))
            }

            result = await local_query(
                "test query",
                mock_kg,
                mock_entities_vdb,
                mock_community_reports,
                mock_text_chunks,
                QueryParam(),
                mock_tokenizer,
                global_config
            )

            global_config['best_model_func'].assert_called_once()
            call_args = global_config['best_model_func'].call_args
            expected_prompt = template_content.format(
                context_data="Test context",
                response_type="Multiple Paragraphs"
            )
            assert call_args[1]['system_prompt'] == expected_prompt

    async def test_local_query_invalid_template_fallback(self):
        """Test local query falls back to default when template invalid."""
        invalid_template = "Missing placeholders template"

        mock_kg = AsyncMock()
        mock_entities_vdb = AsyncMock()
        mock_community_reports = AsyncMock()
        mock_text_chunks = AsyncMock()
        mock_tokenizer = MagicMock()

        with patch('nano_graphrag._query._build_local_query_context') as mock_build:
            mock_build.return_value = "Test context"

            global_config = {
                'best_model_func': AsyncMock(return_value="Response"),
                'query_config': QueryConfig(local_template=invalid_template)
            }

            with patch('nano_graphrag._query.logger') as mock_logger:
                result = await local_query(
                    "test query",
                    mock_kg,
                    mock_entities_vdb,
                    mock_community_reports,
                    mock_text_chunks,
                    QueryParam(),
                    mock_tokenizer,
                    global_config
                )

                mock_logger.warning.assert_called()
                global_config['best_model_func'].assert_called_once()
                call_args = global_config['best_model_func'].call_args
                assert 'You are a helpful assistant' in call_args[1]['system_prompt']

    async def test_local_query_extra_placeholders_fallback(self):
        """Test local query falls back to default when template has extra placeholders."""
        template_with_extra = "Context: {context_data}\nType: {response_type}\nExtra: {undefined_var}"

        mock_kg = AsyncMock()
        mock_entities_vdb = AsyncMock()
        mock_community_reports = AsyncMock()
        mock_text_chunks = AsyncMock()
        mock_tokenizer = MagicMock()

        with patch('nano_graphrag._query._build_local_query_context') as mock_build:
            mock_build.return_value = "Test context"

            global_config = {
                'best_model_func': AsyncMock(return_value="Response"),
                'query_config': QueryConfig(local_template=template_with_extra)
            }

            with patch('nano_graphrag._query.logger') as mock_logger:
                result = await local_query(
                    "test query",
                    mock_kg,
                    mock_entities_vdb,
                    mock_community_reports,
                    mock_text_chunks,
                    QueryParam(),
                    mock_tokenizer,
                    global_config
                )

                assert any('formatting failed' in str(call) for call in mock_logger.warning.call_args_list)
                global_config['best_model_func'].assert_called_once()
                call_args = global_config['best_model_func'].call_args
                assert 'You are a helpful assistant' in call_args[1]['system_prompt']


@pytest.mark.asyncio
class TestGlobalQueryTemplates:
    async def test_global_query_custom_template(self):
        """Test global query uses custom template in _map_global_communities."""
        custom_template = "Global analysis:\n{context_data}"

        mock_kg = AsyncMock()
        mock_kg.community_schema.return_value = {}
        mock_kg.nodes_to_fetch_batch.return_value = []
        mock_entities_vdb = AsyncMock()
        mock_entities_vdb.retrieval_with_scores.return_value = []
        mock_community_reports = AsyncMock()
        mock_community_reports.get_storage_keys.return_value = []
        mock_text_chunks = AsyncMock()
        mock_tokenizer = MagicMock()

        global_config = {
            'best_model_func': AsyncMock(return_value='{"points": []}'),
            'cheap_model_func': AsyncMock(return_value="Summary"),
            'convert_response_to_json_func': lambda x: {"points": []},
            'query_config': QueryConfig(global_template=custom_template)
        }

        result = await global_query(
            "test query",
            mock_kg,
            mock_entities_vdb,
            mock_community_reports,
            mock_text_chunks,
            QueryParam(),
            mock_tokenizer,
            global_config
        )

        assert result is not None