# Quickstart: 계약 검사 단계 시험과 전환

순서: 로컬 테스트 → 배포(관찰 모드) → 검사만·알림 없음 → 검사만·알림 → 매일 실행 7번 관찰 → 차단 모드.

## 1. 로컬 테스트

```bash
cd services/tms-silver && uv run pytest -q tests/test_lambda_ktms_ml_ready_check.py
cd ../.. && PYTHONPATH=src services/tms-silver/.venv/bin/python -m pytest -q tests
```

기대: 정상 표본 통과, 변조 표본 5종(컬럼 누락, 출처 섞임, 키 중복, 라벨 변조, Feature 변조) 위반, 범위 첫 행·끝 1시간 오탐 없음(SC-001·SC-002 일부).

## 2. 레이어 확인 (사용자, 한 번)

```bash
aws lambda get-layer-version-by-arn --region ap-northeast-2 --arn "<pandas_layer_arn 기본값>"
```

없으면 콘솔 Lambda → 레이어 추가 → "AWS 레이어"에서 `AWSSDKPandas-Python312` 최신 버전 ARN을 보고 `TF_VAR_pandas_layer_arn`으로 준다.

## 3. 배포 (사용자, PowerShell)

```powershell
cd infra/stacks/tms-silver
terraform plan    # 기대: Lambda·레이어·역할·로그 그룹 추가, 상태 머신·SFN 역할 변경. 테이블·스케줄 변경 없음
terraform apply
```

`ktms_check_mode`는 기본 `observe`다. 바꾸지 않는다.

## 4. 검사만, 알림 없음 (SC-004)

contracts/check-interface.md §1의 첫 명령. 확인:

- 실행 그래프: `Check`만 초록, `Silver`·`MlReady` 미실행
- 메일 0통
- `silver2/_runs/ktms_ml_ready_check/`에 기록 1개, `result = passed`
- `tms_silver2.ktms_ml_ready$snapshots` 최신 행이 실행 전과 같음

## 5. 검사만, 알림 (문안 확인)

위반이 없으면 메일이 오지 않는 것이 정상이다. 위반 문안은 로컬 테스트의 출력(`message`)으로 확인한다. 실행 실패 문안은 존재하지 않는 테이블로 확인한다.

```bash
--input '{"stage":"check","check_table":"tms_silver2.no_such_table","notify":true}'
```

기대: 제목 `[tms] K-TMS contract check failed`, 관찰 모드라 실행은 성공.

## 6. 매일 실행 관찰 (SC-001)

03:00 실행 7번 동안 위반 메일 0통, 기록 7개 모두 `passed`. 소요 시간(SC-005)을 기록한다.

## 7. 차단 모드 전환

```powershell
$env:TF_VAR_ktms_check_mode = "block"; terraform apply
```

## 8. E에게 안내 (SC-006)

008 `contracts/ktms-tables.md`의 "검사를 통과한 스냅샷 읽기"를 공유한다.
