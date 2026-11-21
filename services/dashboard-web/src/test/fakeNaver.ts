// 시험용 가짜 네이버 지도 SDK. 실제 SDK는 시험에서 부를 수 없어 window.naver.maps를 흉내 낸다.
// 투영은 웹 메르카토르(세계 폭 tileBase × 2^줌)이고, tileBase를 바꿔 "타일 기준이 다른 SDK"도 흉내 낼 수 있다.
import type { NaverLatLng, NaverMapEvent, NaverMapInstance, NaverMaps, NaverSize } from "../map/naver/types";

interface Listener { target: object; name: string; fn: (e: NaverMapEvent) => void; removed: boolean }

export class FakeMap implements NaverMapInstance {
  center: NaverLatLng;
  zoom: number;
  size: NaverSize;
  typeId = "";
  destroyed = false;
  morphs: Array<{ lat: number; lng: number; zoom: number; duration?: number }> = [];
  sets: Array<{ lat: number; lng: number; zoom?: number }> = [];
  sizes: NaverSize[] = [];
  constructor(public el: HTMLElement, public options: Record<string, unknown>, private env: FakeEnv) {
    this.center = options.center as NaverLatLng;
    this.zoom = options.zoom as number;
    this.size = options.size as NaverSize;
    env.maps.push(this);
  }
  /** 설정하면 실제 SDK처럼 오프셋이 '처음 중심' 기준(판 기준)이라 끌어도 같은 좌표가 같은 값을 낸다 */
  paneOrigin?: NaverLatLng;
  getCenter() { return this.center; }
  getZoom() { return this.zoom; }
  getSize() { return this.size; }
  getProjection() {
    const base = this.env.tileBase;
    const world = (c: NaverLatLng) => {
      const rad = (c.lat() * Math.PI) / 180;
      const k = base * 2 ** this.zoom;
      return { x: ((c.lng() + 180) / 360) * k, y: ((1 - Math.asinh(Math.tan(rad)) / Math.PI) / 2) * k };
    };
    return {
      fromCoordToOffset: (c: NaverLatLng) => {
        const a = world(c), o = world(this.paneOrigin ?? this.center);
        return { x: a.x - o.x + this.size.width / 2, y: a.y - o.y + this.size.height / 2 };
      },
    };
  }
  setCenter(c: NaverLatLng) { this.center = c; this.sets.push({ lat: c.lat(), lng: c.lng() }); }
  setZoom(z: number) { this.zoom = z; this.sets.push({ lat: this.center.lat(), lng: this.center.lng(), zoom: z }); }
  morph(c: NaverLatLng, z: number, t?: { duration?: number }) {
    this.morphs.push({ lat: c.lat(), lng: c.lng(), zoom: z, duration: t?.duration });
    this.center = c;
    this.zoom = z;
  }
  setMapTypeId(id: string) { this.typeId = id; }
  setSize(s: NaverSize) { this.size = s; this.sizes.push(s); }
  setOptions() {}
  destroy() { this.destroyed = true; }
}

interface FakeEnv { maps: FakeMap[]; listeners: Listener[]; tileBase: number }

export function installFakeNaver(opts: { tileBase?: number; withMorph?: boolean } = {}) {
  const env: FakeEnv = { maps: [], listeners: [], tileBase: opts.tileBase ?? 256 };
  class LatLng implements NaverLatLng {
    constructor(private a: number, private b: number) {}
    lat() { return this.a; }
    lng() { return this.b; }
  }
  class Size implements NaverSize {
    constructor(public width: number, public height: number) {}
  }
  class LatLngBounds { constructor(public sw: NaverLatLng, public ne: NaverLatLng) {} }
  class MapCtor extends FakeMap {
    constructor(el: HTMLElement, options: Record<string, unknown>) { super(el, options, env); }
  }
  if (opts.withMorph === false) (MapCtor.prototype as { morph?: unknown }).morph = undefined;
  const Event = {
    addListener(target: object, name: string, fn: (e: NaverMapEvent) => void) {
      const l: Listener = { target, name, fn, removed: false };
      env.listeners.push(l);
      return l;
    },
    removeListener(l: unknown) { (l as Listener).removed = true; },
    clearInstanceListeners(target: object) { for (const l of env.listeners) if (l.target === target) l.removed = true; },
  };
  const maps = { Map: MapCtor, LatLng, Size, LatLngBounds, MapTypeId: { NORMAL: "normal", SATELLITE: "satellite" }, Event } as unknown as NaverMaps;
  window.naver = { maps };
  return {
    maps: env.maps,
    /** 지도 이벤트를 일으킨다 */
    emit(map: FakeMap, name: string, e: NaverMapEvent = {}) {
      for (const l of [...env.listeners]) if (!l.removed && l.target === map && l.name === name) l.fn(e);
    },
    /** 아직 살아 있는(해제되지 않은) 이벤트 연결 수 */
    liveListeners(map?: FakeMap) { return env.listeners.filter((l) => !l.removed && (!map || l.target === map)).length; },
    /** 이 좌표가 지금 화면 어디인지(가짜 투영 기준) */
    screenOf(map: FakeMap, lng: number, lat: number) { return map.getProjection().fromCoordToOffset(new LatLng(lat, lng)); },
    LatLng,
    uninstall() { Reflect.deleteProperty(window, "naver"); },
  };
}
