# Implementation Plan — Official Cycle 10

## Goal

Close final installer, lifecycle, quality, and release-evidence gaps without restarting the live Cloudflare tunnel.

## Tasks

1. Make remote installs default to `main` and fail clearly for missing branches.
2. Fast-forward existing managed installations while refusing dirty working trees and non-repository destinations.
3. Preserve `.env`, enforce mode `600`, validate symlink resolution, and retain legacy installer delegation.
4. Add an isolated installer regression covering local, piped, remote, update, dirty-tree, and invalid-branch paths.
5. Restrict port ownership checks to TCP listeners and coordinate server recreation with the active supervisor.
6. Add a listener/client regression test for the original Cloudflare misclassification bug.
7. Clean Ruff/Bandit findings and rerun dependency, secret, shell, and workflow scans.
8. Reconcile README, CI, release checklist, and final verification evidence.
9. Confirm the live tunnel PID and URL remain unchanged.
