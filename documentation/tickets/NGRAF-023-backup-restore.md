# NGRAF-023: Unified Backup & Restore

## Summary
We need a first-class way to capture and restore the full GraphRAG state. Operators currently dump Neo4j, Qdrant, and Redis/JSON individually before large ingests; failures leave the system in an inconsistent state with no supported rollback path. This ticket introduces a simple backup/restore workflow exposed via the API and dashboard: export everything to a single archive, download it, and later reupload/restore.

## Goals
1. `POST /api/v1/backup` produces a single tarball (.ngbak) containing Neo4j, Qdrant, and KV data.
2. `POST /api/v1/restore` accepts an uploaded backup archive and rehydrates all backends.
3. Dashboard UI shows existing backups, provides a “Download backup” button, and a file-upload form to trigger restore.
4. Archives include a manifest with metadata (timestamp, versions, counts, checksum).

## Scope
- Support the default docker-compose stack (Neo4j + Qdrant + Redis JSON KV).
- Store backups under `./backups` by default (configurable `BACKUP_DIR`).
- No incremental/autosave support; full snapshots only.
- No special auth/audit features in this phase (reuse existing API auth model).

## Backup Format
```
backups/
└── snapshot_2025-10-06T14-30-00Z.ngbak
    ├── manifest.json
    ├── graph/neo4j.dump                # neo4j-admin dump (or APOC export)
    ├── vectors/qdrant/<collection>.snapshot
    ├── kv/full_docs.json
    ├── kv/text_chunks.json
    ├── kv/community_reports.json
    └── config/graphrag_config.json     # effective config for reference
```

`manifest.json` example:
```json
{
  "backup_id": "snapshot_2025-10-06T14-30-00Z",
  "created_at": "2025-10-06T14:30:00Z",
  "nano_graphrag_version": "0.1.0",
  "storage_backends": {
    "graph": "neo4j",
    "vector": "qdrant",
    "kv": "redis"
  },
  "statistics": {
    "documents": 1250,
    "entities": 15420,
    "relationships": 32100,
    "communities": 892,
    "chunks": 8943
  },
  "checksum": "sha256:a3d5f..."
}
```

## API Endpoints
- `POST /api/v1/backup`: Kick off asynchronous backup job; response returns job ID + backup metadata.
- `GET /api/v1/backup`: List existing backups (from manifests).
- `GET /api/v1/backup/{backup_id}/download`: Stream archive to browser.
- `POST /api/v1/restore`: Multipart upload (file + options) that starts restore job.
- `DELETE /api/v1/backup/{backup_id}`: Remove archive (optional, to enforce retention).

## UI Integration (Dashboard)
- Add “Backups” section with:
  - Button “Create Backup” → calls `POST /api/v1/backup` and polls job status.
  - Table of backups showing timestamp, size, download link, delete button.
  - File upload + submit button: “Restore from Backup” → POSTs to `/api/v1/restore`.

## Implementation Plan
1. **BackupManager (`nano_graphrag/backup/manager.py`)**
   - `create_backup()` orchestrates exports:
     - Neo4j: invoke `neo4j-admin database dump` (or APOC fallback) to temp dir.
     - Qdrant: call snapshot API, copy snapshot files.
     - Redis JSON: copy JSON files or run `BGSAVE` for redis dump.
     - Write manifest + checksum.
     - Tar/gzip into `backups/<backup_id>.ngbak`.
   - `restore_backup()` reverses the process:
     - Extract archive to temp dir.
     - Stop services if necessary; load Neo4j dump; upload Qdrant snapshot; restore Redis file.
     - Restart/refresh GraphRAG storages.
   - Provide helper: `list_backups()`, `delete_backup()`.

2. **API router (`nano_graphrag/api/routers/backup.py`)**
   - Wire endpoints; reuse JobManager for async work (similar to batch insert jobs).
   - Responses include backup metadata pulled from manifest.

3. **Dashboard template**
   - Extend `dashboard.html` and supporting JS to display backup list, call endpoints, and handle file upload for restore.

4. **Configuration**
   - Add `BACKUP_DIR` env variable (default `./backups`).
   - Add `BACKUP_RETENTION` (max number of backups to keep, optional).

5. **Testing**
   - Unit tests: mock storage exporters and ensure BackupManager orchestrates correctly.
   - (Optional) docker-compose integration smoke test: insert sample data, run backup, wipe DBs, restore, verify query results.

## Risks & Mitigations
- **In-flight writes**: Document recommendation to pause ingestion before backup.
- **Service restarts**: Restore may require restarting Neo4j/Qdrant containers; surface warnings/status via job logs.
- **Large archives**: Provide retention configuration and log size/time for operator awareness.

## Acceptance Criteria
- Backup API returns metadata and creates `.ngbak` archive containing all storage layers + manifest.
- Restore API rehydrates system from a chosen archive and basic smoke test (sample query) passes afterward.
- Dashboard shows backups, allows download, and triggers restore via file upload.
- Logs provide clear success/failure messages for backup and restore jobs.
