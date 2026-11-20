"""사업장 이름 인식: 지역 → 사업장 순서. 굴뚝 번호는 사업장이 정해진 뒤에 읽는다.

규칙만 쓰고 모델·임베딩·형태소 분석기는 쓰지 않는다(빠르고, 같은 입력은 같은 결과).
안전이 먼저다: 자동으로 고르는 것은 (1) 정규화한 이름이 정확히 같을 때, (2) 글자 검색 1위가
기준(적중 비율·점수 차)을 넘을 때뿐이다. 그 밖에는 후보 카드로 묻고, 후보가 없으면 없다고 한다.

11/18 이름 분석 결과(877곳): 합성 고유명사는 형태소 분석기가 쪼개지 못하고, 소재지 말을 뺀 이름은
시·군을 알면 96%, 모르면 49%로 인식된다. 알파벳↔한글 읽기를 통일하면 74% → 100%다.
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from typing import Literal

_MARKERS = re.compile(r"주식회사|\(주\)|\(유\)|\(사\)|\(재\)|\(합\)|유한회사|재단법인|사단법인")
LETTER_NAME = {
    "a": "에이", "b": "비", "c": "씨", "d": "디", "e": "이", "f": "에프", "g": "지",
    "h": "에이치", "i": "아이", "j": "제이", "k": "케이", "l": "엘", "m": "엠", "n": "엔",
    "o": "오", "p": "피", "q": "큐", "r": "알", "s": "에스", "t": "티", "u": "유", "v": "브이",
    "w": "더블유", "x": "엑스", "y": "와이", "z": "제트",
}  # fmt: skip
# 알파벳 읽기로 풀 수 없는 브랜드 말과 속어. 알려진 것만 둔다.
WORD_ALIASES = {"posco": "포스코", "슼": "에스케이"}

# 시도 이름 → 짧은 키. 어떤 표기(서울/서울특별시/충북/충청북도)든 같은 키로 모은다.
SIDO_KEYS = {
    "서울": ("서울특별시", "서울시", "서울"), "부산": ("부산광역시", "부산"),
    "대구": ("대구광역시", "대구"), "인천": ("인천광역시", "인천"),
    "광주": ("광주광역시", "광주"), "대전": ("대전광역시", "대전"),
    "울산": ("울산광역시", "울산"), "세종": ("세종특별자치시", "세종시", "세종"),
    "경기": ("경기도", "경기"), "강원": ("강원특별자치도", "강원도", "강원"),
    "충북": ("충청북도", "충북"), "충남": ("충청남도", "충남"),
    "전북": ("전북특별자치도", "전라북도", "전북"), "전남": ("전라남도", "전남"),
    "경북": ("경상북도", "경북"), "경남": ("경상남도", "경남"),
    "제주": ("제주특별자치도", "제주도", "제주"),
}  # fmt: skip

NOISE_WORDS = {
    "nox", "sox", "질소산화물", "황산화물", "엔옥스", "에스옥스", "굴뚝", "스택", "평균", "최댓값",
    "최대", "최고", "최솟값", "최소", "최저", "합계", "어제", "오늘", "지금", "현재", "최근",
    "알려줘", "알려", "보여줘", "보여", "줘", "주세요", "해줘", "좀", "얼마", "궁금", "확인",
    "조회", "부탁", "값", "수치", "농도", "기준", "대비", "비율", "데이터", "몇", "뭐야", "인가요",
    "그럼", "그러면", "그리고", "지난", "시간", "배출", "측정", "사업장", "물질",
}  # fmt: skip
_PARTICLES = "의은는이가을를도에와과랑"
# 문장 끝 구어체 꼬리("얼마야?", "알려줘요", "궁금해요")는 사업장 이름이 아니다.
# 낱말 전체가 이 모양일 때만 뺀다.
_NOISE_TAIL = re.compile(
    r"(?:얼마|몇|뭐|뭔|어떻|어때)(?:야|죠|지|예요|에요|인가요|인지|이야|이에요|입니까|나요|니|임|인데|나)?"
    r"|(?:알려|보여|확인해|조회해|말해|찾아|가르쳐)(?:줘|줘요|주세요|줄래|줄래요|주라|달라|봐|봐요)"
    r"|궁금(?:해|해요|합니다|한데)"
)


def sido_key(text: str) -> str | None:
    """시도 이름(어떤 표기든)을 짧은 키로. 모르면 None."""
    folded = unicodedata.normalize("NFKC", text)
    if ":" in folded:  # '전남광주통합특별시:광주'처럼 나뉜 표기는 뒤쪽이 실제 시도다.
        folded = folded.rsplit(":", 1)[1]
    for key, names in SIDO_KEYS.items():
        if any(folded.startswith(n) for n in names):
            return key
    for key, names in SIDO_KEYS.items():
        if any(n in folded for n in names if len(n) >= 3):
            return key
    return None


def sigungu_stem(text: str) -> str:
    stem = re.sub(r"(시|군|구)$", "", text.strip())
    return stem if len(stem) >= 2 else text.strip()


def letters_to_korean(text: str) -> str:
    return "".join(LETTER_NAME[c] for c in text.lower() if c in LETTER_NAME)


def canon(text: str) -> str:
    """이름 비교용 정규화: NFKC, 소문자, 법인 표기·공백·기호 제거, 알파벳 약어는 한글 읽기로."""
    t = unicodedata.normalize("NFKC", text).lower()
    t = _MARKERS.sub(" ", t)
    for word, replacement in WORD_ALIASES.items():
        t = t.replace(word, replacement)
    t = re.sub(r"[a-z]{2,}", lambda m: letters_to_korean(m.group(0)), t)
    return re.sub(r"[^0-9a-z가-힣]", "", t)


def _compact_name(text: str) -> str:
    """이름 포함 여부 비교용: NFKC, 법인 표기·공백을 뺀 소문자(글자 읽기 변환 없음)."""
    return re.sub(r"\s+", "", _MARKERS.sub(" ", unicodedata.normalize("NFKC", text))).lower()


def bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)} if len(text) > 1 else {text}


@dataclass(frozen=True)
class Site:
    site_id: str
    business: str
    region: str = ""  # 시도
    sigungu: str = ""
    codes: tuple[str, ...] = ()

    @property
    def sido(self) -> str | None:
        return sido_key(self.region) if self.region else None


@dataclass(frozen=True)
class RegionMention:
    """질문에서 읽은 지역 말 하나. 시도 키 또는 시군 어간 중 하나라도 맞으면 그 지역이다."""

    text: str
    sidos: frozenset[str] = frozenset()
    sigungus: frozenset[str] = frozenset()


Outcome = Literal["AUTO", "CARD", "NONE"]


@dataclass(frozen=True)
class Resolution:
    outcome: Outcome
    sites: tuple[Site, ...] = ()
    path: str = ""  # EXACT, EXACT_REGION, FUZZY_AUTO, FUZZY_CARD, NO_MATCH, COLLISION
    coverage: float = 0.0
    margin: float = 0.0
    name_coverage: float = 0.0
    regions: tuple[str, ...] = field(default_factory=tuple)
    numbers: tuple[str, ...] = ()  # 사업장 말 옆에 남은 단독 숫자(굴뚝 번호일 수 있음)
    by_code: bool = False  # 같은 이름 여럿 중 말한 굴뚝 번호가 있는 곳으로 좁혔다


# 글자 검색 자동 선택 기준. 이름 분석 변형 시험(11/18)에서 틀린 자동 선택이 0이 되도록 보정했다.
AUTO_COVERAGE = 0.75  # 질문 글자(IDF 가중)가 1위 이름에 들어 있는 비율
AUTO_MARGIN = 0.30  # (1위 − 2위) / 1위 점수
AUTO_NAME_COVERAGE = (
    0.70  # 질문이 1위 이름 글자(IDF 가중)를 채운 비율. 이름 일부만 말한 질문은 묻는다
)
MIN_COVERAGE = 0.25  # 이보다 낮으면 후보로도 내지 않는다
MAX_CARD = 3


class SiteResolver:
    def __init__(self, sites: list[Site]) -> None:
        self.sites = list(sites)
        self._canon = [canon(s.business) for s in self.sites]
        self._by_canon: dict[str, list[int]] = defaultdict(list)
        for i, c in enumerate(self._canon):
            if c:
                self._by_canon[c].append(i)
        self._grams = [bigrams(c) for c in self._canon]
        df: Counter[str] = Counter(g for grams in self._grams for g in grams)
        n = len(self.sites)
        self._idf = {g: math.log(n / c) + 0.1 for g, c in df.items()}
        self._inverted: dict[str, list[int]] = defaultdict(list)
        for i, grams in enumerate(self._grams):
            for g in grams:
                self._inverted[g].append(i)
        self._sigungu_stems: dict[str, set[str]] = defaultdict(set)
        for s in self.sites:
            if s.sigungu:
                self._sigungu_stems[sigungu_stem(s.sigungu)].add(s.sigungu)

    @property
    def known_text(self) -> str:
        """사업장·지역 이름 전체를 이어 붙인 글. 질문의 낱말이 이름의 일부인지 확인하는 데 쓴다."""
        if not hasattr(self, "_known_text"):
            regions = [canon(n) for names in SIDO_KEYS.values() for n in names]
            stems = [canon(s.sigungu) for s in self.sites if s.sigungu]
            self._known_text = "".join([*self._canon, *regions, *stems])
        return self._known_text

    # ── 지역 ──────────────────────────────────────────────────────────
    def _ensure_name_index(self) -> None:
        if not hasattr(self, "_name_keys"):
            by_key: dict[str, list[Site]] = defaultdict(list)
            for s in self.sites:
                by_key[_compact_name(s.business)].append(s)
            self._sites_by_key = by_key
            self._name_keys = sorted((k for k in by_key if len(k) >= 3), key=len, reverse=True)

    def named_sites(self, text: str) -> list[Site]:
        """질문 안에 이름 전체가 그대로 들어 있는 사업장(가장 긴 이름). 이름 밖의 말은 상관없다.

        `resolve`는 질문 전체가 이름에 가까워야 자동으로 고르지만, 법령 질문처럼 이름 뒤에 긴 문장이
        붙으면 이 함수로 이름만 찾는다. 같은 이름이 여러 곳이면 모두 돌려준다(고를 수 없다는 뜻)."""
        self._ensure_name_index()
        compact = _compact_name(text)
        for key in self._name_keys:
            if key in compact:
                return list(self._sites_by_key[key])
        return []

    def _strip_site_names(self, folded: str) -> str:
        """사업장 이름 전체가 질문 안에 있으면 그 부분을 뺀 글을 돌려준다(없으면 그대로).

        이름 속 글자는 지역이 아니다: `대원화성㈜`의 "화성", `구미하수처리장`의 "구미"를
        시·군으로 읽으면 그 사업장이 소재지가 달라 후보에서 빠진다.
        지역 말이 이름 밖에도 있으면("화성 대원화성㈜") 남는다.
        """
        self._ensure_name_index()
        compact = _compact_name(folded)
        hit = False
        for key in self._name_keys:
            if key in compact:
                compact = compact.replace(key, " ")
                hit = True
        return compact if hit else folded

    def parse_regions(self, text: str) -> list[RegionMention]:
        """질문에 나온 시도·시군 말을 찾는다. 같은 글자를 두 번 세지 않도록 긴 말부터 지운다."""
        folded = self._strip_site_names(unicodedata.normalize("NFKC", text))
        found: list[RegionMention] = []
        candidates: list[tuple[str, RegionMention]] = []
        for key, names in SIDO_KEYS.items():
            for name in names:
                candidates.append((name, RegionMention(name, sidos=frozenset({key}))))
        for stem, full in self._sigungu_stems.items():
            for word in {stem, *full}:
                candidates.append((word, RegionMention(word, sigungus=frozenset({stem}))))
        for word, mention in sorted(candidates, key=lambda c: -len(c[0])):
            if len(word) >= 2 and word in folded:
                # '광주'처럼 시도와 시군에 모두 있는 말은 둘 다 후보로 합친다.
                same = [m for m in found if m.text == word]
                if same:
                    merged = RegionMention(
                        word, same[0].sidos | mention.sidos, same[0].sigungus | mention.sigungus
                    )
                    found[found.index(same[0])] = merged
                elif not any(word in m.text for m in found):
                    found.append(mention)
        return found

    def sites_in_region(self, text: str) -> list[Site]:
        """질문 속 지역 말에 속한 사업장 목록(지역 말이 없으면 빈 목록)."""
        mentions = self.parse_regions(text)
        return [s for s in self.sites if mentions and self._in_region(s, mentions)]

    def _in_region(self, site: Site, mentions: list[RegionMention]) -> bool:
        for m in mentions:
            ok = (site.sido in m.sidos) or (sigungu_stem(site.sigungu) in m.sigungus)
            if not ok:
                return False
        return True

    # ── 질문 정리 ─────────────────────────────────────────────────────
    @staticmethod
    def clean_mention(text: str, keep_numbers: bool = False) -> str:
        """질문에서 사업장 말만 남긴다: 굴뚝 번호·기간·물질·집계 말·요청 말을 뺀다.

        단독 숫자는 이름의 일부일 수도(서해그린에너지 2) 굴뚝 번호일 수도 있어 선택해서 남긴다."""
        t = unicodedata.normalize("NFKC", text)
        t = re.sub(r"굴뚝\s*\d+|\d+\s*번\s*굴뚝|\d+\s*번(?!째)|\d+\s*호기", " ", t)
        t = re.sub(r"\d{4}\s*년|\d{1,2}\s*월\s*\d{1,2}\s*일", " ", t)
        t = re.sub(r"(?:최근|지난)\s*\d+\s*(?:시간|일|주|달|개월)", " ", t)
        kept = []
        for token in re.split(r"\s+", t):
            bare = token.strip("?!.,~")
            stripped = bare[:-1] if bare and bare[-1] in _PARTICLES else bare
            lowered = bare.lower()
            if (
                not bare
                or lowered in NOISE_WORDS
                or stripped.lower() in NOISE_WORDS
                or _NOISE_TAIL.fullmatch(lowered)
                or re.fullmatch(r"[?!.,~]*", bare)
                or (not keep_numbers and re.fullmatch(r"[?!.,~\d]*", bare))
            ):
                continue
            kept.append(bare)
        return " ".join(kept)

    # ── 인식 ──────────────────────────────────────────────────────────
    def resolve(self, text: str, mentions: list[RegionMention] | None = None) -> Resolution:
        """사업장을 인식한다. 말한 굴뚝 번호가 있는 사업장을 우선한다(같은 이름 여럿·후보 순서)."""
        result = self._resolve(text, mentions)
        code = stack_code_from(text)
        if not code or result.outcome != "CARD" or result.path == "NUMBER_AMBIGUOUS":
            return result
        owners = tuple(s for s in result.sites if code in s.codes)
        if not owners or len(owners) == len(result.sites):
            return result
        if len(owners) == 1 and result.path == "COLLISION":
            return replace(
                result, outcome="AUTO", sites=owners, path="COLLISION_CODE", by_code=True
            )
        rest = tuple(s for s in result.sites if code not in s.codes)
        return replace(result, sites=(*owners, *rest))

    def similar_with_code(self, text: str, code: str, exclude: str = "") -> list[Site]:
        """이름이 비슷하고 그 굴뚝 번호가 있는 사업장(번호 안내용). 이름 겹침이 낮으면 뺀다."""
        query = canon(self.clean_mention(text))
        grams = bigrams(query)
        total = sum(self._idf.get(g, 0.1) for g in grams) or 1.0
        scores: dict[int, float] = defaultdict(float)
        for g in grams:
            if g in self._idf:
                for i in self._inverted[g]:
                    scores[i] += self._idf[g]
        ranked = sorted(scores, key=lambda i: (-scores[i], self.sites[i].site_id))
        return [
            self.sites[i]
            for i in ranked
            if scores[i] / total >= MIN_COVERAGE
            and code in self.sites[i].codes
            and self.sites[i].site_id != exclude
        ][:MAX_CARD]

    def _resolve(self, text: str, mentions: list[RegionMention] | None = None) -> Resolution:
        regions = mentions if mentions is not None else self.parse_regions(text)
        kept = canon(self.clean_mention(text, keep_numbers=True))
        dropped = canon(self.clean_mention(text, keep_numbers=False))
        numbers = tuple(
            re.findall(
                r"\d+",
                re.sub(r"[가-힣a-z]+\d+|\d+[가-힣a-z]+", " ", self.clean_mention(text, True)),
            )
        )
        region_texts = tuple(m.text for m in regions)
        pool = [i for i in range(len(self.sites)) if self._in_region(self.sites[i], regions)]
        # 지역 말이 이름의 일부인 경우를 위해, 지역으로 거르면 후보가 없을 때는 거르지 않는다.
        used_region = bool(regions) and bool(pool)
        if not pool:
            pool = list(range(len(self.sites)))
        if not dropped and not kept:
            return Resolution("NONE", path="NO_MATCH")
        with_numbers = self._exact(kept, pool, used_region, region_texts) if kept else None
        without = self._exact(dropped, pool, used_region, region_texts) if dropped else None
        if kept != dropped and with_numbers and without:
            a = {s.site_id for s in with_numbers.sites}
            b = {s.site_id for s in without.sites}
            if a != b:
                # 숫자가 이름의 일부인지 굴뚝 번호인지 알 수 없다(서해그린에너지 2): 묻는다.
                both = tuple({s.site_id: s for s in (*with_numbers.sites, *without.sites)}.values())
                return Resolution(
                    "CARD", both[:MAX_CARD], "NUMBER_AMBIGUOUS", 1.0, 0.0, 1.0, region_texts
                )
        if with_numbers:
            return with_numbers
        if without:
            return Resolution(
                without.outcome,
                without.sites,
                without.path,
                without.coverage,
                without.margin,
                without.name_coverage,
                without.regions,
                numbers,
            )
        result = self._fuzzy(dropped or kept, pool, region_texts if used_region else ())
        return Resolution(
            result.outcome,
            result.sites,
            result.path,
            result.coverage,
            result.margin,
            result.name_coverage,
            result.regions,
            numbers,
        )

    def _exact(
        self, query: str, pool: list[int], used_region: bool, regions: tuple[str, ...]
    ) -> Resolution | None:
        in_pool = set(pool)
        # 1) 정규화한 이름이 질문과 정확히 같다.
        same = [i for i in self._by_canon.get(query, []) if i in in_pool]
        if not same:
            # 2) 이름 전체가 질문 안에 있고(가장 긴 것), 지역 말을 빼면 남는 말이 없다.
            #    남는 말이 있으면 더 구체적인 다른 사업장을 말했을 수 있어 정확 일치로 보지 않는다.
            best: tuple[str, list[int]] | None = None
            for a in range(len(query)):
                for b in range(a + 2, len(query) + 1):
                    name = query[a:b]
                    idxs = self._by_canon.get(name)
                    if idxs and (best is None or len(name) > len(best[0])):
                        hits = [k for k in idxs if k in in_pool]
                        if hits:
                            best = (name, hits)
            if best:
                rest = query.replace(best[0], "", 1)
                for m in regions:
                    rest = rest.replace(canon(m), "", 1)
                if not rest:
                    same = best[1]
        if not same:
            return None
        sites = tuple(self.sites[i] for i in same)
        if len(sites) == 1:
            path = "EXACT_REGION" if used_region else "EXACT"
            return Resolution("AUTO", sites, path, 1.0, 1.0, 1.0, regions)
        # 같은 이름이 여러 곳(다른 지역): 지역을 몰랐으면 묻는다.
        return Resolution("CARD", sites[:MAX_CARD], "COLLISION", 1.0, 0.0, 1.0, regions)

    def _fuzzy(self, query: str, pool: list[int], regions: tuple[str, ...]) -> Resolution:
        grams = bigrams(query)
        total = sum(self._idf.get(g, 0.1) for g in grams) or 1.0
        in_pool = set(pool)
        scores: dict[int, float] = defaultdict(float)
        for g in grams:
            weight = self._idf.get(g)
            if weight is None:
                continue
            for i in self._inverted[g]:
                if i in in_pool:
                    scores[i] += weight
        if not scores:
            return Resolution("NONE", path="NO_MATCH", regions=regions)
        ordered = sorted(scores, key=lambda i: (-scores[i], self.sites[i].site_id))
        top = scores[ordered[0]]
        second = scores[ordered[1]] if len(ordered) > 1 else 0.0
        coverage = top / total
        margin = (top - second) / top if top else 0.0
        doc_total = sum(self._idf.get(g, 0.1) for g in self._grams[ordered[0]]) or 1.0
        name_coverage = top / doc_total
        if coverage < MIN_COVERAGE:
            return Resolution("NONE", path="NO_MATCH", coverage=coverage, regions=regions)
        if (
            coverage >= AUTO_COVERAGE
            and margin >= AUTO_MARGIN
            and name_coverage >= AUTO_NAME_COVERAGE
        ):
            return Resolution(
                "AUTO",
                (self.sites[ordered[0]],),
                "FUZZY_AUTO",
                coverage,
                margin,
                name_coverage,
                regions,
            )
        cards = tuple(self.sites[i] for i in ordered[:MAX_CARD])
        return Resolution("CARD", cards, "FUZZY_CARD", coverage, margin, name_coverage, regions)


# ── 굴뚝 번호: 사업장이 정해진 뒤에 읽는다 ─────────────────────────────────
_STACK_CODE = re.compile(r"굴뚝\s*(\d+)|(\d+)\s*번\s*굴뚝|(\d+)\s*번(?!째)|(\d+)\s*호기")


def stack_code_from(text: str, site: Site | None = None) -> str | None:
    """'굴뚝 N', 'N번 굴뚝', 'N번', 'N호기'만 굴뚝 번호로 읽는다.

    사업장 이름에 묶인 숫자(울산1공장, 제2공장, 용성2단지)는 번호가 아니다. 이름을 먼저 지운다.
    """
    t = unicodedata.normalize("NFKC", text)
    if site is not None:
        name = re.sub(r"\s+", "", _MARKERS.sub("", unicodedata.normalize("NFKC", site.business)))
        compact = re.sub(r"\s+", "", t)
        if name and name in compact:
            t = compact.replace(name, " ", 1)
    match = _STACK_CODE.search(t)
    if not match:
        return None
    return next(g for g in match.groups() if g)
