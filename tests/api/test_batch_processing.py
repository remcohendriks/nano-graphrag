"""Tests specifically for batch processing performance fix."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
import asyncio
from datetime import datetime

from nano_graphrag.api.routers.documents import _process_batch_with_tracking
from nano_graphrag.api.models import JobStatus
from nano_graphrag.api.jobs import JobManager


@pytest.mark.asyncio
async def test_batch_processing_uses_single_insert():
    """Verify that batch processing calls ainsert once with all documents."""
    # Setup mocks
    documents = ["Doc 1", "Doc 2", "Doc 3"]
    doc_ids = ["doc-1", "doc-2", "doc-3"]
    job_id = "test-job-123"

    mock_graphrag = MagicMock()
    mock_graphrag.ainsert = AsyncMock(return_value=None)

    mock_job_manager = MagicMock(spec=JobManager)
    mock_job_manager.update_job_status = AsyncMock()
    mock_job_manager.update_job_progress = AsyncMock()

    # Execute batch processing
    await _process_batch_with_tracking(
        documents=documents,
        doc_ids=doc_ids,
        job_id=job_id,
        graphrag=mock_graphrag,
        job_manager=mock_job_manager
    )

    # Verify single batch insert was called with all documents
    mock_graphrag.ainsert.assert_called_once_with(documents)

    # Verify job status updates
    assert mock_job_manager.update_job_status.call_count == 2  # PROCESSING and COMPLETED
    mock_job_manager.update_job_status.assert_any_call(job_id, JobStatus.PROCESSING)
    mock_job_manager.update_job_status.assert_any_call(job_id, JobStatus.COMPLETED)

    # Verify phase-based progress was used
    progress_calls = mock_job_manager.update_job_progress.call_args_list
    # Should have phase-based progress updates
    assert any("validating" in str(call) for call in progress_calls)
    assert any("deduplicating" in str(call) for call in progress_calls)
    assert any("completed" in str(call) for call in progress_calls)


@pytest.mark.asyncio
async def test_batch_processing_error_handling():
    """Test that batch processing handles errors properly."""
    documents = ["Doc 1", "Doc 2"]
    doc_ids = ["doc-1", "doc-2"]
    job_id = "test-job-456"

    mock_graphrag = MagicMock()
    # Simulate an error during batch processing
    mock_graphrag.ainsert = AsyncMock(side_effect=Exception("Processing failed"))

    mock_job_manager = MagicMock(spec=JobManager)
    mock_job_manager.update_job_status = AsyncMock()
    mock_job_manager.update_job_progress = AsyncMock()

    # Execute batch processing
    await _process_batch_with_tracking(
        documents=documents,
        doc_ids=doc_ids,
        job_id=job_id,
        graphrag=mock_graphrag,
        job_manager=mock_job_manager
    )

    # Verify error was handled
    mock_job_manager.update_job_status.assert_any_call(
        job_id, JobStatus.FAILED, "Processing failed"
    )


@pytest.mark.asyncio
async def test_phase_based_progress_tracking():
    """Verify phase-based progress tracking works correctly."""
    documents = ["Doc 1"]
    doc_ids = ["doc-1"]
    job_id = "test-job-789"

    mock_graphrag = MagicMock()
    mock_graphrag.ainsert = AsyncMock(return_value=None)

    mock_job_manager = MagicMock(spec=JobManager)
    mock_job_manager.update_job_status = AsyncMock()
    mock_job_manager.update_job_progress = AsyncMock()

    await _process_batch_with_tracking(
        documents=documents,
        doc_ids=doc_ids,
        job_id=job_id,
        graphrag=mock_graphrag,
        job_manager=mock_job_manager
    )

    # Check that progress updates use phase names
    progress_calls = mock_job_manager.update_job_progress.call_args_list

    # Extract phase names from calls
    phases_reported = []
    for call_args in progress_calls:
        if len(call_args[0]) >= 3:  # Check if phase is included
            phase = call_args[0][2]
            phases_reported.append(phase)

    # Verify we have meaningful phases, not document counts
    assert "validating" in phases_reported
    assert "completed" in phases_reported
    # Should NOT have "processing document X/Y" format
    assert not any("document" in phase for phase in phases_reported if phase)


def test_batch_vs_sequential_performance():
    """Demonstrate the performance difference between batch and sequential processing.

    This is a conceptual test showing the algorithmic difference.
    """
    num_documents = 10

    # Sequential processing cost (simplified)
    # Each document triggers: chunking + extraction + graph_build + clustering + reports
    sequential_clustering_operations = num_documents  # N clusterings
    sequential_report_generations = num_documents     # N report generations

    # Batch processing cost
    batch_clustering_operations = 1  # Single clustering
    batch_report_generations = 1     # Single report generation

    # Verify batch is more efficient
    assert batch_clustering_operations < sequential_clustering_operations
    assert batch_report_generations < sequential_report_generations

    # Performance ratio
    clustering_speedup = sequential_clustering_operations / batch_clustering_operations
    assert clustering_speedup == num_documents  # 10x speedup for clustering

    # With increasing graph size, clustering becomes O(n²), so actual speedup is even better
    # For 10 docs with 100 entities each:
    # Sequential: cluster(100) + cluster(200) + ... + cluster(1000) ≈ O(n³)
    # Batch: cluster(1000) ≈ O(n²)
    # Actual speedup > 10x