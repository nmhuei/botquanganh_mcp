# Remediation Log — Official Cycle 05

- Gateway and API-key variables are absent from child commands unless specifically allowed.
- Shell startup and dynamic-loader injection variables are always removed.
- Command shell is non-login and ignores user profiles.
- Output is drained concurrently and bounded in memory; no unbounded tempfile remains.
- Timeout signals the full process group and removes surviving descendants.
- Allowlist rejects dynamic substitution and sees background chains.
- Live bridge and public tests passed with tunnel preserved.
