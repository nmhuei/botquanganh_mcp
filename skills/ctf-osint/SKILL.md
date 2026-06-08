# ctf-osint

## Description

OSINT skill — public information gathering, username pivoting, geolocation,
metadata correlation, WHOIS/DNS, social media clues, public repos, leak search,
map imagery, timestamps, and attribution puzzles.

Use this skill only for public CTF targets and intentionally provided clues. Do
not attempt doxxing, credential theft, harassment, or access to private accounts.

## Prerequisites

```bash
apt-get install -y whois dnsutils jq curl exiftool
python3 -m pip install requests beautifulsoup4 dnspython pillow --break-system-packages
```

Optional tools: sherlock, maigret, holehe, gh CLI, mapillary/google maps/manual browser.

## Scope Rules

- Stay inside the CTF challenge scope.
- Use public sources only.
- Do not log into accounts unless the challenge explicitly provides credentials.
- Do not contact real people.
- Do not attempt password reset, phishing, or account takeover.
- Preserve URLs, screenshots, timestamps, and query strings as evidence.

## Recon Checklist

```bash
mkdir -p recon evidence
cat artifacts/description.txt 2>/dev/null || true
exiftool artifacts/* 2>/dev/null | tee recon/exiftool.txt
strings artifacts/* 2>/dev/null | tee recon/strings.txt
grep -RniE 'http|https|@|username|twitter|x.com|instagram|github|linkedin|discord|telegram|whois|dns|lat|lon|gps|flag|ctf' .
```

## Entity Extraction

Create `recon/entities.md`:

```markdown
## People/Usernames
-

## Domains/IPs
-

## Locations
-

## Images/Media
-

## Dates/Times
-

## Unique phrases
-
```

## Username Pivot

```bash
# Manual first: exact username in search engine
# Then tool-assisted:
sherlock username --timeout 10 --print-found
```

Check:

- same avatar
- same bio phrase
- reused handle variants
- GitHub commits/email
- social profile links
- old usernames
- public gists/pastes

## Domain / DNS / WHOIS

```bash
whois example.com
dig example.com any
dig txt example.com
dig axfr @ns1.example.com example.com
curl -s https://crt.sh/\?q\=%25.example.com\&output=json | jq .
```

Check:

- TXT records
- certificate transparency subdomains
- old staging/dev hostnames
- zone transfer
- leaked admin panels
- GitHub Pages / cloud bucket names

## GitHub / Public Repo OSINT

```bash
gh repo view owner/repo
gh api repos/owner/repo/commits --paginate | jq '.[].sha'
git clone https://github.com/owner/repo
git log --all --stat
git grep -niE 'flag|secret|token|password|ctf'
git log -S'flag' --all
```

Check:

- commit history
- deleted files
- GitHub Actions artifacts/logs
- issues/PR comments
- releases
- branches/tags
- package metadata

## Image Geolocation

Use:

- EXIF GPS
- road signs
- shop names
- language/script
- license plates
- architecture
- vegetation/climate
- shadows/time
- mountains/coastline
- public transit maps
- reverse image search

Local extraction:

```bash
exiftool image.jpg
identify -verbose image.jpg
```

Record reasoning:

```markdown
Clue:
Evidence:
Candidate:
Confidence:
Next check:
```

## Timezone / Timestamp

```bash
exiftool image.jpg | grep -i date
python3 - <<'PY'
from datetime import datetime, timezone
print(datetime.fromtimestamp(1700000000, tz=timezone.utc))
PY
```

Check mismatch between local time, EXIF time, upload time, event time.

## Verification

An OSINT flag is valid only when:

- The final answer is directly supported by public evidence, and
- At least two independent clues corroborate it when possible, and
- The flag format or scoreboard confirms it.

Save:

```markdown
## Evidence
- URL:
- Archived/screenshot:
- Observed value:
- Why it supports the flag:
```

## Pivot Rules

- Public repo exploit/Actions → `ctf-misc` or `ctf-web`
- Image/audio hidden data → `ctf-forensics`
- Crypto/hash recovered from public clue → `ctf-crypto`
