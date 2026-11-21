// 네이버 지도 Client ID(ncpKeyId).
// 브라우저 공개용 앱 ID이며 Client Secret이 아니다(소유자가 공개를 명시했고, 사용자가 2026-11-20에 저장소에 두기로 결정했다).
// 보호는 이 값이 아니라 네이버 클라우드 콘솔의 Web 서비스 URL(등록 도메인 목록)이 한다:
//   http://localhost:5173 과 운영 도메인이 등록돼 있어야 인증이 통과한다.
// 환경 변수 VITE_NAVER_MAP_KEY_ID가 있으면 이 기본값 대신 그 값을 쓴다(덮어쓰기용, 배포 설정에 추가할 필요 없음).
export const NAVER_DEFAULT_KEY_ID = "mn0l1r8cir";
