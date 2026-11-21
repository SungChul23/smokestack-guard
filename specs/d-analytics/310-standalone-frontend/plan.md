# 분리 계획

기존 정적 HTML/CSS/JavaScript를 유지한다. D/frontend-export/tms-frontend를 스테이징으로 만들고, 검증 후 별도 저장소 디렉터리로 복사한다. public/index.html에 실제 관제 입구를 두고 자산 경로를 상대 경로로 유지한다. 기존 ui-review 디렉터리는 ui로 정리한다. package.json과 Node 정적 개발 서버만 제공하며 프레임워크·외부 패키지를 추가하지 않는다.

HTML의 정적 참조와 JS/CSS의 자산 참조·등고선 manifest를 추적해 허용 목록으로 복사한다. latest.js를 단일30분·NOx/SOx만 남긴 data/snapshot.js로 변환하고 이력·재생 플러그인을 연결하지 않는다. 개인 저장은 데모임을 유지한다. 네이버 브라우저 공개 Client ID와 서버 비밀값은 구분한다.

수집·원본·Silver·모델·AWS는 변경하지 않는다. 원본은 복사만 한다. 비밀값·수신자 설정·로컬 브라우저 저장·모델 캐시를 저장소에 넣지 않는다. 외부 API 비용을 일으키는 신규 서비스 설정은 없다. 원격 업로드는 구체적인 분리본 확인 및 인증/외부 설정 승인 뒤 처리한다.
