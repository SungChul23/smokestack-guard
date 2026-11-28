// 네이버 지도 SDK(window.naver.maps)에서 우리가 쓰는 부분만 적은 최소 형식. SDK 자체 형식 파일을 들이지 않는다.
export interface NaverLatLng { lat(): number; lng(): number }
export interface NaverPoint { x: number; y: number }
export interface NaverSize { width: number; height: number }
export interface NaverProjection { fromCoordToOffset(coord: NaverLatLng): NaverPoint }

/** 지도 이벤트가 주는 값(우리는 화면 좌표만 쓴다) */
export interface NaverMapEvent {
  point?: NaverPoint; // 지도 영역 기준 화면 좌표
  offset?: NaverPoint;
  coord?: NaverLatLng;
  pointerEvent?: MouseEvent;
}

export interface NaverMapInstance {
  getCenter(): NaverLatLng;
  getZoom(): number;
  getSize(): NaverSize;
  getProjection(): NaverProjection;
  setCenter(coord: NaverLatLng): void;
  setZoom(zoom: number, effect?: boolean): void;
  /** 부드럽게 이동·확대한다(없는 버전이면 setCenter/setZoom으로 대신한다) */
  morph?(coord: NaverLatLng, zoom: number, transition?: { duration?: number }): void;
  setMapTypeId(id: string): void;
  setSize(size: NaverSize): void;
  setOptions(options: Record<string, unknown>): void;
  destroy?(): void;
}

export interface NaverEventApi {
  addListener(target: object, name: string, handler: (e: NaverMapEvent) => void): unknown;
  removeListener(listener: unknown): void;
  clearInstanceListeners(target: object): void;
}

export interface NaverMaps {
  Map: new (el: HTMLElement, options: Record<string, unknown>) => NaverMapInstance;
  LatLng: new (lat: number, lng: number) => NaverLatLng;
  LatLngBounds: new (sw: NaverLatLng, ne: NaverLatLng) => unknown;
  Size: new (width: number, height: number) => NaverSize;
  MapTypeId: { NORMAL: string; SATELLITE: string };
  Event: NaverEventApi;
}

declare global {
  interface Window {
    naver?: { maps?: NaverMaps };
    /** 네이버가 인증에 실패하면 부르는 전역 함수(SDK 규약) */
    navermap_authFailure?: () => void;
  }
}
