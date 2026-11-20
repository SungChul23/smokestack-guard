# Contract: 학습 스냅샷 알림 (Lambda 입력·메일 형식)

## 1. Lambda 입력

```json
{}                                  // 정기(05:00 KST): 오늘 기준
{"as_of": "2026-11-22"}             // 손으로 다시 보낼 때: 그날 기준
{"as_of": "2026-11-22", "dry_run": true}   // 발행하지 않고 본문만 돌려줌
```

응답: `{"subject": "...", "body": "...", "sources": {"ktms": [...], "ktms_synth": [...]}, "published": true}`

## 2. 출처

학습 첫날은 실측·합성 모두 10/31이다(실측 10/30은 16:30부터라 하루치가 아님, 2026-11-20 결정). Silver 표에는 10/30도 있다.

| 출처 | Silver 표 | ML-ready 표 | 첫날 |
|---|---|---|---|
| 실측 `ktms` | `tms_silver2.ktms` | `tms_silver2.ktms_ml_ready` | 2026-10-31 |
| 합성 `ktms_synth` | `tms_silver2.ktms_synth` | `tms_silver2.ktms_synth_ml_ready` | 2026-10-31 |

## 3. 메일

```
제목: [tms] 학습 스냅샷 2026-11-22 · 실측 확정 ~11-20 · 합성 확정 ~11-20

계약 검사를 통과한 스냅샷입니다. 학습은 맨 위(최신)를 쓰세요. 확정 범위는 첫날 ~ 실행일-2일입니다.

■ 실측 K-TMS (tms_silver2.ktms / ktms_ml_ready)
  [최신] 11-22 실행 · 확정 10-31 ~ 11-20
         Silver   5531201988374615123
         ML-ready 8812001733456129001
  11-21 실행 · 확정 10-31 ~ 11-19
         Silver   ...   ML-ready ...
  11-20 실행 · ...

■ 합성 K-TMS v2 (tms_silver2.ktms_synth / ktms_synth_ml_ready) — 학습(Train)에만
  [최신] 11-22 실행 · 확정 10-31 ~ 11-20
         Silver   ...
         ML-ready ...
  ...

읽기 예시 (Athena · awswrangler)
  SELECT * FROM tms_silver2.ktms_ml_ready FOR VERSION AS OF 8812001733456129001 WHERE measured_at >= TIMESTAMP '2026-10-31 00:00:00' AND measured_at < TIMESTAMP '2026-11-21 00:00:00'
  SELECT * FROM tms_silver2.ktms_synth_ml_ready FOR VERSION AS OF <합성 ML-ready> WHERE measured_at >= TIMESTAMP '2026-10-31 00:00:00' AND measured_at < TIMESTAMP '2026-11-21 00:00:00'

자세히: specs/a-platform/008-ktms-silver-pipeline/contracts/ktms-tables.md
```

- 그날 통과한 실행이 없으면 출처 줄 아래에 `오늘 새 스냅샷 없음: 검사 실패(violation) / 실행 없음` 한 줄을 쓰고, 마지막 통과분을 `[최신]`으로 둔다.
- 7일 안에 통과분이 하나도 없으면 `최근 7일 통과한 스냅샷 없음 — 운영자 확인 필요`.
