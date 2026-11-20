# 검증

기존 로컬 관제 서버 8765와 Node를 사용한다. 새 인증/설치 없음.

```powershell
node D/site-navigation/build-core.cjs
node --test D/dashboard-preview/regional-console/tests/query-router/site-navigation.test.cjs
node D/site-navigation/qa-navigation.cjs
```

http://127.0.0.1:8765/ 새로고침 → 에이전트 → `사업장 코드 113205로 지도 이동해줘`. 실제 지도/상세의 사업장과 안내가 같아야 한다. `신재생자원센터 찾아줘`는 후보 확인 전 이동하지 않아야 한다. `사업장 코드 999999 어디야`는 결과 없음으로 안내한다. 기존 법령 질문과 초과 조회도 검사한다.

결과·백업: `D/site-navigation/`. 별도 8767 검토 화면은 계속 실행 전 계획만 확인한다.
