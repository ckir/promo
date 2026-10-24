"""Deterministic post-processing checks (spec section 6). Pure functions over strings."""

import re
from difflib import SequenceMatcher
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from promo.networks import measured_length
from promo.schema import Beat, Manifest, Network

_NUMBER = re.compile(r"\d[\d.,]*")
_HASHTAG = re.compile(r"(?<!\w)#\w+")
_URL_RE = re.compile(r"https?://\S+")
_SENTENCE_END = re.compile(r"[.!?\n]")
_PUNCT = re.compile(r"[^\w\s]")


def inject_disclosures(text: str, disclosures: list[str]) -> str:
    missing = [
        d for d in disclosures if not re.search(r"(?<!\w)" + re.escape(d) + r"(?!\w)", text, re.I)
    ]
    if not missing:
        return text
    return text.rstrip() + "\n" + " ".join(missing)


def _tag_one(url: str, network: Network, campaign: str, beat: str) -> str:
    parts = urlsplit(url)
    pairs = parse_qsl(parts.query, keep_blank_values=True)
    existing = {k for k, _ in pairs}
    added = [
        ("utm_source", network.value),
        ("utm_medium", "social"),
        ("utm_campaign", campaign),
        ("utm_content", beat),
    ]
    pairs.extend((k, v) for k, v in added if k not in existing)
    return urlunsplit(parts._replace(query=urlencode(pairs)))


def tag_links(text: str, target_url: str, network: Network, campaign: str, beat: str) -> str:
    if not target_url:
        return text
    tagged = _tag_one(target_url, network, campaign, beat)
    pattern = re.compile(re.escape(target_url) + r"(?![\w/~%:&=+-]|\.\w|[?#]\S)", re.I)
    return pattern.sub(lambda _m: tagged, text)


def check_length(text: str, network: Network, limit: int) -> bool:
    """True when the text fits the limit as the network measures it."""
    return measured_length(text, network) <= limit


def _manifest_strings(manifest: Manifest) -> list[str]:
    p = manifest.product
    out = [
        p.name,
        p.tagline,
        p.problem_statement,
        p.target_url,
        p.audience,
        *p.key_features,
        *p.proof_points,
        *p.prohibited_claims,
        *p.disclosures,
    ]
    out.extend(b.notes for b in manifest.beats if b.notes)
    return out


def unsourced_numbers(text: str, manifest: Manifest, tagged_url: str) -> list[str]:
    haystack = "\n".join([*_manifest_strings(manifest), tagged_url])
    sourced = {m.group(0).rstrip(".,") for m in _NUMBER.finditer(haystack)}
    found: list[str] = []
    for m in _NUMBER.finditer(text):
        num = m.group(0).rstrip(".,")
        if num and num not in sourced and num not in found:
            found.append(num)
    return found


def prohibited_matches(text: str, phrases: list[str]) -> list[str]:
    lowered = text.lower()
    return [p for p in phrases if p and p.lower() in lowered]


def too_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() > threshold


def _opening(text: str) -> str:
    m = _SENTENCE_END.search(text)
    first = text[: m.start()] if m else text
    return _PUNCT.sub("", first.lower()).strip()


def shares_opening(a: str, b: str) -> bool:
    oa, ob = _opening(a), _opening(b)
    return bool(oa) and oa == ob


def hashtag_count(text: str) -> int:
    return len(_HASHTAG.findall(_URL_RE.sub("", text)))


def finalize(
    text: str,
    *,
    manifest: Manifest,
    beat: Beat,
    network: Network,
    campaign: str,
    limit: int,
    hashtag_cap: int,
) -> tuple[str, list[str]]:
    """Run the fixed-order pipeline; returns final text and warnings."""
    product = manifest.product
    text = inject_disclosures(text, product.disclosures)
    text = tag_links(text, product.target_url, network, campaign, beat.id)
    tagged_url = tag_links(product.target_url, product.target_url, network, campaign, beat.id)
    warnings: list[str] = []
    if not check_length(text, network, limit):
        warnings.append("too_long")
    if unsourced_numbers(text, manifest, tagged_url):
        warnings.append("unsourced_number")
    if prohibited_matches(text, product.prohibited_claims):
        warnings.append("prohibited_claim")
    if hashtag_count(text) > hashtag_cap:
        warnings.append("too_many_hashtags")
    return text, warnings
