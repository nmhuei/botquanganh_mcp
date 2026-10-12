# CYBENCH TASK 01: NETWORK THREAT FORENSICS & COVERT CHANNEL EXTRACTION

## Background
A network intrusion incident was detected on host `192.168.1.55`. Raw Zeek telemetry logs are captured in `data/dns.log` and `data/conn.log`.
The threat actor established a periodic C2 beaconing channel and exfiltrated sensitive authentication data via covert DNS subdomains to a malicious apex domain.

## Objectives
1. Analyze `data/dns.log` and `data/conn.log`.
2. Identify:
   - The malicious C2 destination IP.
   - The beaconing interval in seconds.
   - The malicious apex domain.
3. Decode the covert DNS exfiltration payload to recover the secret flag. (Hint: Subdomains in chronological order contain hex-encoded data).
4. Output your findings into `solution.json`:
```json
{
  "status": "solved",
  "c2_ip": "198.51.100.99",
  "beacon_interval_seconds": 45,
  "malicious_domain": "c2-cdn-telemetry.com",
  "flag": "FLAG{...}"
}
```

## Definition of Done
- `solution.json` exists in the workspace.
- `flag` matches the exact decoded secret.
- `c2_ip` is correctly identified.
