"""Draft generation orchestration: planning, retries, sibling checks (spec section 6)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal

from promo import drafts
from promo.config import ConfigError, Profile, Settings, resolve_api_key
from promo.drafts import Draft, DraftError, DraftMeta, Status, Usage
from promo.generators import (
    GenerationError,
    GenerationRequest,
    Generator,
    make_generator,
)
from promo.networks import NEEDS_MEDIA, hashtag_cap_for, limit_for
from promo.postprocess import finalize, shares_opening, too_similar
from promo.prompts import build_request, load_brand_voice
from promo.schema import SLUG_RE, Beat, Manifest, ManifestError, Network

MAX_REGENERATIONS = 2

Action = Literal["generate", "skip-exists", "skip-posted", "refuse-status"]


@dataclass
class DraftPlan:
    campaign: str
    beat: Beat
    network: Network
    path: Path
    action: Action


@dataclass
class RunReport:
    generated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: dict[str, list[str]] = field(default_factory=dict)
    calls: int = 0


@dataclass
class _Outcome:
    meta: DraftMeta
    variants: list[str]
    calls: int


def plan_run(
    manifest: Manifest,
    campaign: str,
    drafts_root: Path,
    *,
    beat: str | None,
    network: str | None,
    force: bool,
) -> list[DraftPlan]:
    if beat is not None and beat not in {b.id for b in manifest.beats}:
        valid = ", ".join(b.id for b in manifest.beats)
        raise ManifestError(f"unknown beat {beat!r} (valid: {valid})")
    if network is not None:
        used = [n.value for n in dict.fromkeys(n for b in manifest.beats for n in b.networks)]
        if network not in used:
            raise ManifestError(f"unknown network {network!r} (valid: {', '.join(used)})")
    plans: list[DraftPlan] = []
    for b in manifest.beats:
        if beat is not None and b.id != beat:
            continue
        for n in b.networks:
            if network is not None and n.value != network:
                continue
            path = drafts.draft_path(drafts_root, drafts.draft_id(campaign, b.id, n))
            plans.append(DraftPlan(campaign, b, n, path, _action_for(path, force)))
    return plans


def _action_for(path: Path, force: bool) -> Action:
    if not path.exists():
        return "generate"
    if not force:
        return "skip-exists"
    try:
        status = drafts.load(path).meta.status
    except DraftError:
        return "generate"
    if status is Status.posted:
        return "skip-posted"
    if status is Status.scheduled:
        return "refuse-status"
    return "generate"


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def _first_variant(path: Path) -> str | None:
    try:
        return drafts.load(path).variants[0]
    except (DraftError, IndexError):
        return None


def _sibling_checks(
    manifest: Manifest, campaign: str, beat: Beat, network: Network, drafts_root: Path
) -> Callable[[list[str]], list[str]]:
    """Build the check that compares a new first variant with written sibling drafts."""
    same_beat: list[str] = []
    for n in beat.networks:
        if n is network:
            continue
        found = _first_variant(
            drafts.draft_path(drafts_root, drafts.draft_id(campaign, beat.id, n))
        )
        if found is not None:
            same_beat.append(found)
    same_intent: list[str] = []
    for other in manifest.beats:
        if other.id == beat.id or other.intent is not beat.intent:
            continue
        found = _first_variant(
            drafts.draft_path(drafts_root, drafts.draft_id(campaign, other.id, network))
        )
        if found is not None:
            same_intent.append(found)

    def check(variants: list[str]) -> list[str]:
        if not variants:
            return []
        first = variants[0]
        out: list[str] = []
        if any(too_similar(first, s) for s in same_beat):
            out.append("near_duplicate")
        if any(shares_opening(first, s) for s in same_intent):
            out.append("repeats_beat")
        return out

    return check


_NOTES = {
    "unusable": (
        "The previous attempt was unusable; give non-empty variants and never start a "
        "line with '## Variant'."
    ),
    "wrong_variant_count": "The previous attempt returned the wrong number of variants; "
    "return exactly {n} distinct variants.",
    "too_long": "The previous attempt was too long; keep every variant within {limit} characters.",
    "near_duplicate": "The previous attempt was too similar to the same beat on another "
    "network; write it noticeably differently.",
    "repeats_beat": "The previous attempt opened like another beat with the same intent; "
    "use a different opening sentence.",
}


def _run_attempts(
    generator: Generator,
    request: GenerationRequest,
    *,
    campaign: str,
    beat: Beat,
    network: Network,
    manifest: Manifest,
    settings: Settings,
    draft_id: str,
    path_profile: str,
    siblings: Callable[[list[str]], list[str]] | None,
    now: datetime,
    base_meta: DraftMeta | None,
) -> _Outcome:
    """Generate, post-process and sibling-check, retrying within MAX_REGENERATIONS."""
    limit = limit_for(network, settings)
    cap = hashtag_cap_for(network, settings)
    n = settings.variants_per_draft
    total = Usage(input_tokens=0, output_tokens=0)
    calls = 0
    current = request
    for attempt in range(MAX_REGENERATIONS + 1):
        result = generator.generate(current)
        calls += 1
        total = Usage(
            input_tokens=total.input_tokens + result.usage.input_tokens,
            output_tokens=total.output_tokens + result.usage.output_tokens,
        )
        variants: list[str] = []
        found: list[str] = []
        for text in result.variants:
            final, warns = finalize(
                text,
                manifest=manifest,
                beat=beat,
                network=network,
                campaign=campaign,
                limit=limit,
                hashtag_cap=cap,
            )
            variants.append(final)
            found.extend(warns)
        if len(variants) != n:
            found.append("wrong_variant_count")
        if siblings is not None:
            found.extend(siblings(variants))
        warnings = _unique(found)
        meta = _meta(
            base_meta, campaign, beat, network, draft_id, path_profile, now, variants, total,
            result.model, warnings,
        )  # fmt: skip
        failing: list[str] = []
        if not variants:
            failing.append("unusable")
        else:
            try:
                drafts.render(meta, variants)
            except DraftError:
                failing.append("unusable")
        failing.extend(
            w
            for w in warnings
            if w in {"too_long", "wrong_variant_count", "near_duplicate", "repeats_beat"}
        )
        if not failing:
            return _Outcome(meta, variants, calls)
        if attempt == MAX_REGENERATIONS:
            if "unusable" in failing:
                raise GenerationError(f"model returned unusable variants for {draft_id}")
            return _Outcome(meta, variants, calls)
        note = " ".join(_NOTES[f].format(n=n, limit=limit) for f in dict.fromkeys(failing))
        current = request.model_copy(update={"user": f"{request.user}\n\n{note}"})
    raise AssertionError("unreachable")  # pragma: no cover


def _meta(
    base: DraftMeta | None,
    campaign: str,
    beat: Beat,
    network: Network,
    draft_id: str,
    profile: str,
    now: datetime,
    variants: list[str],
    usage: Usage,
    model: str,
    warnings: list[str],
) -> DraftMeta:
    if base is not None:
        return base.model_copy(
            update={
                "variants": len(variants),
                "chosen": None,
                "usage": usage,
                "model": model,
                "warnings": warnings,
                "generated_at": now,
            }
        )
    return DraftMeta(
        id=draft_id,
        campaign=campaign,
        beat=beat.id,
        network=network,
        status=Status.draft,
        variants=len(variants),
        chosen=None,
        generated_at=now,
        profile=profile,
        model=model,
        usage=usage,
        needs_media=network in NEEDS_MEDIA,
        warnings=warnings,
    )


def run_draft(
    manifest: Manifest,
    campaign: str,
    settings: Settings,
    profile_name: str | None,
    generator: Generator,
    drafts_root: Path,
    *,
    beat: str | None,
    network: str | None,
    force: bool,
    dry_run: bool,
    now: datetime,
) -> RunReport:
    if not SLUG_RE.fullmatch(campaign):
        raise ManifestError(f"campaign name {campaign!r} must match [a-z0-9-]+")
    profile = settings.profile(profile_name)
    resolved_name = settings.default_profile if profile_name is None else profile_name
    if profile.trains_on_input and manifest.confidential:
        raise ConfigError(
            f"profile {resolved_name!r} trains on input and the campaign is confidential; "
            "set `confidential: false` in the manifest to allow it"
        )
    plans = plan_run(manifest, campaign, drafts_root, beat=beat, network=network, force=force)
    report = RunReport()
    todo = [p for p in plans if p.action == "generate"]
    report.skipped = [
        drafts.draft_id(p.campaign, p.beat.id, p.network) for p in plans if p.action != "generate"
    ]
    if dry_run:
        report.calls = len(todo)
        return report
    if not todo:
        return report
    prose, examples = load_brand_voice(manifest.brand_voice)
    for plan in todo:
        did = drafts.draft_id(campaign, plan.beat.id, plan.network)
        request = build_request(
            manifest,
            plan.beat,
            plan.network,
            campaign,
            prose,
            examples,
            settings.variants_per_draft,
            limit_for(plan.network, settings),
            hashtag_cap_for(plan.network, settings),
        )
        outcome = _run_attempts(
            generator,
            request,
            campaign=campaign,
            beat=plan.beat,
            network=plan.network,
            manifest=manifest,
            settings=settings,
            draft_id=did,
            path_profile=resolved_name,
            siblings=_sibling_checks(manifest, campaign, plan.beat, plan.network, drafts_root),
            now=now,
            base_meta=None,
        )
        report.calls += outcome.calls
        drafts.save(Draft(meta=outcome.meta, variants=outcome.variants, path=plan.path))
        report.generated.append(did)
        if outcome.meta.warnings:
            report.warnings[did] = list(outcome.meta.warnings)
    return report


def regenerate_one(
    path: Path,
    manifest: Manifest,
    settings: Settings,
    note: str,
    now: datetime,
    *,
    generator_factory: Callable[[Profile, str | None], Generator] = make_generator,
) -> Draft:
    draft = drafts.load(path)
    if draft.meta.status is not Status.draft:
        raise DraftError(f"{path}: cannot regenerate a draft with status {draft.meta.status}")
    beat = next((b for b in manifest.beats if b.id == draft.meta.beat), None)
    if beat is None or draft.meta.network not in beat.networks:
        raise ManifestError(
            f"{path}: beat {draft.meta.beat!r} on {draft.meta.network.value} is not in the manifest"
        )
    network = draft.meta.network
    campaign = draft.meta.campaign
    profile = settings.profile(draft.meta.profile)
    generator = generator_factory(profile, resolve_api_key(profile))
    prose, examples = load_brand_voice(manifest.brand_voice)
    request = build_request(
        manifest,
        beat,
        network,
        campaign,
        prose,
        examples,
        settings.variants_per_draft,
        limit_for(network, settings),
        hashtag_cap_for(network, settings),
    )
    if note.strip():
        request = request.model_copy(update={"user": f"{request.user}\n\n{note.strip()}"})
    outcome = _run_attempts(
        generator,
        request,
        campaign=campaign,
        beat=beat,
        network=network,
        manifest=manifest,
        settings=settings,
        draft_id=draft.meta.id,
        path_profile=draft.meta.profile,
        siblings=None,
        now=now,
        base_meta=draft.meta,
    )
    result = Draft(meta=outcome.meta, variants=outcome.variants, path=path)
    drafts.save(result)
    return result
