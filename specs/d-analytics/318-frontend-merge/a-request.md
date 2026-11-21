# A에게 요청: 대시보드 관제 화면 올리기 전에 필요한 것

대상: A(플랫폼·AWS) · 작성: D · 날짜: 2026-11-21
관련: spec 318(`spec.md`), 이슈 #71(관제 화면 React 새로 구현), 이슈 #62·012(RDS 적재)

## 한 줄 요약

새 관제 화면(`dashboard-web`)과 화면용 데이터 API(`dashboard-api`)를 올립니다. **지금 상태로 머지하면 `main` 머지 즉시 운영에 배포**되므로, 아래 1번(IAM)을 먼저 적용해 주셔야 실제 데이터가 나옵니다. 내용은 화면 외에 인프라 한 줄(IAM)과 A 소유 파일 약간(아래 3번)입니다.

## 1. 꼭 필요한 것 (막혀 있음)

### 1-1. 서버 역할에 `rds-db:connect` 추가 — `infra/stacks/tms-app/iam.tf`
- API 서버가 RDS에 **`tms_app`(IAM 인증)** 으로 접속해야 하는데, 서버 역할 `tms-app-server`에 `rds-db:connect`가 없습니다(콘솔 정책으로도 확인했습니다).
- 추가한 문장(적재 Lambda의 `ConnectAsLoader`와 같은 방식, `tms_app`만 허용):
  ```hcl
  statement {
    sid       = "ConnectAsApp"
    actions   = ["rds-db:connect"]
    resources = ["arn:aws:rds-db:ap-northeast-2:${data.aws_caller_identity.current.account_id}:dbuser:*/tms_app"]
  }
  ```
- `terraform fmt`·`validate`는 통과했습니다. **제 IAM 사용자(`de-ai-05`)는 이 스택의 읽기 권한(Route 53·ACM·ECR·VPC·SSM 태그)이 없어 `plan`을 못 돌렸습니다.** `plan`·`apply`는 A가 해 주세요. `plan`에는 `aws_iam_role_policy.app`에 문장 1개 추가만 나와야 합니다.
- DB 쪽은 DBeaver로 확인했습니다: `tms_app`의 `rds_iam` 멤버십 true, `obs.measurement_30m`·`ref.v_stack`·`ref.site`·`ref.status_code` SELECT 가능, `app.user_favorite` INSERT 가능.

### 1-2. 머지 순서·시점
`services/dashboard-api/**`와 `services/dashboard-web/**`가 모두 `main` 머지 때 자동 배포됩니다(워크플로 각각).
1. (A) iam.tf `plan`·`apply`
2. API 먼저 배포(또는 같은 PR이면 동시에) → 서버 재시작 후 `GET /api/sites`가 200인지 확인
3. 웹 배포
- 순서가 어긋나면: API가 없거나 DB 접속이 안 되면 화면은 로그인·초대 코드까지는 정상이고, 대시보드 자리에 **"데이터 연결 전 (…)"** 만 나옵니다. 로그인 흐름은 영향이 없습니다.
- 한 PR(커밋 여러 개)로 올릴지, iam.tf만 따로 PR로 먼저 올릴지 A가 편한 쪽으로 정해 주세요. 제 추천은 **iam.tf 단독 PR을 먼저 머지·apply → API+웹 PR**입니다.

## 2. 부탁하고 싶은 것 (선택)

- **CI에 `npm test` 추가**: `.github/workflows/dashboard-web.yml`의 `build` 잡은 `npm run build`만 합니다. 새 화면은 시험이 687개(`vitest`) 있어서 `npm ci` 다음에 `npm test`를 넣고 싶습니다. A 소유 파일이라 허락을 구합니다. (`npm run build`가 `tsc -b`를 하므로 타입 검사는 이미 돕니다.)
- **서버 환경 변수**: 새로 필요한 것은 없습니다. `DB_HOST`·`DB_PORT`·`DB_NAME`·`APP_ORIGIN`은 기존 그대로이고, 접속 계정은 코드 기본값이 `tms_app`입니다(`DB_USER`로 바꿀 수 있음). 관리자 비밀(`DB_SECRET_ARN`)은 `/api/db-check`에만 쓰입니다.

## 3. A 소유 파일을 건드린 부분 (확인해 주세요)

| 파일 | 바뀐 것 |
|---|---|
| `services/dashboard-web/src/App.tsx` | 회원이면 새 관제 화면(`DashboardApp`)을 그리고 로그인 토큰을 넘김. 기존 "대시보드 준비 중" 자리표시자 컴포넌트 삭제. **Landing → Google → 초대 코드 흐름은 그대로입니다.** |
| `services/dashboard-web/src/main.tsx` | `ThemeProvider`(다크·라이트)로 감싸고 `tokens.css`를 불러옴 |
| `services/dashboard-web/src/api.ts` | `apiSend`(PUT·DELETE) 추가 — 즐겨찾기용 |
| `services/dashboard-web/vite.config.ts` | `vitest` 설정, 개발 전용 데이터 플러그인(`apply: "serve"`라 운영 빌드에 안 들어감) |
| `services/dashboard-web/package.json`·`package-lock.json` | `zustand` 추가, 시험 도구(`vitest`·`jsdom`·`@testing-library/*`)는 devDependencies |

`landing.css`·`Landing.tsx`·`Invite.tsx`·`auth.ts`는 건드리지 않았습니다. 새 대시보드의 색 이름(`--stage-*` 등)은 `landing.css`의 `--chart-bg` 등과 충돌하지 않게 따로 만들었습니다.

## 4. 바뀌는 것 (검토 대상)

**`services/dashboard-api` (D·A 공동 소유)**
- 새 라우트(모두 로그인한 회원만): `GET /api/sites`(사업장·굴뚝), `GET /api/day`(최신 시각 기준 30분 48칸, 같은 시각이면 캐시), `GET/PUT/DELETE /api/favorites`(`app.user_favorite`, Cognito sub 기준).
- gzip 응답, DB 꺼짐 503·관측 없음 404, 시험 34개(가짜 DB 연결).
- 첫 `/api/day` 호출은 약 19만 행을 가공하므로 몇 초 걸릴 수 있습니다(이후 30분 캐시). 서버 메모리(2GB)로 충분할 것으로 보지만 실제 확인은 못 했습니다.

**`services/dashboard-web`**
- 운영 빌드는 `/api/sites`·`/api/day`를 읽고(개발은 로컬 `dev-data`), 지역 경계(`public/map-data/geo.json`, 약 0.4MB)만 정적 파일로 같이 배포됩니다.
- 등고선 파일(약 6MB)은 **저장소에 올리지 않았습니다**(`.gitignore`). 운영 지도에는 등고선이 없고 화면은 정상으로 뜹니다. 나중에 올릴지 정해지면 알려 주세요.
- 갱신: 열어 둔 화면은 :17·:47에 `/api/day`를 다시 받습니다(적재 :15·:45 직후).
- 비밀값 없음: 네이버 지도 키는 공개 앱 ID라 `config.ts`에 기본값을 둡니다(도메인 등록으로 보호).

## 5. 올린 뒤 확인(제가 하겠습니다)

1. `GET /api/sites`·`/api/day` 200, 응답 크기·시간(CloudWatch `/tms/app/api`).
2. 화면: 지도에 핀, 경고 목록, 추세 그래프.
3. 즐겨찾기 별 → 새로고침 뒤에도 유지.
4. 네이버 지도 인증(`smokestack-guard.store`·로컬호스트 등록 확인).

문제 시 되돌리기: 웹 PR 되돌리면 이전(자리표시자) 화면으로 돌아가고, API 새 라우트는 기존 라우트(`/api/me` 등)에 영향이 없습니다.

## 6. 같이 정하면 좋은 것 (급하지 않음)

- **알림 서비스**: 즐겨찾기한 사업장이 초과일 때 외부(이메일 등)로 알리려면 서버에서 경보를 판정하고 보내는 곳이 필요합니다(SNS·SES 등, E·A와 협의). 화면에는 배너·스티커(화면 안 알림)만 있습니다.
- **예측값**: E의 예측이 나오면 배너·스티커에 "예측"으로 같이 보여 줄 자리가 있습니다. API 형식을 정해 주세요.
