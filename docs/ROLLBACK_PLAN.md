# Rollback Plan

## Rollback steps
1. Identify last stable commit/tag before this release.
2. Deploy rollback commit:
   ```bash
   git checkout <stable_sha>
   git push --force-with-lease origin main
   ```
3. Restart service.

## If partial runtime config changed
- Revert workflow/config files (`.github/workflows/ci.yml`, `pyproject.toml`, `requirements-dev.txt`, `package.json`) with code rollback.
- No schema migration rollback needed.

## Post-rollback smoke tests
```bash
curl -fsS http://<host>/healthz
curl -i http://<host>/api/store/me
# verify profile modal guest/auth rendering manually
```
