import subprocess
import time
from pathlib import Path
from typing import Dict, List, Tuple
from app.config import (
    DOCKER_MEMORY,
    DOCKER_CPUS,
    DOCKER_PIDS_LIMIT,
    DOCKER_USER,
    RUNNER_IMAGE_PYTHON,
    RUNNER_IMAGE_PWN,
    RUNNER_IMAGE_SAGE,
    ENABLE_EGRESS_FIREWALL,
)
from app.logging_audit import log_audit_event
from app.egress_firewall import apply_egress_rules, remove_egress_rules

def get_runner_image(language: str) -> str:
    """Maps language profile to Docker image name."""
    lang = language.lower()
    if lang == "pwn":
        return RUNNER_IMAGE_PWN
    elif lang == "sage":
        return RUNNER_IMAGE_SAGE
    return RUNNER_IMAGE_PYTHON

def get_container_ip(container_name: str) -> str:
    """Inspects the container to fetch its assigned network IP address."""
    try:
        cmd = [
            "docker", "inspect", 
            "-f", "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}", 
            container_name
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception as e:
        raise RuntimeError(f"Failed to inspect IP address of container '{container_name}': {e}")

def run_in_docker(
    container_name: str,
    run_input_dir: Path,
    entrypoint: str,
    args: List[str],
    env: Dict[str, str],
    timeout: int,
    language: str,
    target_host: str,
    target_port: int
) -> Tuple[int, str, str, bool]:
    """Orchestrates container lifecycle, applies firewall, execs code, captures logs, and cleans up."""
    image = get_runner_image(language)
    
    # 1. Construct the docker run command to start a detached sleeper container
    # Sagemath usually runs as uid 1000, python runs under uid 1000 inside the Dockerfile.
    # We enforce limits here.
    docker_run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--memory", DOCKER_MEMORY,
        "--cpus", str(DOCKER_CPUS),
        "--pids-limit", str(DOCKER_PIDS_LIMIT),
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "-v", f"{run_input_dir.resolve()}:/work:rw",
        "-v", "/home/light/miniforge3:/home/light/miniforge3:ro",
        "-w", "/work",
        "-e", f"CTF_HOST={target_host}",
        "-e", f"CTF_PORT={target_port}",
    ]
    
    # Add environment variables requested by user
    for k, v in env.items():
        docker_run_cmd.extend(["-e", f"{k}={v}"])
        
    docker_run_cmd.extend([image, "sleep", str(timeout + 30)])
    
    log_audit_event("DOCKER_START", {
        "container_name": container_name,
        "image": image,
        "timeout": timeout,
        "target": f"{target_host}:{target_port}",
        "language": language
    })
    
    # 2. Launch container
    try:
        res = subprocess.run(docker_run_cmd, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as e:
        log_audit_event("DOCKER_START_FAIL", {"error": e.stderr})
        return -1, "", f"Failed to start Docker container: {e.stderr}", False

    container_ip = ""
    firewall_applied = False
    
    try:
        # 3. Fetch container IP and apply egress firewall
        if ENABLE_EGRESS_FIREWALL:
            # Settle network setup briefly
            time.sleep(0.5)
            container_ip = get_container_ip(container_name)
            apply_egress_rules(container_ip, target_host, target_port)
            firewall_applied = True
            
        # 4. Construct execution command
        exec_executable = "sage" if language.lower() == "sage" else "python3"
        exec_cmd = ["docker", "exec"]
        
        # Inject environments to exec too
        for k, v in env.items():
            exec_cmd.extend(["-e", f"{k}={v}"])
            
        exec_cmd.extend([container_name, exec_executable, entrypoint])
        exec_cmd.extend(args)
        
        # 5. Exec solver with timeout
        timed_out = False
        exit_code = -1
        stdout_bytes = b""
        stderr_bytes = b""
        
        try:
            # We capture as bytes to handle raw binaries from CTF output safely
            res_exec = subprocess.run(exec_cmd, capture_output=True, timeout=timeout)
            exit_code = res_exec.returncode
            stdout_bytes = res_exec.stdout
            stderr_bytes = res_exec.stderr
        except subprocess.TimeoutExpired as te:
            timed_out = True
            exit_code = -1
            stdout_bytes = te.output or b""
            stderr_bytes = (te.stderr or b"") + b"\n[MCP SERVER] Process timed out after " + str(timeout).encode() + b" seconds."
            log_audit_event("RUN_TIMEOUT", {"container_name": container_name, "timeout": timeout})
            
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        
        log_audit_event("DOCKER_END", {
            "container_name": container_name,
            "exit_code": exit_code,
            "timed_out": timed_out
        })
        
        return exit_code, stdout, stderr, timed_out
        
    finally:
        # 6. Stop and remove the container
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        subprocess.run(["docker", "rm", container_name], capture_output=True)
        
        # 7. Cleanup egress firewall
        if firewall_applied and container_ip:
            remove_egress_rules(container_ip, target_host, target_port)
