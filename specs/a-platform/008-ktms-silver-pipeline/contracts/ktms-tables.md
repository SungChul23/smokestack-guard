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
