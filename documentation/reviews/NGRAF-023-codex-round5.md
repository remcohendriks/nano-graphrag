# Review: NGRAF-023 Round 5 (Codex)

## Critical

### CODEX-012: nano_graphrag/backup/manager.py:77 | Critical
**What I saw**
```python
checksum = compute_directory_checksum(temp_dir)
manifest = BackupManifest(..., checksum=checksum)
await save_manifest(...)
archive_size = await create_archive(temp_dir, archive_path)
```
`compute_directory_checksum` runs *before* `manifest.json` exists, so the stored hash reflects only the exported payload. During restore we extract the archive (which now includes `manifest.json`), recompute the checksum, and the values diverge.

**Impact**
Every restore logs `Checksum mismatch` and operators lose the integrity guarantee we set out to provide. In practice the bug is still critical because the system can’t validate backups reliably.

**How to verify**
1. Create a backup.
2. Extract the `.ngbak` and run `compute_directory_checksum` on the extracted directory.
3. Compare with `manifest["checksum"]`; they always differ.
4. Run `restore_backup`; the warning is emitted on each run.

**Recommendation (with patch sketch)**
Write the manifest *before* hashing (or explicitly exclude it in both locations). Here’s a minimal patch that keeps the current helper but moves checksum calculation after the manifest exists:
```python
# Save manifest to temp directory first
manifest_path = temp_dir / "manifest.json"
await save_manifest(manifest.model_dump(exclude={"checksum"}), manifest_path)

# Now compute checksum with manifest included
checksum = compute_directory_checksum(temp_dir)
manifest.checksum = checksum
await save_manifest(manifest.model_dump(), manifest_path)

# Archive once the manifest is final
archive_size = await create_archive(temp_dir, archive_path)
```
_(If you prefer to exclude `manifest.json`, do it symmetrically in both backup and restore.)_

Also add a regression test that extracts an archive and asserts `compute_directory_checksum(extracted_dir) == manifest.checksum`. That will fail if this ever slips again.

## Positive

### CODEX-GOOD-005: nano_graphrag/backup/utils.py:69 | Positive
The new deterministic `compute_directory_checksum` helper (hashing paths + content in sorted order) is exactly the right building block once the manifest timing is fixed. It keeps the design simple and avoids the tar self-reference trap.
