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


# ── 이름 속 지역 글자, 구어체 꼬리 (E2E 시험 결함 1·2) ─────────────────────────
OVERLAP = [
    Site("a1", "대원화성㈜", "경기도", "평택시", ("7",)),
    Site("a2", "화성그린에너지", "경기도", "화성시", ("1",)),
    Site("a3", "삼성전자㈜화성사업장", "경기도", "화성시", ("1",)),
    Site("a4", "구미하수처리장", "경상북도", "칠곡군", ("1",)),
    Site("a5", "구미시 자원회수시설", "경상북도", "구미시", ("1",)),
    Site("a6", "㈜휴스틸 당진공장", "충청남도", "당진시", ("13",)),
    Site("a7", "㈜휴스틸 포항공장", "경상북도", "포항시", ("2",)),
]


@pytest.fixture(scope="module")
def overlap() -> SiteResolver:
    return SiteResolver(OVERLAP)


def test_a_region_word_inside_the_exact_name_is_not_read_as_a_region(overlap):
    # 대원화성㈜는 평택시 소재다. 이름 속 "화성"을 지역으로 읽으면 후보에서 빠졌다.
    found = overlap.resolve("대원화성㈜")
    assert found.outcome == "AUTO" and ids(found) == ["a1"]
    asked = overlap.resolve("어제 대원화성㈜ 굴뚝 7 NOx 최소 알려줘")
    assert asked.outcome == "AUTO" and ids(asked) == ["a1"]
    assert overlap.parse_regions("대원화성㈜") == []


def test_another_site_named_in_the_same_region_word_is_still_found(overlap):
    found = overlap.resolve("구미하수처리장")  # 칠곡군 소재인데 이름에 "구미"가 있다
    assert found.outcome == "AUTO" and ids(found) == ["a4"]
    other = overlap.resolve("구미시 자원회수시설")
    assert other.outcome == "AUTO" and ids(other) == ["a5"]


def test_real_region_words_are_still_read_as_regions(overlap):
    assert [m.text for m in overlap.parse_regions("화성 NOx 평균")] == ["화성"]
    assert [m.text for m in overlap.parse_regions("충북 동서식품")] == ["충북"]
    assert {s.site_id for s in overlap.sites_in_region("화성 사업장")} == {"a2", "a3"}


@pytest.mark.parametrize(
    "tail", ["얼마야?", "얼마죠", "얼마예요?", "알려줘요", "궁금해요", "몇이야"]
)
def test_spoken_endings_are_not_part_of_the_business_name(overlap, tail):
    text = f"어제 ㈜휴스틸 당진공장 13번 굴뚝 질소산화물 평균 {tail}"
    assert overlap.clean_mention(text) == "(주)휴스틸 당진공장"  # NFKC로 ㈜ → (주)
    found = overlap.resolve(text)
    assert found.outcome == "AUTO" and ids(found) == ["a6"]


def test_a_business_word_that_only_contains_an_ending_is_kept(overlap):
    # 꼬리 말은 낱말 전체가 그 모양일 때만 뺀다.
    assert overlap.clean_mention("나와에너지 알려줘") == "나와에너지"


def test_named_sites_finds_a_name_inside_a_long_sentence(overlap):
    law = "대원화성㈜ 굴뚝 7이 허용기준을 넘는다고 가정하면 개선명령 같은 어떤 조치를 받게 되나요?"
    assert [s.site_id for s in overlap.named_sites(law)] == ["a1"]
    # 이름 전체가 없으면 찾지 않는다(비슷한 글자만으로는 고르지 않는다)
    assert overlap.named_sites("화성 사업장 NOx 평균") == []
    assert overlap.named_sites("허용기준을 넘으면 어떤 조치를 받나요?") == []


def test_named_sites_returns_every_site_that_shares_the_name(overlap):
    # 같은 이름이 여럿이면 하나로 고를 수 없다는 뜻으로 모두 돌려준다
    twin = SiteResolver(
        [
            Site("t1", "동서식품(주)", "충청북도", "청주시", ("1",)),
            Site("t2", "동서식품(주)", "인천광역시", "서구", ("1",)),
        ]
    )
    found = twin.named_sites("동서식품 굴뚝 1이 허용기준을 넘으면")
    assert {s.site_id for s in found} == {"t1", "t2"}
