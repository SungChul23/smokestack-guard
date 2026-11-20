"""사업장 이름 인식: 지역 → 사업장 → 굴뚝 순서, 안전한 자동 선택, 모르면 카드."""

import pytest

from app.agent.names import (
    Site,
    SiteResolver,
    canon,
    sido_key,
    stack_code_from,
)

SITES = [
    Site("s1", "㈜가나에너지", "경기도", "안산시", ("1", "2")),
    Site("s2", "다라화학(주)", "울산광역시", "남구", ("3",)),
    Site("s3", "동서식품(주)", "충청북도", "청주시", ("1",)),
    Site("s4", "동서식품(주)", "인천광역시", "서구", ("1",)),
    Site("s5", "한국남부발전㈜ 삼척발전본부", "강원특별자치도", "삼척시", ("1", "2")),
    Site("s6", "한국남부발전㈜ 하동빛드림본부", "경상남도", "하동군", ("1",)),
    Site("s7", "한화솔루션㈜ 울산1공장", "울산광역시", "남구", ("1", "2", "3")),
    Site("s8", "한화솔루션㈜ 울산3공장", "울산광역시", "남구", ("1",)),
    Site("s9", "서해그린에너지㈜", "충청남도", "서산시", ("1",)),
    Site("s10", "서해그린에너지㈜ 2", "충청남도", "서산시", ("1",)),
    Site("s11", "에스케이에너지㈜", "울산광역시", "남구", ("1", "2", "3", "4")),
    Site("s12", "㈜KCC 문막공장", "강원특별자치도", "원주시", ("1", "2")),
    Site("s13", "삼정펄프㈜", "경기도", "안성시", ("1",)),
    Site("s14", "삼정펄프㈜ 청주공장", "충청북도", "청주시", ("1",)),
]


@pytest.fixture(scope="module")
def resolver() -> SiteResolver:
    return SiteResolver(SITES)


def ids(res):
    return [s.site_id for s in res.sites]


# ── 정규화 ────────────────────────────────────────────────────────────
def test_corporate_markers_spaces_and_case_are_ignored():
    assert (
        len(
            {
                canon(n)
                for n in ["㈜가나에너지", "(주)가나에너지", "가나 에너지", "주식회사 가나에너지"]
            }
        )
        == 1
    )


def test_latin_abbreviations_match_their_korean_readings():
    assert canon("SK에너지") == canon("에스케이에너지")
    assert canon("KCC 문막공장") == canon("케이씨씨 문막공장")
    assert canon("슼에너지") == canon("에스케이에너지")
    assert canon("POSCO") == canon("포스코")


def test_sido_names_in_any_notation_share_a_key():
    assert sido_key("전남광주통합특별시:광주") == "광주"
    assert sido_key("강원특별자치도") == sido_key("강원도") == "강원"
    assert sido_key("충청남도") == sido_key("충남") == "충남"
    assert sido_key("없는곳") is None


# ── 정확 일치가 먼저 ──────────────────────────────────────────────────
def test_exact_name_in_a_sentence_is_selected():
    for text in ["가나에너지", "(주)가나에너지", "어제 가나에너지 굴뚝 1 NOx 평균 알려줘"]:
        res = resolver_for().resolve(text)
        assert res.outcome == "AUTO" and ids(res) == ["s1"] and res.path == "EXACT"


def resolver_for() -> SiteResolver:
    return SiteResolver(SITES)


def test_short_name_wins_over_longer_names_that_contain_it(resolver):
    assert ids(resolver.resolve("삼정펄프")) == ["s13"]
    assert ids(resolver.resolve("삼정펄프 청주공장")) == ["s14"]


def test_latin_and_korean_readings_are_the_same_site(resolver):
    for text in [
        "SK에너지",
        "에스케이에너지",
        "슼에너지",
        "KCC 문막공장",
        "케이씨씨 문막공장",
        "KCC문막공장",
    ]:
        assert resolve_ids(resolver, text) in (["s11"], ["s12"]), text
    assert resolve_ids(resolver, "SK에너지") == ["s11"]
    assert resolve_ids(resolver, "케이씨씨 문막공장") == ["s12"]


def resolve_ids(resolver, text):
    res = resolver.resolve(text)
    assert res.outcome == "AUTO", (text, res)
    return ids(res)


# ── 지역이 먼저 ───────────────────────────────────────────────────────
def test_same_name_in_two_regions_asks_unless_the_region_is_given(resolver):
    res = resolver.resolve("동서식품")
    assert res.outcome == "CARD" and res.path == "COLLISION"
    assert sorted(ids(res)) == ["s3", "s4"]
    assert ids(resolver.resolve("충북 동서식품")) == ["s3"]
    assert ids(resolver.resolve("인천 동서식품")) == ["s4"]
    assert ids(resolver.resolve("청주 동서식품")) == ["s3"]  # 시·군
    assert resolver.resolve("충청북도 동서식품").path == "EXACT_REGION"


def test_region_words_are_read_for_both_sido_and_sigungu(resolver):
    assert [m.sidos for m in resolver.parse_regions("충북 동서식품")] == [frozenset({"충북"})]
    assert any("삼척" in m.sigungus for m in resolver.parse_regions("삼척 발전본부"))


def test_a_region_that_excludes_everything_is_ignored(resolver):
    # 제주에는 다라화학이 없다. 지역 말 때문에 정답을 놓치지 않는다.
    res = resolver.resolve("제주 다라화학")
    assert res.outcome == "AUTO" and ids(res) == ["s2"]


# ── 이름 속 숫자와 굴뚝 번호 ──────────────────────────────────────────
def test_digits_that_belong_to_the_name_are_not_stack_codes(resolver):
    assert ids(resolver.resolve("한화솔루션 울산1공장")) == ["s7"]
    assert ids(resolver.resolve("한화솔루션 울산3공장")) == ["s8"]
    assert stack_code_from("한화솔루션 울산1공장") is None
    assert stack_code_from("한화솔루션 울산1공장 굴뚝 3") == "3"
    assert stack_code_from("한화솔루션 울산1공장 3번") == "3"
    assert stack_code_from("한화솔루션 울산1공장 2호기") == "2"
    assert stack_code_from("가나에너지 굴뚝 2") == "2"


def test_a_digit_after_a_name_is_asked_when_both_readings_exist(resolver):
    res = resolver.resolve("서해그린에너지 2")
    assert res.outcome == "CARD" and res.path == "NUMBER_AMBIGUOUS"
    assert sorted(ids(res)) == ["s10", "s9"]
    assert ids(resolver.resolve("서해그린에너지")) == ["s9"]
    assert ids(resolver.resolve("서해그린에너지 굴뚝 2")) == ["s9"]


def test_a_bare_number_is_kept_for_the_stack_step(resolver):
    res = resolver.resolve("가나에너지 2")
    assert res.outcome == "AUTO" and ids(res) == ["s1"] and res.numbers == ("2",)


# ── 글자 검색은 확실할 때만 고르고, 아니면 묻는다 ──────────────────────
def test_fragments_are_asked_not_guessed(resolver):
    res = resolver.resolve("한국남부발전")
    assert res.outcome == "CARD" and set(ids(res)) == {"s5", "s6"}
    res = resolver.resolve("발전본부")
    assert res.outcome in ("CARD", "NONE")


def test_a_fragment_inside_one_region_is_still_not_auto(resolver):
    res = resolver.resolve("삼척 남부발전")
    assert res.outcome in ("AUTO", "CARD") and ids(res)[0] == "s5"
    if res.outcome == "AUTO":
        assert res.path != "FUZZY_AUTO" or res.name_coverage >= 0.7


def test_unknown_or_empty_text_is_none(resolver):
    for text in ["", "알려줘", "전혀없는이름의회사", "어제 NOx 평균"]:
        assert resolver.resolve(text).outcome == "NONE", text


def test_request_words_are_not_read_as_a_name(resolver):
    assert resolver.clean_mention("어제 다라화학 굴뚝 3 NOx 평균 알려줘") == "다라화학"
    assert resolver.clean_mention("다라화학 굴뚝 알려줘") == "다라화학"
    assert resolver.clean_mention("11월 10일 다라화학 지난 3시간") == "다라화학"
