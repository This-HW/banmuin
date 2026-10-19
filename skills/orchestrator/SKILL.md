---
name: orchestrator
description: 일일 마케팅 루틴 전체를 조율하는 프로젝트 매니저. cron 트리거에 기동해 수집→분석→제작→검수→발행→보고 단계를 순서대로 실행하고, 치명도 분류에 따라 중단·재시도·DLQ 격리를 처리한다.
---

# Orchestrator (프로젝트 매니저)

## 역할
일일 루틴 전체 조율. 스케줄러(cron)가 깨운 오케스트레이터 AI 에이전트가 이 스킬을 읽고 단계별로 실행한다.
판단·실행의 주체는 오케스트레이터 AI 에이전트이며 (`docs/agent-compatibility.md`의 최소 요구사항을 만족하는 임의의 에이전트), 이 문서는 실행 순서와 규칙의 정본이다.

## 입력
- 사업 슬러그: `business` (기본값 `main`). 모든 사업별 경로(`businesses/<slug>/...`)의
  `<slug>` 자리에 사용된다. 예: `business=mycafe` → `businesses/mycafe/knowledge/`,
  `businesses/mycafe/state/`, `businesses/mycafe/config.yaml`.
  새 사업은 `templates/config.yaml`과 `templates/knowledge/`를
  `businesses/<slug>/` 아래에 복사해 시작한다.
- 트리거 종류: `main` (매일 06:30) / `naver_publish` (매일 09:00) / `weekly_calendar` (일요일 20:00)
- 실행 날짜 (기본: 오늘, KST)

## 사업 단계 분기
루틴 시작 시 `businesses/<slug>/knowledge/00_사업개요.md`의 `사업 단계` 값을 읽고
아래 표에 따라 파이프라인을 분기한다. 값은 `아이디어` / `준비중` / `사전예약중` / `운영중`
중 하나여야 한다. 값이 없거나 4단계 외의 값이면 루틴을 시작하지 않고 대표에게 확인을 요청한다.

| 사업 단계 | main 트리거 파이프라인 | 담당 스킬 |
|---|---|---|
| `아이디어` | 시장조사만: 수요 검증 리포트, 고객 인터뷰 질문지 10개, 합격선 판정 | pre-launch |
| `준비중` | 시장조사 + 빌드인퍼블릭 콘텐츠 주 3회 + 랜딩 페이지 카피 초안 | pre-launch · content |
| `사전예약중` | 사전예약 유도 콘텐츠 + 대기리스트 관리 + 베타테스터 모집 + 얼리버드 혜택 운영 | pre-launch · content |
| `운영중` | 기존 파이프라인 전체 (수집→분석→제작→검수→발행→보고) | 전체 (아래 트리거별 수행 내용) |

- `naver_publish` 트리거는 단계와 무관하게 동작한다 (SPEC 8.4). 큐에 발행 대기 콘텐츠가 없으면
  no-op이다 (예: `아이디어` 단계). `사전예약중` 단계에서 큐에 쌓인 예약 유도 콘텐츠도 정상 발행한다.
- `weekly_calendar` 트리거는 단계에 맞춰 캘린더를 생성한다
  (`준비중`=빌드인퍼블릭 캘린더, `사전예약중`=예약 유도 캘린더, `운영중`=기존 주간 캘린더).
- **사업 단계 값은 대표의 명시적 승인 없이 변경하지 않는다**
  (전환 절차는 pre-launch 스킬의 "운영중 전환 체크리스트" 참조).

## 트리거별 수행 내용

### 트리거 시작 공통 절차 (main·naver_publish·weekly_calendar 3개 트리거 공통.
engagement 트리거는 `skills/engagement/SKILL.md`의 시작 절차를 따른다)

1. 락 획득: `businesses/<slug>/state/scheduler.lock` 생성
   (`{"started_at","host","run_id"}`). 24시간 이상 된 락은 stale로 간주하고 경고 후 정리.
2. KILL 확인: `businesses/<slug>/state/KILL`이 있으면 루틴 전체를 즉시 중단하고
   텔레그램으로 알림한다 (핵심 규칙 1).
3. 알림 큐 drain: SPEC 20.5의 **원자적 drain 절차**를 수행한다
   (rename → 발송 → config_changed 동기화 → draining 파일 삭제).
   대시보드에서 적재된 제어 알림(`kill`·`resume`·`dlq_resolve`·`integration_request`·
   `config_changed`)이 이 단계에서 대표에게 전달된다. 큐가 비어 있으면(다른 트리거가
   이미 drain했으면) 아무 것도 하지 않는다.
   `config_changed`를 받으면 `detail.keys`를 확인하고, 예산 캡·게이트 임계값 변경이 포함된 경우
   `knowledge/08_승인기준.md` 정본에도 동일하게 반영한다 (SPEC 20.10 4차).
4. 헬스체크 (main 트리거만): 채널 세션/API 상태를 확인하고, 결과와 무관하게
   `businesses/<slug>/state/health.json`을 먼저 기록한 뒤 (스키마 SPEC 20.10),
   실패 시 루틴 전체를 중단하고 텔레그램으로 즉시 알림한다.
   체크는 읽기 호출만 수행한다 (쓰기·발송 금지).

### 트리거 종료 공통 절차 (main·naver_publish·weekly_calendar 3개 트리거 공통)

1. `businesses/<slug>/state/last_run.json` 기록:
   `{"date":"<오늘>","trigger":"main|naver_publish|weekly_calendar",`
   `"status":"completed|failed","finished_at":"<KST ISO>","failed_stage":"<단계명|null>"}`.
   대시보드 상태 배너의 판정 근거 (SPEC 20.3).
2. 락 해제: `scheduler.lock` 삭제.

### main (06:30)
| 시각 | 단계 | 담당 스킬 | 타임아웃 | 치명 |
|---|---|---|---|---|
| 06:30 | 트리거 시작 공통 절차 (락 → KILL 확인 → 알림 큐 drain → 헬스체크 + `health.json` 기록) | — | 10분 | 치명 |
| 06:40 | 수집: Meta MCP 성과(ads 스킬에 위임), 전날 발행 콘텐츠 반응(채널별), 미답변 문의 | ads · customer-research · analytics · customer-care | 15분 | 비치명 |
| 07:00 | 분석 리포트 생성 | analytics | 15분 | 비치명 |
| 07:20 | 콘텐츠 제작 (블로그·스레드·카드뉴스·숏폼) | content | 40분 | 비치명 |
| 08:00 | 품질 게이트 (1차 규칙 → 2차 AI) | content | 20분 | 비치명 |
| 08:30 | API 채널 발행: 큐에서 `channel∈{threads,instagram,youtube}`·`status=queued`인 건을 읽어 발행 후 `published`로 갱신 (승인 필터 미적용 — 18 #12) | 오케스트레이터 직접 (API 호출) | 30분 | 비치명 |
| 09:00 | 아침 리포트 생성 → 텔레그램 발송 → 락 해제 | — | 10분 | 비치명 |

- 월요일 루틴에는 AEO 주간 측정 포함 (customer-research 스킬)
- 네이버 블로그 발행은 이 루틴에 포함하지 않는다 (별도 트리거)

### naver_publish (09:00)
1. 기동 후 09:00~11:00 사이 균등 랜덤으로 대기
2. `businesses/<slug>/state/queue.jsonl`에서 `channel=naver_blog`, `status=queued`인 건 조회.
   `config.yaml`의 `publishing.require_approval=true`면 `approved_at`이 기록된 건만 발행 대상으로 한다
   (미승인 건은 건너뛰고 다음 실행에서 다시 확인 — SPEC 11.3 #1 승인 모드)
3. `playbooks/naver-blog-publish.task.md`를 Aside(`aside exec`)에 전달해 발행. 큐 레코드의 `category`를 `{{카테고리}}` 변수로 전달 (없으면 `미지정`)
4. 성공 시 `publish_log.jsonl`에 기록, 큐 상태 → `published` (발행 URL 포함)
5. 실패 시 재시도 정책 적용 (아래 참조)

### 발행 승인 모드 (`publishing.require_approval`, SPEC 11.3 #1)
- `true`면 네이버 블로그 발행(09:00 트리거)에서 `approved_at`이 기록된 큐 레코드만 발행한다.
- 미승인 건은 건너뛰고 다음 실행에서 다시 확인한다 (DLQ에 넣지 않는다).
- v1.10.5 범위: 네이버 블로그 발행에만 적용. 08:30 API 채널 발행 단계도 큐에서 읽어
  발행하지만 승인 필터는 적용하지 않는다 — API 채널 연동 시점에 승인 흐름을 별도
  설계한다 (SPEC 18장 #12).

### weekly_calendar (일요일 20:00)
- 다음 주 `businesses/<slug>/content_calendar.md` 생성
- `businesses/<slug>/config.yaml`의 `channels.<채널>.max_per_day` 빈도 상한 준수

## 출력 (산출물 경로)
- `businesses/<slug>/reports/daily/YYYY-MM-DD.md` — 아침 리포트
- `businesses/<slug>/state/queue.jsonl` — 발행 큐 상태 업데이트
- `businesses/<slug>/state/health.json` — 헬스체크 결과 (main 트리거 시작 시 기록, SPEC 20.10)
- `businesses/<slug>/state/last_run.json` — 트리거 종료 시 실행 결과 기록 (SPEC 20.3)
- `businesses/<slug>/state/publish_log.jsonl` — 발행 이력 (append-only)
- `businesses/<slug>/state/dead_letter.jsonl` — DLQ
- `businesses/<slug>/logs/YYYY-MM-DD/` — 단계별 실행 로그 (JSONL)
- 텔레그램: 아침 리포트 파일 첨부 + 핵심 5줄 요약 / 즉시 알림 (아래 참조)

## 핵심 규칙
1. **매 단계 시작 전 `businesses/<slug>/state/KILL` 존재 확인.** 있으면 루틴 전체를 즉시 중단하고 텔레그램으로 알림한다. (`bin/resume.sh`로 해제되기 전까지 어떤 트리거도 실행하지 않는다)
2. **치명도 분류를 지킨다.** 치명 단계(락 획득, 헬스체크, KILL 확인) 실패 → 루틴 전체 중단 + 즉시 알림. 비치명 단계(수집·분석·제작·검수·발행·보고) 실패 → DLQ 기록 + 알림 후 다음 단계로 진행한다. 헬스체크 실패 상태에서 제작을 진행하지 않는다 (Higgsfield 크레딧·토큰 낭비 방지).
3. **락을 획득하고 종료 시 해제한다.** `businesses/<slug>/state/scheduler.lock` (`{"started_at","host","run_id"}`). 비정상 종료에 대비해 정리 절차를 실행 순서에 포함한다. 24시간 이상 된 락은 stale로 간주하고 경고 후 무시한다.
4. **재시도 정책:** 단계별 최대 3회, 지수 백오프 (5분 → 15분 → 45분, `businesses/<slug>/config.yaml`의 `retry`).
5. **멱등성을 보장한다.** 발행 전 멱등키(`content_id:channel:date`)로 `publish_log.jsonl`을 확인하고, 이미 `published`면 스킵한다. 의도적 재발행은 `--force`로만.
6. **모든 단계의 산출물을 지정된 경로에 저장한다.** (위의 출력 목록)
7. **`state/`는 Git에 커밋하지 않는다.** `businesses/<slug>/state/`는 Git 추적 제외 (SPEC 10.3). 백업은 별도 private 경로로 관리한다.
8. **텔레그램 즉시 알림 조건:** 치명 단계 실패, DLQ 발생, 세션 만료, KILL 발동/해제, 예산 임계값(잔량 20%) 도달.

## 참조 파일
- `SPEC.md` 2장 (아키텍처·치명도), 8장 (스케줄러), 10장 (상태 관리), 11장 (가드레일), 12장 (알림·리포트)
- `businesses/<slug>/config.yaml` — 스케줄·채널 상한·재시도·보관 정책
- `businesses/<slug>/knowledge/08_승인기준.md` — 예산 캡·게이트 기준 (정본)
- `playbooks/naver-blog-publish.task.md` — 네이버 발행 작업 지시서

## 실패 시 처리
| 실패 | 처리 |
|---|---|
| 치명 단계 실패 (락/헬스체크/KILL) | 루틴 전체 중단, 텔레그램 즉시 알림, 락 해제 |
| 비치명 단계 실패 (3회 재시도 후) | `businesses/<slug>/state/dead_letter.jsonl`에 격리, 텔레그램 알림, 다음 단계 진행 |
| Aside 작업 실패 (네이버) | 플레이북의 실패 보고 형식으로 원인 파악. UI 변경이면 플레이북 수정 후 재실행, 봇체크/CAPTCHA면 당일 스킵 → 다음날 큐로 이월 |
| API 한도·429 (Threads/IG/YouTube) | 지수 백오프 후 다음날 이월 |
| 전체 루틴 비정상 종료 | 다음 기동 시 stale 락 감지 → 경고 후 정리, DLQ에서 미완료 건 확인 |
