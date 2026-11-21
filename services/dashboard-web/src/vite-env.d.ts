/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** 화면 데이터 출처: api(서버) | dev(로컬 dev-data). 없으면 운영 빌드는 api, 개발은 dev */
  readonly VITE_DATA_SOURCE?: "api" | "dev";
  /** 네이버 지도 인증 키(ncpKeyId). 저장소에 쓰지 않고 환경 변수로만 받는다. 없으면 네이버 지도 선택이 꺼진다 */
  readonly VITE_NAVER_MAP_KEY_ID?: string;
}

