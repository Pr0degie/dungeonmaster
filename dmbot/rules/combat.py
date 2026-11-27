"""Pure combat arithmetic pulled out of the dice cog (golden rule #2: dice rolling AND
resolution are deterministic engine/rules code, never the LLM). No Discord, no WorldState
mutation — the RNG is injected and every soak/roll/Perils computation is reproducible from a
seed. The cog keeps the IO and the state mutations (``apply_damage`` / ``reset_warp_charge``)
and the post-mutation narration (``engine.describe_damage_de``, which reads updated wounds).

Objects (profile / store / target / character) are duck-typed — the cog passes its live
WorldState combatant, PC sheet and CharacterStore through unchanged.
"""
from __future__ import annotations

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass

from . import engine
from .characters import augmetic_armour


def toughness_bonus(profile, store, character) -> int:
    """Toughness Bonus for a player from the sheet: the profile's soak characteristic (IM: Tgh),
    rendered per soak mode (IM: tens digit). 0 if no profile/character/characteristic."""
    if profile is None or character is None:
        return 0
    char_key = profile.soak_characteristic()
    if not char_key:
        return 0
    # Reuse the store's lookup (case-insensitive + strip, skill→characteristic fallback) so a
    # whitespace-drifted sheet key (e.g. "Tgh ") still resolves.
    value = store.skill_value(character, char_key) if store else None
    if value is None:
        return 0
    return value // 10 if profile.soak_mode() == "tens" else value


@dataclass(frozen=True, slots=True)
class AttackOutcome:
    """The deterministic result of one attack's soak + weapon-damage resolution."""

    toughness_bonus: int
    armour: int
    augmetic_armour: int
    soak: int
    damage: engine.DamageResult


_WORD_RE = re.compile(r"[^\W_]+")
_HEAD_MIN = 5  # "Wächter" names the "Torwächter"; a short tail like "mann" names nobody
_ENDINGS = ("", "s", "es", "n", "en")  # Brees Haare, den Kultisten, dem Soldaten
# A line that turns a named figure down ("nicht auf den Wächter, sondern …") decides nothing.
_TURNS_DOWN = frozenset({
    "nicht", "kein", "keine", "keinen", "keinem", "keiner", "statt", "anstatt", "sondern",
    "außer", "ausser", "ohne",
})


def _words(text: str) -> list[str]:
    return [w.casefold() for w in _WORD_RE.findall(text or "")]


def _says(said: str, word: str) -> bool:
    """``said`` is ``word``, bare or inflected ("Brees Haare", "den Kultisten")."""
    return any(said == word + ending for ending in _ENDINGS)


def _phrase_at(words: list[str], phrase: list[str]) -> list[str]:
    """The words of ``text`` that say ``phrase`` as one run, or ``[]``."""
    n = len(phrase)
    for i in range(len(words) - n + 1 if n else 0):
        if all(_says(words[i + j], phrase[j]) for j in range(n)):
            return words[i:i + n]
    return []


def _stems(word: str) -> set[str]:
    return {word.removesuffix(ending) for ending in _ENDINGS if ending == "" or word.endswith(ending)}


def named_targets(text: str, candidates: Sequence[tuple[str, Sequence[str]]]) -> list[str]:
    """The candidates the attacker's own line names, in candidate order.

    ``candidates`` are ``(name, aliases)`` pairs. A candidate is named when its full name or one
    of its authored aliases stands in ``text`` as whole words (case-insensitive, hyphens read as
    spaces, the endings -s/-es/-n/-en tolerated). A one-word name without aliases — an improvised
    figure like "Torwächter" — is also named by the head of its compound ("dem Wächter").
    Deliberately strict: a single word of a longer name ("Alter" of "Alter Fenk") names nobody
    unless it is an alias. But a word that named one candidate names every other candidate whose
    name carries it too ("Kultist" with "Kultist 2" present, "Soldat" with "Sturmsoldat" and
    "Soldat Kern"), so an ambiguous word never singles one figure out."""
    words = _words(text)
    used: dict[str, set[str]] = {}   # candidate → the said words that named it
    for name, aliases in candidates:
        for phrase in (name, *aliases):
            run = _phrase_at(words, _words(phrase))
            if run:
                used.setdefault(name, set()).update(run)
        tail = name.casefold()
        if name not in used and not aliases and len(name.split()) == 1:
            heads = {w for w in words for stem in _stems(w)
                     if len(stem) >= _HEAD_MIN and len(stem) < len(tail) and tail.endswith(stem)}
            if heads:
                used[name] = heads
    said = {stem for run in used.values() for word in run for stem in _stems(word)}
    named: list[str] = []
    for name, aliases in candidates:
        own = {w for phrase in (name, *aliases) for w in _words(phrase)}
        if name in used or any(len(w) >= 4 and w in said for w in own):  # 4: not "der"/"die"
            named.append(name)
    return named


@dataclass(frozen=True)
class TargetChoice:
    """Who a hit lands on: ``auto`` is the one NPC the attacker's line names, or ``None`` when
    the player has to pick; ``order`` is the picker's order."""

    auto: str | None
    order: list[str]


def choose_attack_target(
    text: str,
    npcs: Sequence[tuple[str, Sequence[str]]],
    party: Sequence[tuple[str, Sequence[str]]],
) -> TargetChoice:
    """Read the target of a hit from the attacker's own line (D151).

    Exactly one candidate named, it is an NPC and the line turns nobody down ("nicht", "statt",
    "sondern" …) → that NPC. Everything else leaves the choice to the picker: named NPCs first,
    then the other NPCs, then the party (named team-mates first) — friendly fire is never applied
    unasked and never sits on top. The line is the player's transcribed speech, never narration.

    Known limit: a line that names exactly one present NPC without attacking it ("Ich stelle
    mich vor den Wächter und schlage zu") still hits that NPC."""
    named = named_targets(text, [*npcs, *party])
    npc_names = [name for name, _ in npcs]
    party_names = [name for name, _ in party]
    order = (
        [n for n in npc_names if n in named] + [n for n in npc_names if n not in named]
        + [n for n in party_names if n in named] + [n for n in party_names if n not in named]
    )
    turned_down = any(word in _TURNS_DOWN for word in _words(text))
    auto = named[0] if len(named) == 1 and named[0] in npc_names and not turned_down else None
    return TargetChoice(auto=auto, order=order)


def resolve_attack(
    profile, store, *, target, target_sheet, notation, success_level, rng: random.Random
) -> AttackOutcome:
    """Roll the weapon's damage and subtract the target's soak (Toughness Bonus + armour, plus
    augmetic armour for a PC, ADR 023), yielding the wounds applied. Pure: rolls through the
    injected RNG, mutates nothing. The cog applies ``damage.applied`` to the WorldState and
    narrates the consequence afterward.

    ``target`` is the WorldState combatant (duck-typed: ``.is_npc``, ``.toughness_bonus``,
    ``.armour``); ``target_sheet`` is the PC ``Character`` sheet, or ``None`` for an NPC."""
    augm_armour = 0
    if target.is_npc:
        tb = target.toughness_bonus
    else:
        tb = toughness_bonus(profile, store, target_sheet)
        if profile is not None:  # augmetic armour adds to a PC's soak (ADR 023)
            augm_armour = augmetic_armour(profile, target_sheet)
    soak = tb + target.armour + augm_armour
    weapon_roll = engine.roll_damage(notation, rng)
    dmg = engine.resolve_damage(weapon_roll, success_level, soak)
    return AttackOutcome(
        toughness_bonus=tb, armour=target.armour, augmetic_armour=augm_armour,
        soak=soak, damage=dmg,
    )


@dataclass
class WarpConsequence:
    """The Perils/containment lines a manifest produced, plus whether Warp Charge must reset.
    The cog applies ``reset_charge`` via ``state.reset_warp_charge`` — this stays pure."""

    lines: list[str]
    reset_charge: bool


def resolve_warp_consequences(
    profile, *, immediate_perils, over_threshold, warp_charge, threshold, contain_base,
    character, rng: random.Random,
) -> WarpConsequence:
    """Resolve the Perils-of-the-Warp risk a manifest just created (ADR 022). A Push-Fumble
    triggers Perils immediately (IM p.163); otherwise, if Warp Charge now exceeds the Threshold,
    the psyker makes the Challenging containment Test — on success the energy is held (powers
    turn Overt), on failure Perils erupt. Pure: the cog applies ``reset_charge`` (Perils resets
    Warp Charge to 0 and ends Sustained powers)."""
    if not (immediate_perils or over_threshold):
        return WarpConsequence(lines=[], reset_charge=False)
    over_by = max(0, warp_charge - threshold)
    lines: list[str] = []
    if not immediate_perils:  # over threshold → containment Test first
        # The containment Test rolls against Disziplin (Psi), not Psi-Meisterschaft (IM p.163).
        contain_target = (contain_base or 0) + (profile.difficulty_modifier("Herausfordernd") or 0)
        contain = engine.scope_doubles(
            profile, engine.resolve_test(profile, contain_target, rng), "Warp-Kontrolle")
        lines.append(engine.describe_result_de(
            contain, skill="Warp-Kontrolle", character=character, difficulty="Herausfordernd"))
        if contain.success:
            lines.append(f"🜏 {character} hält die Warp-Energie zurück — alle gewirkten Kräfte gelten "
                         "bis zur Beruhigung als offen (Overt).")
            return WarpConsequence(lines=lines, reset_charge=False)
    perils = engine.resolve_perils(profile, over_by=over_by, rng=rng)
    lines.append(engine.describe_perils_de(perils, character=character))
    if perils.effect:
        lines.append(f"   → {perils.effect}")
    return WarpConsequence(lines=lines, reset_charge=True)
