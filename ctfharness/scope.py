from __future__ import annotations

from urllib.parse import urlparse


def normalize_target_host_port(target: str) -> list[tuple[str, int | None]]:
    """Normalizes target strings into a list of (hostname, port) tuples.

    Handles URL forms (e.g. http://host:8080), host:port forms, and nc-style (e.g. nc host 8080).
    """
    cleaned = (
        target.replace("ncat", " ")
        .replace("netcat", " ")
        .replace(" nc ", " ")
        .replace("--ssl", " ")
        .replace("-ssl", " ")
        .replace("-nv", " ")
        .replace("-z", " ")
    )
    pieces = cleaned.split() or [target]
    
    results: list[tuple[str, int | None]] = []
    
    # Filter out command flags
    non_flags = [p for p in pieces if not p.startswith("-")]
    
    if non_flags and non_flags[0] in ("nc", "ncat", "netcat"):
        non_flags.pop(0)
    
    if len(non_flags) == 2 and non_flags[1].isdigit():
        # nc host port
        host = non_flags[0]
        port = int(non_flags[1])
        parsed = urlparse(host if "://" in host else f"//{host}")
        hostname = parsed.hostname or host
        results.append((hostname, port))
    else:
        for piece in non_flags:
            if piece.isdigit():
                continue  # ignore standalone ports
            parsed = urlparse(piece if "://" in piece else f"//{piece}")
            if parsed.hostname:
                results.append((parsed.hostname, parsed.port))
            else:
                if ":" in piece:
                    parts = piece.rsplit(":", 1)
                    if len(parts) == 2 and parts[1].isdigit():
                        results.append((parts[0], int(parts[1])))
                        continue
                results.append((piece, None))
                
    return results


def remote_target_allowed(target: str, allowed_domains: list[str]) -> tuple[bool, str]:
    """Check if a remote target is inside authorized scope.

    Supports URL, host:port, and nc/ncat command-like strings. Wildcards such
    as ``*.ctf.example`` match any subdomain of ``ctf.example``.
    """
    if not target:
        return False, "empty remote target"

    normalized = normalize_target_host_port(target)
    if not normalized:
        return False, f"could not parse host from target: {target!r}"

    allowed = [d.lower() for d in allowed_domains]

    def matches(host: str, port: int | None) -> bool:
        h = host.lower()
        for domain in allowed:
            allowed_host = domain
            allowed_port = None
            if ":" in domain:
                parts = domain.rsplit(":", 1)
                if len(parts) == 2 and parts[1].isdigit():
                    allowed_host = parts[0]
                    allowed_port = int(parts[1])

            if allowed_host.startswith("*."):
                suffix = allowed_host[1:]  # .example.com
                if not h.endswith(suffix):
                    continue
            elif not (h == allowed_host or h.endswith("." + allowed_host)):
                continue

            if allowed_port is not None:
                if port != allowed_port:
                    continue

            return True
        return False

    blocked = [f"{h}:{p}" if p else h for h, p in normalized if not matches(h, p)]
    if blocked:
        return False, f"host(s) {blocked} not in authorized_remote_domains={allowed_domains}"
    hosts_str = ", ".join(f"{h}:{p}" if p else h for h, p in normalized)
    return True, f"allowed host(s): {hosts_str}"
