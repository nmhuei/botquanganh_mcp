# Ke hoach them chuc nang Skill cho botquanganh_mcp

Muc tieu: them mot lop `skills` cho MCP de ChatGPT web co the mo dung workflow/reference khi gap kho khan. ChatGPT van la nao: tu nhan biet minh dang bi ket, goi tool search/open skill, doc phan can thiet, roi tiep tuc goi tool khac. MCP khong tu lap plan, khong tu solve, khong nho context dai.

## 1. Nguyen tac thiet ke

- Metadata nho luon san sang: `name`, `description`, `category`, `tags`, `entrypoint`.
- Noi dung skill chi load khi ChatGPT goi `skill_open`.
- Reference lon chi load khi ChatGPT goi `skill_read_reference`.
- Scripts/assets khong dua vao context, chi expose duong dan va cach chay neu duoc phep.
- MCP chi tra ve trich yeu va file paths, khong nhung ca skill repo vao response.
- Moi lan open skill la stateless request, khong tao memory dai han.

## 2. Skill format

Dung format gan voi Agent Skills:

```text
skills/
  ctf-web/
    SKILL.md
    references/
      sql-injection.md
      server-side.md
    scripts/
      quick_recon.py
    assets/
  ctf-pwn/
    SKILL.md
    references/
    scripts/
```

`SKILL.md` bat buoc co frontmatter:

```yaml
---
name: ctf-web
description: Use when the challenge is mainly HTTP/API/browser/auth/upload/template/JWT/SSRF/XSS/SQLi.
category: ctf
tags: [ctf, web, sqli, xss, ssrf, jwt]
---
```

Body nen ngan:

- Khi nao dung skill.
- Workflow 5-10 buoc.
- Tool prerequisites.
- Reference map: file nao doc khi nao.
- Quick commands.
- Pivot rules.

Khong nen:

- Nhung qua nhieu payload/technique vao `SKILL.md`.
- Tao README phu khong can thiet.
- De skill tu execute command mac dinh.

## 3. Skill storage

De xuat 3 nguon skill:

```text
repo-local:
  ./skills/

user-local:
  ~/.mcp/skills/

imported:
  ~/.mcp/skill_repos/<owner>/<repo>/
```

Priority:

1. repo-local override
2. user-local
3. imported

Ly do:

- Repo co the co skill rieng cho CTF/team.
- User co skill ca nhan dung lai.
- Imported repo nhu `ljagiello/ctf-skills` khong lam ban repo chinh.

## 4. Skill index

Tao index nhe:

```json
{
  "skill_id": "ctf-web",
  "name": "ctf-web",
  "description": "...",
  "category": "ctf",
  "tags": ["ctf", "web", "sqli"],
  "root": "/home/light/.mcp/skill_repos/ljagiello/ctf-skills/ctf-web",
  "entrypoint": "SKILL.md",
  "references": [
    {"path": "references/sql-injection.md", "title": "SQL injection"}
  ],
  "scripts": [
    {"path": "scripts/quick_recon.py", "executable": true}
  ],
  "sha256": "..."
}
```

Index cache:

```text
~/.mcp/skill_index.json
```

Cache invalidation:

- Rebuild khi skill dir mtime doi.
- Rebuild khi import/update skill repo.
- Co tool manual `skill_reindex()`.

## 5. Tool API de xuat

### 5.1 Discovery

```text
skill_list(category="", limit=100)
skill_search(query, category="", limit=10)
skill_suggest(problem, recent_error="", category="", limit=5)
```

`skill_suggest` chi lam retrieval dua tren query/error text. No khong phan tich context dai va khong tu quyet dinh thay ChatGPT.

Output:

```json
{
  "ok": true,
  "matches": [
    {
      "skill_id": "ctf-pwn",
      "score": 0.87,
      "reason": "query mentions ELF, crash, cyclic offset",
      "description": "..."
    }
  ]
}
```

### 5.2 Open skill

```text
skill_open(skill_id, max_chars=12000)
skill_open_summary(skill_id)
skill_read_section(skill_id, heading, max_chars=8000)
```

Rules:

- `skill_open` chi doc `SKILL.md`.
- Neu qua dai, tra preview + headings.
- Tra `references_available` de ChatGPT chon doc tiep.

### 5.3 Reference progressive disclosure

```text
skill_list_references(skill_id)
skill_search_references(skill_id, query, limit=10)
skill_read_reference(skill_id, path, max_chars=16000)
```

Rules:

- Chi cho path nam trong root skill.
- Khong follow symlink ra ngoai root tru khi allowlist.
- Reference lon thi tra chunk/headings.

### 5.4 Scripts/assets

```text
skill_list_scripts(skill_id)
skill_describe_script(skill_id, path)
skill_run_script(skill_id, path, args=[], workspace_id="", dry_run=true)
skill_list_assets(skill_id)
```

Default:

- `skill_run_script(..., dry_run=true)`.
- Muon chay that phai set `dry_run=false`.
- Script chay trong workspace/sandbox neu co.
- Log command, args, cwd, stdout/stderr, sha256 script.

## 6. Luong "ChatGPT gap kho thi mo skill"

Flow mong muon:

```text
1. ChatGPT dang solve CTF va bi ket.
2. ChatGPT goi skill_suggest(problem="ELF crashes after cyclic input...", category="ctf").
3. MCP tra top skills: ctf-pwn, ctf-reverse.
4. ChatGPT goi skill_open("ctf-pwn").
5. ChatGPT doc workflow ngan va reference map.
6. ChatGPT goi skill_search_references("ctf-pwn", "canary byte leak").
7. ChatGPT goi skill_read_reference(...) neu can.
8. ChatGPT quay lai goi ctf_harness/run_command/tool khac.
```

MCP khong can biet ChatGPT bi ket vi sao. MCP chi can retrieval tot va output gon.

## 7. Ket hop voi CTF harness

Skill layer nen dung chung voi `harnes_ctf.md`:

- `ctf_triage()` tra `suggested_skills`.
- `ctf_prepare_env(category)` co the doc prerequisites tu skill metadata.
- `ctf_build_proof_bundle()` khong nhung skill text, chi luu `skills_used`.
- `doctor_ctf_harness()` bao skill index co/khong.

Vi du output:

```json
{
  "ok": true,
  "category_candidates": ["pwn", "reverse"],
  "suggested_skills": [
    {"skill_id": "ctf-pwn", "reason": "ELF service with crash"},
    {"skill_id": "ctf-reverse", "reason": "unknown binary logic"}
  ]
}
```

## 8. Import skill repo

Tool de xuat:

```text
skill_import_git(repo_url, ref="main", trust="read_only")
skill_update_repo(repo_id)
skill_remove_repo(repo_id)
skill_repo_status()
```

Default trust:

- `read_only`: cho doc SKILL/reference, khong chay scripts.
- `trusted`: cho run scripts sau policy check.

Voi `ljagiello/ctf-skills`:

```text
skill_import_git("https://github.com/ljagiello/ctf-skills.git", trust="read_only")
skill_reindex()
skill_search("JWT forgery ctf", category="ctf")
```

## 9. Security model

Guardrails:

- Skill path phai nam trong configured roots.
- Khong execute script tu imported repo neu `trust=read_only`.
- Khong auto-install package khi open skill.
- `skill_run_script` di qua policy engine giong shell/file tools.
- Redact secrets trong logs.
- Log moi lan import/update/open/run script.
- Pin repo ref/commit trong index de replay.

Block reason nen ro:

```json
{
  "ok": false,
  "error": "POLICY_BLOCKED",
  "blocked_reason": "skill_script_untrusted",
  "suggested_action": "re-import with trust=trusted or copy script into workspace"
}
```

## 10. Module de them

```text
app/
  skills/
    __init__.py
    model.py
    roots.py
    parser.py
    index.py
    search.py
    reader.py
    importer.py
    runner.py
    policy.py
```

Dang ky MCP tools trong:

```text
app/tools/skills.py
```

Config moi:

```env
ENABLE_SKILL_TOOLS=true
SKILL_ROOTS=./skills,~/.mcp/skills,~/.mcp/skill_repos
SKILL_INDEX_PATH=~/.mcp/skill_index.json
SKILL_ALLOW_SCRIPT_RUN=false
SKILL_IMPORT_ALLOW_GIT=true
```

## 11. Search implementation

Ban dau chi can BM25/lightweight:

- Tokenize `name`, `description`, `tags`, headings.
- Score exact tag/category cao hon body text.
- Return reason bang matched terms.

Sau nay co the them embeddings, nhung khong can cho MVP.

File can index:

- `SKILL.md` frontmatter
- headings trong `SKILL.md`
- reference filenames/headings
- script filenames

Khong index full reference qua lon vao memory; chi index snippets/headings.

## 12. Tests

Unit tests:

- Parse frontmatter hop le.
- Reject skill thieu `name`/`description`.
- Reindex multiple roots voi priority dung.
- Search match theo tag/description.
- Read section by heading.
- Reject path traversal `../`.
- Reject symlink escape.
- Reject script run khi untrusted.

Integration tests:

- Import fixture skill repo local.
- Search `jwt` -> `ctf-web`.
- Open skill -> chi co `SKILL.md`, references listed but not loaded.
- Read reference -> load dung file.
- Run script dry-run -> khong execute.

Commands:

```bash
./.venv/bin/python -m pytest tests/test_skills.py -q
./.venv/bin/python -m pytest tests/test_skill_import.py -q
```

## 13. Roadmap implement

### Phase 1: Read-only skill MVP

- Add `app/skills/parser.py`.
- Add `app/skills/index.py`.
- Add `app/tools/skills.py`.
- Implement `skill_list`, `skill_search`, `skill_open`, `skill_list_references`, `skill_read_reference`.
- Add tests path traversal/frontmatter/search.

### Phase 2: Import git

- Implement `skill_import_git`.
- Store under `~/.mcp/skill_repos`.
- Pin commit hash.
- Reindex sau import.
- Default trust `read_only`.

### Phase 3: CTF integration

- Import `ljagiello/ctf-skills`.
- Map category to skill id.
- Add `suggested_skills` vao `ctf_triage`.
- Add `skills_used` vao proof bundle.

### Phase 4: Script support

- Implement `skill_list_scripts`.
- Implement `skill_run_script` dry-run.
- Add trusted mode + policy check.
- Log script sha256 va args.

### Phase 5: Better retrieval

- Add heading/snippet search.
- Add `skill_read_section`.
- Add `skill_suggest(problem, recent_error)`.
- Add cache invalidation by mtime/commit.

## 14. Definition of done

Chuc nang skill coi la xong khi:

- ChatGPT co the search/open/read skill qua MCP.
- Skill content duoc load theo nhu cau, khong day context mac dinh.
- Imported skill repo read-only an toan.
- CTF harness co the goi/suggest skill theo category.
- Moi read/import/script action co audit log.
- Khong co memory store dai han, chi co skill index va technical metadata.

