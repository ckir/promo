from promo.networks import LIMITS, measured_length
from promo.postprocess import (
    check_length,
    finalize,
    hashtag_count,
    inject_disclosures,
    prohibited_matches,
    shares_opening,
    tag_links,
    too_similar,
    unsourced_numbers,
)
from promo.schema import Network


def test_tag_links_preserves_fragment_and_owner_utm():
    out = tag_links(
        "Buy: https://e.com/p?utm_source=mine#pricing",
        "https://e.com/p?utm_source=mine#pricing",
        Network.x,
        "camp",
        "teaser",
    )
    assert out.endswith("#pricing")
    assert "utm_source=mine" in out and out.count("utm_source") == 1
    assert "utm_campaign=camp" in out and "utm_content=teaser" in out
    assert "utm_medium=social" in out


def test_tag_links_adds_params_in_order_and_keeps_existing_query():
    out = tag_links("see https://e.com/p?a=1 now", "https://e.com/p?a=1", Network.bluesky, "c", "b")
    assert out == (
        "see https://e.com/p?a=1&utm_source=bluesky&utm_medium=social"
        "&utm_campaign=c&utm_content=b now"
    )


def test_tag_links_only_touches_target_url():
    text = "a https://e.com/p b https://other.com/x c https://e.com/page d https://e.com/p"
    out = tag_links(text, "https://e.com/p", Network.x, "c", "b")
    assert "https://other.com/x " in out
    assert "https://e.com/page " in out
    assert out.count("utm_source=x") == 2


def test_disclosure_added_once_case_insensitive():
    out = inject_disclosures("Hello world", ["#ad", "Sponsored"])
    assert out == "Hello world\n#ad Sponsored"
    assert inject_disclosures(out, ["#AD", "sponsored"]) == out
    assert inject_disclosures("Hi #AD", ["#ad", "Sponsored"]) == "Hi #AD\nSponsored"
    assert inject_disclosures("Hi", []) == "Hi"


def test_year_not_in_manifest_is_unsourced(manifest):
    assert unsourced_numbers("Launching 2026!", manifest, "https://e.com/p") == ["2026"]


def test_trailing_punctuation_stripped_and_unique(manifest):
    got = unsourced_numbers("In 2026. Again 2026, then 77.", manifest, "https://e.com/p")
    assert got == ["2026", "77"]


def test_number_inside_tagged_url_is_sourced(manifest):
    url = "https://e.com/p?utm_content=beat-2"
    assert unsourced_numbers("go https://e.com/p?utm_content=beat-2", manifest, url) == []


def test_manifest_number_is_sourced(manifest):
    assert unsourced_numbers("Cuts setup time by 40%", manifest, "https://e.com/p") == []


def test_prohibited_case_insensitive():
    assert prohibited_matches("GUARANTEED results", ["guaranteed"]) == ["guaranteed"]
    assert prohibited_matches("fine", ["guaranteed"]) == []


def test_too_similar_threshold():
    assert too_similar("Meet the Acme Widget today", "meet the acme widget today!")
    assert not too_similar("Meet the Acme Widget today", "Completely different words here")
    assert not too_similar("abcd", "abce", threshold=0.99)


def test_shares_opening():
    assert shares_opening("Big news! Details inside.", "big NEWS. other stuff")
    assert not shares_opening("Big news! x", "Small news! x")
    assert shares_opening("Hello there, friend", "hello there friend")
    assert not shares_opening("", "")


def test_hashtag_count_ignores_url_fragments():
    assert hashtag_count("#one and #two, see https://e.com/p#pricing") == 2


def test_check_length_uses_network_measure():
    assert check_length("x" * 280, Network.x, 280)
    assert not check_length("x" * 281, Network.x, 280)


def test_finalize_order_tagging_before_length(manifest):
    beat = manifest.beats[0]
    url = manifest.product.target_url
    filler = "w" * (270 - len(url) - 1)
    text = f"{filler} {url}"
    assert len(text) == 270
    out, warnings = finalize(
        text,
        manifest=manifest,
        beat=beat,
        network=Network.x,
        campaign="camp",
        limit=LIMITS[Network.x],
        hashtag_cap=3,
    )
    assert len(out) > 280  # tagging pushed the literal length over
    assert measured_length(out, Network.x) <= 280
    assert "too_long" not in warnings
    out_b, warnings_b = finalize(
        text,
        manifest=manifest,
        beat=beat,
        network=Network.bluesky,
        campaign="camp",
        limit=LIMITS[Network.bluesky],
        hashtag_cap=3,
    )
    assert len(out_b) > 300
    assert warnings_b == ["too_long"]


def test_finalize_warning_order_and_once_each(manifest):
    beat = manifest.beats[0]
    text = "Guaranteed guaranteed 2026 2027 #a #b #c #d " + "z" * 300
    _, warnings = finalize(
        text,
        manifest=manifest,
        beat=beat,
        network=Network.x,
        campaign="camp",
        limit=280,
        hashtag_cap=3,
    )
    assert warnings == ["too_long", "unsourced_number", "prohibited_claim", "too_many_hashtags"]


def test_tag_links_leaves_url_continuations_alone():
    t = "https://e.com/p"
    for other in ("https://e.com/p.html", "https://e.com/p:80", "https://e.com/p.evil.com"):
        assert tag_links(f"go {other} now", t, Network.x, "c", "b") == f"go {other} now"
    assert tag_links("x https://e.com.evil.com y", "https://e.com", Network.x, "c", "b") == (
        "x https://e.com.evil.com y"
    )


def test_tag_links_trailing_punctuation_and_repeats():
    for tail in (".", ",", ")", "!"):
        out = tag_links(f"see https://e.com/p{tail}", "https://e.com/p", Network.x, "c", "b")
        assert (
            out
            == f"see https://e.com/p?utm_source=x&utm_medium=social&utm_campaign=c&utm_content=b{tail}"
        )
    out = tag_links("https://e.com/p and https://e.com/p", "https://e.com/p", Network.x, "c", "b")
    assert out.count("utm_source=x") == 2


def test_tag_links_no_path_and_case_insensitive():
    out = tag_links("visit https://e.com now", "https://e.com", Network.x, "c", "b")
    assert "utm_source=x" in out and out.startswith("visit https://e.com?utm_")
    out = tag_links("visit HTTPS://E.COM/p now", "https://e.com/p", Network.x, "c", "b")
    assert "utm_source=x" in out


def test_number_token_membership_not_substring(manifest):
    m = manifest.model_copy(
        update={
            "product": manifest.product.model_copy(update={"proof_points": ["120 users", "40%"]})
        }
    )
    assert unsourced_numbers("12 and 40 and 120", m, "https://e.com/p") == ["12"]
    assert unsourced_numbers("4", m, "https://e.com/p") == ["4"]


def test_hashtag_count_excludes_url_fragments():
    assert hashtag_count("https://e.com/p/#pricing and https://e.com/#top") == 0
    assert hashtag_count("#a https://e.com/#top #b") == 2


def test_disclosure_word_boundaries():
    assert inject_disclosures("Try #address", ["#ad"]) == "Try #address\n#ad"
    assert inject_disclosures("Try #AD", ["#ad"]) == "Try #AD"
    assert inject_disclosures("Sponsored.", ["Sponsored."]) == "Sponsored."
    assert inject_disclosures("Hello\n", ["#ad"]) == "Hello\n#ad"
