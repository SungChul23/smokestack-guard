# 검증 방법

저장소 루트에서 기존 Node와 로컬 Kiwi 서버(8767)를 사용한다. 새 설치·자격증명은 필요 없다.

```powershell
node --test D/dashboard-preview/regional-console/tests/query-router/approved-plans.test.cjs
node D/query-router-lab/build-workbench.cjs
node D/query-router-lab/check-approved-plans.cjs
node D/query-router-lab/qa-manual-review.cjs
```

검토 화면 http://127.0.0.1:8767/ 에서 ‘선택한 굴뚝 어제 NOx와 SOx 평균 알려줘’, ‘선택한 굴뚝 어제 NOx 평균과 최댓값 알려줘’, ‘선택한 굴뚝 지금 NOx 경고 근거와 대응 절차 알려줘’, ‘NOx 그래프 켜고 SOx 그래프 꺼줘’를 입력한다. 선택 참조는 화면 조건을 체크하고, 빠진 기간/법령 기준일은 카드로 받는다. 계획만 표시되며 실제 실행은 없다.

‘하루 NOx 배출 총량 kg 알려줘’는 자료 미보유, ‘대출 관련 문서 찾아줘’는 범위 밖, 원본 변조는 차단이 기대다. 결과 상태 대조는 단위 테스트의 합성 표본으로만 실행한다. 보고서와 고정 사례는 `D/query-router-lab/approved-plans-20261114/`에 둔다.
