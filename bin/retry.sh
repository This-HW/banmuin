#!/usr/bin/env bash
# bin/retry.sh — 단계 재실행 (수동 복구용, SPEC 13.4)
# ------------------------------------------------------------------
# 사용법: bin/retry.sh [--business <slug>] --stage <수집|분석|제작|검수|발행|보고> --date YYYY-MM-DD [--force]
#   --force: 멱등키를 무시하고 재발행 허용 (의도적 재발행 전용)
# ------------------------------------------------------------------
set -euo pipefail
export TZ=Asia/Seoul

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUSINESS="main"
STAGE=""
DATE=""
FORCE=0

usage() {
  cat <<'EOF'
사용법: bin/retry.sh [--business <slug>] --stage <단계> --date YYYY-MM-DD [--force]

  --business 사업 슬러그 (기본: main).
             businesses/<slug>/ 아래의 config.yaml, state/, logs/ 를 사용한다.
  --stage  수집|분석|제작|검수|발행|보고 중 하나 (필수)
  --date   실행 기준 날짜 (필수)
  --force  멱등키 무시하고 재발행 허용 (의도적 재발행 전용)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --business) BUSINESS="${2:?--business 에는 사업 슬러그가 필요합니다}"; shift 2 ;;
    --stage) STAGE="${2:?--stage 에는 단계명이 필요합니다}"; shift 2 ;;
    --date)  DATE="${2:?--date 에는 날짜가 필요합니다}"; shift 2 ;;
    --force) FORCE=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[retry] 알 수 없는 인자: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ -z "$STAGE" || -z "$DATE" ]]; then
  echo "[retry] --stage 와 --date 는 필수입니다." >&2
  usage
  exit 1
fi

# 사업 슬러그 형식 검증 (경로 탈출 방지)
if [[ ! "$BUSINESS" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "[retry] 잘못된 사업 슬러그: $BUSINESS (영문·숫자·-·_ 만 허용)" >&2
  exit 1
fi

case "$STAGE" in
  수집|분석|제작|검수|발행|보고) ;;
  *) echo "[retry] 잘못된 단계: $STAGE" >&2; exit 1 ;;
esac

if ! date -d "$DATE" +%F >/dev/null 2>&1; then
  echo "[retry] 잘못된 날짜 형식: $DATE (YYYY-MM-DD)" >&2
  exit 1
fi

BIZ_DIR="$ROOT/businesses/$BUSINESS"
STATE="$BIZ_DIR/state"
KILL_FILE="$STATE/KILL"
LOCK_FILE="$STATE/scheduler.lock"

# 사업 설정 확인 — 없으면 템플릿에서 복사하도록 안내
if [[ ! -f "$BIZ_DIR/config.yaml" ]]; then
  echo "[retry] 오류: 사업 [$BUSINESS] 의 설정 파일이 없습니다: businesses/$BUSINESS/config.yaml" >&2
  echo "[retry] templates/config.yaml 을 businesses/$BUSINESS/config.yaml 로 복사하시오." >&2
  exit 4
fi

# 킬스위치 확인
if [[ -f "$KILL_FILE" ]]; then
  echo "[retry] 중단: 킬스위치가 발동되어 있습니다. bin/resume.sh --business $BUSINESS 로 해제한 뒤 재시도하시오."
  exit 2
fi

# 실행 중 락 확인 (재실행은 루틴이 돌고 있지 않을 때만)
if [[ -f "$LOCK_FILE" ]]; then
  echo "[retry] 중단: 루틴이 실행 중입니다. 종료 후 재시도하시오."
  cat "$LOCK_FILE"
  exit 3
fi

mkdir -p "$BIZ_DIR/logs/$DATE"

echo "[retry] 사업: $BUSINESS / 재실행 대상: 단계=[$STAGE] 날짜=[$DATE]"
if [[ "$FORCE" -eq 1 ]]; then
  echo "[retry] --force 지정: 멱등키를 무시하고 재발행합니다."
else
  echo "[retry] 멱등키(businesses/$BUSINESS/state/publish_log.jsonl) 기준으로 중복 발행을 방지합니다."
fi
echo ""
echo "오케스트레이터 AI 에이전트는 [$STAGE] 단계를 $DATE 기준으로 재실행하시오 (사업: $BUSINESS)."
echo "실패 원인 분석은 businesses/$BUSINESS/logs/$DATE/ 를 참조할 것."
