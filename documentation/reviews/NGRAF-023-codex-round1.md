# Review: NGRAF-023 Round 1 (Codex)

## Critical

### CODEX-001: nano_graphrag/backup/manager.py:90-104 | Critical
**Evidence**
```python
archive_path = self.backup_dir / f"{backup_id}.ngbak"
archive_size = await create_archive(temp_dir, archive_path)
checksum = compute_checksum(archive_path)
manifest.checksum = checksum
await save_manifest(manifest.model_dump(), manifest_path)
# …
await create_archive(temp_dir, archive_path)  # overwrites archive
```
**Impact**: The checksum recorded in the manifest corresponds to the *first* archive (without the checksum inside). The second `create_archive` rewrites the file, so `manifest.checksum` is no longer valid. Any consumer verifying the manifest will see a mismatch, invalidating the snapshot.
**Recommendation**: Reorder the steps so the manifest (with checksum) is written before a single archive operation, or recompute the checksum after the final archive is produced.

### CODEX-002: nano_graphrag/backup/exporters/qdrant_exporter.py:96-112 | Critical
**Evidence**
```python
await client.upload_snapshot(
    collection_name=self.collection_name,
    snapshot=snapshot_data
)
```
The async Qdrant client does not implement `upload_snapshot`; the code will hit the `AttributeError` branch and raise `NotImplementedError`, leaving restore unsupported.
**Impact**: Restores cannot succeed for Qdrant collections, so the backup bundle cannot rehydrate the system—core acceptance criterion fails.
**Recommendation**: Use the actual Qdrant snapshot restore API (`client.service.restore_snapshot`, `client.upload_collection_snapshot`, or HTTP call depending on version) and verify end-to-end that a collection is recreated. Remove the fallback that simply raises.

## High

### CODEX-003: nano_graphrag/backup/manager.py:146-170 | High
**Evidence**
```python
exporter = QdrantExporter(self.graphrag.entities_vdb)
```
Only the entities vector store is exported/restored. `GraphRAG` can also host `chunks_vdb` (enabled when naive RAG is on), but that namespace is omitted entirely.
**Impact**: After restore, chunk-based retrieval is empty/inconsistent, breaking naive RAG deployments.
**Recommendation**: Gather all configured vector stores (`entities_vdb`, `chunks_vdb`, others if present) and export/restore each collection.

### CODEX-004: nano_graphrag/api/templates/dashboard.html | High
**Evidence**: The template still contains only the Documents/Search/Jobs tabs; no backup list, download link, or file-upload form were added.
**Impact**: The UI deliverable from NGRAF-023 is missing—operators still have to call the raw API, contradicting the ticket contract.
**Recommendation**: Add a “Backups” section to the dashboard with a create-backup button, table of manifest metadata (with download/delete), and a multipart upload form that posts to `/api/v1/backup/restore`.

## Positives

### CODEX-GOOD-001: nano_graphrag/api/routers/backup.py | Positive
Nicely structured router: consistent JobManager usage, background tasks for long-running operations, and typed responses (`BackupMetadata`). Error messages and validation (extension check) are clear.
