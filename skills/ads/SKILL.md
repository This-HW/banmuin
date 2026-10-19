---
name: ads
description: 광고운영. Meta 광고 성과를 조회·분석하고 캠페인 초안을 생성하며, 상품 구성·객단가 설계도 지원한다. 기본값은 읽기+초안만. 광고 집행은 config `channels.meta_ads.mode=auto` 명시적 opt-in에서만 가능.
---

# Ads (광고운영)

## 역할
상품 구성·객단가 설계 지원 (4주차 상품기획자 역할 포함) + Meta 광고 운영·분석.
Meta MCP를 통해 광고 계정을 다룬다.

## 입력
- 성과 조회 요청 (기간 지정)
- 캠페인 생성 요청 (상품, 타겟, 소재 지정)
- 상품 기획 요청 (상품 구성·객단가 설계)

## 출력 (산출물 경로)
- 아침 리포트 내 광고 섹션 (`businesses/<slug>/reports/daily/YYYY-MM-DD.md`의 일부)
  - 지표 표 (ROAS, CTR, CPC, CPM, 학습 단계) + 해석
- 캠페인 초안 (Meta 광고 계정에 **일시정지 상태로 생성 시도**)

## 핵심 규칙
1. **광고 집행·예산 변경은 `businesses/<slug>/config.yaml`의 `channels.meta_ads.mode`가
   `approval` 또는 `auto`일 때만 가능하다 (대표의 명시적 opt-in, 11.3 #3).**
   기본값 `draft_only`(키 누락 포함)에서는 성과 읽기 + 캠페인 초안 생성만 하고,
   집행·예산 변경은 절대 금지한다.
   - `approval` (건별 승인, v1.10.6): 캠페인을 **일시정지 상태로 생성**한 뒤
     `businesses/<slug>/state/ad_drafts.jsonl`에 초안을 기록한다
     (`id`, `campaign_name`, `meta_campaign_id`, `daily_budget_krw`,
     `status=draft`, `created_at`). 대시보드에서 승인(`status=approved`,
     `approved_at` 기록)된 건만 다음 실행 시 Meta에서 활성화한다.
     반려(`status=rejected`)된 건은 Meta 캠페인을 삭제한다.
   - `auto`: 아래 조건을 모두 충족하면 자동 집행한다:
   ① `budgets.meta_daily_cap_krw` 일예산 캡 준수 ② `08_승인기준.md` 임계값 준수
   ③ 집행 전후 `businesses/<slug>/logs/`에 기록 ④ 첫 집행은 소액 파일럿 권장
   ⑤ 집행 후 24시간 내 성과 모니터링 (급격한 지표 악화 시 즉시 일시정지 후 대표 보고).
   또한 사업 단계가 `사전예약중` 이하이면 규칙 9의 단계 규칙이 우선해 집행하지 않는다.
   `draft_only`에서 집행을 시도하면 즉시 중단하고 대표에게 알린다.
2. **일시정지 생성 [미검증] 대응 절차:** Meta 공식 문서에 "새 캠페인 기본 PAUSED 생성"이
   확인되지 않았으므로, 캠페인 생성 후 반드시 상태를 조회한다.
   상태가 `active`이면 즉시 일시정지(`paused`)로 전환하고,
   전환 결과를 로그에 기록한다.
3. **캠페인 명명 규칙:** `[YYYYMMDD]_[상품약칭]_[타겟]_[소재버전]`
   (예: `[20260929]_PT_3040남_v1` — 실제 값은 지식파일에서 가져온다)
4. **지표 정의:** ROAS (광고수익률), CTR (클릭률), CPC (클릭당 비용),
   CPM (노출 1,000회당 비용), 학습 단계 (Learning / Learning Limited / Active).
   해석 시 학습 단계와 어트리뷰션 지연을 함께 고지한다.
5. **어트리뷰션 지연 고지:** 당일 수치는 확정치가 아니므로 리포트에 명시한다.
6. **광고 소재 핸드오프:** 광고 소재는 content 파이프라인 산출물 중
   `businesses/<slug>/knowledge/07_채널전략.md`에서 광고용으로 지정한 것을 사용한다.
   content 스킬이 만들지 않은 소재를 임의로 쓰지 않는다.
7. **Meta MCP** (`https://mcp.facebook.com/ads`, OAuth)를 사용한다.
   인증 만료 시 재연결 안내를 오케스트레이터 경유로 알린다.
8. **예산 캡 준수:** `businesses/<slug>/knowledge/08_승인기준.md`의 일예산 캡을 초과하는 초안은 만들지 않는다.
9. **사업 단계별 활성화** (`businesses/<slug>/knowledge/00_사업개요.md`의 `사업 단계` 기준):
   - `아이디어` / `준비중`: 비활성. 성과 조회·캠페인 초안 생성을 모두 중단한다.
   - `사전예약중`: 인지도·사전예약 목적의 캠페인 초안만 생성한다. `channels.meta_ads.mode=auto`라도 단계 규칙이 우선해 집행은 금지한다.
   - `운영중`: 기존 규칙(1–8)을 적용한다.

## 참조 파일
- `businesses/<slug>/knowledge/01_상품서비스.md` — 상품·가격·구성
- `businesses/<slug>/knowledge/02_가격정책.md` — 할인·환불 정책 (객단가 설계 시)
- `businesses/<slug>/knowledge/07_채널전략.md` — 광고용 소재 지정
- `businesses/<slug>/knowledge/08_승인기준.md` — 예산 캡 (정본)
- `SPEC.md` 7.5 (Meta Ads), 11장 (가드레일)

## 실패 시 처리
| 실패 | 처리 |
|---|---|
| Meta MCP 인증 만료 | 성과 조회 중단, 재연결 안내를 텔레그램으로 알림 (오케스트레이터 경유) |
| 캠페인 생성 실패 | 3회 재시도 후 DLQ에 기록, 오케스트레이터에 보고 |
| 생성 후 상태 조회 실패 | 캠페인을 만진 것으로 간주하지 않고 DLQ에 기록 + 알림 (active 방치 방지) |
| 예산 캡 초과 초안 요청 | 생성하지 않고 요청자에게 반려 사유 반환 |
