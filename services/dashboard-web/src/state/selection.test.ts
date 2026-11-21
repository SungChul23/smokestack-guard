import { beforeEach, describe, expect, it } from "vitest";
import { initialSelection, MAP_SHOW_ORDER, mapLevel, selectedStackKey, useSelection } from "./selection";

const get = () => useSelection.getState();

beforeEach(() => {
  useSelection.setState({ ...initialSelection });
});

describe("선택", () => {
  it("처음에는 아무것도 고르지 않았다", () => {
    expect(get().selectedSiteId).toBeNull();
    expect(get().selectedStackCode).toBeNull();
    expect(selectedStackKey(get())).toBeNull();
  });

  it("사업장을 고르면 굴뚝은 비어 있다", () => {
    get().selectSite("130554");
    expect(get().selectedSiteId).toBe("130554");
    expect(get().selectedStackCode).toBeNull();
    expect(selectedStackKey(get())).toBeNull(); // 굴뚝까지 골라야 에이전트에 보낼 키가 생긴다
  });

  it("굴뚝까지 고르면 에이전트 계약의 selectedStackId 모양이 된다", () => {
    get().selectSite("130554", "3");
    expect(selectedStackKey(get())).toBe("130554:3");
  });

  it("사업장 없이 굴뚝만 고를 수 없다", () => {
    get().selectStack("3");
    expect(get().selectedStackCode).toBeNull();
    get().selectSite("130554");
    get().selectStack("3");
    expect(get().selectedStackCode).toBe("3");
  });

  it("다른 사업장을 고르면 굴뚝 선택은 새로 시작한다", () => {
    get().selectSite("130554", "3");
    get().selectSite("130576");
    expect(get().selectedStackCode).toBeNull();
  });

  it("선택을 지운다", () => {
    get().selectSite("130554", "3");
    get().clearSelection();
    expect(get().selectedSiteId).toBeNull();
    expect(get().selectedStackCode).toBeNull();
  });
});

describe("지도 위치", () => {
  it("전국 → 시도 → 시군으로 내려가고 한 단계씩 올라온다", () => {
    expect(mapLevel(get())).toBe("nation");
    get().enterSido("경상북도");
    expect(mapLevel(get())).toBe("sido");
    get().enterSigungu("성주군");
    expect(mapLevel(get())).toBe("sigungu");
    expect(get().mapPath).toEqual({ sido: "경상북도", sigungu: "성주군" });
    get().goUp();
    expect(get().mapPath).toEqual({ sido: "경상북도", sigungu: null });
    get().goUp();
    expect(mapLevel(get())).toBe("nation");
    get().goUp(); // 전국에서 더 올라갈 곳은 없다
    expect(mapLevel(get())).toBe("nation");
  });

  it("시도 없이 시군으로 들어갈 수 없다", () => {
    get().enterSigungu("성주군");
    expect(mapLevel(get())).toBe("nation");
  });

  it("다른 시도로 가면 시군은 비운다", () => {
    get().enterSido("경상북도");
    get().enterSigungu("성주군");
    get().enterSido("경기도");
    expect(get().mapPath).toEqual({ sido: "경기도", sigungu: null });
  });

  it("전국으로 한 번에 돌아간다", () => {
    get().enterSido("경상북도");
    get().enterSigungu("성주군");
    get().goNation();
    expect(mapLevel(get())).toBe("nation");
  });

  it("선택과 지도 위치는 서로 영향을 주지 않는다(선택해도 지도가 갇히지 않는다)", () => {
    get().enterSido("경기도");
    get().selectSite("130554", "3"); // 경북 사업장
    expect(get().mapPath).toEqual({ sido: "경기도", sigungu: null });
    get().goNation();
    expect(get().selectedSiteId).toBe("130554");
  });
});

describe("차트 조건", () => {
  it("물질과 기간을 바꾼다. 기본은 NOx, 24시간이다", () => {
    expect(get().pollutants).toEqual(["nox"]);
    expect(get().periodHours).toBe(24);
    get().togglePollutant("sox");
    get().setPeriodHours(6);
    expect(get().pollutants).toEqual(["nox", "sox"]);
    expect(get().periodHours).toBe(6);
  });
});

describe("필터·검색·즐겨찾기", () => {
  it("상태 필터를 켜고 끈다(비어 있으면 모두)", () => {
    expect(get().statusFilter).toEqual([]);
    get().toggleStatus("risk");
    get().toggleStatus("exceed");
    expect(get().statusFilter).toEqual(["risk", "exceed"]);
    get().toggleStatus("risk");
    expect(get().statusFilter).toEqual(["exceed"]);
  });

  it("검색어를 저장한다", () => {
    get().setSearch("성주");
    expect(get().search).toBe("성주");
  });

  it("즐겨찾기를 켜고 끈다", () => {
    get().toggleFavorite("130554");
    expect(get().favorites).toEqual(["130554"]);
    get().toggleFavorite("130554");
    expect(get().favorites).toEqual([]);
  });
});

describe("지도 경로 한 번에 정하기", () => {
  beforeEach(() => useSelection.setState({ ...initialSelection }));
  it("시도·시군을 함께 정한다", () => {
    useSelection.getState().setMapPath({ sido: "서울", sigungu: "중구" });
    expect(useSelection.getState().mapPath).toEqual({ sido: "서울", sigungu: "중구" });
  });
  it("시도 없이 시군만 오면 시군은 버린다", () => {
    useSelection.getState().setMapPath({ sido: null, sigungu: "중구" });
    expect(useSelection.getState().mapPath).toEqual({ sido: null, sigungu: null });
  });
  it("같은 값이면 상태 객체를 바꾸지 않는다(불필요한 다시 그리기 방지)", () => {
    useSelection.getState().setMapPath({ sido: "경기", sigungu: null });
    const before = useSelection.getState().mapPath;
    useSelection.getState().setMapPath({ sido: "경기", sigungu: null });
    expect(useSelection.getState().mapPath).toBe(before);
  });
  it("전국으로 돌리면 둘 다 비운다", () => {
    useSelection.getState().setMapPath({ sido: "경기", sigungu: "수원시" });
    useSelection.getState().setMapPath({ sido: null, sigungu: null });
    expect(useSelection.getState().mapPath).toEqual({ sido: null, sigungu: null });
  });
});

describe("지도에 표시할 상태", () => {
  beforeEach(() => useSelection.setState({ ...initialSelection, mapLevels: [...MAP_SHOW_ORDER] })); // 켜고 끄는 시험은 모두 켠 상태에서 시작
  it("처음(웹 기본)에는 위험·초과만 선택돼 있다", () => {
    expect(initialSelection.mapLevels).toEqual(["risk", "exceed"]);
    useSelection.setState({ ...initialSelection });
    expect(useSelection.getState().mapLevels).toEqual(["risk", "exceed"]);
  });
  it("누르면 끄고 다시 누르면 켠다(늘 정해진 순서)", () => {
    const { toggleMapLevel } = useSelection.getState();
    toggleMapLevel("warn");
    expect(useSelection.getState().mapLevels).toEqual(["ok", "caution", "risk", "exceed", "gap"]);
    toggleMapLevel("ok");
    expect(useSelection.getState().mapLevels).toEqual(["caution", "risk", "exceed", "gap"]);
    toggleMapLevel("warn");
    expect(useSelection.getState().mapLevels).toEqual(["caution", "warn", "risk", "exceed", "gap"]); // 순서 유지
  });
  it("정상과 공백도 끌 수 있다", () => {
    const { toggleMapLevel } = useSelection.getState();
    toggleMapLevel("ok");
    toggleMapLevel("gap");
    expect(useSelection.getState().mapLevels).toEqual(["caution", "warn", "risk", "exceed"]);
  });
  it("모두 끌 수 있다", () => {
    const { toggleMapLevel } = useSelection.getState();
    for (const l of ["ok", "caution", "warn", "risk", "exceed", "gap"] as const) toggleMapLevel(l);
    expect(useSelection.getState().mapLevels).toEqual([]);
  });
  it("목록의 단계 필터와는 따로다", () => {
    useSelection.getState().toggleMapLevel("exceed");
    expect(useSelection.getState().statusFilter).toEqual([]);
    useSelection.getState().toggleStatus("risk");
    expect(useSelection.getState().mapLevels).toEqual(["ok", "caution", "warn", "risk", "gap"]);
  });
});

describe("차트 물질 두 개 동시에 보기", () => {
  beforeEach(() => useSelection.setState({ ...initialSelection }));
  it("처음에는 NOx만 보인다", () => {
    expect(useSelection.getState().pollutants).toEqual(["nox"]);
  });
  it("SOx를 켜면 둘 다 보이고, 순서는 늘 NOx → SOx다", () => {
    useSelection.getState().togglePollutant("sox");
    expect(useSelection.getState().pollutants).toEqual(["nox", "sox"]);
    useSelection.getState().togglePollutant("nox");
    useSelection.getState().togglePollutant("nox");
    expect(useSelection.getState().pollutants).toEqual(["nox", "sox"]);
  });
  it("하나를 끄면 나머지만 남는다", () => {
    useSelection.getState().togglePollutant("sox");
    useSelection.getState().togglePollutant("nox");
    expect(useSelection.getState().pollutants).toEqual(["sox"]);
  });
  it("둘 다 끌 수도 있다(옛 웹과 같음)", () => {
    useSelection.getState().togglePollutant("nox");
    expect(useSelection.getState().pollutants).toEqual([]);
    useSelection.getState().togglePollutant("sox");
    expect(useSelection.getState().pollutants).toEqual(["sox"]);
    useSelection.getState().togglePollutant("nox");
    expect(useSelection.getState().pollutants).toEqual(["nox", "sox"]); // 다시 켜면 순서는 그대로
  });
});

describe("차트 조회 범위", () => {
  beforeEach(() => useSelection.setState({ ...initialSelection }));
  it("처음에는 지정한 범위가 없다(자료 기준)", () => {
    expect(useSelection.getState().chartRange).toBeNull();
  });
  it("범위를 지정하고 자료 기준으로 되돌린다", () => {
    useSelection.getState().setChartRange({ start: 1, end: 2 });
    expect(useSelection.getState().chartRange).toEqual({ start: 1, end: 2 });
    useSelection.getState().setChartRange(null);
    expect(useSelection.getState().chartRange).toBeNull();
  });
  it("기간 버튼을 누르면 지정한 범위가 지워진다(옛 웹과 같음)", () => {
    useSelection.getState().setChartRange({ start: 1, end: 2 });
    useSelection.getState().setPeriodHours(12);
    expect(useSelection.getState().chartRange).toBeNull();
    expect(useSelection.getState().periodHours).toBe(12);
  });
  it("사업장·굴뚝·물질을 바꿔도 지정한 범위는 유지된다(같은 시간대를 비교할 수 있다)", () => {
    useSelection.getState().setChartRange({ start: 1, end: 2 });
    useSelection.getState().selectSite("A", "1");
    useSelection.getState().selectStack("2");
    useSelection.getState().togglePollutant("sox");
    expect(useSelection.getState().chartRange).toEqual({ start: 1, end: 2 });
  });
});

describe("지도가 보여 주는 범위", () => {
  beforeEach(() => useSelection.setState({ ...initialSelection }));
  it("처음에는 모른다(null)", () => {
    expect(useSelection.getState().mapBounds).toBeNull();
  });
  it("범위를 알리면 저장되고, 같은 값을 다시 알려도 상태 객체는 바뀌지 않는다", () => {
    useSelection.getState().setMapBounds({ minX: 1, minY: 2, maxX: 3, maxY: 4 });
    const first = useSelection.getState().mapBounds;
    expect(first).toEqual({ minX: 1, minY: 2, maxX: 3, maxY: 4 });
    useSelection.getState().setMapBounds({ minX: 1, minY: 2, maxX: 3, maxY: 4 });
    expect(useSelection.getState().mapBounds).toBe(first); // 같은 값이면 다시 그리지 않는다
    useSelection.getState().setMapBounds({ minX: 1, minY: 2, maxX: 3, maxY: 5 });
    expect(useSelection.getState().mapBounds).not.toBe(first);
  });
  it("다시 모른다(null)로 되돌릴 수 있다", () => {
    useSelection.getState().setMapBounds({ minX: 1, minY: 2, maxX: 3, maxY: 4 });
    useSelection.getState().setMapBounds(null);
    expect(useSelection.getState().mapBounds).toBeNull();
  });
});

