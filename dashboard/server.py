#!/usr/bin/env python3
"""
마케팅 자동화 시스템 웹 대시보드 서버 — SPEC 20장 레퍼런스 구현.

- 표준 라이브러리 + ruamel.yaml (4차 설정 편집의 YAML round-trip용) 사용.
- 상태 계약(SPEC 10장)의 파일들을 직접 읽고, 승인된 제어 연산(20.5)만 수행한다.
- 새로운 실행 로직을 만들지 않는다. 효과는 대응하는 bin/*.sh와 동일해야 한다.
- secrets.env는 쓰기만 하고 읽기는 어떤 API로도 제공하지 않는다 (write-only, 20.10 4차).

환경변수:
  DASHBOARD_TOKEN      Bearer 토큰 (필수, 없으면 시작 거부)
  DASHBOARD_REPO_ROOT  저장소 루트 (기본: 이 스크립트의 상위 디렉토리 = 저장소 루트)
  DASHBOARD_PORT       포트 (기본: 8787)

의존성: 표준 라이브러리만으로 동작. 단, 대시보드 설정 화면의 YAML 편집은
ruamel.yaml이 필요하다 (없으면 해당 API가 에러 메시지와 함께 실패).
설치: pip install ruamel.yaml
"""
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote

KST = timezone(timedelta(hours=9))
# 기본값: dashboard/server.py의 상위 디렉토리 = 저장소 루트.
# 어느 머신에 클론해도 환경변수 없이 동작한다.
_DEFAULT_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.environ.get("DASHBOARD_REPO_ROOT", _DEFAULT_REPO_ROOT)
TOKEN = os.environ.get("DASHBOARD_TOKEN")
PORT = int(os.environ.get("DASHBOARD_PORT", "8787"))
if not TOKEN:
    sys.exit("[dashboard] DASHBOARD_TOKEN 환경변수가 필요합니다.")

SLUG_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DRAFT_ID_RE = re.compile(r"^\d{8}-[a-z_]+-\d+$")  # SPEC 20.10 초안 저장 규약

# SPEC 8.1 정적 스케줄 (KST). 화면의 "다음 예정 트리거" 출처.
TRIGGERS = [
    ("main", "daily", (6, 30)),
    ("naver_publish", "daily", (9, 0)),
    ("weekly_calendar", "sunday", (20, 0)),
]

# SPEC 20.10 4차 — 설정 화이트리스트 (정본)
CHANNEL_KEYS = ["naver_blog", "threads", "instagram", "youtube", "meta_ads"]
# 2단계 확인(confirmed:true)이 필수인 정책 변경 키
POLICY_CONFIRM_KEYS = {"channels.meta_ads.mode", "customer_care.mode",
                       "repurchase.d7_channel", "publishing.require_approval"}
# POST /api/secrets가 저장할 수 있는 키 (연동 위자드 표의 6종)
SECRET_WRITE_KEYS = ["TELEGRAM_BOT_TOKEN", "META_OAUTH_ACCESS_TOKEN",
                     "THREADS_ACCESS_TOKEN", "INSTAGRAM_ACCESS_TOKEN",
                     "YOUTUBE_API_KEY", "HIGGSFIELD_API_KEY"]
PUBLISH_WINDOW_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def validate_setting(key, value):
    """SPEC 20.10 4차 화이트리스트·타입·범위 검증. (ok, 오류메시지) 반환."""
    parts = key.split(".") if isinstance(key, str) else []
    if len(parts) == 3 and parts[0] == "channels" and parts[1] in CHANNEL_KEYS:
        if parts[2] == "enabled":
            return isinstance(value, bool), "bool이어야 합니다."
        if parts[2] == "max_per_day":
            return _is_int(value) and 0 <= value <= 50, \
                "0~50 정수여야 합니다."
        return False, "허용되지 않은 키입니다."
    if key == "channels.naver_blog.publish_window":
        return isinstance(value, str) and bool(
            PUBLISH_WINDOW_RE.match(value)), "HH:MM-HH:MM 형식이어야 합니다."
    if key == "channels.meta_ads.mode":
        return value in ("draft_only", "approval", "auto"), \
            "draft_only|approval|auto 중 하나여야 합니다."
    if key in ("budgets.meta_daily_cap_krw", "budgets.higgsfield_monthly_krw"):
        return _is_int(value) and value >= 0, "0 이상 정수여야 합니다."
    if key == "customer_care.mode":
        return value in ("draft_only", "auto_send"), \
            "draft_only|auto_send 중 하나여야 합니다."
    if key == "repurchase.d7_channel":
        return value is None or value in ("sms", "alimtalk", "dm"), \
            "null|sms|alimtalk|dm 중 하나여야 합니다."
    if key == "publishing.require_approval":
        return isinstance(value, bool), "bool이어야 합니다."
    if key == "quality_gate.max_rework":
        return _is_int(value) and 0 <= value <= 5, "0~5 정수여야 합니다."
    if key == "retry.max_attempts":
        return _is_int(value) and 1 <= value <= 5, "1~5 정수여야 합니다."
    if key == "retry.backoff_minutes":
        ok = (isinstance(value, list) and 1 <= len(value) <= 5
              and all(_is_int(x) and 1 <= x <= 120 for x in value))
        return ok, "1~120 정수 배열(길이 1~5)이어야 합니다."
    if key in ("retention.logs_days", "retention.assets_days"):
        return _is_int(value) and 7 <= value <= 365, "7~365 정수여야 합니다."
    if key == "notifications.telegram_chat_id":
        return isinstance(value, str) and len(value) <= 64, \
            "문자열(최대 64자)이어야 합니다."
    return False, "허용되지 않은 키입니다."


def _load_config_rt(path):
    """config.yaml을 주석 보존 round-trip 모드로 읽는다. (yaml, data) 반환."""
    try:
        from ruamel.yaml import YAML
    except ImportError:
        raise RuntimeError(
            "ruamel.yaml이 필요합니다: pip install ruamel.yaml")
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    with open(path, encoding="utf-8") as f:
        return yaml, yaml.load(f)


def now_kst():
    return datetime.now(KST)


def today_str():
    return now_kst().strftime("%Y-%m-%d")


def biz_dir(slug):
    return os.path.join(REPO_ROOT, "businesses", slug)


def read_jsonl(path):
    """JSONL을 읽어 dict 리스트로. 깨진 줄은 건너뛴다."""
    out = []
    if not os.path.isfile(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def read_json(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def list_businesses():
    """config.yaml이 있는 slug 목록. example 계열은 데모 표시."""
    base = os.path.join(REPO_ROOT, "businesses")
    out = []
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if not SLUG_RE.match(name):
            continue
        if os.path.isfile(os.path.join(base, name, "config.yaml")):
            out.append({"slug": name, "demo": name.startswith("example")})
    return out


def next_trigger():
    """SPEC 8.1 기준 다음 트리거."""
    now = now_kst()
    best = None
    for name, kind, (hh, mm) in TRIGGERS:
        if kind == "daily":
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
            if cand <= now:
                cand = cand + timedelta(days=1)
        else:  # sunday
            days_ahead = (6 - now.weekday()) % 7
            cand = now.replace(hour=hh, minute=mm, second=0, microsecond=0) \
                + timedelta(days=days_ahead)
            if cand <= now:
                cand = cand + timedelta(days=7)
        if best is None or cand < best[1]:
            best = (name, cand)
    return {"name": best[0], "at": best[1].isoformat()}


def routine_status(slug):
    """20.3 화면 1 판정 규칙."""
    state = os.path.join(biz_dir(slug), "state")
    lock = read_json(os.path.join(state, "scheduler.lock"))
    if lock:
        return "running"
    last = read_json(os.path.join(state, "last_run.json"))
    if last and last.get("date") == today_str():
        return "completed" if last.get("status") == "completed" else "failed"
    return "waiting"


# SPEC 20.10: 7개 연동 항목 (7.6 체크리스트 매핑)
INTEGRATIONS = [
    {"key": "meta_ads", "name": "Meta 광고",
     "cfg": ("channel", "meta_ads"),
     "guide": "Meta 개발자 앱 생성 → 광고 계정 OAuth 연결 → 토큰을 secrets.env에 등록 (SPEC 7.6)"},
    {"key": "threads", "name": "Threads API",
     "cfg": ("channel", "threads"),
     "guide": "Threads API 앱 생성 → 권한 승인 → 토큰을 secrets.env에 등록 (SPEC 7.6)"},
    {"key": "instagram", "name": "Instagram",
     "cfg": ("channel", "instagram"),
     "guide": "Instagram 프로페셔널 계정 전환 → Facebook 페이지 연결 → 토큰을 secrets.env에 등록 (SPEC 7.6)"},
    {"key": "youtube", "name": "YouTube Data API",
     "cfg": ("channel", "youtube"),
     "guide": "Google Cloud 프로젝트 생성 → YouTube Data API 활성화 → 감사 통과 → 토큰을 secrets.env에 등록 (SPEC 7.6)"},
    {"key": "higgsfield", "name": "Higgsfield",
     "cfg": ("budget", "higgsfield_monthly_krw"),
     "guide": "Higgsfield 계정 생성 → 크레딧 충전 → config.yaml budgets.higgsfield_monthly_krw 확인 (SPEC 7.6)"},
    {"key": "telegram", "name": "Telegram",
     "cfg": ("chat_id", "telegram_chat_id"),
     "guide": "BotFather로 봇 생성 → 토큰을 secrets.env에 등록 → chat_id를 config.yaml notifications.telegram_chat_id에 입력 (SPEC 7.6)"},
    {"key": "naver_blog", "name": "네이버 블로그 (Aside 세션)",
     "cfg": ("channel", "naver_blog"),
     "guide": "HW가 브라우저에서 네이버 로그인 1회 수행 (takeover) → Aside 세션 연결 (SPEC 7.6)"},
]


def _strip_yaml_comment(line):
    """따옴표 밖의 # 주석을 제거한다."""
    in_s = in_d = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            return line[:i]
    return line


def parse_integration_config(slug):
    """config.yaml에서 연동 판정에 필요한 값만 추출 (stdlib 인덴트 기반 파서).
    channels의 인라인 `{ enabled: true }` 스타일과 block 스타일 둘 다 읽는다.
    파싱 실패 시 None을 반환하면 호출자가 '미확인'으로 표기한다.
    secrets.env는 절대 읽지 않는다."""
    path = os.path.join(biz_dir(slug), "config.yaml")
    out = {"channels": {}, "higgsfield_budget": None, "telegram_chat_id": ""}
    if not os.path.isfile(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    top = None        # 현재 최상위 키 (channels / budgets / notifications)
    channel = None    # channels 안에서 현재 채널명
    try:
        for raw in lines:
            line = _strip_yaml_comment(raw).rstrip("\n")
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip(" "))
            body = line.strip()
            if "\t" in line[:indent]:
                continue  # YAML은 탭 금지. 이상한 줄은 건너뛴다
            if indent == 0:
                m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", body)
                if m:
                    top = m.group(1) if not m.group(2) else None
                    channel = None
                else:
                    top = None
                continue
            if top == "channels" and indent == 2:
                m = re.match(r"^([\w-]+):\s*(\{[^}]*\})?\s*$", body)
                if m:
                    channel = m.group(1)
                    if m.group(2):  # 인라인 스타일
                        en = re.search(r"enabled\s*:\s*(true|false)", m.group(2))
                        out["channels"][channel] = (en.group(1) == "true") if en else False
                        channel = None
                else:
                    channel = None
            elif top == "channels" and channel and indent == 4:
                m = re.match(r"^enabled\s*:\s*(true|false)\s*$", body)
                if m:
                    out["channels"][channel] = m.group(1) == "true"
            elif top == "budgets" and indent == 2:
                m = re.match(r"^higgsfield_monthly_krw\s*:\s*(\S+)\s*$", body)
                if m:
                    out["higgsfield_budget"] = m.group(1)
            elif top == "notifications" and indent == 2:
                m = re.match(r'^telegram_chat_id\s*:\s*"(.*)"\s*$', body)
                if m:
                    out["telegram_chat_id"] = m.group(1)
    except Exception:
        return None
    return out



def integration_status(slug):
    """SPEC 20.10 상태 판정 규칙 (위에서 아래로 처음 맞는 것):
    1. 설정 근거 off·비어 있음 → 비활성 / 2. health.json 없음 → 미확인 /
    3. ok=true → 정상 / 4. ok=false → 이상 / 5. ok=null → 미연결"""
    cfg = parse_integration_config(slug)
    cfg_broken = cfg is None  # config.yaml 파싱 실패 → 전부 '미확인'
    if cfg_broken:
        cfg = {"channels": {}, "higgsfield_budget": None, "telegram_chat_id": ""}
    health = read_json(os.path.join(biz_dir(slug), "state", "health.json"))
    health_at = health.get("at") if isinstance(health, dict) else None
    channels = (health.get("channels") or {}) if isinstance(health, dict) else {}
    out = []
    for item in INTEGRATIONS:
        key = item["key"]
        kind, ref = item["cfg"]
        if kind == "channel":
            configured = bool(cfg["channels"].get(ref, False))
        elif kind == "budget":
            configured = bool(cfg["higgsfield_budget"])
        else:  # chat_id
            configured = bool(cfg["telegram_chat_id"])
        if cfg_broken:
            status, detail = "미확인", "config.yaml 파싱 실패"
        elif not configured:
            status, detail = "비활성", "설정에서 비활성화됨"
        elif health is None:
            status, detail = "미확인", "헬스체크 미실행 (06:30 루틴 시작 시 기록)"
        else:
            ch = channels.get(key, {})
            ok = ch.get("ok")
            if ok is True:
                status, detail = "정상", ch.get("detail") or ""
            elif ok is False:
                status, detail = "이상", ch.get("detail") or ""
            else:
                status, detail = "미연결", ch.get("detail") or "연동 정보 없음"
        out.append({"key": key, "name": item["name"], "status": status,
                    "checked_at": health_at, "detail": detail,
                    "guide": item["guide"]})
    return {"integrations": out, "health_at": health_at}


def scan_drafts(slug):
    """SPEC 20.10 초안 저장 규약대로 drafts/를 스캔.
    규약 초안: meta.json 파싱. 구 초안(meta.json 없음): "미확인" 항목."""
    base = os.path.join(biz_dir(slug), "drafts")
    out = []
    if not os.path.isdir(base):
        return out
    for date in sorted(os.listdir(base), reverse=True):
        if not DATE_RE.match(date):
            continue
        ddir = os.path.join(base, date)
        if not os.path.isdir(ddir):
            continue
        for dirname in sorted(os.listdir(ddir)):
            dpath = os.path.join(ddir, dirname)
            if not os.path.isdir(dpath):
                continue
            meta = read_json(os.path.join(dpath, "meta.json"))
            if DRAFT_ID_RE.match(dirname) and isinstance(meta, dict):
                out.append({
                    "id": dirname,
                    "channel": meta.get("channel") or "미확인",
                    "title": meta.get("title") or "미확인",
                    "status": meta.get("status") or "미확인",
                    "created_at": meta.get("created_at") or "미확인",
                    "date": date, "_dir": dpath, "_meta": meta})
            else:
                out.append({
                    "id": f"{date}/{dirname}", "channel": "미확인",
                    "title": dirname, "status": "미확인",
                    "created_at": "미확인", "date": date,
                    "_dir": dpath, "_meta": None})
    return out


def read_draft_content(dpath):
    """content.md 우선, 없으면 첫 번째 .md 파일."""
    cand = os.path.join(dpath, "content.md")
    if os.path.isfile(cand):
        with open(cand, encoding="utf-8") as f:
            return f.read()
    try:
        for name in sorted(os.listdir(dpath)):
            if name.endswith(".md"):
                with open(os.path.join(dpath, name),
                          encoding="utf-8") as f:
                    return f.read()
    except OSError:
        pass
    return ""


class Handler(BaseHTTPRequestHandler):
    server_version = "MarketingDashboard/1.0"

    # ---------- 공통 ----------
    def log_message(self, *args):
        pass  # 감사 로그로 충분. stdout 스팸 방지

    def _send(self, code, obj, ctype="application/json; charset=utf-8"):
        body = obj if isinstance(obj, bytes) else obj.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def _err(self, code, err_code, message, http=400):
        self._json({"error": {"code": err_code, "message": message}}, code=http)

    def _auth(self):
        return self.headers.get("Authorization") == f"Bearer {TOKEN}"

    def _slug(self, qs):
        slug = qs.get("business", ["main"])[0]
        if not SLUG_RE.match(slug):
            return None
        return slug

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except ValueError:
            n = 0
        raw = self.rfile.read(n) if n > 0 else b""
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    def _audit(self, slug, action, params, result):
        logdir = os.path.join(biz_dir(slug), "logs", today_str())
        os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, "dashboard_audit.jsonl"),
                  "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": now_kst().isoformat(), "actor": "dashboard",
                "business": slug, "action": action,
                "params": params, "result": result,
            }, ensure_ascii=False) + "\n")

    def _notify(self, slug, ntype, detail):
        path = os.path.join(biz_dir(slug), "state", "notification_queue.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "at": now_kst().isoformat(), "business": slug,
                "type": ntype, "detail": detail,
            }, ensure_ascii=False) + "\n")

    def _kill_info(self, slug):
        path = os.path.join(biz_dir(slug), "state", "KILL")
        if not os.path.isfile(path):
            return {"active": False}
        info = {"active": True, "reason": None, "at": None}
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("사유:"):
                        info["reason"] = line[3:].strip()
                    elif line.startswith("시각:"):
                        info["at"] = line[3:].strip()
        except OSError:
            pass
        return info

    # ---------- 라우팅 ----------
    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if parsed.path == "/" or parsed.path == "/index.html":
            return self._static("index.html", "text/html; charset=utf-8")
        if not self._auth():
            return self._err(401, "DASHBOARD_UNAUTHORIZED",
                             "토큰이 없거나 일치하지 않습니다.", http=401)
        slug = self._slug(qs)
        if slug is None:
            return self._err(400, "DASHBOARD_BAD_SLUG",
                             "사업 slug 형식이 잘못되었습니다.")
        routes = {
            "/api/businesses": self._api_businesses,
            "/api/status": self._api_status,
            "/api/queue": self._api_queue,
            "/api/dlq": self._api_dlq,
            "/api/publish-log": self._api_publish_log,
            "/api/reports": self._api_reports,
            "/api/config": self._api_config,
            "/api/integrations": self._api_integrations,
            "/api/health": self._api_health,
            "/api/drafts": self._api_drafts,
            "/api/ads/drafts": self._api_ad_drafts,
            "/api/settings": self._api_settings_get,
        }
        if parsed.path in routes:
            return routes[parsed.path](slug, qs)
        if parsed.path.startswith("/api/reports/"):
            date = parsed.path[len("/api/reports/"):]
            return self._api_report(slug, date)
        if parsed.path.startswith("/api/drafts/"):
            draft_id = unquote(parsed.path[len("/api/drafts/"):])
            return self._api_draft(slug, draft_id)
        return self._err(404, "DASHBOARD_NOT_FOUND", "없는 경로입니다.", http=404)

    def do_POST(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        if not self._auth():
            return self._err(401, "DASHBOARD_UNAUTHORIZED",
                             "토큰이 없거나 일치하지 않습니다.", http=401)
        slug = self._slug(qs)
        if slug is None:
            return self._err(400, "DASHBOARD_BAD_SLUG",
                             "사업 slug 형식이 잘못되었습니다.")
        body = self._body()
        if body is None:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "JSON 본문을 해석할 수 없습니다.")
        routes = {
            "/api/kill": self._api_kill,
            "/api/resume": self._api_resume,
            "/api/dlq/resolve": self._api_dlq_resolve,
            "/api/queue/approval": self._api_queue_approval,
            "/api/ads/approval": self._api_ad_approval,
            "/api/integrations/request": self._api_integrations_request,
            "/api/settings": self._api_settings_post,
            "/api/secrets": self._api_secrets,
        }
        if parsed.path in routes:
            return routes[parsed.path](slug, body)
        return self._err(404, "DASHBOARD_NOT_FOUND", "없는 경로입니다.", http=404)

    def _static(self, name, ctype):
        path = os.path.join(STATIC_DIR, name)
        if not os.path.isfile(path):
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return
        with open(path, "rb") as f:
            self._send(200, f.read(), ctype)

    # ---------- 읽기 API ----------
    def _api_businesses(self, slug, qs):
        self._json({"businesses": list_businesses()})

    def _api_status(self, slug, qs):
        state = os.path.join(biz_dir(slug), "state")
        queue = read_jsonl(os.path.join(state, "queue.jsonl"))
        today = today_str()
        counts = {"queued": 0, "publishing": 0, "published": 0, "failed": 0}
        for r in queue:
            if r.get("date") == today and r.get("status") in counts:
                counts[r["status"]] += 1
        dlq = read_jsonl(os.path.join(state, "dead_letter.jsonl"))
        report_path = os.path.join(biz_dir(slug), "reports", "daily",
                                   f"{today}.md")
        report = {"exists": os.path.isfile(report_path), "at": None}
        if report["exists"]:
            report["at"] = datetime.fromtimestamp(
                os.path.getmtime(report_path), KST).isoformat()
        self._json({
            "business": slug,
            "kill": self._kill_info(slug),
            "lock": read_json(os.path.join(state, "scheduler.lock")),
            "last_run": read_json(os.path.join(state, "last_run.json")),
            "routine": routine_status(slug),
            "next_trigger": next_trigger(),
            "today": counts,
            "today_date": today,
            "dlq_count": len(dlq),
            "report": report,
        })

    def _api_queue(self, slug, qs):
        recs = read_jsonl(os.path.join(biz_dir(slug), "state", "queue.jsonl"))
        status = qs.get("status", [None])[0]
        channel = qs.get("channel", [None])[0]
        try:
            limit = int(qs.get("limit", ["100"])[0])
        except ValueError:
            limit = 100
        out = [r for r in recs
               if (status is None or r.get("status") == status)
               and (channel is None or r.get("channel") == channel)]
        self._json({"records": out[:max(limit, 0)], "total": len(out)})

    def _api_dlq(self, slug, qs):
        recs = read_jsonl(os.path.join(biz_dir(slug), "state",
                                       "dead_letter.jsonl"))
        self._json({"records": recs, "total": len(recs)})

    def _api_publish_log(self, slug, qs):
        recs = read_jsonl(os.path.join(biz_dir(slug), "state",
                                       "publish_log.jsonl"))
        try:
            limit = int(qs.get("limit", ["100"])[0])
        except ValueError:
            limit = 100
        recs = recs[::-1]
        self._json({"records": recs[:max(limit, 0)], "total": len(recs)})

    def _api_reports(self, slug, qs):
        d = os.path.join(biz_dir(slug), "reports", "daily")
        out = []
        if os.path.isdir(d):
            for name in sorted(os.listdir(d), reverse=True):
                if name.endswith(".md"):
                    out.append({"date": name[:-3],
                                "path": f"reports/daily/{name}"})
        self._json({"reports": out})

    def _api_report(self, slug, date):
        if not DATE_RE.match(date):
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "날짜 형식이 잘못되었습니다 (YYYY-MM-DD).")
        path = os.path.join(biz_dir(slug), "reports", "daily", f"{date}.md")
        if not os.path.isfile(path):
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "리포트가 없습니다.", http=404)
        with open(path, encoding="utf-8") as f:
            self._json({"date": date, "markdown": f.read()})

    def _api_config(self, slug, qs):
        # secrets.env는 절대 읽지 않는다.
        # 응답은 예산 캡 위주 구조화 데이터 (SPEC 20.4). 사용량 집계 규격은 없어 usageKnown=false.
        path = os.path.join(biz_dir(slug), "config.yaml")
        if not os.path.isfile(path):
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "설정 파일이 없습니다.", http=404)
        budgets = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                m = re.match(r"^\s{2}(\w+):\s*(\d+)\s*(#.*)?$", line)
                if m and m.group(1).endswith("_krw"):
                    budgets.append({"key": m.group(1),
                                    "capKrw": int(m.group(2))})
        self._json({"business": slug, "budgets": budgets,
                    "usageKnown": False})

    # ---------- 2차 API (SPEC 20.10) ----------
    def _api_integrations(self, slug, qs):
        self._json(integration_status(slug))
    def _api_health(self, slug, qs):
        health = read_json(os.path.join(biz_dir(slug), "state",
                                        "health.json"))
        if health is None:
            self._json({"exists": False})
        else:
            self._json(health)

    def _api_integrations_request(self, slug, body):
        channel = body.get("channel", "")
        valid = [i["key"] for i in INTEGRATIONS]
        if not isinstance(channel, str) or channel not in valid:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "channel은 7개 연동 키 중 하나여야 합니다.")
        # KILL 발동 중에도 허용 (20.5 예외 — 알림 적재만, 실행 없음)
        self._audit(slug, "integration_request", {"channel": channel},
                    {"ok": True})
        self._notify(slug, "integration_request", {"channel": channel})
        self._json({"ok": True, "business": slug, "channel": channel})

    # ---------- 3차 API (SPEC 20.10) ----------
    def _api_drafts(self, slug, qs):
        drafts = scan_drafts(slug)
        channel = qs.get("channel", [None])[0]
        status = qs.get("status", [None])[0]
        date = qs.get("date", [None])[0]
        if date is not None and not DATE_RE.match(date):
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "날짜 형식이 잘못되었습니다 (YYYY-MM-DD).")
        try:
            limit = int(qs.get("limit", ["100"])[0])
        except ValueError:
            limit = 100
        out = [d for d in drafts
               if (channel is None or d["channel"] == channel)
               and (status is None or d["status"] == status)
               and (date is None or d["date"] == date)]
        # created_at 내림차순 ("미확인"은 마지막)
        out.sort(key=lambda d: d["created_at"]
                 if d["created_at"] != "미확인" else "", reverse=True)
        rows = [{k: d[k] for k in
                 ("id", "channel", "title", "status", "created_at", "date")}
                for d in out[:max(limit, 0)]]
        self._json({"drafts": rows, "total": len(out)})

    def _api_draft(self, slug, draft_id):
        # 경로 탈출 방지
        if not draft_id or ".." in draft_id or draft_id.startswith("/"):
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "초안 id 형식이 잘못되었습니다.")
        base = os.path.join(biz_dir(slug), "drafts")
        target = None
        meta = None
        if DRAFT_ID_RE.match(draft_id):
            for d in scan_drafts(slug):
                if d["id"] == draft_id:
                    target, meta = d["_dir"], d["_meta"]
                    break
        else:
            m = re.match(r"^(\d{4}-\d{2}-\d{2})/([^/]+)$", draft_id)
            if not m:
                return self._err(400, "DASHBOARD_BAD_REQUEST",
                                 "초안 id 형식이 잘못되었습니다.")
            cand = os.path.normpath(os.path.join(base, m.group(1),
                                                m.group(2)))
            if not cand.startswith(os.path.normpath(base) + os.sep):
                return self._err(400, "DASHBOARD_BAD_REQUEST",
                                 "초안 id 형식이 잘못되었습니다.")
            if os.path.isdir(cand):
                target = cand
        if target is None:
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "초안을 찾을 수 없습니다.", http=404)
        self._json({"id": draft_id, "meta": meta,
                    "content_markdown": read_draft_content(target)})

    # ---------- 4차 API (SPEC 20.10) ----------
    def _api_settings_get(self, slug, qs):
        # secrets.env는 절대 읽지 않는다.
        path = os.path.join(biz_dir(slug), "config.yaml")
        if not os.path.isfile(path):
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "설정 파일이 없습니다.", http=404)
        _, cfg = _load_config_rt(path)
        cfg = cfg or {}
        out = {}
        channels = {}
        for ch in CHANNEL_KEYS:
            node = (cfg.get("channels") or {}).get(ch) or {}
            item = {}
            for k in ("enabled", "max_per_day"):
                if k in node:
                    item[k] = node[k]
            if ch == "naver_blog" and "publish_window" in node:
                item["publish_window"] = node["publish_window"]
            if ch == "meta_ads" and "mode" in node:
                item["mode"] = node["mode"]
            if item:
                channels[ch] = item
        if channels:
            out["channels"] = channels
        for section, keys in [
            ("budgets", ["meta_daily_cap_krw", "higgsfield_monthly_krw"]),
            ("customer_care", ["mode"]),
            ("repurchase", ["d7_channel"]),
            ("publishing", ["require_approval"]),
            ("quality_gate", ["max_rework"]),
            ("retry", ["max_attempts", "backoff_minutes"]),
            ("retention", ["logs_days", "assets_days"]),
            ("notifications", ["telegram_chat_id"]),
        ]:
            node = cfg.get(section) or {}
            item = {k: node[k] for k in keys if k in node}
            if item:
                out[section] = item
        self._json(out)

    def _api_settings_post(self, slug, body):
        # KILL 발동 중에도 허용 (20.5 예외 — 실행이 아니라 설정).
        updates = body.get("updates")
        confirmed = body.get("confirmed") is True
        if not isinstance(updates, list) or not updates:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "updates는 비어 있지 않은 배열이어야 합니다.")
        # 1) 전체 검증 (all-or-nothing)
        norm = []
        for u in updates:
            if not isinstance(u, dict):
                return self._err(400, "DASHBOARD_BAD_REQUEST",
                                 "updates 항목은 {key, value} 객체여야 합니다.")
            key, value = u.get("key"), u.get("value")
            ok, msg = validate_setting(key, value)
            if not ok:
                return self._err(400, "DASHBOARD_BAD_REQUEST",
                                 f"키 '{key}': {msg}")
            norm.append((key, value))
        # 2) 정책 변경 키는 2단계 확인 필수 (서버 강제)
        if any(k in POLICY_CONFIRM_KEYS for k, _ in norm) and not confirmed:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "정책 변경 키는 2단계 확인(confirmed:true)이 "
                             "필요합니다.")
        path = os.path.join(biz_dir(slug), "config.yaml")
        if not os.path.isfile(path):
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "설정 파일이 없습니다.", http=404)
        # 3) 백업 후 적용 (YAML round-trip — 주석·미편집 키 유지)
        import shutil
        shutil.copy2(path, path + ".bak")
        yaml, cfg = _load_config_rt(path)
        cfg = cfg or {}
        for key, value in norm:
            parts = key.split(".")
            node = cfg
            for p in parts[:-1]:
                if not isinstance(node.get(p), dict):
                    node[p] = {}
                node = node[p]
            node[parts[-1]] = value
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f)
        keys = [k for k, _ in norm]
        self._audit(slug, "settings_update", {"keys": keys}, {"ok": True})
        self._notify(slug, "config_changed", {"keys": keys})
        self._json({"ok": True, "business": slug, "updated": keys})

    def _api_secrets(self, slug, body):
        # KILL 발동 중에도 허용 (20.5 예외 — 실행이 아니라 설정).
        # 값은 저장만 하고, 어떤 API로도 읽을 수 없다 (write-only).
        key = body.get("key", "")
        value = body.get("value", "")
        if not isinstance(key, str) or key not in SECRET_WRITE_KEYS:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "key는 허용된 시크릿 키 중 하나여야 합니다.")
        if not isinstance(value, str) or not value or len(value) > 512:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "value는 비어 있지 않은 문자열(최대 512자)이어야 "
                             "합니다.")
        import shutil
        path = os.path.join(biz_dir(slug), "secrets.env")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.isfile(path):
            shutil.copy2(path, path + ".bak")
            with open(path, encoding="utf-8") as f:
                lines = f.readlines()
        else:
            lines = []
        pat = re.compile(rf"^{re.escape(key)}=.*$")
        replaced = False
        out = []
        for line in lines:
            if pat.match(line.rstrip("\n")):
                if not replaced:
                    out.append(f"{key}={value}\n")
                    replaced = True
                # 중복 라인은 제거
            else:
                out.append(line)
        if not replaced:
            if out and not out[-1].endswith("\n"):
                out[-1] += "\n"
            out.append(f"{key}={value}\n")
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(out)
        # 값은 절대 기록하지 않는다 (key만)
        self._audit(slug, "secret_save", {"key": key}, {"ok": True})
        self._json({"ok": True, "business": slug, "key": key})

    # ---------- 쓰기 API (20.5 매핑) ----------
    def _api_kill(self, slug, body):
        reason = body.get("reason", "")
        if not isinstance(reason, str) or not reason.strip():
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "사유(reason)는 필수입니다.")
        reason = " ".join(reason.split())  # 개행 제거 (한 줄 제한)
        kill_path = os.path.join(biz_dir(slug), "state", "KILL")
        if os.path.isfile(kill_path):
            return self._err(409, "DASHBOARD_KILL_ACTIVE",
                             "킬스위치가 이미 발동되어 있습니다.", http=409)
        os.makedirs(os.path.dirname(kill_path), exist_ok=True)
        # bin/kill.sh의 `date '+%Y-%m-%d %H:%M:%S %Z'` (TZ=Asia/Seoul → KST)와 동일 포맷.
        # Python의 고정 오프셋 timezone은 %Z가 "UTC+09:00"이 되므로 KST를 직접 붙인다.
        at = now_kst().strftime("%Y-%m-%d %H:%M:%S") + " KST"
        with open(kill_path, "w", encoding="utf-8") as f:
            f.write(f"사업: {slug}\n사유: {reason}\n시각: {at}\n")
        self._audit(slug, "kill", {"reason": reason}, {"ok": True})
        self._notify(slug, "kill", reason)
        self._json({"ok": True, "business": slug, "reason": reason, "at": at})

    def _api_resume(self, slug, body):
        if self._kill_info(slug)["active"]:
            kill_path = os.path.join(biz_dir(slug), "state", "KILL")
            os.remove(kill_path)
            self._audit(slug, "resume", {}, {"ok": True})
            self._notify(slug, "resume", "킬스위치 해제")
            self._json({"ok": True, "business": slug})
        else:
            return self._err(409, "DASHBOARD_KILL_NOT_ACTIVE",
                             "킬스위치가 발동되어 있지 않습니다.", http=409)

    def _api_queue_approval(self, slug, body):
        # 발행 승인/취소 (SPEC 20.4). KILL 발동 중에도 허용 — 실행이 아니라 승인 기록이므로.
        target = body.get("id", "")
        approved = body.get("approved")
        if not isinstance(target, str) or not target:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "id는 필수입니다.")
        if not isinstance(approved, bool):
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "approved는 bool이어야 합니다.")
        queue_path = os.path.join(biz_dir(slug), "state", "queue.jsonl")
        recs = read_jsonl(queue_path)
        found = None
        for r in recs:
            if r.get("id") == target:
                found = r
                break
        if found is None:
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "큐에서 해당 id를 찾을 수 없습니다.", http=404)
        approved_at = now_kst().isoformat() if approved else None
        found["approved_at"] = approved_at
        with open(queue_path, "w", encoding="utf-8") as f:
            for obj in recs:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._audit(slug, "queue_approval",
                    {"id": target, "approved": approved},
                    {"ok": True, "approved_at": approved_at})
        self._json({"ok": True, "id": target, "approved_at": approved_at})

    def _api_ad_drafts(self, slug, qs):
        # 광고 초안 목록 (SPEC 20.12). status 필터 지원.
        drafts_path = os.path.join(biz_dir(slug), "state", "ad_drafts.jsonl")
        recs = read_jsonl(drafts_path)
        status = qs.get("status", [None])[0]
        if status:
            recs = [r for r in recs if r.get("status") == status]
        self._json({"ok": True, "records": recs})

    def _api_ad_approval(self, slug, body):
        # 광고 승인/반려 (SPEC 20.12). KILL 발동 중에도 허용 — 실행이 아니라 승인 기록이므로.
        target = body.get("id", "")
        approved = body.get("approved")
        if not isinstance(target, str) or not target:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "id는 필수입니다.")
        if not isinstance(approved, bool):
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "approved는 bool이어야 합니다.")
        drafts_path = os.path.join(biz_dir(slug), "state", "ad_drafts.jsonl")
        recs = read_jsonl(drafts_path)
        found = None
        for r in recs:
            if r.get("id") == target:
                found = r
                break
        if found is None:
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "광고 초안에서 해당 id를 찾을 수 없습니다.", http=404)
        if found.get("status") not in ("draft", "approved"):
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "이미 처리된 초안입니다 (status=%s)." % found.get("status"))
        approved_at = now_kst().isoformat() if approved else None
        found["approved_at"] = approved_at
        found["status"] = "approved" if approved else "rejected"
        with open(drafts_path, "w", encoding="utf-8") as f:
            for obj in recs:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._audit(slug, "ad_approval",
                    {"id": target, "approved": approved},
                    {"ok": True, "approved_at": approved_at})
        self._json({"ok": True, "id": target, "approved_at": approved_at})

    def _api_dlq_resolve(self, slug, body):
        if self._kill_info(slug)["active"]:
            return self._err(409, "DASHBOARD_KILL_ACTIVE",
                             "KILL 발동 중에는 복구할 수 없습니다.", http=409)
        target = body.get("id", "")
        if not isinstance(target, str) or not target:
            return self._err(400, "DASHBOARD_BAD_REQUEST",
                             "id는 필수입니다.")
        dlq_path = os.path.join(biz_dir(slug), "state", "dead_letter.jsonl")
        queue_path = os.path.join(biz_dir(slug), "state", "queue.jsonl")
        moved, kept = None, []
        for line in read_jsonl(dlq_path):
            if moved is None and line.get("id") == target:
                moved = line
            else:
                kept.append(line)
        if moved is None:
            return self._err(404, "DASHBOARD_NOT_FOUND",
                             "DLQ에서 해당 id를 찾을 수 없습니다.", http=404)
        moved["status"] = "queued"
        moved["resolved_at"] = now_kst().isoformat()
        with open(dlq_path, "w", encoding="utf-8") as f:
            for obj in kept:
                f.write(json.dumps(obj, ensure_ascii=False) + "\n")
        with open(queue_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(moved, ensure_ascii=False) + "\n")
        self._audit(slug, "dlq_resolve", {"id": target}, {"ok": True})
        self._notify(slug, "dlq_resolve", target)
        self._json({"ok": True, "queue_id": moved.get("id")})


def main():
    if not os.path.isdir(REPO_ROOT):
        sys.exit(f"[dashboard] 저장소를 찾을 수 없습니다: {REPO_ROOT}")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[dashboard] http://127.0.0.1:{PORT} (repo: {REPO_ROOT})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
