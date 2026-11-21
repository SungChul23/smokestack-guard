# 지도 시간 인터페이스

- `TmsMapTime.evaluate(observation)`: NOx/SOx 비율/원문 관측 유무. 다른 물질은 판정하지 않는다.
- `TmsMapTime.exact(observations,time)`: 타임스탬프가 정확히 같은 관측만 선택한다.
- `StackDashboard.getMapTime()`: 현재 지도 기준시각. `getReferenceTime()`은 별도 차트/보관 기준으로 불변이다.
- `StackDashboard.applyMapFrame(time, frameMap)`: 모든 굴뚝에 공통 time 부여 후 지도·목록·집계만 갱신한다. 카메라와 차트 범위/원 관측 배열을 바꾸지 않는다.
- `TmsMapTimeline.select(index)`, `play()`, `pause()`, `latest()`: 0~47만 허용하고 최신 복귀/새 선택 후 이전 비동기 응답을 무효화한다.

실제 예측 수신 인터페이스는 이번 범위에 없으며 팀 계약 후 별도 계획한다.
