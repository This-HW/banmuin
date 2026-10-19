# 품질 게이트 체크리스트

content 스킬이 제작한 모든 콘텐츠는 아래 1차 → 2차 순서로 검수한다.
판정은 **통과 / 수정 후 재검수 / 폐기** 중 하나다.

## 1차 검수 — 규칙 기반 (에이전트가 직접 대조)

- [ ] **분량·규격 준수**: 채널별 포맷 가이드(`blog_format.md`·`threads_format.md`·
  `cardnews_format.md`·`shorts_format.md`)의 분량·규격·수량 항목 전부 통과
- [ ] **금지어 미포함**: `businesses/<slug>/knowledge/06_브랜드보이스.md`의 금지어 목록과 대조
- [ ] **필수 요소 포함**: CTA, 핵심 키워드 (채널별 포맷 가이드의 필수 항목)
- [ ] **중복 검사**: 최근 30일 `businesses/<slug>/state/publish_log.jsonl`과 주제·표현 중복 여부 대조.
  기준은 `businesses/<slug>/knowledge/08_승인기준.md`. 중복이면 폐기

→ 1차 실패 시 **폐기** (`businesses/<slug>/drafts/` 보관, 사유 기록)

## 2차 검수 — AI (에이전트가 지식파일과 대조)

- [ ] **근거 없는 주장 여부**: 모든 효능·차별점·수치 주장이
  `businesses/<slug>/knowledge/01_상품서비스.md`·`05_후기_사례.md`·`04_고객질문_FAQ.md`에 근거하는지 확인
- [ ] **과장·허위 표현 여부**: "1위"·"최고"·"100% 보장" 등 근거 없는 절대 표현 검출
- [ ] **브랜드보이스 일치 여부**: `businesses/<slug>/knowledge/06_브랜드보이스.md`의 말투·문체·이모지 정책과 일치

## 판정 기준

| 판정 | 조건 | 처리 |
|---|---|---|
| 통과 | 1차·2차 전부 통과 | `businesses/<slug>/state/queue.jsonl`에 `queued`로 등록 |
| 수정 후 재검수 | 2차에서 수정 가능 항목만 실패 | content 스킬이 수정 후 재검수. **최대 2회** (`businesses/<slug>/config.yaml`의 `quality_gate.max_rework`) |
| 폐기 | 1차 실패, 또는 2차 재검수 2회 초과, 또는 근거 자체가 없는 주장 | `businesses/<slug>/drafts/YYYY-MM-DD/`에 보관. 아침 리포트에 기록 |

## 검수 리포트
- `businesses/<slug>/logs/YYYY-MM-DD/quality_*.md`에 항목별 통과/실패와 사유를 기록한다.
- 리포트 양식:
  ```
  # 검수 리포트 (YYYY-MM-DD)
  ## 대상: <content_id> (<channel>)
  ## 1차: 통과/실패 — 사유
  ## 2차: 통과/수정/폐기 — 사유
  ## 판정: 통과/수정 후 재검수(n회차)/폐기
  ## 조치: 큐 등록/drafts 보관
  ```
