# Review: NGRAF-023 Round 3 (Codex)

## Critical

### CODEX-009: nano_graphrag/backup/manager.py:78 | Critical
**Issue**: The `manifest.json` bundled inside every `.ngbak` archive still records `"checksum": ""`. After computing the real digest you only write it to the sibling `.checksum` file and mutate the in-memory `BackupManifest`, but the archive that operators download continues to ship the placeholder manifest.
**Impact**: The ticket contract requires the manifest to expose the archive checksum so operators can validate a download in isolation. As soon as the archive is copied off the server (normal workflow), integrity checks fail because the embedded manifest lacks the checksum. Any tooling that relies on the manifest—exactly what the spec prescribes—treats the backup as malformed, undermining disaster-recovery guarantees.
**Reproduction**:
1. Trigger `POST /api/v1/backup`.
2. Download the resulting `.ngbak`, extract it, and inspect `manifest.json`.
3. Observe `"checksum": ""` despite the archive having a non-empty digest in `<backup>.checksum`.
**Recommendation**: Persist the computed checksum into the manifest that lives inside the archive—e.g. rewrite `manifest.json` in the temp directory before creating the tarball, or patch the tar after hashing. Add a regression test that extracts an archive and asserts `manifest["checksum"]` is populated.

### CODEX-010: nano_graphrag/backup/exporters/qdrant_exporter.py:50-101 | Critical
**Issue**: Snapshot download/upload now bypasses the Qdrant client and uses raw `httpx` calls, but the code never forwards the configured API key. `QdrantVectorStorage` stores the key on `self._api_key`; the HTTP calls hit the secured endpoint unauthenticated.
**Impact**: In the common deployment where Qdrant enforces API keys, both backup (`GET /collections/.../snapshots/...`) and restore (`POST /collections/.../snapshots/upload`) immediately return `401 Unauthorized`. End-to-end backup/restore therefore breaks in production environments, despite succeeding against an unsecured local instance.
**Reproduction**:
1. Configure Qdrant with any non-empty API key (set `storage.qdrant_api_key`).
2. Call `BackupManager.create_backup()`.
3. The export fails with 401; likewise restore fails when trying to upload the snapshot.
**Recommendation**: Reuse the existing async client (which already handles auth) or at minimum add the `api-key`/`Authorization` header derived from `self.storage._api_key` to both HTTP requests. Cover this with a unit test that asserts the header is present when an API key is configured.

## Positives

### CODEX-GOOD-003: nano_graphrag/backup/exporters/kv_exporter.py:193
Nice improvement delegating Redis restores to `storage.upsert()` with detailed diagnostics. That reuses the storage abstraction, avoids duplicate serialization logic, and the added logging will be invaluable during recovery drills.
