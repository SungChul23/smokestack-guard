# 내부 표현

- MapClock: reference(불변 최신 보관시각), time(선택시각), mode(latest/history), playing.
- FramesAsset: version, reference, stepMs=1800000, stackIds(유일 내부ID), frames(48개 `{time,rows}`), provenance(사용 이력 경로).
- FrameRow: `[stackIndex,noxRaw,noxLimit,soxRaw,soxLimit]`. raw는 숫자/문자열/NULL 그대로. 행이 없으면 그 시점 관측이 없다. 숫자로 변환할 때 기존 TmsNumber.parse를 재사용한다.
- MapStack: 원 관측 배열과 기존 차트 latest 유지, 현재 지도 시각의 mapLatest(관측 또는 undefined), ratio(두 물질 최대 유효비율 또는 null), mapTime, mapState.
- ForecastPlaceholder: 모델 미연결 상태이며 count/list를 만들지 않는다.

동일 ID/시각의 충돌은 생성 실패로 중지한다. 코드에서 타 시각을 보간/앞 값으로 채우지 않는다. 내부 표현은 Silver·운영 API·모델 계약이 아니다.
