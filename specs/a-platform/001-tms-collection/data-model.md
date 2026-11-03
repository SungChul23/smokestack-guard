# Data Model: TMS 원본 수집 인프라

시각은 모두 UTC ISO 8601(초 단위)이다. 단, API 응답 안의 `mesure_dt`는 한국 시각 `YYYY-MM-DD HH:MM`이다.

## 회차 (run_ts)

| 필드 | 설명 |
|---|---|
| `run_ts` | Scheduler 예정 시각을 10분 단위로 내린 UTC 시각. 콘솔 테스트처럼 `time`이 없으면 현재 시각 사용 |

- 저장 경로와 재시도 중복 방지의 기준이다.
- 한국 시각 14:10 실행 → `run_ts=...T051000Z`, `hour=05`

## 스냅샷 (`snapshot.json.gz`)

- API 응답 바이트를 그대로 gzip(`mtime=0`)한 것. 같은 응답은 같은 압축 결과가 나온다.
- 구조(API 원문): `response.header{resultCode, resultMsg, totalCount}`, `response.body.items[]`
- 항목 주요 필드: `fact_manage_nm`(사업장), `stack_code`(배출구), `area_nm`, `mesure_dt`, `*_mesure_value`, `*_exhst_perm_stdr_value`
- **주의**: 측정값 필드는 숫자 문자열 외에 `"측정자료확인중(가동중지)"` 같은 상태 문자열이나 `null`이 올 수 있다. 해석은 Silver(C)의 몫이다.
- 한 번 쓰면 바꾸지 않는다. 같은 `run_ts`로 재실행되면 같은 키에 같은 내용이 다시 쓰일 수 있다(버전 관리로 이전 버전 유지).

## 메타 (`snapshot.meta.json`)

스키마: [contracts/snapshot-meta.schema.json](contracts/snapshot-meta.schema.json)

| 필드 | 설명 |
|---|---|
| `source` | `data.go.kr/B552584/cleansys/rltmMesureResult` |
| `run_ts` | 회차 시각 |
| `requested_at` | 첫 요청 시각 |
| `saved_at` | 메타 저장 시각 |
| `status_code` | HTTP 상태 |
| `elapsed_ms` | 성공한 시도의 소요 시간 |
| `attempts` | 시도 횟수(1–3) |
| `raw_bytes`, `gz_bytes` | 원문·압축 크기 |
| `sha256_raw` | 원문 바이트 SHA-256 |
| `raw_key` | 스냅샷 S3 키 |
| `inspect` | `{ok, result_code, total_count, item_count, reason}` 또는 구조 오류 시 `{ok:false, reason}` |

## 상태 (`_state/latest.json`)

스키마: [contracts/state.schema.json](contracts/state.schema.json). 버킷 전체에 하나.

| 필드 | 설명 |
|---|---|
| `sha256_raw` | 마지막으로 **정상 저장된** 원문의 해시 |
| `last_changed_at` | 마지막으로 원문이 바뀐 회차 |
| `last_checked_at` | 마지막으로 실행된 회차(매 실행 갱신) |
| `raw_key` | 마지막 원문 키 |

### 상태 전이

```text
실행 시작
 ├─ 해시 == state.sha256_raw ─▶ last_checked_at만 갱신 ─▶ 성공 (changed=false)
 └─ 해시 != (또는 상태 없음)
      ├─ 원문·메타 저장
      ├─ 점검 실패 ─▶ 상태 그대로 ─▶ 예외 (Errors +1)
      └─ 점검 성공 ─▶ 상태 전체 갱신 ─▶ 성공 (changed=true)
API 호출 실패(재시도 후) ─▶ 아무것도 쓰지 않음 ─▶ 예외 (Errors +1)
```

### 판단 기준

| `last_checked_at` | `last_changed_at` | 의미 |
|---|---|---|
| 최근 10분 이내 | 최근 30분 이내 | 정상 |
| 최근 10분 이내 | 오래됨 | 수집은 정상, API 갱신 없음 |
| 10분 넘게 멈춤 | — | 수집 중단 또는 연속 실패 |
