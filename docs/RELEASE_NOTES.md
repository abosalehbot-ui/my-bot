# Release Notes

## Added
- CI pipeline with Python/JS linting, tests, SAST and secret scanning.
- Regression tests for bulk return parsing and manage_balance safe-failure behavior.
- Security headers middleware and `/healthz` endpoint.

## Changed
- Profile session bootstrap/guard behavior in storefront JS.
- Admin bulk return ID parsing to support commas, spaces and newlines.
- manage_balance returns explicit error codes and no-crash failure path.

## Fixed
- Guest/auth profile state overlap and refresh-state inconsistencies.
- manage_balance runtime NameError-like crash path.

## Security
- Escaped status message rendering in frontend.

## Breaking changes
- None expected.

## Migration
- No DB migration required.
- Ensure CI secrets for gitleaks/semgrep actions are available in GitHub.
