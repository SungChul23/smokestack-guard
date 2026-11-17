# 계약: 켜고 끄는 변수와 운영 구성

시간당 요금이 붙는 자원은 아래 변수로만 켜고 끈다. 기본값은 모두 "꺼짐". A가 PowerShell에서 `-var`로 넘기거나 `*.tfvars`(커밋하지 않음)에 둔다.

## 변수

| 스택 | 변수 | 타입 | 기본 | 뜻 |
|---|---|---|---|---|
| `tms-network` | `nat_gateway_count` | number (0·1·2) | `0` | NAT 개수. 1이면 두 AZ가 AZ-a NAT를 같이 씀 |
| `tms-network` | `bastion_ssh_cidrs` | list(string) | `["0.0.0.0/0"]` | 배스천 SSH 허용 주소 (보안그룹이 이 스택에 있음) |
| `tms-database` | `rds_enabled` | bool | `false` | DB와 배스천을 함께 켬 |
| `tms-database` | `db_multi_az` | bool | `false` | DB Multi-AZ |
| `tms-database` | `db_restore_snapshot_id` | string | `""` | 켤 때 이 스냅샷에서 되살림 (빈 값이면 새 DB) |
| `tms-database` | `bastion_key_name` | string | `"tms-bastion"` | 콘솔에서 만든 키 쌍 이름 |
| `tms-database` | `db_user_names` | list(string) | 팀원 6명 | DB 비밀을 읽는 IAM 사용자 |
| `tms-app` | `alb_enabled` | bool | `false` | ALB + `api.` 레코드 |
| `tms-app` | `api_desired` | number (0·1·2) | `0` | API 서버 대수 |
| `tms-app` | `agent_desired` | number (0·1·2) | `0` | 에이전트 서버 대수 |
| `tms-app` | `api_instance_type` | string | `"t3.small"` | |
| `tms-app` | `agent_instance_type` | string | `"t3.small"` | 메모리 부족 시 `t3.medium` |

## 운영 구성 3가지

| 구성 | `nat_gateway_count` | `rds_enabled` / `db_multi_az` | `alb_enabled` | `api_desired` / `agent_desired` | 하루 비용(대략) |
|---|---|---|---|---|---|
| 꺼 둠 (기본) | 0 | false / false | false | 0 / 0 | 약 $0.05 |
| 개발 | 1 | true / false | true | 1 / 1 | 약 $5 |
| 시연 | 2 | true / true | true | 2 / 2 | 약 $8 |

## 켜는 순서와 끄는 순서

- **켤 때**: `tms-network`(NAT) → `tms-database`(DB, 약 10분) → `tms-app`(ALB·서버).
- **끌 때**: `tms-app` → `tms-database` → `tms-network`. 서버가 NAT보다 먼저 사라져야 한다.
- 지키지 않으면: `tms-app`은 NAT가 없을 때 서버를 켜려 하면 plan에서 멈춘다(precondition).
