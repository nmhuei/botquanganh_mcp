# ctf-crypto

## Description

Cryptography skill — RSA, ECC, lattices, symmetric crypto, stream ciphers, hashes,
PRNGs, protocols, oracles, signatures, encoding layers, and custom constructions.

Use this skill when the challenge includes words such as `RSA`, `AES`, `cipher`,
`encrypt`, `decrypt`, `modulus`, `hash`, `signature`, `oracle`, `nonce`, `LFSR`,
`MT19937`, `ECC`, `ECDSA`, `lattice`, or large integer parameters.

Do not treat a base64/hex-only puzzle as crypto until the underlying primitive is
identified. If the problem is mostly file carving, route to `ctf-forensics`. If it
is mostly jail/protocol abuse, route to `ctf-misc`.

## Prerequisites

```bash
python3 -m pip install pycryptodome sympy gmpy2 z3-solver hashpumpy fpylll py_ecc --break-system-packages
which sage || echo "Install SageMath for Coppersmith/LLL-heavy tasks"
```

Optional:

```bash
apt-get install -y sagemath pari-gp john hashcat
```

## Recon Checklist

```bash
file artifacts/*
grep -RniE "rsa|aes|ecc|ecdsa|nonce|iv|seed|random|oracle|encrypt|decrypt|flag|ctf" .
python3 - <<'PY'
import re, pathlib
for p in pathlib.Path(".").rglob("*"):
    if p.is_file():
        b=p.read_bytes()[:200000]
        vals=re.findall(rb'\b[0-9]{20,}\b', b)
        if vals:
            print(p, "large integers:", len(vals), "sample:", vals[:3])
PY
```

Questions to answer before exploiting:

- What is public and what is secret?
- Is there an oracle? encryption, decryption, padding, signing, verification, timing?
- Are parameters reused? key, IV, nonce, seed, prime, modulus, ephemeral `k`?
- Is padding present? raw RSA/no OAEP, CBC/no MAC, CTR/GCM nonce reuse?
- Can the flag be recovered offline, or must the remote oracle be queried?

## Attack Map

| Signal | First attack |
|--------|--------------|
| RSA `e=3`, small ciphertext | integer root / broadcast / Franklin-Reiter |
| Many RSA moduli | batch GCD shared prime |
| Small private exponent | Wiener / Boneh-Durfee |
| Partial prime bits | Coppersmith small roots |
| Same RSA message to many moduli | Hastad broadcast |
| Textbook RSA signing | multiplicative forgery |
| ECDSA same `r` | recover nonce `k`, then private key |
| AES-ECB | block cut-and-paste / byte-at-a-time |
| AES-CBC padding error | padding oracle |
| CTR/GCM nonce reuse | XOR keystream recovery |
| Hash with `secret || msg` | length extension |
| Python `random` outputs | MT19937 state recovery |
| LFSR bits | Berlekamp-Massey |
| Smooth group order | Pohlig-Hellman |
| Small subgroup / invalid curve | subgroup confinement |
| Custom XOR stream | known plaintext + frequency analysis |

## RSA Playbook

### Parse parameters

```python
from Crypto.Util.number import *
import json, re

data = open("artifacts/output.txt","rb").read()
ints = list(map(int, re.findall(rb"\d+", data)))
print(len(ints), ints[:5])
```

### Small exponent / no padding

```python
from gmpy2 import iroot
m, exact = iroot(c, e)
assert exact
print(long_to_bytes(int(m)))
```

### Shared prime

```python
from math import gcd
from Crypto.Util.number import long_to_bytes

for i,n1 in enumerate(ns):
    for j,n2 in enumerate(ns[i+1:], i+1):
        g = gcd(n1,n2)
        if 1 < g < n1:
            p, q = g, n1//g
            phi = (p-1)*(q-1)
            d = pow(e, -1, phi)
            print(i, j, long_to_bytes(pow(c, d, n1)))
```

### Wiener

```python
# Use convergents of e/n. If d is small, recover d then decrypt.
```

### Coppersmith

Use Sage when the unknown is small:

```sage
N = ...
R.<x> = Zmod(N)[]
f = known_high_bits + x
roots = f.small_roots(X=2^128, beta=0.5)
print(roots)
```

## Symmetric Crypto Playbook

### ECB detection

```python
ct = bytes.fromhex(open("artifacts/ct.txt").read().strip())
blocks = [ct[i:i+16] for i in range(0,len(ct),16)]
print(len(blocks), len(set(blocks)), "repeated?", len(blocks) != len(set(blocks)))
```

### CBC padding oracle skeleton

```python
def valid(iv, block):
    # send iv+block to remote; return True if padding accepted
    ...

def decrypt_block(prev, cur):
    inter = bytearray(16)
    out = bytearray(16)
    for pos in range(15, -1, -1):
        pad = 16 - pos
        prefix = bytearray(16)
        for i in range(pos+1,16):
            prefix[i] = inter[i] ^ pad
        for g in range(256):
            prefix[pos] = g
            if valid(bytes(prefix), cur):
                inter[pos] = g ^ pad
                out[pos] = inter[pos] ^ prev[pos]
                break
    return bytes(out)
```

### CTR/GCM nonce reuse

```python
def xor(a,b): return bytes(x^y for x,y in zip(a,b))
# c1 ^ c2 = p1 ^ p2. Use known plaintext to recover keystream.
```

## PRNG / Stream Playbook

### MT19937

Need 624 tempered 32-bit outputs. Untemper each, clone state, predict future.

### LFSR

```python
def berlekamp_massey(bits):
    c,b=[1],[1]; L,m=0,1
    for n in range(len(bits)):
        d=bits[n]
        for i in range(1,L+1): d ^= c[i] & bits[n-i]
        if d:
            t=c[:]
            c += [0]*(len(b)+m-len(c))
            for j in range(len(b)): c[j+m] ^= b[j]
            if 2*L <= n:
                L = n+1-L; b=t; m=1
            else: m += 1
        else: m += 1
    return L, c
```

## Oracle Discipline

- Cache all oracle calls in `recon/oracle_cache.jsonl`.
- Add `sleep(0.5)` for remote services unless the challenge requires timing.
- Treat rate limits as part of the protocol; do not brute-force blindly.
- Always build an offline verifier for recovered key/plaintext when possible.

## Verify

A crypto flag is valid only when at least one is true:

- The plaintext decrypts from the provided ciphertext using recovered key/material.
- The recovered key verifies against public parameters.
- The remote service accepts the final answer.
- The output contains the expected flag format and is derived from challenge data, not guessed.

## Pivot Rules

- Pure encoding/file layers → `ctf-forensics` or `ctf-misc`
- Decompiled binary implements crypto check → `ctf-reverse` first, then this skill
- Web oracle/API challenge → combine `ctf-web` and this skill
- Blockchain/EVM math → `ctf-web3` if available, otherwise this skill + `ctf-web`
