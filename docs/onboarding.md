# docs/onboarding.md — 새 사업 온보딩 가이드

> 새 사업을 이 시스템에 올리는 절차입니다.
> 사업주(사람)가 설문에 답하면 → 에이전트가 11개 지식파일을 채우고 → 드라이런으로 검증합니다.

## 0. 사업 단계 먼저 정하기

이 시스템은 사업 단계에 따라 실행 파이프라인이 달라진다 (SPEC 1.7).
설문에 답하기 전에 단계를 먼저 정한다. 단계는 `00_사업개요.md`의 `사업 단계` 필드에 기록된다.

| 단계 | 상태 | 시스템이 하는 일 |
|---|---|---|
| 아이디어 | 사업 아이템 검증 전 | 시장조사만 (수요 검증·인터뷰 질문지·합격선 판정) |
| 준비중 | 검증 통과, 출시 준비 중 | 시장조사 + 빌드인퍼블릭 콘텐츠(주 3회) + 랜딩 카피 |
| 사전예약중 | 출시 직전, 고객 모집 중 | 사전예약 유도 콘텐츠 + 대기리스트 + 베타테스터 + 얼리버드 |
| 운영중 | 출시 후 정상 운영 | 전체 파이프라인 |

단계 변경은 대표의 명시적 승인이 필요하다. 에이전트가 임의로 바꾸지 않는다.

## 1. 설문 → 지식파일 매핑표

각 질문의 답이 어느 지식파일에 들어가는지 보여줍니다.
지식파일 템플릿은 `templates/knowledge/`에 있습니다.

| # | 설문 문항 | 답이 들어가는 파일 |
|---|---|---|
| 1 | 사업명, 업종, 위치, 영업시간, 연락처를 적어주세요 | `00_사업개요.md` |
| 2 | 대표 상품/서비스 3~5개와 각각의 특징·차별점을 적어주세요 | `01_상품서비스.md` |
| 3 | 가격표(메뉴·요금제·할인/프로모션 조건)를 적어주세요 | `02_가격정책.md` |
| 4 | 주 고객은 누구인가요? (연령·성별·직업·방문 동기·고민) 2~3개 페르소나로 적어주세요 | `03_고객페르소나.md` |
| 5 | 고객이 자주 묻는 질문과 실제 답변을 10개 이상 적어주세요 | `04_고객질문_FAQ.md` |
| 6 | 실제 후기·리뷰·성공사례를 5개 이상 붙여넣어주세요 (출처 포함) | `05_후기_사례.md` |
| 7 | 브랜드 말투를 정해주세요 (존댓말/반말, 이모지 사용 여부, 금지 표현) + 참고할 만한 기존 글 2~3개 | `06_브랜드보이스.md` |
| 8 | 운영 중인 채널(블로그·인스타·유튜브 등)과 각 채널의 목표를 적어주세요 | `07_채널전략.md` |
| 9 | 하루 콘텐츠 발행 상한, 월 광고 예산 상한, 검수 기준을 정해주세요 (기본값은 템플릿 참조) | `08_승인기준.md` |
| 10 | 경쟁사 3~5곳과 그들의 강점·약점을 적어주세요 | `09_경쟁사.md` |
| 11 | 사업에서만 쓰는 용어·약어를 적어주세요 | `10_용어집.md` |
| 12 | (선택) 절대 하지 않겠다고 정한 마케팅 표현·주제가 있나요? | `06_브랜드보이스.md` (금지 표현) |

**규칙**:
- 빈칸으로 두지 마세요. 모르는 항목은 `[작성 필요]` 그대로 두고, 에이전트에게 맡기지 마세요.
- 후기·가격·실적은 **실제 자료만**. 없는 내용을 지어내면 안 됩니다 (전역 규칙).
- `08_승인기준.md`의 예산 캡·게이트 임계값이 정본입니다. `config.yaml`의 같은 값은 미러입니다.

### 단계별 지식파일 작성 가이드 차이

같은 설문이라도 단계에 따라 지식파일을 다르게 채운다:

| 단계 | 작성 가이드 |
|---|---|
| 아이디어 | `01_상품서비스.md`는 가안(후보)으로 작성하고 "미확정" 표기. `04_고객질문_FAQ.md`는 예상 질문으로 채움. `05_후기_사례.md`는 비워둔다 (후기를 지어내지 않는다). `08_승인기준.md`에 수요 검증 합격선(인터뷰 N명 중 M명)을 정의 |
| 준비중 | `01`의 가안을 구체화. `06_브랜드보이스.md` 톤 확정 (랜딩 카피에 사용). `07_채널전략.md`에 빌드인퍼블릭 채널·빈도(주 3회) 명시 |
| 사전예약중 | `02_가격정책.md`에 얼리버드 가격·조건 명시. `04_고객질문_FAQ.md`에 사전예약 관련 질문(예약금·환불·출시일) 추가. `07_채널전략.md`의 모든 CTA를 사전예약 유도로 통일 |
| 운영중 | 전부 실데이터로 작성. 기존 가이드 그대로 |

## 2. 사업 디렉토리 만들기

```bash
cd ai-marketing-agent

# 1) 사업 슬러그 정하기 (영문 소문자, 예: mycafe)
BUSINESS=mycafe

# 2) 디렉토리 뼈대 + 템플릿 복사
mkdir -p businesses/$BUSINESS/{state,logs,reports,drafts,assets,data}
cp templates/config.yaml businesses/$BUSINESS/config.yaml
cp -r templates/knowledge businesses/$BUSINESS/knowledge
cp templates/secrets.env.example businesses/$BUSINESS/secrets.env
cp templates/content_calendar.md businesses/$BUSINESS/content_calendar.md
cp templates/data/orders.csv businesses/$BUSINESS/data/orders.csv   # D+7 재구매용 (수동 입력)

# 3) Git 제외 확인 (businesses/* 는 README·example 제외하고 커밋되지 않음)
git status --short businesses/ | grep -v README || echo "OK: 사업 데이터는 Git 추적 제외"
```

완성 구조:

```
businesses/mycafe/
├── config.yaml          # 채널 on/off, 스케줄, 예산 미러값 조정
├── secrets.env          # API 키·토큰 입력 (절대 커밋 금지)
├── knowledge/           # 1장의 설문 답으로 11개 파일 채우기
├── content_calendar.md  # 주간 캘린더 (일요일 20:00 자동 생성)
├── state/               # queue.jsonl, dead_letter.jsonl, KILL
├── drafts/              # 게이트 미통과 초안 보관소
├── logs/                # 실행 로그
├── reports/             # 일일/주간 리포트
└── assets/              # 생성 이미지·영상
```

## 3. 설정 다듬기

1. `businesses/<slug>/config.yaml` — 사용할 채널만 `enabled: true`
   (브라우저 자동화 도구가 없으면 `naver_blog.enabled: false`).
2. `businesses/<slug>/secrets.env` — 필요한 API 키·토큰 입력.
   값은 에이전트의 시크릿 관리(Secure Vault 등)로 주입하는 것을 권장.
3. 스케줄러 등록 — `docs/agent-compatibility.md` 4.2 참조
   (cron 예: `30 6 * * * /path/to/bin/run.sh --business <slug>`).

## 4. 드라이런으로 검증하기

실제 발행 없이 파이프라인 전체가 도는지 확인합니다.

```bash
# 발행 제외 전체 실행
bin/run.sh --business mycafe --dry-run

# 단계별 실행 (문제 구간만)
bin/run.sh --business mycafe --dry-run --stage 제작
bin/run.sh --business mycafe --dry-run --stage 검수
```

**확인 체크리스트**:
- [ ] `logs/<오늘날짜>/`에 단계별 로그가 생성됐는가
- [ ] `reports/`에 리포트가 생성됐는가
- [ ] 실제 발행이 일어나지 않았는가 (블로그·SNS에 글이 올라오지 않았는지 확인)
- [ ] 게이트 미통과 콘텐츠가 `drafts/<오늘날짜>/`에 보관됐는가
- [ ] `state/queue.jsonl`에 발행 대기 건이 쌓였는가
- [ ] 에러가 `state/dead_letter.jsonl`에 기록되고 알림이 왔는가 (고의로 실패를 유도해 테스트)
- [ ] 사업 단계가 `아이디어`면 시장조사 단계만 실행됐는가 (SPEC 8.4)

드라이런이 깨끗하면 `--dry-run`을 빼고 파일럿 운영(1~2주, 발행량 최소)으로 들어갑니다.
문제가 있으면 `CONTRIBUTING.md`의 이슈 양식으로 보고해주세요.
