# specs/

기능별 spec·plan·tasks를 두는 폴더다. 작업 절차는 저장소 루트 `AGENTS.md`의 "Spec Kit 작업 절차"를 따른다.

## 역할 폴더와 번호 대역

| 담당 | 역할 | 폴더 | 대역 |
|---|---|---|---|
| A | 플랫폼·AWS·통합 | [`a-platform/`](a-platform/) | 001–100 |
| B | 수집·Bronze (+Kafka) | [`b-collection/`](b-collection/) | 101–200 |
| C | 데이터 계약·Silver·Iceberg | [`c-contract/`](c-contract/) | 201–300 |
| D | 분석·화면·RAG | [`d-analytics/`](d-analytics/) | 301–400 |
| E | 판정·AI 경고·MLOps | [`e-ml/`](e-ml/) | 401–500 |

```
specs/
├── a-platform/
│   └── 001-tms-collection/
│       ├── spec.md
│       ├── plan.md
│       └── tasks.md
└── e-ml/
    └── 401-ml-data-readiness/
```

- 자기 역할 폴더 안에만 spec을 만든다.
- 폴더 이름: `<세 자리 번호>-<짧은-이름>` (예: `b-collection/101-daily-gap-check`)
- 자기 폴더 안에서 가장 큰 번호의 다음 번호를 쓴다. 대역의 마지막 번호(`100`, `200`, …)도 그 담당의 번호다.
- AI 에이전트에게 맡길 때는 담당을 알려준다. 예: `/speckit-specify (담당 B) 전날 수집 누락을 아침에 확인하고 싶다`
