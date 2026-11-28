# 계약: 배포 파이프라인 (A → D)

## 트리거

| 워크플로 | 경로 | PR | main push |
|---|---|---|---|
| `.github/workflows/dashboard-api.yml` | `services/dashboard-api/**` | 린트·테스트·이미지 빌드(푸시 안 함) | 빌드 → ECR → 태그 기록 → 켜진 서버에 배포 |
| `.github/workflows/dashboard-agent.yml` | `services/dashboard-agent/**` | 같음 | 같음 |
| `.github/workflows/dashboard-web.yml` | `services/dashboard-web/**` | 린트·빌드 | 빌드 → S3 → `index.html` 무효화 |

각 워크플로는 자기 파일이 바뀔 때도 돈다.

## 배포 역할 (`tms-github-deploy`)

- 신뢰: GitHub OIDC, main 브랜치만. 저장소가 변하지 않는 sub 형식(`use_immutable_subject`)을 써서 `repo:SungChul23@143672987/smokestack-guard@1437820168:ref:refs/heads/main`으로 온다. 이름 형식 `repo:SungChul23/smokestack-guard:ref:refs/heads/main`도 함께 허용한다.
- 권한:
  - ECR: `GetAuthorizationToken`(계정), 두 저장소에 push 관련 동작
  - SSM: `PutParameter` — `/tms/app/api/image-tag`, `/tms/app/agent/image-tag`
  - SSM: `SendCommand` — 문서 `AWS-RunShellScript` + 태그 `tms:app`가 있는 인스턴스, `GetCommandInvocation`, `ListCommandInvocations`
  - EC2: `DescribeInstances`(켜진 서버 수 확인)
  - S3: 화면 버킷 `ListBucket`·`PutObject`·`DeleteObject`
  - CloudFront: 화면 배포 1개에 `CreateInvalidation`
- 워크플로에는 역할 ARN만 쓴다(비밀 아님). 액세스 키는 쓰지 않는다.

## 화면 배포 역할 (`tms-github-web-deploy`, #94)

화면은 별도 저장소 `SungChul23/smokestack-guard-web-v2`의 `.github/workflows/deploy.yml`이 배포한다(UI와 API를 따로 고쳐 나가기 위해).

- 신뢰: GitHub OIDC, 그 저장소의 main 브랜치만. `repo:SungChul23/smokestack-guard-web-v2:ref:refs/heads/main`과 변하지 않는 형식 `repo:SungChul23@143672987/smokestack-guard-web-v2@1472580451:ref:refs/heads/main`.
- 권한(최소): 서버 배포 역할과 나눠 화면 저장소가 ECR·서버 배포 권한을 갖지 않게 한다.
  - S3: 화면 버킷 `ListBucket`, 객체 `PutObject`·`DeleteObject`·`GetObject` (`aws s3 sync --delete`)
  - CloudFront: 화면 배포 1개에 `CreateInvalidation`·`GetInvalidation` (`index.html`)
  - SSM: `GetParameter(s)` — `/tms/app/config/cognito-user-pool-id`, `cognito-client-id`, `cognito-domain`, `web-distribution-id` (빌드에 넣는 값, 비밀 아님)
- 워크플로: PR·push 모두 시험·빌드, main push만 업로드. 미리보기 판정(`src/preview/mode.ts`)이 환경 변수 방식이 아니면 빌드를 멈춘다(운영에 가짜 데이터 방지).

## "현재 버전" 기록

| SSM 파라미터 | 처음 값 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| `/tms/app/api/image-tag` | `none` | 배포(main) | API 서버 시작·배포 스크립트 |
| `/tms/app/agent/image-tag` | `none` | 배포(main) | 에이전트 서버 시작·배포 스크립트 |

Terraform은 처음 값만 만들고 이후 값 변경은 무시한다(`ignore_changes`).

## 서버 0대일 때

배포는 태그만 기록하고 성공으로 끝난다. 나중에 대수를 올리면 서버가 기록된 태그로 뜬다.
