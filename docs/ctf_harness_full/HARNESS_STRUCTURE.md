# Harness Structure

```text
ctf_harness_full/
├── ctfharness/                 # CLI engine
├── scripts/new-challenge.sh    # workspace generator
├── templates/                  # solver templates
├── skills/                     # category skills
├── docs/                       # design notes
├── workspaces/.knowledge/      # reusable findings
├── ctf.example.yaml            # config template
└── Dockerfile                  # reproducible tool env
```

Evidence model:

- Local evidence proves the primitive works locally.
- Remote evidence proves the exploit touched the official target.
- Report generation includes source file, SHA256 and command timeline.
