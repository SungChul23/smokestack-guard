# 테스트 fixture (가짜 데이터)

이 폴더의 JSONL은 **모두 가짜 데이터**다. 실제 원본(`bronze/tw_cems/historical/`) 값을 복사하지 않았다.
키 15개는 실제 원본과 같지만 사업장·지역·설명은 `가짜…`로 채웠다.

| 파일 | 줄 수 | 용도 |
|---|---|---|
| `synthetic_2025_10.jsonl` | 9 | 정상 달. `status` 5종(`ok`, `not_monitored`, `other_code`, `partial`, `invalid`)이 한 번씩 나온다. `m_time`에 `T`·공백 구분이 섞여 있다 |
| `synthetic_2025_10_mixed.jsonl` | 10 | 위 9줄 + `m_time = 2025-09-30T23:45:00` 1줄. 다른 달 행이 섞인 경우 |
| `synthetic_2025_09.jsonl` | 2 | 9월. 기존 다른 달 파티션 역할 |
