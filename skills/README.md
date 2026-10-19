# skills/

AI 직원 8종의 역할 정의. 각 스킬은 `SKILL.md`(행동 지침) + `references/`(참조 자료)로 구성됩니다
(Anthropic Agent Skills 오픈 스펙 형식).

| 스킬 | 역할 |
|---|---|
| `orchestrator/` | 일일 루틴 조율 (단계 실행·게이트·실패 처리) |
| `customer-research/` | 시장·고객·경쟁사 조사 |
| `content/` | 콘텐츠 기획·제작 (블로그·Threads·카드뉴스·숏폼) |
| `ads/` | 광고 성과 조회·광고 초안 생성 (집행은 `channels.meta_ads.mode=auto` opt-in에서만) |
| `customer-care/` | 고객 문의 응대 (FAQ 근거) |
| `analytics/` | 성과 분석·리포트 |
| `pre-launch/` | 런칭기 지원 (수요 검증·빌드인퍼블릭·사전예약·베타테스터·얼리버드·운영중 전환 체크리스트) |
| `engagement/` | 인스타그램 댓글→DM 자동화 (SPEC §21, 30분 폴링·기본 비활성) |

- **읽는 이**: AI 에이전트 (오케스트레이터가 단계별로 호출)
- **쓰는 이**: 사람 (기여자). 스킬 내용은 SPEC의 해당 절과 일치해야 합니다.
- **규칙**: 특정 AI 제품 전용 문법·경로를 하드코딩하지 마세요 (`CONTRIBUTING.md` 5장).
