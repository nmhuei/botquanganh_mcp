import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

from app.config import (
    DOCKER_MEMORY,
    DOCKER_CPUS,
    DOCKER_PIDS_LIMIT,
    DOCKER_USER,
    RUNNER_IMAGES,
)
from app.logging_audit import log_audit_event


def get_runner_image(language: str) -> str:
    """Maps language profile to Docker image name."""
    return RUNNER_IMAGES.get(language.lower(), RUNNER_IMAGES["python"])


def run_in_docker(
    container_name: str,
    run_input_dir: Path,
    entrypoint: str,
    args: List[str],
    env: Dict[str, str],
    timeout: int,
    language: str,
    target_host: str,
    target_port: int,
) -> Tuple[int, str, str, bool]:
    """Orchestrates container lifecycle, execs code, captures logs, and cleans up."""
    image = get_runner_image(language)
    is_networked = bool(target_host and target_host not in ("localhost", "127.0.0.1"))
    network_mode = "bridge" if is_networked else "none"

    # Construct docker run command
    docker_run_cmd = [
        "docker", "run", "-d",
        "--name", container_name,
        "--network", network_mode,
        "--memory", DOCKER_MEMORY,
        "--cpus", str(DOCKER_CPUS),
        "--pids-limit", str(DOCKER_PIDS_LIMIT),
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "-v", f"{run_input_dir.resolve()}:/work:rw",
        "-w", "/work",
        "-e", f"TARGET_HOST={target_host}",
        "-e", f"TARGET_PORT={target_port}",
        "-e", f"CTF_HOST={target_host}",
        "-e", f"CTF_PORT={target_port}",
    ]

    for k, v in env.items():
        docker_run_cmd.extend(["-e", f"{k}={v}"])

    docker_run_cmd.extend([image, "sleep", str(timeout + 30)])

    log_audit_event("DOCKER_START", {
        "container_name": container_name,
        "image": image,
        "timeout": timeout,
        "target": f"{target_host}:{target_port}",
        "language": language,
    })

    # Launch container
    try:
        res = subprocess.run(docker_run_cmd, capture_output=True, check=True, text=True)
    except subprocess.CalledProcessError as e:
        log_audit_event("DOCKER_START_FAIL", {"error": e.stderr})
        return -1, "", f"Failed to start Docker container: {e.stderr}", False

    try:
        # Construct exec command
        exec_executable = "sage" if language.lower() == "sage" else "python3"
        exec_cmd = [
            "docker", "exec",
            "-e", f"TARGET_HOST={target_host}",
            "-e", f"TARGET_PORT={target_port}",
            "-e", f"CTF_HOST={target_host}",
            "-e", f"CTF_PORT={target_port}",
            container_name,
            exec_executable, entrypoint,
        ]
        for k, v in env.items():
            exec_cmd.extend(["-e", f"{k}={v}"])
        exec_cmd.extend(args)

        # Exec solver with timeout
        timed_out = False
        exit_code = -1
        stdout_bytes = b""
        stderr_bytes = b""

        try:
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
            "timed_out": timed_out,
        })

        return exit_code, stdout, stderr, timed_out

    finally:
        # Cleanup container
        subprocess.run(["docker", "kill", container_name], capture_output=True)
        subprocess.run(["docker", "rm", container_name], capture_output=True)
