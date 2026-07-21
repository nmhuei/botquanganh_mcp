# Remediation Log — Official Cycle 10

- Installer remote behavior now defaults to `main`, validates branch availability, and clones only the requested branch.
- Existing installations now fetch and fast-forward safely; dirty working trees and invalid destinations are rejected.
- `.env` is preserved, permissioned to `600`, and validated by isolated tests.
- CLI symlink resolution, version output, and `pip check` pass for local, piped, and remote-style installations.
- Server-only restart no longer sees the Cloudflare client connection as a listener.
- An active supervisor exclusively recreates the server, eliminating the restart race.
- The regression suite increased from 105 to 106 tests.
- Installer manual testing completed 7/7 scenarios, including origin mismatch rejection.
- Ruff, Bandit, pip-audit, detect-secrets, ShellCheck, and zizmor final scans are clean.
- The live tunnel PID and connector URL were preserved throughout the final post-fix verification.
