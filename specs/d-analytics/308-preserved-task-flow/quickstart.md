# 재현

`node --test D/dashboard-preview/regional-console/tests/query-router/task-flow.test.cjs`

전체 회귀는 같은 폴더 `*.test.cjs`, 브라우저 작업대는 기존8768이다. 새 의존성·자격 증명은 없다.

SC-023/FLOW-008/009에 실제 부족 문서·기준일을 입력하고 일반 문서 검색과 case 미지원이 함께 남는지 확인한다. SC-007은 일반 개요 분기, SC-017은 사용자 시설 선택, FLOW-004는 직접 고장 절차 미확보를 확인한다. 변조·만료·권한 변화·새 도구·읽기 실패도 검사한다.

산출물과 변경 기록: `D/query-router-lab/task-flow-20261116/`. 기존 기대값은 그대로 보존한다.

최종 로컬 검증:

```powershell
node --test D/dashboard-preview/regional-console/tests/query-router/*.test.cjs
node D/query-router-lab/build-workbench.cjs
node D/query-router-lab/task-flow-20261116/qa-browser.cjs browser-new-run
node D/query-router-lab/task-flow-20261116/run.cjs new new-run
node D/query-router-lab/task-flow-20261116/run-variants.cjs new-run
```

브라우저 검사는 기존8768 작업대와 검사용 CDP 세션이 필요하다. `run.cjs`는 저장된 실제 Kiwi·Luna 해석 결과를 현재 코드에 재생하며 새 LLM API를 호출하지 않는다. 카드 응답은 명시적인 가상 QA 사용자 fixture다. 결과를 덮어쓰지 않으므로 재실행마다 사용하지 않은 결과 이름을 지정한다.
