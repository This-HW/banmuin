#!/usr/bin/env bash
# bin/kill.sh — 비상정지 (SPEC 11.2)
# 사용법: bin/kill.sh [--business <slug>] "사유"
set -euo pipefail
export TZ=Asia/Seoul

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUSINESS="main"

usage() {
  cat <<'EOF'
사용법: bin/kill.sh [--business <slug>] "사유"

  --business 사업 슬러그 (기본: main).
             businesses/<slug>/state/KILL 에 킬스위치를 발동한다.
EOF
}

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --business) BUSINESS="${2:?--business 에는 사업 슬러그가 필요합니다}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) ARGS+=("$1"); shift ;;
  esac
done

if [[ ${#ARGS[@]} -lt 1 ]]; then
  echo "사용법: bin/kill.sh [--business <slug>] \"사유\"" >&2
  exit 1
fi

# 사업 슬러그 형식 검증 (경로 탈출 방지)
if [[ ! "$BUSINESS" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "[kill] 잘못된 사업 슬러그: $BUSINESS (영문·숫자·-·_ 만 허용)" >&2
  exit 1
fi

BIZ_DIR="$ROOT/businesses/$BUSINESS"
STATE="$BIZ_DIR/state"
KILL_FILE="$STATE/KILL"

mkdir -p "$STATE"

if [[ -f "$KILL_FILE" ]]; then
  echo "[kill] 경고: 사업 [$BUSINESS] 의 킬스위치가 이미 발동되어 있습니다."
  echo "--- businesses/$BUSINESS/state/KILL ---"
  cat "$KILL_FILE"
  exit 2
fi

printf '사업: %s\n사유: %s\n시각: %s\n' "$BUSINESS" "${ARGS[*]}" "$(date '+%Y-%m-%d %H:%M:%S %Z')" > "$KILL_FILE"

echo "[kill] 사업 [$BUSINESS] 킬스위치 발동. 다음 단계 시작 시 모든 실행이 중단됩니다."
echo "[kill] 해제: bin/resume.sh --business $BUSINESS"
echo "[kill] SPEC 11.2에 따라 텔레그램으로 발동 알림을 발송하시오."
