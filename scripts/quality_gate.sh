#!/usr/bin/env bash

set -Eeuo pipefail

readonly SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
readonly FRONTEND_DIR="${PROJECT_ROOT}/frontend"

next_env_backup=""

usage() {
  echo "Usage: scripts/quality_gate.sh [all|backend|frontend|e2e]"
}

run_step() {
  local label="$1"
  shift
  echo "[quality-gate] ${label}"
  "$@"
}

preserve_next_env() {
  if [[ -n "${next_env_backup}" ]]; then
    return
  fi

  next_env_backup="$(mktemp)"
  cp "${FRONTEND_DIR}/next-env.d.ts" "${next_env_backup}"
}

restore_next_env() {
  if [[ -n "${next_env_backup}" && -f "${next_env_backup}" ]]; then
    cp "${next_env_backup}" "${FRONTEND_DIR}/next-env.d.ts"
  fi
}

run_backend() {
  cd "${PROJECT_ROOT}"
  run_step "Ruff" uv run ruff check .
  run_step "mypy" uv run mypy src
  run_step \
    "pytest" \
    uv run pytest tests/unit tests/contract tests/security tests/integration tests/evaluation -q
}

run_frontend() {
  preserve_next_env
  cd "${FRONTEND_DIR}"
  run_step "frontend typecheck" pnpm typecheck
  run_step "frontend lint" pnpm lint
  run_step "frontend unit tests" pnpm test
  run_step "frontend production build" pnpm build
}

run_e2e() {
  preserve_next_env
  cd "${FRONTEND_DIR}"
  run_step "Playwright critical flow" pnpm test:e2e
}

main() {
  local target="${1:-all}"

  if [[ $# -gt 1 ]]; then
    usage
    return 2
  fi

  case "${target}" in
    all)
      run_backend
      run_frontend
      run_e2e
      ;;
    backend)
      run_backend
      ;;
    frontend)
      run_frontend
      ;;
    e2e)
      run_e2e
      ;;
    -h|--help)
      usage
      ;;
    *)
      usage >&2
      return 2
      ;;
  esac
}

trap restore_next_env EXIT
main "$@"
