# Review: NGRAF-023 Round 1

## Summary
Thanks for the first pass on backup/restore. The core scaffolding (manager, exporters, FastAPI router, tests) is in place, but a few issues keep the implementation from matching the ticket:
- the manifest checksum isn’t valid for the final archive
- Qdrant restore can’t actually replay a snapshot with the client calls used
- the chunk vector store is never exported/restored, so naive-RAG deployments would lose data
- the UI still lacks the required backup-download/upload controls
Fixing those will get us back on spec.

## Blocking issues

### 1. Manifest checksum doesn’t match the archive
**File:** `nano_graphrag/backup/manager.py:90-103`
```python
archive_path = self.backup_dir / f"{backup_id}.ngbak"
archive_size = await create_archive(temp_dir, archive_path)
checksum = compute_checksum(archive_path)
manifest.checksum = checksum
await save_manifest(...)
await create_archive(temp_dir, archive_path)  # overwrites archive
```
You compute the checksum on the first archive (which still contains a manifest with an empty checksum), then repackage the directory after updating the manifest. The second `create_archive` rewrites the `.ngbak` with different bytes, but you never recompute the checksum, so `manifest.checksum` is stale. Please either write the manifest (with checksum) first and archive once, or recompute the checksum after the final archive operation.

### 2. Qdrant restore path can’t work with the public client
**File:** `nano_graphrag/backup/exporters/qdrant_exporter.py:96-112`
```python
await client.upload_snapshot(...)
```
`AsyncQdrantClient` doesn’t expose `upload_snapshot`; the code will hit the `AttributeError` branch and raise `NotImplementedError`, leaving us without a working restore. We need to leverage the actual snapshot API (e.g. `client.service_restore_snapshot`/`client.upload_collection_snapshot` depending on version) or document/execute the HTTP calls directly. Until the restore path successfully recreates a collection, we can’t meet the acceptance criteria.

### 3. Chunk vector stores aren’t included in backups
**File:** `nano_graphrag/backup/manager.py:146-170`
```python
exporter = QdrantExporter(self.graphrag.entities_vdb)
```
Only the entities vector store is exported/restored. If `GraphRAG` is configured with `chunks_vdb` (naive RAG, or multiple vector namespaces), its data never makes it into the archive. Please iterate over all configured vector stores (entities + chunks if present) so a restore yields a complete system.

### 4. Dashboard has no backup/restore controls
The ticket called for a download button and a file-upload form on the UI. `nano_graphrag/api/templates/dashboard.html` is unchanged—there’s no “Backups” section, no link to the new endpoints. Without the UI, operators still have to use the API manually. We need to add the UI affordances described in the ticket (list backups, download, upload for restore).

## Additional suggestions (non-blocking)
- Consider sanitising `backup_id` input (`download_backup`, `delete_backup`, restore upload) to avoid path traversal via crafted IDs.
- During restore you log the manifest checksum but don’t verify it. A quick `verify_checksum` call would catch corrupted archives.
- `list_backups()` currently extracts each archive to disk just to read the manifest. If performance becomes an issue, you could read the manifest entry directly from the tarfile.

Addressing the four blockers will align the implementation with the agreed-upon contract. Happy to re-review once they’re in place.
