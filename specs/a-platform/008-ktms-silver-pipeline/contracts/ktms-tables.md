# 계약: K-TMS Iceberg 테이블 읽는 법

대상: `tms_silver2.ktms`(Silver), `tms_silver2.ktms_ml_ready`(ML-ready). 컬럼은 [data-model.md](../data-model.md) §2·§3에 있다.
읽는 사람: E(학습), D(분석), C(검증).

## 1. 원칙

- **카탈로그로 읽는다.** S3 경로의 Parquet 파일을 직접 읽지 않는다.
  - `data/` 폴더에는 지난 버전의 파일도 남아 있어, 직접 읽으면 같은 행이 여러 번 나온다.
  - 어떤 파일이 현재 버전인지는 `metadata/`가 정한다.
- **쓰기는 이 파이프라인만 한다.** 다른 사람은 읽기만 한다.
- **학습에 쓴 데이터는 `snapshot_id`로 고정한다.** 학습 기록에 테이블 이름과 `snapshot_id`를 남긴다.

## 2. 최신본 읽기

Athena (워크그룹 `tms-eda`):

```sql
SELECT * FROM tms_silver2.ktms_ml_ready
WHERE measured_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND classification_eligible;
```

Spark (Glue 5.0 등, Iceberg 카탈로그 `glue_catalog` 설정 필요):

```python
df = spark.table("glue_catalog.tms_silver2.ktms_ml_ready")
```

pandas (awswrangler):

```python
import awswrangler as wr
df = wr.athena.read_sql_query("SELECT * FROM ktms_ml_ready", database="tms_silver2", workgroup="tms-eda")
```

## 3. 버전 번호 확인과 그 버전 읽기

```sql
-- 최근 버전 (committed_at은 UTC)
SELECT snapshot_id, committed_at, summary['job_run_id'] AS job_run_id
FROM "tms_silver2"."ktms_ml_ready$snapshots"
ORDER BY committed_at DESC LIMIT 5;

-- 그 버전 그대로 읽기
SELECT * FROM tms_silver2.ktms_ml_ready FOR VERSION AS OF 1234567890123456789;
```

```python
spark.read.option("snapshot-id", 1234567890123456789).table("glue_catalog.tms_silver2.ktms_ml_ready")
```

- 같은 `snapshot_id`로 읽으면 이후 갱신과 관계없이 같은 행과 값이 나온다(SC-005).
- 오래된 버전 정리를 하기 전까지 모든 버전이 남아 있다. 정리 규칙을 정하면 이 문서에 보존 기간을 적는다.

## 3-1. 계약 검사를 통과한 버전 읽기 (spec 010)

매일 갱신 뒤 계약 검사가 같은 범위를 검사하고 결과를 `silver2/_runs/ktms_ml_ready_check/`에 남긴다. 검사는 갱신이 커밋된 **뒤**에 돌아 위반 데이터를 되돌리지 않는다. 그래서 학습은 **마지막으로 통과한 `snapshot_id`**로 고정한다.

```bash
# 가장 최근 통과 기록 (파일 이름이 시작 시각순)
aws s3 ls s3://smokestack-tms-raw-952900391026/silver2/_runs/ktms_ml_ready_check/ | tail -5
aws s3 cp s3://smokestack-tms-raw-952900391026/silver2/_runs/ktms_ml_ready_check/<파일>.json - \
  | python -c "import json,sys; r=json.load(sys.stdin); print(r['result'], r['range'], r['snapshot_id'])"
```

- `result`가 `passed`인 가장 최근 기록의 `snapshot_id`를 §3의 방법으로 읽는다.
- `violation`이면 그 기록의 `violations`에 무엇이 어긋났는지 있다. 그 버전으로 학습하지 않고 A에게 알린다.
- 학습 기록에 테이블 이름, `snapshot_id`, 검사 기록 파일 이름을 함께 남긴다.

## 4. 갱신 규칙 (읽는 쪽이 알아야 할 것)

- **갱신 시각**: 매일 03:00 KST에 시작해 수 분 안에 끝난다. 끝난 시각은 `$snapshots`의 `committed_at`으로 알 수 있다.
- **바뀌는 범위**: 끝난 최근 2일(KST)만 다시 쓴다. 그보다 오래된 날짜는 사람이 범위를 지정해 다시 실행할 때만 바뀐다.
- **오늘 날짜**: 진행 중인 오늘(KST)은 테이블에 없다.
- **라벨이 비는 칸**: 어제 마지막 1시간의 라벨은 비어 있을 수 있다(`*_eligible = false`). 다음 날 갱신에서 채워진다. 학습에는 `*_eligible`로 거른 행만 쓴다.
- **도중에 읽어도 안전함**: 갱신 중에 읽으면 직전 버전이 보인다.

## 5. 대만 테이블과 함께 쓸 때

- `tms_silver2.tw_cems_ml_ready`와 컬럼 이름·순서·타입이 같다. 합치기만 하면 된다(합본 테이블은 만들지 않음).
- `stack_code` 형식이 다르다. K-TMS는 `시도|사업장|굴뚝`이고, 대만은 대만 ID다. 출처를 구분하려면 합칠 때 출처 컬럼을 붙인다.
- `measured_at`은 각 출처의 현지 벽시계 시각이다(K-TMS는 KST, 대만은 대만 시각).
- 단위: K-TMS의 NOx·SOx는 ppm으로 본다. 산소 보정은 하지 않는다.

## 6. 바뀔 수 있는 것

- 합성 테이블(`ktms_synthetic*`)은 B의 생성기에 따라 이름·구조가 정해진다. 생기면 이 문서에 추가한다.
- 컬럼 의미가 바뀌면 C의 PR과 `feature_version`, `label_version`, `quality_policy_version` 값으로 알린다.
- **`data_source` 컬럼 (C #48):** 머지와 재배포 뒤 ML-ready 맨 끝에 붙는다(`ktms`, 합성은 `ktms_synth`). 테이블을 합칠 때 출처 구분에 쓴다. 다시 계산하기 전 행은 null이다. 컬럼 추가 전 버전(`snapshot_id`)도 같은 행으로 읽히고, 이 컬럼은 null로 나온다(Spark 확인. 도구에 따라 컬럼 자체가 없게 보일 수 있다).

## 6. 학습용 합성 테이블 (spec 011)

- `tms_silver2.ktms_synth`(Silver), `tms_silver2.ktms_synth_ml_ready`(ML-ready). 실측과 같은 잡·같은 Iceberg 형식·같은 36컬럼이고 `data_source = 'ktms_synth'`다.
- 원본은 `tms_synthetic_train/`(B의 생성기, 30분마다). 굴뚝 코드는 `SYN-T-<시작날짜>-<성분>-<모양>-<번호>`라 실측과 겹치지 않는다(계약 검사가 매일 확인).
- **학습**: 실측과 합쳐 쓴다. 각 테이블의 마지막 통과 `snapshot_id`(§3-1, 합성은 `silver2/_runs/ktms_ml_ready_check/`에서 `table`이 `ktms_synth_ml_ready`인 기록)를 함께 학습 기록에 남긴다.

```sql
SELECT * FROM tms_silver2.ktms_ml_ready FOR VERSION AS OF <실측 통과 스냅샷>
UNION ALL
SELECT * FROM tms_silver2.ktms_synth_ml_ready FOR VERSION AS OF <합성 통과 스냅샷>
```

- **검증·평가**: 합성을 넣지 않는다(`WHERE data_source <> 'ktms_synth'`). 실측만으로 평가해야 같은 조건의 비교가 된다(원칙 V).
- **외부 검증 기간**: 합성 곡선은 실측 참조 통계(현재 `ref-1030-1110`, 2026-10-30 ~ 11-10)를 빌려 만든다. 외부 검증은 이 기간 **이후**(11-11~)로 잡는다. 통계 버전이 바뀌면 이 기간도 바뀐다.
- **양성·음성 비율 확인**: Athena 저장된 쿼리 `tms_label_balance_*`(워크그룹 `tms-eda`, 원문 `scripts/label_balance_queries.sql`)에서 출처별·합친 비율, 모양별 합성 양성, 날짜별 추이를 본다.

