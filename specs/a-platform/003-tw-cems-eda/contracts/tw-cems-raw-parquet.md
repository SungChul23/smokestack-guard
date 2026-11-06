# 계약: EDA 테이블 `tms_eda.tw_cems_raw`

- **소유**: A · **소비자**: C(Silver 계약 확정용 EDA), E(EDA)
- **용도**: Athena EDA 전용. **Silver·ML 파이프라인의 입력이 아니다.** Silver는 원본 JSONL을 직접 읽는다.

## 위치

```
s3://smokestack-tms-eda-952900391026/tw_cems_raw/year=YYYY/month=MM/
├── part-00000-….snappy.parquet
├── part-00001-….snappy.parquet
└── _SUCCESS            # Spark 완료 표지 (빈 파일)
```

- 월마다 원본 파일 하나가 파티션 하나에 대응한다. 대상은 2024-01~2026-10이다(2026-11-06 변경, 이전 2024-11~).
- 같은 월을 다시 변환하면 그 월 폴더 전체가 교체된다. 다른 월에는 영향이 없다.

## 스키마

- **고정 스키마가 없다.** 컬럼은 그 달 원본에 나온 키의 합집합이다. 크롤러가 모든 달을 합쳐 테이블 하나로 등록한다.
- 그 달에 없는 키의 값은 `NULL`이다.
- **모든 원본 값은 문자열이다.** 숫자도 원문 그대로 둔다(예: `"12.30"`, `"nan"`, `""`). 해석과 정제는 하지 않는다.
- 추가 컬럼:
  - `source_file` (string): 원본 파일의 전체 S3 경로
  - `_corrupt_record` (string): JSON으로 읽을 수 없는 줄의 원문. 그 달에 손상 줄이 있을 때만 값이 있다
- 파티션: `year` (string, `'2025'`), `month` (string, 두 자리 `'03'`)
- Athena에서 컬럼 이름은 소문자다. `_`로 시작하는 컬럼은 큰따옴표로 감싼다: `"_id"`, `"_corrupt_record"`.

2024-03 원본 기준 키(다른 달은 미확인): `ImportDate`, `_id`, `abbr`, `cno`, `code2`, `code2desc`, `epb_county`, `itemdesc`, `m_time`, `item`, `m_value`, `std`, `polno`, `std_s`, `unit`

## 보장

1. 손상된 줄도 버리지 않고 한 행으로 남긴다. 그래서 월별 행 수는 원본의 **비어 있지 않은 줄 수**와 같다고 본다. 이 일치는 표본 1~2개월만 직접 확인했으므로, 의심되면 그 월을 다시 센다.
2. 원본에 나온 모든 키가 컬럼으로 있다.
3. 값은 원본 문자열과 같다. 행을 거르지 않는다.
4. `_SUCCESS`가 있는 월은 쓰기가 끝까지 성공한 월이다.

## 조회 예

```sql
-- 반드시 파티션 조건을 붙인다 (워크그룹 tms-eda, 쿼리당 10GB 한도)
SELECT item, code2, count(*) AS n
FROM tms_eda.tw_cems_raw
WHERE year = '2025' AND month = '03'
GROUP BY 1, 2 ORDER BY n DESC;

-- 숫자 계산은 실패 시 NULL이 되는 변환으로
SELECT avg(try_cast(m_value AS double))
FROM tms_eda.tw_cems_raw
WHERE year = '2025' AND month = '03' AND item = '923';
```

## 변경 규칙

- 위치, 파티션, 추가 컬럼 이름, 보장을 바꾸면 이 문서를 고치고 C·E에게 PR로 알린다(원칙 IV).
