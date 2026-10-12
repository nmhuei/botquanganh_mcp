# INTERCODE TASK 04: LINUX INCIDENT RESPONSE & PROCESS TREE AUDIT

## Background
A Linux web server incident report shows an unauthorized backdoor port `4444` open on the host. Mock system artifacts are located in `mock_system/`:
- `ps_dump.txt`: Snapshot of running processes.
- `netstat.txt`: Open listening network sockets.
- `mem_dump_4921.raw`: Memory dump of a suspicious process.

## Objectives
1. Analyze the process lineage tree to identify:
   - The rogue listening process PID and program name.
   - The parent malicious daemon PID that launched the backdoor.
   - The root dropper PID that spawned the intrusion chain.
2. Inspect `mock_system/mem_dump_4921.raw` to recover the exfiltrated environment secret `FLAG{...}`.
3. Write an automation bash script `audit.sh` that extracts these parameters programmatically.
4. Save results to `solution.json`:
```json
{
  "status": "solved",
  "backdoor_pid": 4922,
  "parent_daemon_pid": 4921,
  "dropper_pid": 3410,
  "flag": "FLAG{...}"
}
```

## Definition of Done
- `audit.sh` runs cleanly without error.
- `solution.json` contains exact PIDs and flag.
