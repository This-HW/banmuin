# ai-marketing-agent

1인 사업자를 위한 반무인 AI 마케팅 자동화 시스템 (오픈소스 코어).

사용자의 AI 에이전트가 오케스트레이터가 되어 시장조사 → 콘텐츠 기획·제작 → 품질 검수 → 채널 발행 → 광고 운영 → 고객 응대 → 성과 분석 → 아침 리포트를 매일 자동으로 수행한다. 본체의 대부분은 코드가 아니라 **AI 에이전트가 읽고 실행하는 문서**(스킬·플레이북·설정)이므로, 최소 요구사항을 만족하는 어떤 AI 에이전트에서도 동작하도록 설계되어 있다. → [docs/agent-compatibility.md](docs/agent-compatibility.md)

사업별 데이터는 `businesses/<slug>/`에 격리되며, 코어 업데이트는 `git pull`로 받는다.

> **상태**: SPEC v1.10.6 기반 구현 (스킬 8종·플레이북 3종·실행 껍데기 6종·웹 대시보드 8화면).
> 드라이런 검증 완료, 30분 engagement cron은 비활성(opt-in) 유지 중.
> 실제 발행 전에는 반드시 `--dry-run`으로 파이프라인을 검증할 것.

## 주요 기능

- **Pre-launch 트랙**: 사업 단계(아이디어/준비중/사전예약중/운영중)에 따라 파이프라인 자동 분기.
  런칭 전 수요 검증·빌드인퍼블릭·사전예약 모집 지원 (SPEC 1.7)
- **시장조사** (`skills/customer-research`): 고객 질문·경쟁사 동향 수집, 광고 소구점 도출, 주 1회 AEO(브랜드 언급 여부) 측정
- **콘텐츠 제작** (`skills/content`): 블로그·Threads·카드뉴스·숏폼 4종 파이프라인 (기획 → 초안 → 1차 규칙 검수 → 2차 AI 검수 → 발행 큐)
- **채널 발행**
  - 네이버 블로그: Aside 브라우저 자동화 (`playbooks/` 작업 지시서), 09:00–11:00 균등 랜덤 발행, 일 1건 상한
  - Threads / Instagram / YouTube: 공식 API
  - 네이버 플레이스·스마트스토어: 미구현 (채널 추가 절차는 `AGENTS.md` 참조)
- **Meta 광고** (`skills/ads`): 성과 조회·분석 + 캠페인 초안 생성. 집행은 config `meta_ads.mode=auto` opt-in에서만 (기본값 draft_only)
- **에셋 생성**: Higgsfield로 숏폼 영상·카드뉴스 배경 생성 → `assets/` 저장
- **고객 응대** (`skills/customer-care`): FAQ 근거 답변 초안 작성. 발송은 config `customer_care.mode=auto_send` opt-in에서만 (기본값 draft_only)
- **분석·리포트** (`skills/analytics`): 일간 성과 분석, 아침 리포트 생성·텔레그램 발송
- **안전장치**: 킬스위치(`bin/kill.sh`), 발행 큐·멱등키·DLQ, 단계별 재시도(최대 3회, 5→15→45분 백오프)
- **웹 대시보드** (`dashboard/`, SPEC 20장): 오늘 현황·큐/발행 관리·리포트·제어·연동 상태·콘텐츠·광고·설정 8개 화면.
  시스템 전체의 웹 인터페이스. Python 표준 라이브러리만으로 동작한다
  (설정 화면의 YAML 편집에만 `pip install ruamel.yaml` 필요).
  실행: `DASHBOARD_TOKEN=<토큰> python3 dashboard/server.py` → http://127.0.0.1:8787
  자세한 안내는 `docs/dashboard.md` 참조.

## 빠른 시작

```bash
# 1. 클론
git clone https://github.com/This-HW/banmuin.git ai-marketing-agent
cd ai-marketing-agent

# 2. templates/를 복사해서 내 사업 디렉토리 만들기 (slug는 소문자·하이픈 권장)
slug=mycafe
mkdir -p businesses/$slug/pipeline
cp templates/config.yaml businesses/$slug/
cp -r templates/knowledge businesses/$slug/
cp templates/content_calendar.md businesses/$slug/pipeline/
cp templates/secrets.env.example businesses/$slug/secrets.env

# 3. 지식파일 채우기: businesses/$slug/knowledge/00_사업개요.md ~ 10_용어집.md (11종)
#    - 빈 칸을 두지 말 것. 모르는 내용은 비워두고 "미확인"으로 표기. 절대 지어내지 않는다.
#    - 자세한 온보딩 절차는 docs/onboarding.md 참조

# 4. 시크릿 입력: businesses/$slug/secrets.env 에 API 키·토큰 입력 (Git 추적 제외, 절대 커밋 금지)
#    채널·예산·스케줄 조정: businesses/$slug/config.yaml

# 5. 드라이런으로 검증 (발행 제외, 전체 파이프라인 실행)
bin/run.sh --business $slug --dry-run

# 6. 스케줄 등록 — 사용자의 AI 에이전트를 깨우는 4개 트리거 (KST, SPEC 8.1)
#    에이전트가 깨어나면 skills/orchestrator/SKILL.md (3개 루틴 트리거) 또는
#    skills/engagement/SKILL.md (engagement 트리거)의 트리거별 절차를 실행한다.
#    <agent-launcher>는 에이전트 런타임별 기동 방식 (docs/agent-compatibility.md 참조).
30 6 * * *  TZ=Asia/Seoul <agent-launcher> --business mycafe --trigger main
0 9 * * *   TZ=Asia/Seoul <agent-launcher> --business mycafe --trigger naver_publish
0 20 * * 0  TZ=Asia/Seoul <agent-launcher> --business mycafe --trigger weekly_calendar
*/30 * * * * TZ=Asia/Seoul <agent-launcher> --business mycafe --trigger engagement  # §21 댓글→DM
```

`bin/run.sh` 옵션: `--business <slug>` `--date YYYY-MM-DD` `--dry-run` `--stage 수집|분석|제작|검수|발행|보고`

## 리포 구조

```
SPEC.md                  상세 스펙 v1.10.6 (구현의 정본)
README.md                이 문서
ARCHITECTURE.md          모듈·데이터 플로우·상태 모델·멀티사업 설계·설계 원칙
AGENTS.md                이 리포에서 일하는 AI 에이전트용 지침
dashboard/               웹 대시보드 (server.py + static/). 표준 라이브러리만으로 동작
docs/                    거버넌스·호환성·온보딩·대시보드 문서 (agent-compatibility.md 등)
skills/                  스킬 8종. 에이전트가 읽고 실행하는 역할 정의서
playbooks/               Aside용 작업 지시서 3종. 코드가 아닌 Markdown
bin/                     실행 껍데기 6종 (run / retry / kill / resume / dlq / engagement). 상태관리만 담당
templates/               새 사업 시작용 템플릿 (config.yaml, knowledge 11종, 캘린더, secrets 양식)
businesses/<slug>/       사업별 private 데이터. Git 추적 제외 (businesses/example 데모만 커밋)
```

**핵심 원칙**: `businesses/` 안의 사업 데이터·시크릿은 절대 공개 저장소에 올리지 않는다.
`.gitignore`가 `businesses/*`(README·example 제외)와 `**/secrets.env`를 차단한다.

## 요구사항

- **AI 에이전트**: 파일 읽기·셸 실행·API 호출·브라우저 작업 지시가 가능한 에이전트.
  최소 요구사항은 [docs/agent-compatibility.md](docs/agent-compatibility.md) 참조
- **Aside** (`aside exec`): 네이버 블로그 발행·카드뉴스 렌더링용. 설치·세션 연결은 사용자가 담당
- **계정·API**: Meta / Threads / Instagram / YouTube / Higgsfield / Telegram.
  사전 준비물은 SPEC 7.6 체크리스트 참조

## 문서

- `ARCHITECTURE.md` — 모듈·데이터 플로우·상태 모델·멀티사업 설계·설계 원칙
- `AGENTS.md` — 에이전트용 작업 지침 (크로스 에이전트)
- `docs/agent-compatibility.md` — 에이전트 최소 요구사항, 에이전트별 노트, 어댑터 가이드
- `docs/onboarding.md` — 새 사업 온보딩 가이드
- `docs/dashboard.md` — 대시보드 로컬 실행 가이드
- `CONTRIBUTING.md` — 기여 방법
- `SPEC.md` — 전체 상세 스펙 (정본)

## 라이선스

MIT — `LICENSE` 참조.
