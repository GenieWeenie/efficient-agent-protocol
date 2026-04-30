#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-quick}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PY="${ROOT_DIR}/.venv/bin/python"
STREAMLIT_BIN="${ROOT_DIR}/.venv/bin/streamlit"

if [[ ! -x "${VENV_PY}" ]]; then
  echo "[gate:error] Missing venv python at ${VENV_PY}. Run ./scripts/bootstrap_local.sh first."
  exit 1
fi

PASS_COUNT=0
FAIL_COUNT=0
FAIL_LIST=()

run_gate() {
  local name="$1"
  shift
  echo "[gate] RUN ${name}"
  if "$@"; then
    echo "[gate] PASS ${name}"
    PASS_COUNT=$((PASS_COUNT + 1))
  else
    echo "[gate] FAIL ${name}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
    FAIL_LIST+=("${name}")
  fi
  echo
}

run_pytest() {
  "${VENV_PY}" -m pytest -q "$@"
}

run_ui_smoke() {
  if [[ ! -x "${STREAMLIT_BIN}" ]]; then
    echo "[gate:error] streamlit not installed in .venv"
    return 1
  fi

  local port="${EAP_UI_PORT:-8501}"
  local pid

  cd "${ROOT_DIR}"
  "${STREAMLIT_BIN}" run app.py --server.headless true --server.port "${port}" > /tmp/eap_streamlit.log 2>&1 &
  pid=$!

  for _ in $(seq 1 20); do
    if curl -I -sS "http://127.0.0.1:${port}" >/tmp/eap_ui_health.txt; then
      if grep -q "200" /tmp/eap_ui_health.txt; then
        kill "${pid}" >/dev/null 2>&1 || true
        return 0
      fi
    fi
    sleep 1
  done

  kill "${pid}" >/dev/null 2>&1 || true
  echo "[gate:error] UI health check failed. streamlit log: /tmp/eap_streamlit.log"
  return 1
}

cd "${ROOT_DIR}"

case "${MODE}" in
  quick)
    run_gate "contract+unit" run_pytest tests/contract tests/unit
    ;;
  integration)
    run_gate "runtime-http-api" run_pytest tests/integration/test_runtime_http_api.py
    run_gate "resume-replay-hitl-traces" run_pytest \
      tests/integration/test_resume_replay.py \
      tests/integration/test_human_approval.py \
      tests/integration/test_execution_traces.py
    run_gate "provider-matrix" run_pytest \
      tests/integration/test_provider_selection.py \
      tests/unit/test_provider_adapters.py
    ;;
  ui)
    run_gate "streamlit-ui-smoke" run_ui_smoke
    ;;
  perf)
    run_gate "perf-suite" run_pytest tests/perf
    ;;
  full)
    run_gate "full-suite" run_pytest
    ;;
  all)
    run_gate "contract+unit" run_pytest tests/contract tests/unit
    run_gate "runtime-http-api" run_pytest tests/integration/test_runtime_http_api.py
    run_gate "resume-replay-hitl-traces" run_pytest \
      tests/integration/test_resume_replay.py \
      tests/integration/test_human_approval.py \
      tests/integration/test_execution_traces.py
    run_gate "provider-matrix" run_pytest \
      tests/integration/test_provider_selection.py \
      tests/unit/test_provider_adapters.py
    run_gate "streamlit-ui-smoke" run_ui_smoke
    run_gate "perf-suite" run_pytest tests/perf
    ;;
  *)
    echo "Usage: ./scripts/test_gates.sh [quick|integration|ui|perf|full|all]"
    exit 2
    ;;
esac

echo "[gate] SUMMARY mode=${MODE} pass=${PASS_COUNT} fail=${FAIL_COUNT}"
if (( FAIL_COUNT > 0 )); then
  echo "[gate] FAILED: ${FAIL_LIST[*]}"
  exit 1
fi
