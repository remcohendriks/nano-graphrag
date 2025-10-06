# Review: NGRAF-023 Round 4 (Codex)

## Critical

### CODEX-011: nano_graphrag/backup/manager.py:92 | Critical
**Issue**: The new two-pass archiving workflow still leaves `manifest.json` (and the sidecar `.checksum` file) with the checksum of the *first* archive. After you rewrite the manifest with that value and regenerate the tarball, the file’s bytes change, so the SHA-256 of the shipped archive no longer matches the value recorded in the manifest.
**Impact**: Any operator or tooling that validates a downloaded `.ngbak` against the embedded checksum gets an immediate mismatch, so integrity checks (the stated goal of CODEX-009) still fail. In practice this recreates the original bug from Round 1.
**Reproduction**:
1. Create a backup via `POST /api/v1/backup`.
2. Run `shasum -a 256 backups/<id>.ngbak`; compare with the checksum in the extracted `manifest.json` (or `<id>.checksum`).
3. Values differ because the checksum was computed before the manifest update/repack.
**Recommendation**: Avoid re-packaging after computing the hash. Either: (a) compute the checksum of the *payload directory* and document that the manifest reflects the payload (not the archive), or (b) compute the archive once, write the checksum to a sidecar, and keep the manifest’s checksum field in sync by updating it *before* the final tar is produced (e.g. embed the manifest outside the hashed payload or rewrite the tar entry in place). The current approach can never converge.

## Positive

### CODEX-GOOD-004: nano_graphrag/backup/exporters/qdrant_exporter.py:45
Forwarding the Qdrant API key into the REST snapshot download/upload calls closes the production auth gap from CODEX-010. Thanks for handling both read and write paths and keeping the header addition optional.
