# tms-database — RDS PostgreSQL + 배스천

DB(PostgreSQL 16 + pgvector)와 배스천은 `rds_enabled` 하나로 **같이 켜지고 꺼진다**. 기본은 꺼짐.
설계: [specs/a-platform/009-service-infra](../../../specs/a-platform/009-service-infra/plan.md)

## 팀원 DB 접속 (DBeaver)

DB가 켜져 있을 때만 된다. AWS CLI 없이 DBeaver와 공용 키 파일(`tms-bastion.pem`)만 있으면 된다.

### 준비 (한 번)

- DBeaver 설치
- A에게 `tms-bastion.pem`을 받는다. **저장소·공개 채널에 올리지 않는다.**
- 관리자 비밀번호 확인(아래 둘 중 하나). 팀원 IAM 사용자는 `tms-db-users` 그룹이라 읽을 수 있다.
  - 콘솔: Secrets Manager → 이름이 `rds!db-`로 시작하는 비밀 → "비밀 값 검색" → `password`
  - CLI:
    ```bash
    aws secretsmanager get-secret-value --region ap-northeast-2 \
      --secret-id "$(aws ssm get-parameter --region ap-northeast-2 --name /tms/app/config/db-secret-arn --query Parameter.Value --output text)" \
      --query SecretString --output text
    ```
- DB 주소 확인: 콘솔 RDS → `tms-db` → 엔드포인트, 또는 SSM 파라미터 `/tms/app/config/db-host`

### DBeaver 연결 설정

새 연결 → PostgreSQL

| 탭 | 항목 | 값 |
|---|---|---|
| Main | Host | DB 주소 (`tms-db.xxxx.ap-northeast-2.rds.amazonaws.com`, **IP 말고 이 이름 그대로**) |
| Main | Port | `5432` |
| Main | Database | `tms` |
| Main | Username | `tms_admin` |
| Main | Password | 위에서 확인한 값 |
| SSH | Use SSH Tunnel | 체크 |
| SSH | Host/IP | `bastion.smokestack-guard.store` |
| SSH | Port | `22` |
| SSH | User Name | `ec2-user` |
| SSH | Authentication | Public Key, 키 파일 `tms-bastion.pem` |

"Test Connection"이 되면 저장한다. 모두 관리자 계정이라 테이블 생성·조회·수정·삭제가 다 된다.

### 알아 둘 것

- **다시 켜도 설정은 그대로**: 배스천은 켤 때마다 새로 만들어져 IP가 바뀌지만 `bastion.smokestack-guard.store`가 새 IP를 가리킨다. DB 주소도 같다.
- **비밀번호만 바뀐다**: 30일마다 자동으로 바뀌고, DB를 끄고 새로 켜면 새 비밀번호가 생긴다. 접속이 "password authentication failed"로 거부되면 비밀번호를 다시 확인해 넣는다.
- **처음 접속 때 "Permanently added … to the list of known hosts" 창**: 배스천의 지문(서버 신분증)을 기억한다는 뜻이라 확인을 누르면 된다. DB를 껐다 켜면 배스천이 새 서버라 지문이 바뀌어 "호스트 키가 바뀌었다"며 막힐 수 있다. 그때는 `ssh-keygen -R bastion.smokestack-guard.store`(또는 DBeaver known_hosts에서 그 줄 삭제) 후 다시 접속한다.
- **키로는 터널만 된다**: `ssh -i tms-bastion.pem ec2-user@bastion...`으로 셸에 들어가려 하면 바로 끊긴다(정상). DB 포트로의 터널만 허용한다.
- 처음 쓸 때 pgvector: `CREATE EXTENSION IF NOT EXISTS vector;`

## A: 켜고 끄기

```powershell
terraform apply -var rds_enabled=true                    # 개발 (단일 AZ)
terraform apply -var rds_enabled=true -var db_multi_az=true   # 시연
terraform apply                                          # 끄기: DB는 마지막 스냅샷(tms-db-final-<시각>)을 남기고 삭제
terraform apply -var rds_enabled=true -var db_restore_snapshot_id=tms-db-final-<시각>   # 스냅샷에서 되살리기
```

- 켜기 전에 EC2 콘솔에 키 쌍 `tms-bastion`이 있어야 한다.
- 배스천 셸 작업은 SSM 세션: `aws ssm start-session --target <배스천 인스턴스 ID>`
- 30일 교체 규칙을 provider가 거부하면 한 번만: `aws secretsmanager rotate-secret --secret-id <ARN> --rotation-rules AutomaticallyAfterDays=30`
