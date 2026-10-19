#!/usr/bin/env bash
# bin/run.sh — 일일 루틴 실행 래퍼 (껍데기)
# ------------------------------------------------------------------
# 실제 마케팅 실행 로직은 이 스크립트에 넣지 않는다.
# 락/킬스위치/로그 디렉토리 뼈대만 담당하고, 실행할 단계 목록을 출력하면
# 오케스트레이터 AI 에이전트가 SPEC 8장에 따라 각 단계를 수행한다.
#
# 사용법:
#   bin/run.sh [--business <slug>] [--date YYYY-MM-DD] [--dry-run] [--stage 수집|분석|제작|검수|발행|보고]
# ------------------------------------------------------------------
set -euo pipefail
export TZ=Asia/Seoul

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUSINESS="main"
DATE="$(date +%F)"
DRY_RUN=0
STAGE=""

usage() {
  cat <<'EOF'
사용법: bin/run.sh [--business <slug>] [--date YYYY-MM-DD] [--dry-run] [--stage 수집|분석|제작|검수|발행|보고]

  --business 사업 슬러그 (기본: main).
             businesses/<slug>/ 아래의 config.yaml, state/, logs/ 를 사용한다.
  --date     실행 기준 날짜 (기본: 오늘, KST)
  --dry-run  발행 단계 제외하고 실행
  --stage    지정한 단계만 실행
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --business) BUSINESS="${2:?--business 에는 사업 슬러그가 필요합니다}"; shift 2 ;;
    --date)    DATE="${2:?--date 에는 날짜가 필요합니다}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --stage)   STAGE="${2:?--stage 에는 단계명이 필요합니다}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[run] 알 수 없는 인자: $1" >&2; usage; exit 1 ;;
  esac
done

# 사업 슬러그 형식 검증 (경로 탈출 방지)
if [[ ! "$BUSINESS" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "[run] 잘못된 사업 슬러그: $BUSINESS (영문·숫자·-·_ 만 허용)" >&2
  exit 1
fi

# 날짜 형식 검증
if ! date -d "$DATE" +%F >/dev/null 2>&1; then
  echo "[run] 잘못된 날짜 형식: $DATE (YYYY-MM-DD)" >&2
  exit 1
fi

BIZ_DIR="$ROOT/businesses/$BUSINESS"
STATE="$BIZ_DIR/state"
KILL_FILE="$STATE/KILL"
LOCK_FILE="$STATE/scheduler.lock"

# 사업 설정 확인 — 없으면 템플릿에서 복사하도록 안내
if [[ ! -f "$BIZ_DIR/config.yaml" ]]; then
  echo "[run] 오류: 사업 [$BUSINESS] 의 설정 파일이 없습니다: businesses/$BUSINESS/config.yaml" >&2
  echo "[run] templates/config.yaml 을 businesses/$BUSINESS/config.yaml 로 복사한 뒤" >&2
  echo "[run] 사업 정보를 입력하시오. (templates/knowledge/ 도 businesses/$BUSINESS/knowledge/ 로 복사)" >&2
  exit 4
fi

mkdir -p "$STATE"

# 1. 킬스위치 확인 (SPEC 11.2)
if [[ -f "$KILL_FILE" ]]; then
  echo "[run] 중단: 킬스위치가 발동되어 있습니다."
  echo "--- businesses/$BUSINESS/state/KILL ---"
  cat "$KILL_FILE"
  echo "해제: bin/resume.sh --business $BUSINESS"
  exit 2
fi

# 2. 락 확인 — 24시간 이상 된 락은 stale로 간주하고 경고 후 제거 (SPEC 8.3)
if [[ -f "$LOCK_FILE" ]]; then
  LOCK_MTIME="$(stat -c %Y "$LOCK_FILE")"
  NOW="$(date +%s)"
  AGE_H=$(( (NOW - LOCK_MTIME) / 3600 ))
  if [[ "$AGE_H" -ge 24 ]]; then
    echo "[run] 경고: 24시간 이상 된 stale 락을 무시하고 제거합니다."
    cat "$LOCK_FILE" 2>/dev/null || true
    rm -f "$LOCK_FILE"
  else
    echo "[run] 중단: 이미 실행 중인 루틴이 있습니다."
    cat "$LOCK_FILE"
    exit 3
  fi
fi

# 3. 락 생성 — 종료(정상/비정상) 시 삭제
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
printf '{"started_at":"%s","host":"%s","run_id":"%s","pid":%s}\n' \
  "$(date -Iseconds)" "$(hostname)" "$RUN_ID" "$$" > "$LOCK_FILE"
cleanup() { rm -f "$LOCK_FILE"; }
trap cleanup EXIT

# 4. 실행 단계 목록 결정 (검증 후 로그 디렉토리 생성)
ALL_STAGES=(수집 분석 제작 검수 발행 보고)
if [[ -n "$STAGE" ]]; then
  VALID=0
  for s in "${ALL_STAGES[@]}"; do
    [[ "$s" == "$STAGE" ]] && VALID=1
  done
  if [[ "$VALID" -ne 1 ]]; then
    echo "[run] 잘못된 단계: $STAGE (수집|분석|제작|검수|발행|보고 중 선택)" >&2
    exit 1
  fi
  STAGES=("$STAGE")
else
  STAGES=("${ALL_STAGES[@]}")
fi

# 5. 로그 디렉토리 생성
LOGDIR="$BIZ_DIR/logs/$DATE"
mkdir -p "$LOGDIR"

# 드라이런: 발행 단계 제외 (SPEC 16.2)
if [[ "$DRY_RUN" -eq 1 ]]; then
  FILTERED=()
  for s in "${STAGES[@]}"; do
    [[ "$s" != "발행" ]] && FILTERED+=("$s")
  done
  STAGES=("${FILTERED[@]}")
  echo "[run] 드라이런 모드: 발행 단계 제외"
fi

echo "[run] 날짜: $DATE / run_id: $RUN_ID"
echo ""
echo "오케스트레이터 AI 에이전트는 아래 단계들을 순서대로 실행하시오 (사업: $BUSINESS):"
i=1
for s in "${STAGES[@]}"; do
  echo "  $i. $s"
  i=$((i + 1))
done
echo ""
echo "수행 규칙 (SPEC 8장):"
echo "  - 매 단계 시작 전 businesses/$BUSINESS/state/KILL 존재 여부를 확인할 것"
echo "  - '발행' 단계는 API 채널(Threads·Instagram·YouTube) 대상."
echo "    네이버 블로그는 별도 09:00 트리거에서 큐의 naver_blog 대기건을"
echo "    09:00~11:00 랜덤 지연 후 playbooks/naver-blog-publish.task.md 로 발행"
echo "  - 단계별 산출물은 businesses/$BUSINESS/logs/$DATE/ 및 businesses/$BUSINESS/reports/ 에 저장"
echo "  - 단계 실패 시 businesses/$BUSINESS/state/dead_letter.jsonl에 기록하고 다음 단계로 진행"
echo "    (단, 락 획득·헬스체크 같은 치명 단계 실패 시 루틴 전체 중단)"
echo "  - 종료 후 businesses/$BUSINESS/state/ 는 Git에 커밋하지 않는다 (SPEC 10.3: state/는 Git 추적 제외)"
