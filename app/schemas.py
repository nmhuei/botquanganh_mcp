from typing import List, Dict, Optional
from pydantic import BaseModel, Field, field_validator, model_validator
from app.config import DEFAULT_TIMEOUT_SECONDS

class HealthCheckRequest(BaseModel):
    pass

class HealthCheckResponse(BaseModel):
    ok: bool
    service: str
    version: str
    server_time: str
    runner_images: List[str]

class Target(BaseModel):
    host: str
    port: int
    protocol: str = "tcp"

class SandboxFailure(BaseModel):
    attempted: bool
    attempted_at: Optional[str] = None
    reason: str
    error_excerpt: Optional[str] = None
    command_summary: Optional[str] = None

    @field_validator("attempted")
    def validate_attempted(cls, v):
        if not v:
            raise ValueError("sandbox_failure.attempted must be true to trigger fallback runner")
        return v

    @field_validator("reason")
    def validate_reason(cls, v):
        if not v or not v.strip():
            raise ValueError("sandbox_failure.reason cannot be empty")
        return v

class LocalValidation(BaseModel):
    solved_locally: bool
    summary: str
    solver_sha256: Optional[str] = None

    @field_validator("solved_locally")
    def validate_solved_locally(cls, v):
        if not v:
            raise ValueError("local_validation.solved_locally must be true to trigger fallback runner")
        return v

class FileEntry(BaseModel):
    path: str
    encoding: Optional[str] = None  # "text" or "base64"
    content: Optional[str] = None
    artifact_id: Optional[str] = None

    @field_validator("encoding")
    def validate_encoding(cls, v):
        if v is not None and v not in ("text", "base64"):
            raise ValueError("encoding must be 'text' or 'base64'")
        return v

    @model_validator(mode="after")
    def validate_content_or_artifact(self):
        if self.artifact_id is None:
            if self.encoding is None or self.content is None:
                raise ValueError("Either (encoding and content) or artifact_id must be provided.")
        return self

class FallbackRequest(BaseModel):
    target: Target
    language: str = "python"
    entrypoint: str = "solve.py"
    args: List[str] = Field(default_factory=list)
    env: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    sandbox_failure: SandboxFailure
    local_validation: LocalValidation
    files: List[FileEntry]

class FallbackResponse(BaseModel):
    ok: bool
    run_id: str
    target: str
    exit_code: int
    duration_ms: int
    stdout: str
    stderr: str
    stdout_sha256: str
    stderr_sha256: str
    transcript_sha256: str
    truncated: bool
    log_summary: List[str]

class GetRunLogRequest(BaseModel):
    run_id: str
    include_transcript: bool = True

class GetRunLogResponse(BaseModel):
    ok: bool
    run_id: str
    metadata: Dict
    audit_log: str
    transcript: str
    sha256: Dict[str, str]

class ListRecentRunsRequest(BaseModel):
    limit: int = 20

class RunSummary(BaseModel):
    run_id: str
    target: str
    exit_code: int
    created_at: str
    duration_ms: int

class ListRecentRunsResponse(BaseModel):
    ok: bool
    runs: List[RunSummary]

class ProbeTargetRequest(BaseModel):
    target: Target
    sandbox_failure_reason: str

class ProbeTargetResponse(BaseModel):
    ok: bool
    reachable: bool
    banner: Optional[str] = None
    duration_ms: int
