#!/usr/bin/env bash
# bin/resume.sh — 비상정지 해제 (SPEC 11.2)
# 사용법: bin/resume.sh [--business <slug>]
set -euo pipefail
export TZ=Asia/Seoul

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUSINESS="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --business) BUSINESS="${2:?--business 에는 사업 슬러그가 필요합니다}"; shift 2 ;;
    -h|--help)
      echo "사용법: bin/resume.sh [--business <slug>]"
      echo ""
      echo "  --business 사업 슬러그 (기본: main)."
      echo "             businesses/<slug>/state/KILL 을 해제한다."
      exit 0 ;;
    *) echo "[resume] 알 수 없는 인자: $1" >&2; exit 1 ;;
  esac
done

# 사업 슬러그 형식 검증 (경로 탈출 방지)
if [[ ! "$BUSINESS" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "[resume] 잘못된 사업 슬러그: $BUSINESS (영문·숫자·-·_ 만 허용)" >&2
  exit 1
fi

KILL_FILE="$ROOT/businesses/$BUSINESS/state/KILL"

if [[ ! -f "$KILL_FILE" ]]; then
  echo "[resume] 경고: 사업 [$BUSINESS] 의 킬스위치가 발동되어 있지 않습니다."
  exit 2
fi

rm -f "$KILL_FILE"
echo "[resume] 사업 [$BUSINESS] 킬스위치 해제됨. 루틴을 재개할 수 있습니다."
echo "[resume] SPEC 11.2에 따라 텔레그램으로 해제 알림을 발송하시오."
