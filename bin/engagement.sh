#!/usr/bin/env bash
# bin/engagement.sh — 인스타그램 댓글→DM 트리거 래퍼 (껍데기, SPEC 21장)
# ------------------------------------------------------------------
# 실제 댓글 처리 로직은 이 스크립트에 넣지 않는다.
# 락/킬스위치/알림 큐 drain/활성화 확인 뼈대만 담당하고, 실행할 단계 목록을
# 출력하면 오케스트레이터 AI 에이전트가 skills/engagement/SKILL.md 순서대로
# 각 단계를 수행한다. (bin/run.sh 와 동일한 "껍데기 + 에이전트" 구조)
#
# 사용법:
#   bin/engagement.sh [--business <slug>]
#
# 종료 코드:
#   0 — 정상 (no-op 포함)
#   2 — KILL 발동 중 (실행하지 않음)
#   3 — 다른 engagement 실행이 진행 중
#   4 — 사업 설정 파일 없음
# ------------------------------------------------------------------
set -euo pipefail
export TZ=Asia/Seoul

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUSINESS="main"

usage() {
  cat <<'EOF'
사용법: bin/engagement.sh [--business <slug>]

  --business 사업 슬러그 (기본: main).
             businesses/<slug>/ 아래의 config.yaml, state/ 를 사용한다.
             30분 간격 cron에서 호출한다 (SPEC 21.4).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --business) BUSINESS="${2:?--business 에는 사업 슬러그가 필요합니다}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "[engagement] 알 수 없는 인자: $1" >&2; usage; exit 1 ;;
  esac
done

# 사업 슬러그 형식 검증 (경로 탈출 방지)
if [[ ! "$BUSINESS" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "[engagement] 잘못된 사업 슬러그: $BUSINESS (영문·숫자·-·_ 만 허용)" >&2
  exit 1
fi

BIZ_DIR="$ROOT/businesses/$BUSINESS"
STATE="$BIZ_DIR/state"
KILL_FILE="$STATE/KILL"
LOCK_FILE="$STATE/engagement.lock"

# 사업 설정 확인 — 없으면 템플릿에서 복사하도록 안내
if [[ ! -f "$BIZ_DIR/config.yaml" ]]; then
  echo "[engagement] 오류: 사업 [$BUSINESS] 의 설정 파일이 없습니다: businesses/$BUSINESS/config.yaml" >&2
  echo "[engagement] templates/config.yaml 을 businesses/$BUSINESS/config.yaml 로 복사한 뒤" >&2
  echo "[engagement] 사업 정보를 입력하시오." >&2
  exit 4
fi

mkdir -p "$STATE"

# 1. 킬스위치 확인 (SKILL.md [1]-2)
if [[ -f "$KILL_FILE" ]]; then
  echo "[engagement] 중단: 킬스위치가 발동되어 있습니다."
  echo "--- businesses/$BUSINESS/state/KILL ---"
  cat "$KILL_FILE"
  echo "텔레그램으로 알리시오: 🛑 KILL 발동 중이라 engagement 트리거를 중단했습니다 ($BUSINESS)."
  exit 2
fi

# 2. 락 확인 — engagement 전용 락. 2시간 이상 된 락은 stale로 간주하고 제거 (SKILL.md [1]-1)
#    (일일 루틴의 scheduler.lock — 24시간 기준 — 과 별도 파일이다)
if [[ -f "$LOCK_FILE" ]]; then
  LOCK_MTIME="$(stat -c %Y "$LOCK_FILE")"
  NOW="$(date +%s)"
  AGE_H=$(( (NOW - LOCK_MTIME) / 3600 ))
  if [[ "$AGE_H" -ge 2 ]]; then
    echo "[engagement] 경고: 2시간 이상 된 stale 락을 무시하고 제거합니다."
    cat "$LOCK_FILE" 2>/dev/null || true
    rm -f "$LOCK_FILE"
  else
    echo "[engagement] 중단: 이미 실행 중인 engagement가 있습니다."
    cat "$LOCK_FILE"
    exit 3
  fi
fi

# 3. 락 생성 — 종료(정상/비정상) 시 삭제
RUN_ID="$(date +%Y%m%d-%H%M%S)-$$"
printf '{"started_at":"%s","host":"%s","run_id":"%s"}\n' \
  "$(date -Iseconds)" "$(hostname)" "$RUN_ID" > "$LOCK_FILE"
cleanup() { rm -f "$LOCK_FILE"; }
trap cleanup EXIT

# 4. 알림 큐 drain — 원자적 rename 절차 (SPEC 20.5, SKILL.md [1]-3)
#    rename은 원자적이므로 동시에 drain을 시도한 트리거 중 하나만 성공한다.
DRAIN_SRC="$STATE/notification_queue.jsonl"
DRAIN_DST="$STATE/notification_queue.draining.$RUN_ID.jsonl"
if [[ -f "$DRAIN_SRC" ]]; then
  if mv "$DRAIN_SRC" "$DRAIN_DST" 2>/dev/null; then
    echo "[engagement] 알림 큐를 drain했습니다: $(basename "$DRAIN_DST")"
    echo "아래 각 줄을 텔레그램으로 발송하시오 (SPEC 20.5 타입별 문구):"
    cat "$DRAIN_DST"
    echo "발송이 끝나면 $DRAIN_DST 파일을 삭제하시오."
    echo "detail에 config_changed가 있으면 detail.keys를 확인하고,"
    echo "예산 캡·게이트 임계값 변경이 포함된 경우 knowledge/08_승인기준.md 정본에도 동일하게 반영하시오."
  else
    echo "[engagement] 알림 큐가 비어 있음 (다른 트리거가 이미 drain함)."
  fi
else
  echo "[engagement] 알림 큐가 비어 있음."
fi

# 5. 활성화 확인 — engagement.comment_to_dm.enabled (SKILL.md [2])
#    config.yaml 인덴트 기반 최소 파서 (인라인·block 무관)
ENG_ENABLED="$(awk '
  /^engagement:/ { in_eng=1; next }
  /^[^ \t#]/ && in_eng { in_eng=0 }
  in_eng && /^  comment_to_dm:/ { in_ctd=1; next }
  in_eng && /^  [^ \t]/ { in_ctd=0 }
  in_ctd && /^    enabled:/ {
    v=$2; sub(/#.*/, "", v); gsub(/^[ \t]+|[ \t]+$/, "", v)
    print v; exit
  }
' "$BIZ_DIR/config.yaml")"

if [[ "$ENG_ENABLED" != "true" ]]; then
  echo "[engagement] no-op 종료: engagement.comment_to_dm.enabled=true가 아닙니다 (현재: ${ENG_ENABLED:-미설정})."
  echo "[engagement] 자동 발송 계열은 대표의 명시적 opt-in 없이는 동작하지 않습니다."
  exit 0
fi

# 6. 단계 목록 출력 — 에이전트가 skills/engagement/SKILL.md 순서대로 수행
cat <<EOF
[engagement] 사업 [$BUSINESS] 댓글→DM 실행을 시작합니다.
아래 단계를 skills/engagement/SKILL.md의 절차에 따라 순서대로 수행하시오.

  [3] 토큰 만료 확인 — secrets.env의 INSTAGRAM_ACCESS_TOKEN을 debug_token으로 조회.
      만료까지 7일 이하면 텔레그램으로 알리고 계속 진행 (토큰 갱신은 사람이 수행).
  [4] 상태 읽기 — state/engagement.json (없으면 첫 실행, last_check_at=지금 시각).
  [5] 새 댓글 수집 — 내 미디어 목록 → 각 미디어의 댓글 조회.
      timestamp >= last_check_at 인 것만 남기고 오래된 댓글부터 정렬.
      이 단계 실패는 치명 실패: 루틴 중단 + 텔레그램 즉시 알림.
  [6] 댓글별 처리 (max_per_run 상한까지) — 멱등성 체크 → 키워드 필터 →
      공개 답글(템플릿 로테이션) → 팔로우 확인 → DM 발송(7일 이내만) →
      engagement_processed.jsonl에 기록.
  [7] 상태 갱신 — engagement.json의 last_check_at은 이번 실행에서 처리 시도한
      댓글 중 가장 늦은 timestamp로 둔다 (시도분 없으면 기존 값 유지).
      last_run.json은 건드리지 않는다.
  [8] 종료 — 위 trap이 engagement.lock을 해제한다.

주의: 댓글당 공개 답글 1회·DM 1회를 넘지 않는다. 7일이 지난 댓글에는 DM을 보내지 않는다.
처리 로그에 고객 실명·연락처를 기록하지 않는다.
EOF
