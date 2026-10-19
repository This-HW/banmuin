# ARCHITECTURE.md — 아키텍처

> 상세 계약(스키마·게이트·재시도 정책 등)의 정본은 `SPEC.md`이다.
> 이 문서는 context 없는 개발자가 모듈 구조·데이터 흐름·상태·설계 원칙을 파악하고
> 구현·수정할 수 있는 것을 목표로 한다.

## 1. 설계 사상

> 용어: **대표** = 이 시스템을 운영하는 사용자(1인 사업자 본인). **정본** = 어떤 정보의
> 최종 근거가 되는 원본 파일. **미러** = 정본을 복사해 둔 참조용 사본 (정본이 바뀌면 함께 갱신).

1. **문서가 곧 코드**: 실행 로직의 대부분은 셸 스크립트가 아니라 AI 에이전트가 읽는
   Markdown 지시서(`skills/`, `playbooks/`)에 있다. 그래서 특정 AI 제품에 종속되지 않고,
   에이전트만 교체하면 이식된다.
2. **코어/데이터 분리**: 공개 저장소(시스템)와 `businesses/<slug>/`(사업 데이터·시크릿)는
   엄격히 분리된다. 코어 업데이트는 `git pull` 한 번으로 각 사업에 반영된다.
3. **반무인**: 완전 자동이 아니라 "자동 실행 + 실패 시 알림 + 월 1~2회 손보기".
   사람이 개입하는 지점을 실패 알림 확인·월 1~2회 손보기로 압축한다.
   발행은 반무인 자동 발행(SPEC 11.3 #1), 지출은 명시적 opt-in(SPEC 11.3 #3)에서만 일어난다.
4. **지식 정본주의**: 모든 스킬은 `knowledge/`(사업의 정본 지식)만 근거로 삼는다.
   문서에 없는 내용은 지어내지 않는다.

## 2. 모듈 목록과 책임

### 2.1 `skills/` — 에이전트 역할 정의서 8종

Anthropic Agent Skills 표준 (`SKILL.md` + `references/`). 에이전트가 읽고 직접 실행한다.

| 스킬 | 책임 |
|---|---|
| `orchestrator` | 일일 루틴 조율. 트리거별(main / naver_publish / weekly_calendar / engagement) 단계 실행, 치명도 분류에 따른 중단·재시도·DLQ 격리, 락/KILL/멱등성 관리 |
| `customer-research` | 시장조사. 고객 질문·경쟁사 동향 수집, 광고 소구점 도출, 주 1회 AEO(브랜드 언급) 측정. 출처 없는 주장은 "가설"로 분류 |
| `content` | 콘텐츠 마케터. 블로그·Threads·카드뉴스·숏폼 4종 기획·제작, 1차(규칙)→2차(AI) 품질 게이트, 통과분 발행 큐 적재 |
| `ads` | Meta 광고. 성과 조회·분석 + 캠페인 초안 생성. 집행은 config `meta_ads.mode=auto` 명시적 opt-in에서만 (기본값 draft_only) |
| `customer-care` | 미답변 문의에 대한 FAQ 근거 답변 초안 작성. 발송은 config `customer_care.mode=auto_send` opt-in에서만 (기본값 draft_only) |
| `analytics` | 성과 분석. 기간 비교표·변동 탐지(±20%), 아침 리포트 본문 생성 |
| `pre-launch` | 런칭기 지원. 사업 단계별(아이디어/준비중/사전예약중) 파이프라인 — 시장조사·빌드인퍼블릭·대기리스트·베타테스터 모집 |
| `engagement` | 인스타그램 댓글→DM 자동화 (SPEC §21). 30분 간격 폴링: 새 댓글 수집 → 공개 답글 → 팔로우 체크 → DM 발송. 기본 비활성(opt-in) |

### 2.2 `playbooks/` — Aside 작업 지시서 3종

코드가 아닌 Markdown. `aside exec`에 전달해 브라우저 작업을 수행시킨다.
필수 항목: 사전조건 · 단계별 수행 내용 · 성공 기준(반환값) · 실패 시 보고 형식(어느 단계·무슨 에러·스크린샷).

| 플레이북 | 용도 |
|---|---|
| `naver-blog-publish.task.md` | 네이버 블로그 발행 (로그인 확인 → 스마트에디터 → 제목·본문·이미지 입력 → 발행 → URL 반환) |
| `naver-blog-unpublish.task.md` | 롤백 (글 삭제/비공개) |
| `cardnews-render.task.md` | 카드뉴스 HTML → PNG 렌더링 (브라우저 스크린샷) |

네이버는 공식 글쓰기 API가 없으므로 로그인 세션 기반 브라우저 자동화를 사용한다.
Playwright 코드는 작성·유지보수하지 않는다 (SPEC v1.2 결정).

### 2.3 `bin/` — 실행 껍데기 6종

상태관리(락·킬스위치·로그 뼈대·DLQ)만 담당. 마케팅 로직은 포함하지 않는다.
실제 채널 작업은 에이전트가 `SKILL.md`/플레이북을 읽고 수행한다.

| 스크립트 | 용도 |
|---|---|
| `run.sh` | 루틴 실행 래퍼. `--business/--date/--dry-run/--stage 수집\|분석\|제작\|검수\|발행\|보고` |
| `retry.sh` | 단계 재실행 (수동 복구, SPEC 13.4 런북) |
| `kill.sh` | `state/KILL` 생성 (비상정지) |
| `resume.sh` | KILL 해제 |
| `dlq.sh` | DLQ 조회(`list`)·복구(`resolve <id>`) |
| `engagement.sh` | 댓글→DM 트리거 래퍼 (30분 cron, `skills/engagement/SKILL.md` 실행) |

### 2.4 `templates/` / `businesses/`

| 디렉토리 | 역할 |
|---|---|
| `templates/` | 새 사업 시작용 빈 템플릿. `config.yaml`, `knowledge/` 11종, `content_calendar.md`, `secrets.env.example` |
| `businesses/<slug>/` | 사업별 private 데이터 (Git 제외). 지식·설정·상태·로그·리포트·초안·에셋 |

## 3. 일일 파이프라인 데이터 플로우

```
              ┌──────────────────────────────────────────────┐
              │ 스케줄러 (KST) — 에이전트를 깨움               │
              │  06:30 main / 09:00 naver_publish /           │
              │  일요일 20:00 weekly_calendar /               │
              │  */30 engagement (댓글→DM, SPEC §21)          │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ orchestrator (사용자의 AI 에이전트)           │
              │  락 획득 → KILL 확인 → 헬스체크  [치명 단계]   │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ 사업 단계 확인 (00_사업개요.md의 사업 단계)   │
              │  아이디어 → 시장조사만                        │
              │  준비중 → + 빌드인퍼블릭(주 3회) + 랜딩 카피   │
              │  사전예약중 → + 대기리스트·베타·얼리버드       │
              │  운영중 → 전체 파이프라인 (SPEC 1.7·8.4)      │
              └──────────────────────┬───────────────────────┘
                                     ▼
        ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
        │ 시장조사      │  │ 성과 수집     │  │ 미답변 문의 수집  │
        │ customer-    │  │ Meta MCP ·   │  │ customer-care    │
        │ research     │  │ 채널별 반응   │  │                  │
        └──────┬───────┘  └──────┬───────┘  └────────┬─────────┘
               └────────────────┼───────────────────┘
                                ▼
              ┌──────────────────────────────────────────────┐
              │ 콘텐츠기획 → analytics 리포트 1차 생성         │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ 생성: 블로그·스레드·카드뉴스·숏폼 4종 (content)│
              │ 산출물은 drafts/ 경유                         │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ 품질검수: 1차 규칙 → 2차 AI (content)         │
              │ 통과 → queue.jsonl / 실패 → drafts/ 보관      │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ 발행 (orchestrator)                           │
              │  - API 채널(Threads·IG·YouTube): 즉시 발행     │
              │  - 네이버: 큐 → 09:00~11:00 랜덤 발행 (별도    │
              │    트리거). queue.jsonl 상태 전이 기록         │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ 광고: 성과 조회·캠페인 초안 (ads)             │
              │ 응대: FAQ 근거 답변 초안 (customer-care)       │
              └──────────────────────┬───────────────────────┘
                                     ▼
              ┌──────────────────────────────────────────────┐
              │ 분석 → 아침 리포트 생성 → 텔레그램 발송        │
              │ → 락 해제 (orchestrator + analytics)          │
              └──────────────────────────────────────────────┘

실패 경로
  비치명 단계 실패(3회 재시도 후) → state/dead_letter.jsonl 격리 → 텔레그램 알림 → 다음 단계 진행
  치명 단계 실패(락/헬스체크/KILL) → 루틴 전체 중단 + 즉시 알림
```

타임라인(06:30 기동): 수집 06:40 → 분석 07:00 → 제작 07:20 → 검수 08:00 → API 채널 발행 08:30 → 리포트 09:00.
월요일 루틴에는 AEO 주간 측정 포함. 네이버 발행은 별도 09:00 트리거.

**engagement 트리거 (30분 간격, SPEC §21)** — 위 일일 파이프라인과 독립적으로 동작한다:

```
스케줄러 (*/30 * * * *, KST)
  → orchestrator: 락 획득 → KILL 확인 → 알림 큐 drain (헬스체크 없음)
  → engagement: enabled=false면 종료
  → 새 댓글 수집 (GET /{ig-user-id}/media → GET /{media-id}/comments)
  → 댓글마다: 멱등성 체크 → 키워드 필터 → 공개 답글 (POST /{comment-id}/replies)
             → 팔로우 체크 (is_user_follow_business)
             → DM 발송 (Private Replies, 댓글당 1회·7일 이내)
  → state/engagement.json 갱신 → 락 해제
  (last_run.json은 건드리지 않음 — 30분 간격 덮어쓰기가 대시보드 "오늘 루틴" 배너를
  깨뜨리므로. SPEC §21.4 [7])
```

웹훅 서버를 두지 않는 이유: 이 시스템은 cron+에이전트 구조라 상시 대기 서버가 없다.
폴링은 기존 트리거 구조에 그대로 편입되고, Private Replies의 7일 유효기간 안에
충분히 처리할 수 있다 (SPEC 21.4).

## 4. 런타임 계약

- **오케스트레이터는 사용자의 AI 에이전트이며, 특정 제품에 종속되지 않는다.**
  SPEC v1.3부터 실행 주체는 "사용자의 AI 에이전트"로 일반화되어 있다
  (v1.2까지는 Muse로 명시). 에이전트 최소 요구사항은
  `docs/agent-compatibility.md`에 정의한다.
- **사업 단계에 따라 파이프라인이 분기된다.**
  오케스트레이터는 루틴 시작 시 `businesses/<slug>/knowledge/00_사업개요.md`의
  `사업 단계` 필드를 읽고 해당 단계의 파이프라인만 실행한다
  (아이디어: 시장조사만 / 준비중: +빌드인퍼블릭·랜딩 카피 /
  사전예약중: +대기리스트·베타테스터·얼리버드 / 운영중: 전체).
  단계 변경은 대표의 명시적 승인 없이 하지 않는다. 상세는 SPEC 1.7·8.4.
- **역할 경계**

  | 영역 | 담당 |
  |---|---|
  | 오케스트레이션 (루틴 조율, 단계 실행) | 에이전트 (스케줄러에 의해 기동) |
  | 스킬·플레이북 정의 | 개발자 (Markdown 작성) |
  | 지식파일 내용 | 사용자(사업 대표) |
  | 브라우저 자동화 실행 | Aside (`aside exec` + 플레이북). 장애 시 에이전트의 브라우저 도구가 폴백 |
  | API 호출 | 에이전트 (MCP/커넥터 경유) |
  | 상태·로그·리포트 | 에이전트가 생성, 개발자가 구조 정의 |
  | 스케줄러 | 개발자 (cron 등록). 트리거되면 에이전트 작업으로 실행 |
| 대시보드 (fullstack 웹 아티팩트, 비공개) | 시스템 전체의 웹 인터페이스(컨트롤 플레인). 1차(현황·큐·리포트·제어)·2차(연동 상태)·3차(콘텐츠 초안 뷰어, 읽기 전용) 완료 (SPEC 20.10). 읽기 우선, 쓰기는 SPEC 20.5 매핑의 파일 연산만 |

- 즉 개발자는 **"에이전트가 읽고 실행할 수 있는 파일·스크립트·설정"**을 만든다.
  `bin/*.sh`에 마케팅 실행 로직을 넣지 않는다.

## 5. 상태 모델

모든 런타임 상태는 `businesses/<slug>/state/` 아래에 저장된다.

| 파일 | 용도 |
|---|---|
| `queue.jsonl` | 발행 큐. 상태 머신: `draft → queued → publishing → published` / `failed → (재시도) → publishing` / `failed → dead`. `publishing.require_approval=true`면 `approved_at`이 기록된 레코드만 발행 (현재 네이버 블로그에 적용) |
| `publish_log.jsonl` | 발행 이력. 불변 append-only |
| `dead_letter.jsonl` | DLQ. 3회 재시도 실패 건 격리소 |
| `d7_sent.jsonl` | D+7 재구매 발송 기록. 멱등용 (`order_id`, 발송 중복 방지) |
| `ad_drafts.jsonl` | 광고 초안. 건별 승인용 (`id·campaign_name·meta_campaign_id·daily_budget_krw·status·approved_at`). v1.10.6 |
| `waitlist.jsonl` | 대기리스트. 사전예약중 단계에서 사전예약자 적재 (SPEC 1.7) |
| `scheduler.lock` | 락 파일 (`{"started_at","host","run_id"}`). 24시간 이상이면 stale로 간주 |
| `engagement.lock` | engagement 트리거 전용 락. 2시간 이상이면 stale로 간주 (SPEC 21.4 [1]) |
| `KILL` | 존재하면 비상정지. 오케스트레이터는 매 단계 시작 전 확인 |
| `last_run.json` | 마지막 루틴 실행 결과 (`date·trigger·status·finished_at·failed_stage`). 오케스트레이터가 루틴 종료 시 기록. 대시보드 상태 배너의 판정 근거 (SPEC 20.3) |
| `notification_queue.jsonl` | 대시보드 제어 동작의 텔레그램 알림 요청 적재소. 전 트리거 기동 시 원자적 drain 후 발송 (SPEC 20.5) |
| `health.json` | 채널 세션/API 헬스체크 결과 (`at·trigger·channels{<채널>: {ok, detail}}`). 오케스트레이터가 매 루틴 시작 시 기록. 대시보드 2차 "연동 상태" 화면의 데이터 근거 (SPEC 20.10, v1.8) |
| `engagement.json` | 댓글→DM 자동화 상태 (`last_check_at·reply_template_index`). 30분 간격 engagement 트리거가 갱신 (SPEC §21) |
| `engagement_processed.jsonl` | 댓글당 처리 기록 (`comment_id·replied_at·follow_status·dm_sent·attempts·status`). 멱등성 근거 (SPEC §21) |

그 외 사업별 런타임 경로: `businesses/<slug>/drafts/YYYY-MM-DD/` (게이트 미통과·발행 보류 초안 보관소),
`businesses/<slug>/data/orders.csv` (D+7 재구매용 주문 데이터, 수동 입력),
`businesses/<slug>/logs/YYYY-MM-DD/` (단계별 JSONL, 90일 보관),
`businesses/<slug>/reports/daily|research/`, `businesses/<slug>/assets/YYYY-MM-DD/` (90일 후 압축 아카이브).

**멱등성**: 멱등키 = `content_id:channel:date`. 같은 키로 `published`가 있으면 발행 스킵.
의도적 재발행은 `--force`로만. 레코드 스키마는 SPEC 10.2 참조.

**사업 디렉토리 전체 구조**:

```
businesses/<slug>/
├── config.yaml            설정 (예산 캡·게이트 임계값은 knowledge/08_승인기준.md가 정본, 여기는 미러)
├── secrets.env            API 키·토큰 (Git 제외, Secure Vault 경유 주입)
├── knowledge/             사업 정본 지식 11종 (모든 스킬의 grounding 소스)
├── pipeline/
│   └── content_calendar.md 주간 콘텐츠 캘린더
├── state/                 queue.jsonl / publish_log.jsonl / dead_letter.jsonl / scheduler.lock / KILL
│                           / engagement.json / engagement_processed.jsonl / engagement.lock
├── drafts/YYYY-MM-DD/     게이트 미통과·발행 보류 초안
├── logs/YYYY-MM-DD/       단계별 실행 로그
├── reports/               daily/ · research/
└── assets/                생성 이미지·영상 (90일 후 archive/로 압축)
```

## 6. 멀티사업 설계

- 네임스페이스: `businesses/<slug>/`. slug는 소문자·하이픈 권장.
- **스킬은 공용**이다. 스킬은 사업 데이터를 갖지 않으며, 실행 시 `business` 파라미터로
  slug를 받아 모든 경로에 적용한다.
  예: `business=mycafe` → `businesses/mycafe/knowledge/`, `businesses/mycafe/state/`,
  `businesses/mycafe/config.yaml`.
- 새 사업 추가 = `templates/` 복사 + 지식파일 작성. 코어 수정 불필요.
- 스케줄러는 사업별로 4개 트리거(main / naver_publish / weekly_calendar / engagement)를 등록한다.
- 사업 간 데이터는 완전히 격리된다. 에이전트는 실행 중인 사업의 디렉토리만 읽는다.

## 7. 코어/private 분리

| 구분 | 포함 | Git |
|---|---|---|
| 공개 코어 | `SPEC.md`, `README.md`, `ARCHITECTURE.md`, `AGENTS.md`, `docs/`, `skills/`, `playbooks/`, `bin/`, `templates/`, `businesses/example` (데모) | 커밋 |
| 사용자 private | `businesses/<slug>/` (지식·config·state·logs·reports·drafts·assets), `**/secrets.env`, `*.lock`, `state/KILL` | 추적 제외 (`.gitignore`) |

**업데이트 흐름**:

```bash
git pull origin main          # 코어 개선분 수신
# businesses/<slug>/는 추적 대상이 아니므로 그대로 유지됨
# templates/ 양식이 바뀌었으면 기존 businesses/<slug>/ 파일과 수동 대조
```

사업 데이터를 버전 관리하고 싶으면 별도 private 리포지토리로 관리한다.
코어 리포에 사업 실데이터·토큰을 커밋하지 않는다.

## 8. 멀티에이전트 확장 포인트

- 교체 지점은 시크릿 관리, 스케줄러 등록, 스킬 설치 경로, 브라우저 도구 4곳뿐이다.
  상세는 `docs/agent-compatibility.md` 참조.

## 9. 설계 원칙

1. **사업 데이터 날조 금지.** 지식파일에 없는 상품·가격·후기·수치는 만들지 않는다.
   모르는 것은 비워두고 "미확인"으로 표기한다. 모든 스킬의 전역 규칙.
2. **네이버는 보수적으로.** 발행 상한(블로그 일 1건), 09:00–11:00 균등 랜덤 발행,
   봇체크/CAPTCHA 시 당일 스킵 후 다음날 이월. OSS로 배포되면 다수 사용자가 같은 패턴으로
   네이버에 접근하므로, 탐지 회피를 위해 기본값을 보수적으로 유지한다.
3. **킬스위치 우선.** `state/KILL`이 존재하면 어떤 트리거도 실행하지 않는다.
   매 단계 시작 전 확인. 발동·해제는 텔레그램 알림.
4. **에이전트 비종속.** 특정 제품의 전용 기능·경로·도구를 가정하지 않는다.
   파일·셸·HTTP·Markdown 같은 오픈 표준만 사용한다.
   호환성 요구사항은 `docs/agent-compatibility.md`에 정의.
5. **실패는 알리고 멈춤.** 치명 단계(락·헬스체크·KILL) 실패 시 루틴 전체를 중단하고 즉시 알림한다.
   비치명 실패는 DLQ에 격리하고 알림 후 다음 단계로 진행한다. 실패를 숨기고 계속 진행하지 않는다.
6. **대시보드는 읽기가 우선이다.** 제어는 SPEC 20.5 매핑의 파일 연산(KILL 생성/삭제·DLQ 복구)으로만
   수행하고, 새로운 실행 로직을 만들지 않는다. 모든 쓰기는 감사 로그에 남긴다.
   없는 데이터는 "미확인"으로 표기하고 절대 지어내지 않는다.
   방향: 대시보드는 시스템 전체의 웹 인터페이스(컨트롤 플레인)로 단계적 확장한다
   (1차: 현황+비상 제어 완료 → 2차: 연동 상태 → 3차: 콘텐츠 읽기, SPEC 20.10).
   확장해도 "새 실행 로직을 만들지 않는다"는 원칙은 유지한다.

## 10. 대시보드

> 상세 계약(화면·API·제어 매핑·보안)의 정본은 `SPEC.md` 20장이다.
> 이 섹션은 대시보드가 아키텍처의 어디에 위치하고 어떤 흐름으로 동작하는지만 정의한다.

### 10.1 위치

- 대시보드는 저장소의 모듈(`skills/`·`playbooks/`·`bin/` 같은)이 아니라,
  **Muse fullstack 웹 아티팩트 (비공개)** 로 호스팅되는 별도 배포 단위다.
- 저장소에 대시보드 코드를 두지 않는다. 저장소가 제공하는 것은 **상태 계약**
  (SPEC 10장의 `state/*.jsonl` 스키마·`reports/`·`logs/` 구조)뿐이다.
  대시보드는 이 계약을 읽는 클라이언트다.
- 이 선택의 이유: 사용자의 브라우저가 닿을 수 있는 유일하게 검증된 웹 호스팅 경로가
  Muse 아티팩트이기 때문이다 (SPEC 20.2).

### 10.2 데이터 플로우

읽기 (조회):

```
businesses/<slug>/state/*.jsonl ─┐
businesses/<slug>/reports/       ─┼──▶ 대시보드 서버 ──▶ 사용자 브라우저
businesses/<slug>/logs/          ─┘        (읽기 전용)
businesses/<slug>/config.yaml ───┘
```

- `secrets.env`는 읽지 않는다. 읽을 수 있는 경로에서 제외한다.

쓰기 (제어):

```
사용자 브라우저 ──POST──▶ 대시보드 서버 ──▶ businesses/<slug>/state/ 파일 연산
                                                    ├── KILL 생성/삭제 (SPEC 20.5)
                                                    ├── queue.jsonl 에 DLQ 복구 append
                                                    ├── queue.jsonl 레코드의 approved_at 기록 (발행 승인, SPEC 20.4)
                                                    ├── logs/<오늘>/dashboard_audit.jsonl append
                                                    ├── state/notification_queue.jsonl 에 알림 요청 적재
                                                    ├── config.yaml 쓰기 (설정 변경, SPEC 20.10)
                                                    └── secrets.env 쓰기 (토큰 저장, write-only)
```

- 쓰기는 SPEC 20.5(제어 매핑)·20.10(설정·토큰)·20.4(큐 승인)의 파일 연산으로만 수행한다.
  효과는 대응하는 `bin/kill.sh`·`bin/resume.sh`·`bin/dlq.sh resolve`와 동일해야 한다.
- 대시보드는 `bin/run.sh`·`bin/retry.sh`를 호출하지 않는다.
  이 둘은 실제 실행을 오케스트레이터 AI 에이전트에게 위임하는 껍데기라서,
  대시보드가 직접 실행할 수 없다 (SPEC 20.8: 구조적 선행조건 — 오케스트레이터 실행 구조 변경 시 재검토).

> 방향 (v1.8): 대시보드는 시스템 전체의 웹 인터페이스(컨트롤 플레인)로 단계적 확장한다.
> 1차(현황·큐·리포트·제어)·2차(연동 상태)·3차(콘텐츠 초안 뷰어, 읽기 전용) 완료.
> 상세 로드맵은 SPEC 20.10.

### 10.3 상태 브릿지 검증 (구현 선행 조건)

구현 착수 전, 아티팩트 서버 런타임이 `businesses/<slug>/state|reports|logs`에
읽기·쓰기 접근 가능한지 검증한다 (판정 기준: SPEC 20.2).
검증 실패 시 대시보드는 읽기 전용으로 전환하고, 제어는 기존 수단(채팅·`bin/*.sh`)을 유지한다.
자세한 폴백은 SPEC 20.2.

### 10.4 코어/private·OSS와의 관계

- 대시보드는 Git 추적 대상이 아니다 (호스팅된 아티팩트).
- 대시보드가 의존하는 상태 계약(SPEC 10장)은 공개 코어에 포함되므로,
  타 에이전트·타 구현체도 같은 계약으로 자체 UI를 만들 수 있다.
- 대시보드 UI 자체의 Muse 종속성은 `docs/agent-compatibility.md`에 기록한다.
