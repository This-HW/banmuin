# businesses/

사업별 private 데이터. 사업마다 `<slug>/` 디렉토리 하나씩 둡니다 (멀티사업 지원).

```
businesses/<slug>/
├── config.yaml  사업별 설정
├── secrets.env  API 키·토큰 (Git 제외)
├── knowledge/   사업 정본 지식 11종
├── content_calendar.md
├── state/       queue.jsonl, dead_letter.jsonl, KILL
├── drafts/      게이트 미통과 초안 보관소
├── logs/        실행 로그
├── reports/     리포트
└── assets/      생성 이미지·영상
```

- **읽고 쓰는 이**: AI 에이전트 (실행 주체) + 사업주 (지식파일·설정 관리)
- **Git 추적 제외**: `businesses/*`는 커밋되지 않습니다
  (예외: 이 README.md와 `example/` 데모). `.gitignore` 참조.
- **규칙**: 사업 간 디렉토리를 서로 읽지 마세요 (데이터 격리).
  새 사업 추가는 `docs/onboarding.md` 2장의 절차를 따르세요.
