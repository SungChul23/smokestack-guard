# Contract: K-TMS Bronze 스냅샷 폴더 (읽는 쪽용)

대상: K-TMS Silver(C, `src/smokestack_guard/silver/ktms.py`), 누락률 리포트(`services/tms-missing-rate`), 그 밖에 `tms_cleansys/`를 읽는 모든 코드.

## 읽는 규칙

1. **`_SUCCESS`가 있는 `run_ts` 폴더만 완성된 스냅샷이다.** 없는 폴더(저장 중, 업로드 실패, 원문 점검 실패)는 읽지 않는다.
2. 완성된 폴더의 파일은 바뀌지 않는다. 한 번 읽은 결과를 캐시해도 된다.
3. 파일이 온전한지 다시 확인하려면 `manifest.json`의 `files[].sha256`을 저장된 바이트와 비교한다.
4. 원문 내용의 기준은 지금과 같다: `snapshot.json.gz`를 풀면 API 응답 JSON.
5. 폴더 안에 모르는 파일이 있어도 무시한다(앞으로 파일이 늘 수 있다).

## 적용 시점

| 기간 | 표지 |
|---|---|
| 배포 이후 | 수집 Lambda가 저장할 때 붙인다 (`backfilled: false`) |
| 배포 이전 (2026-10-30 ~ 배포 시각) | 백필로 붙인다 (`backfilled: true`). 검증에 실패한 폴더에는 붙이지 않는다 |

백필이 끝나기 전에 읽는 쪽을 "`_SUCCESS`만"으로 바꾸면 과거 폴더가 빠진다. 읽는 쪽 변경은 백필 결과를 공유받은 뒤에 한다.

## 바뀌지 않는 것

- 폴더 경로 규칙, 원문·메타 파일 이름과 내용
- 상태 파일 `_state/latest.json`의 필드와 의미 (마지막 저장 원문을 가리킨다)
