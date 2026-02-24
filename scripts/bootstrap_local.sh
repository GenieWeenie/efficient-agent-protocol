#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PYTHON_CMD="${PYTHON_CMD:-python3}"
VENV_DIR=".venv"
ENV_FILE=".env"
ARTIFACT_DIR="artifacts/bootstrap"
DB_PATH="artifacts/bootstrap/bootstrap_state.db"
SKIP_INSTALL=0
SKIP_ENV_VALIDATION=0

usage() {
  cat <<'USAGE'
Usage:
  ./scripts/bootstrap_local.sh [options]

Options:
  --python <path>                Python executable to use (default: python3)
  --venv-dir <path>              Virtual environment directory (default: .venv)
  --env-file <path>              Environment file path (default: .env)
  --artifact-dir <path>          Bootstrap artifact directory (default: artifacts/bootstrap)
  --db-path <path>               Bootstrap state DB path (default: artifacts/bootstrap/bootstrap_state.db)
  --skip-install                 Skip venv creation and package install (uses current Python env)
  --skip-env-validation          Skip .env validation
  -h, --help                     Show this help text
USAGE
}

log() {
  echo "[bootstrap] $*"
}

fail() {
  echo "[bootstrap:error] $*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      [[ $# -ge 2 ]] || fail "--python requires a value."
      PYTHON_CMD="$2"
      shift 2
      ;;
    --venv-dir)
      [[ $# -ge 2 ]] || fail "--venv-dir requires a value."
      VENV_DIR="$2"
      shift 2
      ;;
    --env-file)
      [[ $# -ge 2 ]] || fail "--env-file requires a value."
      ENV_FILE="$2"
      shift 2
      ;;
    --artifact-dir)
      [[ $# -ge 2 ]] || fail "--artifact-dir requires a value."
      ARTIFACT_DIR="$2"
      shift 2
      ;;
    --db-path)
      [[ $# -ge 2 ]] || fail "--db-path requires a value."
      DB_PATH="$2"
      shift 2
      ;;
    --skip-install)
      SKIP_INSTALL=1
      shift
      ;;
    --skip-env-validation)
      SKIP_ENV_VALIDATION=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown option: $1"
      ;;
  esac
done

OS_NAME="$(uname -s)"
case "${OS_NAME}" in
  Darwin|Linux)
    ;;
  *)
    fail "Unsupported platform (${OS_NAME}). On Windows, use WSL2 and rerun this command, or follow manual README Quickstart steps."
    ;;
esac

cd "${REPO_ROOT}"

command -v "${PYTHON_CMD}" >/dev/null 2>&1 || fail "Python executable not found: ${PYTHON_CMD}"

"${PYTHON_CMD}" - <<'PY' || fail "Python 3.9-3.13 is required. Install a supported Python version and retry."
import sys
if sys.version_info < (3, 9) or sys.version_info >= (3, 14):
    raise SystemExit(1)
PY

BOOTSTRAP_PYTHON="${PYTHON_CMD}"
BOOTSTRAP_PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

if [[ "${SKIP_INSTALL}" -eq 0 ]]; then
  if [[ ! -d "${VENV_DIR}" ]]; then
    log "Creating virtual environment at ${VENV_DIR}"
    "${PYTHON_CMD}" -m venv "${VENV_DIR}" || fail "Failed to create virtual environment at ${VENV_DIR}."
  else
    log "Reusing virtual environment at ${VENV_DIR}"
  fi

  VENV_PYTHON="${VENV_DIR}/bin/python"
  [[ -x "${VENV_PYTHON}" ]] || fail "Virtual environment python not found: ${VENV_PYTHON}"

  log "Installing package dependencies"
  "${VENV_PYTHON}" -m pip install --upgrade pip || fail "Failed to upgrade pip in ${VENV_DIR}."
  "${VENV_PYTHON}" -m pip install -e . || fail "Failed to install project in editable mode. Run '${VENV_PYTHON} -m pip install -e .' for details."
  BOOTSTRAP_PYTHON="${VENV_PYTHON}"
else
  log "Skipping dependency installation; using current Python environment."
fi

if [[ ! -f "${ENV_FILE}" ]]; then
  [[ -f ".env.example" ]] || fail ".env.example not found. Cannot create ${ENV_FILE}."
  cp .env.example "${ENV_FILE}"
  log "Created ${ENV_FILE} from .env.example"
else
  log "Using existing environment file: ${ENV_FILE}"
fi

if [[ "${SKIP_ENV_VALIDATION}" -eq 0 ]]; then
  PYTHONPATH="${BOOTSTRAP_PYTHONPATH}" "${BOOTSTRAP_PYTHON}" scripts/bootstrap_local.py validate-env --env-file "${ENV_FILE}" \
    || fail "Environment validation failed. Fix ${ENV_FILE} and rerun bootstrap."
else
  log "Skipping environment validation."
fi

PYTHONPATH="${BOOTSTRAP_PYTHONPATH}" "${BOOTSTRAP_PYTHON}" scripts/bootstrap_local.py run-smoke \
  --artifact-dir "${ARTIFACT_DIR}" \
  --db-path "${DB_PATH}" \
  || fail "Smoke workflow failed. See error output above."

log "Bootstrap complete."
log "Run artifact: ${ARTIFACT_DIR}/bootstrap_trace.json"
