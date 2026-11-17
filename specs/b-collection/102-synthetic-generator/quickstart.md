# Quickstart: 합성 데이터 생성 → 점검 → Silver 확인

**Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

> 생성기는 구현 전이다. 아래는 구현 후 따를 순서이며, 명령 이름은 구현하면서 확정한다.

## 준비

1. 저장소 루트에서 `k_tms_synthetic/`로 이동하고 `pip install -r requirements.txt`.
2. 참조 통계 `data/ref_stats.csv`를 만든다. Athena에서 `ktms_flat`로 배출구×항목 통계를 뽑아 CSV로 저장한다(컬럼은 [data-model.md](data-model.md)). 저장소에 커밋하지 않는다.
3. `config/config.yaml`의 시작 시각과 에피소드 개수를 확인한다.
4. **생성 전에** `expected/S-xx-E.yaml`을 쓰고, 생성자와 다른 1명이 검수한다.

## 실행

```bash
cd k_tms_synthetic
python -m synth generate --config config/config.yaml --out out
python -m synth validate --out out --expected expected
```

- `generate`: 합성 스냅샷과 정보 파일(`manifest.jsonl`, `delivery.jsonl`)을 `out/` 아래 합성 경로 레이아웃으로 만든다.
- `validate`: 만든 파일을 다시 읽어 합격 기준(구조·경로·시각·값·응답 점검, 라벨 교차 확인)과 기대 결과를 대조하고, `to_silver`로 Silver 결과도 확인한다.

## 기대 결과

| 확인 | 기대 |
|---|---|
| 같은 설정으로 `generate` 두 번 | 산출물이 바이트 단위로 같음 |
| `validate` | 시나리오별 통과/불일치 목록. 콤마 숫자는 "알려진 불일치"로 표시 |
| 실측 경로 | `tms_cleansys/` 아래에 아무것도 쓰이지 않음 |
| 수동 대조 | 기대 결과 파일과 `out/`을 생성자와 다른 1명이 함께 확인 |

## 업로드와 Silver 읽기 (⑥단계)

합성 경로에만 업로드한다(실측 경로 거부). Silver가 합성 경로를 읽는 방법은 C와 합의한 뒤 적는다.
