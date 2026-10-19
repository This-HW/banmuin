#!/usr/bin/env bash
# bin/dlq.sh — DLQ(Dead Letter Queue) 관리 (SPEC 13.3)
# ------------------------------------------------------------------
# 사용법:
#   bin/dlq.sh [--business <slug>] list            # state/dead_letter.jsonl 내용 출력
#   bin/dlq.sh [--business <slug>] resolve <id>    # 해당 항목을 state/queue.jsonl 로 복구 (상태=queued)
# ------------------------------------------------------------------
set -euo pipefail
export TZ=Asia/Seoul

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

BUSINESS="main"

usage() {
  cat <<'EOF'
사용법:
  bin/dlq.sh [--business <slug>] list            DLQ 내용 출력
  bin/dlq.sh [--business <slug>] resolve <id>    해당 항목을 발행 큐로 복구 (상태=queued)

  --business 사업 슬러그 (기본: main).
             businesses/<slug>/state/ 아래의 DLQ·큐를 다룬다.
EOF
}

# --business 플래그는 서브커맨드 앞·뒤 어디서든 허용
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --business) BUSINESS="${2:?--business 에는 사업 슬러그가 필요합니다}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done
if [[ ${#POSITIONAL[@]} -gt 0 ]]; then
  set -- "${POSITIONAL[@]}"
else
  set --
fi

# 사업 슬러그 형식 검증 (경로 탈출 방지)
if [[ ! "$BUSINESS" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  echo "[dlq] 잘못된 사업 슬러그: $BUSINESS (영문·숫자·-·_ 만 허용)" >&2
  exit 1
fi

BIZ_DIR="$ROOT/businesses/$BUSINESS"
STATE="$BIZ_DIR/state"
DLQ="$STATE/dead_letter.jsonl"
QUEUE="$STATE/queue.jsonl"

CMD="${1:-}"
case "$CMD" in
  list)
    if [[ ! -f "$DLQ" ]] || [[ ! -s "$DLQ" ]]; then
      echo "[dlq] 사업 [$BUSINESS] 의 DLQ가 비어 있습니다."
      exit 0
    fi
    if command -v python3 >/dev/null 2>&1; then
      python3 - "$DLQ" <<'EOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        print(json.dumps(json.loads(line), ensure_ascii=False, indent=2))
        print("---")
EOF
    else
      cat "$DLQ"
    fi
    ;;
  resolve)
    TARGET_ID="${2:?사용법: bin/dlq.sh [--business <slug>] resolve <id>}"
    if [[ ! -f "$DLQ" ]] || [[ ! -s "$DLQ" ]]; then
      echo "[dlq] 사업 [$BUSINESS] 의 DLQ가 비어 있습니다." >&2
      exit 1
    fi
    if ! command -v python3 >/dev/null 2>&1; then
      echo "[dlq] python3이 필요합니다. 수동으로 $DLQ 에서 id=$TARGET_ID 항목을" >&2
      echo "      $QUEUE 로 옮기고 status를 \"queued\"로 변경하시오." >&2
      exit 1
    fi
    mkdir -p "$STATE"
    touch "$QUEUE"
    python3 - "$DLQ" "$QUEUE" "$TARGET_ID" <<'EOF'
import json, sys
from datetime import datetime, timezone, timedelta

dlq_path, queue_path, target_id = sys.argv[1], sys.argv[2], sys.argv[3]
kst = timezone(timedelta(hours=9))

moved = None
kept = []
with open(dlq_path, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if moved is None and obj.get("id") == target_id:
            moved = obj
        else:
            kept.append(line)

if moved is None:
    print(f"[dlq] id={target_id} 를 DLQ에서 찾을 수 없습니다.", file=sys.stderr)
    sys.exit(1)

moved["status"] = "queued"
moved["resolved_at"] = datetime.now(kst).isoformat()

with open(dlq_path, "w", encoding="utf-8") as f:
    if kept:
        f.write("\n".join(kept) + "\n")

with open(queue_path, "a", encoding="utf-8") as f:
    f.write(json.dumps(moved, ensure_ascii=False) + "\n")

print(f"[dlq] id={target_id} 를 발행 큐로 복구했습니다 (status=queued).")
EOF
    ;;
  *)
    usage
    exit 1
    ;;
esac
