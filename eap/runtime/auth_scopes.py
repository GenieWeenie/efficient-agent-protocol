from __future__ import annotations

SCOPE_RUNS_EXECUTE = "runs:execute"
SCOPE_RUNS_RESUME = "runs:resume"
SCOPE_RUNS_READ = "runs:read"
SCOPE_POINTERS_READ = "pointers:read"
SCOPE_RUNS_RESUME_ANY = "runs:resume:any"
SCOPE_RUNS_READ_ANY = "runs:read:any"
SCOPE_POINTERS_READ_ANY = "pointers:read:any"

FULL_RUNTIME_SCOPES = {
    SCOPE_RUNS_EXECUTE,
    SCOPE_RUNS_RESUME,
    SCOPE_RUNS_READ,
    SCOPE_POINTERS_READ,
    SCOPE_RUNS_RESUME_ANY,
    SCOPE_RUNS_READ_ANY,
    SCOPE_POINTERS_READ_ANY,
}

