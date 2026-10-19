---
name: engagement
description: 인스타그램 댓글→DM 자동화. 30분 폴링으로 새 댓글을 수집해 공개 답글을 달고, 댓글 작성자의 팔로우 여부를 확인한 뒤 DM을 발송한다. 기본 비활성 — config `engagement.comment_to_dm.enabled=true` 명시적 opt-in에서만 동작한다.
---

# Engagement (인게이지먼트 담당자)

## 역할

인스타그램 게시물에 달린 새 댓글에 자동으로 공개 답글을 달고, 댓글 작성자가 우리
계정을 팔로우하는지 확인한 뒤 조건에 맞는 안내 DM을 보내는 담당자.
(ManyChat식 comment-to-DM을 공식 Meta API로 구현한 것)

```
댓글 작성 → 공개 답글 (자동) → 팔로우 여부 확인 → DM 발송
                                              ├─ 팔로워 → 정보 DM
                                              └─ 미팔로워 → 팔로우 요청 + 정보 DM
```

- 대상은 **인스타그램만**이다. Threads는 DM API가 없어서 범위 외다 (SPEC 21.10).
- **웹훅이 아니라 30분 간격 폴링**으로 동작한다. 이 시스템은 cron+에이전트 구조라
  상시 대기 서버가 없기 때문이다 (SPEC 21.4).
- 일일 루틴(main·naver_publish·weekly_calendar)과 **독립적으로** 동작한다.
  `state/last_run.json`을 건드리지 않는다 — 30분마다 덮어쓰면 대시보드의
  "오늘 루틴" 배너가 engagement 상태로 바뀌어 버리기 때문이다 (SPEC 21.4 [7]).

## 입력

- 사업 슬러그: `business` (기본값 `main`)
- 설정: `businesses/<slug>/config.yaml`의 `engagement.comment_to_dm` (SPEC 21.3)
- 토큰: `secrets.env`의 `INSTAGRAM_ACCESS_TOKEN` (장기 토큰, 60일 유효)

## 실행 절차

트리거: `*/30 * * * *` (30분 간격, KST). 트리거명 `engagement`.

### [1] 시작 공통 절차

1. 락 획득: `businesses/<slug>/state/engagement.lock`
   (`{"started_at","host","run_id"}`). 30분 주기에 맞춰 stale 기준은 **2시간**이다
   (SPEC 21.4 [1] — scheduler.lock의 24시간과 다름).
   - 일일 루틴의 `scheduler.lock`과 **별도 파일**이다. engagement는 30분마다 돌고
     main 루틴은 06:30에 약 2.5시간 동안 락을 잡으므로, 같은 락을 쓰면 매번 충돌한다.
     두 트리거가 건드리는 상태 파일이 다르므로(engagement.json vs queue/last_run)
     분리해도 안전하다.
2. KILL 확인: `businesses/<slug>/state/KILL`이 있으면 즉시 중단하고 텔레그램으로 알린다.
3. 알림 큐 drain: SPEC 20.5의 **원자적 drain 절차**를 수행한다
   (rename → 발송 → config_changed 동기화 → draining 파일 삭제).
   engagement도 drain의 소비자이므로 절차는 3개 트리거와 완전히 동일하다
   (어느 트리거가 drain하든 동기화가 유실되지 않는다).

### [2] 활성화 확인

`engagement.comment_to_dm.enabled`가 `false`(기본값)이면 **no-op 종료**하고 락을 해제한다.
자동 발송 계열은 대표의 명시적 opt-in 없이는 절대 동작하지 않는다.

### [3] 토큰 만료 확인

`INSTAGRAM_ACCESS_TOKEN`의 만료를 확인한다
(`GET /debug_token?input_token=<토큰>`, 앱 액세스 토큰으로 조회).
만료까지 7일 이하로 남았으면 텔레그램으로 알리고 계속 진행한다
(토큰 자체는 사람이 갱신 — 자동 갱신하지 않는다).

### [4] 상태 읽기

`businesses/<slug>/state/engagement.json`을 읽는다
(없으면 첫 실행으로 간주하고 `last_check_at`을 지금 시각으로 둔다):

```json
{"last_check_at": "<KST ISO>", "reply_template_index": 0,
 "last_run_at": "<KST ISO>", "last_status": "completed|failed", "processed_count": 0}
```

### [5] 새 댓글 수집

1. 내 미디어 목록 조회: `GET /{ig-user-id}/media`
   (권한: `instagram_business_basic`)
2. 각 미디어의 댓글 조회: `GET /{media-id}/comments`
   (권한: `instagram_business_basic`)
3. 댓글 객체의 `timestamp`가 `last_check_at` **이후인 것만** 남긴다
   (`>=` 비교 — 같은 초에 달린 여러 댓글 누락 방지. 클라이언트에서 필터링하며,
   `since` 파라미터 지원 여부에 의존하지 않는다.
   이미 처리된 댓글은 [6-1] 멱등성으로 걸러지므로 중복 처리되지 않는다).
4. **오래된 댓글부터** 순서대로 정렬한다 (7일 유효기간이 임박한 것부터 처리).
5. 이 단계 자체가 실패하면 **치명 실패**로 간주한다: 루틴 중단 + 텔레그램 즉시 알림
   (SPEC 8.2 치명 분류 준용). 재시도는 다음 30분 실행에서.

### [6] 댓글별 처리 (`max_per_run` 상한까지)

댓글마다 아래 순서대로 처리한다. 멱등성 키는 `comment_id`다.

**[6-1] 멱등성 체크**
- `businesses/<slug>/state/engagement_processed.jsonl`에서 `comment_id`를 조회한다:
  - 레코드 없음 → 신규 처리.
  - `status=done` → 스킵 (이미 답글·DM 완료).
  - `status=skipped_keyword` → 스킵.
  - `status=failed` + `attempts>=3` → 스킵 (재시도 중단 — 수동 확인 대상).
  - `status=failed` + `attempts<3` → **재시도**. `failed_step`부터 이어서 처리한다
    (`reply`면 답글부터, `dm`이면 답글은 건너뛰고 DM만).
    (주의: SPEC 21.4 [5-1]의 "comment_id가 있으면 스킵"은 완료 건에만 해당한다.
    실패 건까지 스킵하면 아래 실패 처리의 재시도가 절대 일어나지 않는다.)
- **자기 계정이 작성한 댓글은 처리 대상에서 제외**한다 (자기 답글에 답글 다는 무한 루프 방지).

**[6-2] 키워드 필터**
- `keywords`가 비어 있으면 전체 통과.
- 비어 있지 않으면 댓글 본문에 키워드 중 하나라도 포함된 댓글만 처리한다 (부분 일치).

**[6-3] 공개 답글**
- `POST /{comment-id}/replies` (권한: `instagram_business_manage_comments`)
- 문구는 `public_reply_templates`에서 `reply_template_index` 순번으로 선택하고,
  답글을 보낼 때마다 `index = (index + 1) % 템플릿 수`로 순환한다
  (동일 문구 반복은 스팸 시그널 — 템플릿 3개 이상 필수).
- 답글은 댓글당 **1회**만. `replied_at`이 이미 기록된 댓글은 답글을 건너뛴다.

**[6-4] 팔로우 확인**
- 댓글 작성자의 User Profile 조회 → `is_user_follow_business` 필드
  (권한: `instagram_business_basic`)
- 조회 실패 시 `follow_status="unknown"`으로 두고 DM은 정보 제공 목적이므로
  정상 진행한다 (아래 분기 참조).

**[6-5] DM 발송 (Private Replies)**
- `POST /{ig-user-id}/messages` (권한: `instagram_business_manage_messages`),
  `recipient={comment_id}`.
- DM은 댓글당 **1회**, 댓글 작성 후 **7일 이내**에만 발송한다.
  7일이 지난 댓글이면 DM을 건너뛰고 공개 답글까지만 처리한다
  (Meta Private Replies 제한).
- 본문 선택:
  | 조건 | DM 본문 |
  |---|---|
  | 팔로워 | `dm_template` (정보 DM) |
  | 미팔로워 + `require_follow=true` | `dm_follow_request_template` (팔로우 요청 DM) |
  | 미팔로워 + `require_follow=false` | `dm_template` (정보 DM) |
  | 팔로우 확인 실패 (`unknown`) | `dm_template` (정보 DM) |
- `HUMAN_AGENT` 태그를 자동화에 사용하지 않는다 (Meta 정책 위반).
  DM 본문에 홍보성 콘텐츠를 포함할 때는 Meta 메시지 정책을 준수한다.

**[6-6] 처리 기록 append**

`businesses/<slug>/state/engagement_processed.jsonl`에 한 줄 추가:

```json
{"comment_id": "<id>", "media_id": "<id>", "user_id": "<id>", "username": "<이름>",
 "commented_at": "<KST ISO>", "replied_at": "<KST ISO|null>",
 "follow_status": "follower|non_follower|unknown",
 "dm_sent": true, "dm_kind": "info|follow_request|null",
 "attempts": 1, "status": "done|failed", "failed_step": "reply|dm|null"}
```

- `username`은 식별용으로만 보관한다. 실명·연락처는 절대 기록하지 않는다.
- 이 파일은 Git에 커밋하지 않는다 (SPEC 10.3). 보관 기간 90일.

### [7] 상태 갱신

`businesses/<slug>/state/engagement.json`을 갱신한다:

```json
{"last_check_at": "<KST ISO>", "reply_template_index": <다음 순번>,
 "last_run_at": "<KST ISO>", "last_status": "completed|failed", "processed_count": <이번 실행 처리 시도 수>}
```

- `last_check_at`은 **이번 실행에서 처리 시도한 댓글 중 가장 늦은 `timestamp`**로 둔다.
  시도한 댓글이 없으면 기존 값을 유지한다.
  (주의: "실행 시작 시각"으로 두면 `max_per_run` 초과 시 미처리 댓글이 다음 수집에서
  영원히 제외된다 — 수집 필터가 `timestamp >= last_check_at`이기 때문이다.
  처리 시도분까지만 전진시켜야 미처리분이 다음 실행에서 잡힌다.
  크래시로 [7]이 실행되지 않으면 기존 값이 유지되어 다음 실행에서 멱등성으로
  중복 없이 재처리된다.)
- `processed_count`는 이번 실행에서 처리 시도한 댓글 수다 (스킵 제외).
- `last_run.json`에는 **기록하지 않는다** ([1]의 주의사항 참조).

### [8] 종료

락(`engagement.lock`)을 해제한다.

## 핵심 규칙

1. **기본 비활성.** `enabled=true`는 대표의 명시적 opt-in이다. 설정 화면에서도
   정책 변경 키로 2단계 확인을 요구한다.
2. **댓글당 공개 답글 1회·DM 1회를 넘지 않는다** (멱등성으로 강제).
3. **7일이 지난 댓글에는 DM을 보내지 않는다** (공개 답글만 가능).
4. **공개 답글 템플릿은 3개 이상 등록하고 로테이션**한다.
5. **KILL 발동 중에는 트리거 전체를 중단**한다.
6. **처리 로그에 고객 실명·연락처를 기록하지 않는다.**
7. **`last_run.json`을 건드리지 않는다.**
8. **API 호출 실패 시 SPEC 8.3 재시도 정책**(최대 3회, 5→15→45분 백오프)을 준용한다.
   정확한 레이트리밋은 응답 헤더로 실측한다 (출처마다 수치가 엇갈리므로 하드코딩 금지).

## 참조 파일

- `SPEC.md` 21장 — 댓글→DM 자동화 정본 (설계 변경 시 이 장을 먼저 고친다)
- `ARCHITECTURE.md` — engagement 트리거 다이어그램·상태 파일 표
- `businesses/<slug>/config.yaml` — `engagement.comment_to_dm` 설정
- `businesses/<slug>/knowledge/08_승인기준.md` — 승인 기준 정본
- 사전 리서치 `comment-to-dm-automation-20261003-0639` (Private Reply 제한·
  App Review 요구사항·정책 위험) — private, 저장소 미포함

## 실패 시 처리

| 실패 | 처리 |
|---|---|
| [6-3] 공개 답글 실패 | 해당 댓글을 `status=failed, attempts+1, failed_step=reply`로 기록하고 다음 댓글로 진행. 다음 실행에서 재시도 (답글부터) |
| [6-5] DM 발송 실패 | `status=failed, attempts+1, failed_step=dm`로 기록. 다음 실행에서는 답글을 건너뛰고(`replied_at` 존재) DM만 재시도 |
| `attempts >= 3` | 재시도 중단 + 텔레그램 알림. 해당 댓글은 수동 확인 대상으로 남긴다 |
| [5] 댓글 조회 실패 (치명) | 루틴 전체 중단 + 텔레그램 즉시 알림. 다음 30분 실행에서 처음부터 재시도 |
| 토큰 만료 임박 (7일 이하) | 텔레그램 알림 후 계속 진행 (토큰 갱신은 사람이 수행) |
| API 429 (레이트리밋) | 지수 백오프로 대기 후 재시도. 응답 헤더의 제한 수치를 로그에 기록 |

## 구현 단계별 검증 (SPEC 21.9)

이 스킬의 실제 동작은 아래 순서로 검증한다. 각 단계는 검수 통과 후 다음으로 진행한다.

| 순서 | 검증 내용 |
|---|---|
| 2 | 댓글 조회 폴링 (읽기 전용): 실제 댓글을 읽어 로그만 남긴다. 발송 없음 |
| 3 | 공개 답글 자동화: 템플릿 로테이션 + 멱등성 실검증 (개발 모드·테스터 계정) |
| 4 | 팔로우 체크 + Private Reply DM: `is_user_follow_business` 분기 실검증 |
| 6 | App Review: 2~4의 실제 동작 화면으로 screencast 제출 |
| 7 | 대시보드 설정 화이트리스트에 `engagement.*` 추가 |

- 2~4는 개발 모드(테스터 계정)에서 검증하고, App Review 통과 후 실제 계정에 적용한다.
- 순서 1(사전 준비)은 대표가 직접 진행하고, 순서 5(스케줄러 편입)는 이 스킬 파일과
  30분 cron 등록으로 완료한다.
