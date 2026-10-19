# D+7 재구매 메시지 트리거 설계안

> 상태: **구현됨 (A안 수동 CSV)** — 2026-10-04, HW 승인 "남은것들 전부 다 구현 먼저 하자".
> 구현 내용: `templates/config.yaml`에 `repurchase.order_source: manual_csv` 추가,
> `skills/customer-care/SKILL.md` 규칙 7에 D+7 구체 절차(수집 편입·대상 선정·초안·멱등·실패 처리) 반영,
> `templates/data/orders.csv` 헤더 템플릿 추가. SPEC 5.6·11.3 #5·18 #6·19 반영, v1.10.4.
> 아래는 설계 기록으로 유지한다.
> 관련: `SPEC.md` 5.6·8.1·8.2·11.3, `skills/customer-care/SKILL.md` 규칙 7, `repurchase.d7_channel`.

## 1. 현재 상태 (2026-10-04 구현 완료)

- `repurchase.d7_channel` 기본값 `null` → D+7 비활성. fail-closed 동작은 검증됨 (null·키 누락 시 미수행).
- 채널 지정 시 customer-care 스킬이 초안 생성까지만 수행, 실제 발송은 채널 연동 후 별도 승인.
- 주문 데이터: `businesses/<slug>/data/orders.csv` 수동 입력 (`order_source: manual_csv`, 템플릿 `templates/data/orders.csv`).
  매일 루틴 수집 단계(06:40)에 편입 — 구매일 == 오늘-7일 · 수신 동의(Y) · 미발송 건만 대상으로 초안 생성.
  발송 기록은 `state/d7_sent.jsonl` (멱등).

## 2. 주문 데이터 입력 방식 (결정 필요)

| 안 | 방식 | 장점 | 단점 |
|---|---|---|---|
| A | 수동 CSV (`businesses/<slug>/data/orders.csv`, 대표가 직접 입력) | 지금 바로 가능. 실사업 없어도 메커니즘 검증 가능 | 대표가 직접 입력해야 함 |
| B | 스마트스토어 API 연동 | 자동화 | 실사업·API 키 필요. 지금은 불가 |
| C | 외부 웹훅/주문 폼 | 자동화 | 인프라 필요. 지금은 불가 |

**권장: A로 시작.** 주문 소스를 추상화(`repurchase.order_source: manual_csv | smartstore_api`)해 두면
B/C는 나중에 어댑터만 교체하면 된다. 지금은 A만 구현한다.

## 3. 데이터 계약

### 3.1 `businesses/<slug>/data/orders.csv` (Git 추적 제외 — 사업 데이터)

```csv
order_id,customer_ref,product_name,purchased_at,consent_marketing
20261001-001,cust_a1b2,시그니처 라떼 500ml,2026-10-01T14:30:00+09:00,Y
```

- `customer_ref`: 익명 고객 ID. **실명·연락처를 이 파일에 넣지 않는다** (AGENTS.md 규칙).
- `consent_marketing`: 마케팅 수신 동의 여부 (Y/N). N이면 D+7 대상에서 제외 — 정보통신망법상 사전 동의 없는 영리 목적 전송은 불법이므로.
- `purchased_at`: ISO 8601 + KST.

### 3.2 연락처 매핑 (별도 private 저장)

실제 발송(sms/alimtalk/dm)에 필요한 연락처는 `businesses/<slug>/data/contacts.json` (Git 제외,
`customer_ref` → 연락처)에 둔다. 주문 CSV와 분리해 유출 범위를 최소화한다. 키는 Secure Vault 또는
`secrets.env` 경유를 권장.

## 4. 트리거 흐름

메인 루틴(06:30)의 **06:40 수집 단계**에 편입한다 (customer-care가 이미 미답변 문의를 처리하는 단계).

1. `repurchase.d7_channel`이 `null`이거나 키 누락 → **스킵** (fail-closed, 현행 유지).
2. `data/orders.csv` 읽기. `purchased_at`의 날짜 == 오늘 - 7일인 주문 추출.
3. `consent_marketing != Y` 제외. `state/d7_sent.jsonl`에 `order_id`가 이미 있으면 제외 (멱등).
4. 대상 건을 customer-care 스킬에 전달 → 메시지 초안 생성 (`drafts/YYYY-MM-DD/d7_*.md`).
   - 브랜드보이스(06) 준수, 개인정보 익명화, FAQ 근거 규칙은 문의 답변에만 적용.
5. 발송: 채널 연동(발신번호 등록 등) 완료 + 대표 별도 승인 후에만. 그 전까지 초안만 둔다.
6. 발송 성공 시 `state/d7_sent.jsonl`에 `{"order_id","sent_at","channel"}` append.

### 실패 시 처리

- CSV 파싱 실패 → 해당 단계만 실패로 기록하고 다음 단계 진행 (비치명), 리포트에 명시.
- 발송 API 실패 → 3회 재시도(5→15→45분) 후 DLQ. `d7_sent.jsonl`에는 성공 건만 기록 (재발송 허용).

## 5. 설정 추가안 (구현 시)

```yaml
repurchase:
  d7_channel: null                # 현행 유지 (null | sms | alimtalk | dm)
  order_source: manual_csv        # manual_csv | smartstore_api (향후)
```

- `order_source`가 `smartstore_api`인데 키가 없으면 fail-closed로 스킵하고 알림.

## 6. 검증 계획

1. 가상 주문 CSV 1건 입력 (구매일을 오늘-7일로) → 드라이런 → 초안 생성 확인 → 발송 안 함.
2. `d7_sent.jsonl` 멱등 확인 (같은 주문에 중복 초안/발송 없음).
3. `d7_channel: null` → 전체 스킵 확인 (기존 검증과 동일).
4. 실제 발송은 채널 연동 + 대표 승인 후 별도 검증.

## 7. 대표 결정 요청

1. 주문 데이터 입력 방식: **A(수동 CSV)** 로 시작하는가?
2. 위 설계대로 구현 착수해도 되는가? (구현 시 SPEC 5.6·8.2·11.3·18·19 및 customer-care SKILL에 반영)
