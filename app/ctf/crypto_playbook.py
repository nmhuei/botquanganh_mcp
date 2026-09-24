"""BQA Crypto Playbook query engine and deterministic attack router lookup.

Loads and queries app/ctf/playbooks/crypto_playbook.md for fast lookup of
cryptographic attack vectors, preconditions, mathematical equations, and templates.
"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Optional


PLAYBOOK_PATH = Path(__file__).resolve().parent / "playbooks" / "crypto_playbook.md"


def _read_playbook_content() -> str:
    """Read the raw markdown playbook content."""
    if PLAYBOOK_PATH.is_file():
        return PLAYBOOK_PATH.read_text(encoding="utf-8")
    return ""


def get_playbook_overview() -> dict[str, Any]:
    """Return structured overview of the 5-Phase Crypto Discipline and attack categories."""
    return {
        "discipline": "BQA Extreme Crypto Playbook (Deterministic Cryptanalysis Engine)",
        "protocol": [
            "Phase 1: Parameter & Scheme Triage (extract n, e, c, curve, PRNG state, cipher mode)",
            "Phase 2: Mathematical Modeling (write algebraic relations & bounds in notes/math_model.md)",
            "Phase 3: Attack Vector Selection (query ctf_crypto_playbook or Attack Router Matrix)",
            "Phase 4: Deterministic Local Verification (script/ with parse_data, derive_secret, verify_solution)",
            "Phase 5: Solution Promotion & Hoarding (auto-promote to solver/solve.py, WRITEUP.md, flag.txt)",
        ],
        "attack_categories": [
            {"category": "RSA", "vectors": ["Integer e-th Root", "Common Modulus", "Batch/Shared GCD", "Fermat", "Pollard p-1", "Wiener", "Boneh-Durfee", "Franklin-Reiter", "Coppersmith Small Roots", "Partial Key Exposure"]},
            {"category": "Elliptic Curves (ECC)", "vectors": ["Repeated Nonce", "Biased Nonce / HNP", "Pohlig-Hellman", "Smart's Attack (Anomalous)", "Singular Curves"]},
            {"category": "Discrete Logarithm (DLP)", "vectors": ["Baby-step Giant-step (BSGS)", "Pollard's Rho", "Pohlig-Hellman"]},
            {"category": "Lattices", "vectors": ["CVP / Babai Nearest Plane", "LLL / BKZ Reduction", "Subset Sum / Knapsack (CLOS)", "Noisy Modular Equations"]},
            {"category": "PRNG", "vectors": ["LCG Inversion", "Truncated LCG (Lattice)", "Mersenne Twister Untemper", "Truncated MT19937 (Z3 SMT)", "LFSR Berlekamp-Massey"]},
            {"category": "Symmetric & Hashes", "vectors": ["AES-CBC Padding Oracle", "CBC Bit-Flipping", "Byte-at-a-time ECB", "AES-GCM Nonce Reuse GHASH", "Hash Length Extension", "OTP / Keystream Reuse"]},
        ],
        "playbook_file": str(PLAYBOOK_PATH),
        "guidance": "Pass 'query' (e.g. 'wiener', 'ecc', 'coppersmith', 'lattice', 'gcm') to inspect specific attack parameters and preconditions.",
    }


def parse_router_matrix(content: str) -> list[dict[str, str]]:
    """Parse table rows from Phase 2 Attack Router Matrix in markdown."""
    matrix = []
    in_table = False
    for line in content.splitlines():
        line_clean = line.strip()
        if "## 2. Attack Router Matrix" in line_clean:
            in_table = True
            continue
        if in_table and line_clean.startswith("## "):
            break
        if in_table and line_clean.startswith("|") and not line_clean.startswith("|---") and not line_clean.startswith("| Dấu hiệu"):
            parts = [p.strip() for p in line_clean.split("|")[1:-1]]
            if len(parts) >= 3:
                matrix.append({
                    "observation": parts[0],
                    "prerequisite": parts[1],
                    "vector": parts[2],
                })
    return matrix


def query_crypto_playbook(
    query: Optional[str] = None,
    section: Optional[str] = None,
) -> dict[str, Any]:
    """Query the Crypto Playbook for attack vectors, preconditions, or specific sections."""
    content = _read_playbook_content()
    if not content:
        return {"ok": False, "error": "Crypto playbook file not found."}

    # If no parameters provided, return overview
    if not query and not section:
        overview = get_playbook_overview()
        overview["ok"] = True
        return overview

    # Section lookup
    if section:
        sec_lower = section.lower().strip()
        sections_map = {
            "phases": "## 1. Quy trình 5 Giai đoạn",
            "matrix": "## 2. Attack Router Matrix",
            "router": "## 2. Attack Router Matrix",
            "rsa": "### 3.1. RSA Deep-Dive",
            "ecc": "### 3.2. Elliptic Curves Deep-Dive",
            "lattice": "### 3.3. Lattice Discipline",
            "audit": "## 4. Checklist Kỷ luật",
        }
        for key, header in sections_map.items():
            if sec_lower in key or key in sec_lower:
                pattern = re.compile(rf"({re.escape(header)}.*?)(?=\n## |\Z)", re.DOTALL)
                match = pattern.search(content)
                if match:
                    return {
                        "ok": True,
                        "section": key,
                        "content": match.group(1).strip(),
                    }

    # Query search across Attack Router Matrix and deep-dive text
    if query:
        q_lower = query.lower().strip()
        matrix = parse_router_matrix(content)
        matched_vectors = []
        for row in matrix:
            combined = f"{row['observation']} {row['prerequisite']} {row['vector']}".lower()
            if any(term in combined for term in q_lower.split()):
                matched_vectors.append(row)

        # Also search deep dive sections
        deep_dive_matches = []
        deep_sections = [
            ("RSA", "### 3.1. RSA Deep-Dive"),
            ("ECC", "### 3.2. Elliptic Curves Deep-Dive"),
            ("Lattice", "### 3.3. Lattice Discipline"),
            ("Audit", "## 4. Checklist Kỷ luật"),
        ]
        for name, header in deep_sections:
            pattern = re.compile(rf"({re.escape(header)}.*?)(?=\n### |\n## |\Z)", re.DOTALL)
            match = pattern.search(content)
            if match and any(term in match.group(1).lower() for term in q_lower.split()):
                deep_dive_matches.append({
                    "topic": name,
                    "excerpt": match.group(1).strip(),
                })

        return {
            "ok": True,
            "query": query,
            "matched_vectors_count": len(matched_vectors),
            "matched_vectors": matched_vectors,
            "deep_dive_notes": deep_dive_matches,
            "guidance": "Verify the prerequisite checks before writing exploit code. Document parameters in notes/math_model.md.",
        }

    return {"ok": False, "error": f"No matches found for query='{query}' and section='{section}'."}
