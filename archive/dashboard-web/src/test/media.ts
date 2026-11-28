// 시험용 화면 조건(matchMedia) 흉내. jsdom에는 matchMedia가 없어서 폭·모션 줄이기 같은 조건을 시험에서 정해 준다.
type Listener = () => void;

export function installMedia(initial: Record<string, boolean> = {}) {
  const state: Record<string, boolean> = { ...initial };
  const listeners = new Map<string, Set<Listener>>();
  const mql = (q: string) => ({
    get matches() { return !!state[q]; },
    media: q,
    onchange: null,
    addEventListener: (_: string, l: Listener) => { (listeners.get(q) ?? listeners.set(q, new Set()).get(q)!).add(l); },
    removeEventListener: (_: string, l: Listener) => { listeners.get(q)?.delete(l); },
    addListener: (l: Listener) => { (listeners.get(q) ?? listeners.set(q, new Set()).get(q)!).add(l); },
    removeListener: (l: Listener) => { listeners.get(q)?.delete(l); },
    dispatchEvent: () => false,
  });
  Object.defineProperty(window, "matchMedia", { configurable: true, writable: true, value: (q: string) => mql(q) });
  return {
    /** 조건이 바뀐 것처럼 값을 바꾸고 듣고 있는 쪽에 알린다 */
    set(query: string, value: boolean) {
      state[query] = value;
      listeners.get(query)?.forEach((l) => l());
    },
  };
}

export function uninstallMedia() {
  Reflect.deleteProperty(window, "matchMedia");
}

/** 창(뷰포트) 크기를 바꾼다. 에이전트 창·마스코트는 이 값을 기준으로 경계를 계산한다 */
export function setViewport(w: number, h: number) {
  Object.defineProperty(window, "innerWidth", { configurable: true, writable: true, value: w });
  Object.defineProperty(window, "innerHeight", { configurable: true, writable: true, value: h });
}
