# docs/dashboard.md — 대시보드 로컬 실행 가이드

> 웹 대시보드(`dashboard/`)를 내 머신에서 직접 실행하는 방법이다.
> 대시보드는 시스템 전체의 웹 인터페이스(컨트롤 플레인)이며, SPEC 20장의 레퍼런스 구현이다.
> 새로운 실행 로직을 만들지 않는다. 모든 제어 연산의 효과는 대응하는 `bin/*.sh`와 동일해야 한다.

## 요구사항

- Python 3.8+ (표준 라이브러리만 사용)
- (선택) `pip install ruamel.yaml` — 설정 화면의 YAML 편집에만 필요. 없으면 조회는 정상 동작하고 설정 저장 API만 실패한다.

## 실행

```bash
cd ai-marketing-agent

# Bearer 토큰은 필수. 안전한 랜덤 문자열을 직접 만든다.
export DASHBOARD_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"

python3 dashboard/server.py
# → [dashboard] http://127.0.0.1:8787 (repo: /path/to/ai-marketing-agent)
```

브라우저에서 http://127.0.0.1:8787 을 열고, 위 토큰을 입력한다.
토큰은 브라우저 세션 스토리지에 저장되며 서버에는 평문으로 보관되지 않는다.
(탭을 닫으면 토큰이 지워진다.)

환경변수:

| 변수 | 기본값 | 설명 |
|---|---|---|
| `DASHBOARD_TOKEN` | (필수) | Bearer 토큰. 없으면 서버가 시작을 거부한다 |
| `DASHBOARD_PORT` | `8787` | 리스닝 포트 |
| `DASHBOARD_REPO_ROOT` | 스크립트의 상위 디렉토리 | 저장소 루트. 보통 설정 불필요 |

## 화면 8종 (SPA, 상단 탭으로 전환)

1. 오늘 현황 — 오늘의 큐·발행·실패 현황
2. 큐·발행 관리 — 발행 큐 조회, 승인/승인취소, DLQ 복구
3. 리포트 — 일간/주간 리포트 조회
4. 제어 — 킬스위치 발동/해제, 단계 재실행
5. 연동 상태 — 채널별 연결 상태, 토큰 저장 위자드
6. 콘텐츠 — 초안 목록, 게이트 통과/미통과 확인
7. 설정 — 사업별 `config.yaml` 편집 (ruamel.yaml 필요)
8. 광고 — 광고 초안 목록, 건별 승인/반려

## 토큰 저장 (write-only)

연동 상태 화면의 위자드에서 API 토큰을 저장할 수 있다.
저장된 토큰은 `businesses/<slug>/secrets.env`에 추가되며,
**어떤 API로도 읽기를 제공하지 않는다** (SPEC 20.10).
서버 로그·화면·API 응답에 토큰 값이 노출되지 않는다.

## 보안 주의

- 대시보드는 로컬 전용으로 설계됐다. 인터넷에 직접 노출하지 않는다.
  외부에서 접근해야 하면 Tailscale·VPN 등 사설 네트워크 경유를 권장한다.
- `DASHBOARD_TOKEN`은 안전한 저장소에 보관하고, 주기적으로 교체한다.

## 문제 해결

- `저장소를 찾을 수 없습니다` — `DASHBOARD_REPO_ROOT`가 잘못됐거나, 저장소가 아닌 곳에서 실행 중이다.
  저장소 루트에서 실행하거나 환경변수로 루트를 지정한다.
- 설정 저장이 실패한다 — `pip install ruamel.yaml` 후 재시작한다.
- 포트가 이미 사용 중이다 — `DASHBOARD_PORT=8788` 등으로 변경한다.
