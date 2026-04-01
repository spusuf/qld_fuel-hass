## Learned User Preferences
- Prefer Windows-compatible workflows and command/script formats over Unix-only hooks.
- Prefer Home Assistant-style entity attributes while preserving backward compatibility.
- Do not add tool/vendor branding text in repo content, commit messages, or PR/comment text.
- Prefer graceful logging for expected upstream failures in services (for example API errors) without emitting full tracebacks.

## Learned Workspace Facts
- The workspace is a Home Assistant custom integration repository for QLD fuel prices.
- The user maintains and contributes changes upstream via fork-based GitHub pull requests.
- Stacked pull requests may use a feature branch as the merge base when later work depends on earlier in-flight changes.
- HACS repository validation can fail on GitHub repository settings (for example topics and issues) rather than integration code alone.
- Use `scripts/run-tests.ps1` to run the project test suite on Windows when available.
