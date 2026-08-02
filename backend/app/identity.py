from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Iterable

from .domain import Player

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
TEAM_ALIASES = {"JAC": "JAX", "LA": "LAR", "WSH": "WAS"}


def normalize_team_id(team: str | None) -> str:
    value = (team or "").strip().upper()
    return TEAM_ALIASES.get(value, value)


def normalize_player_name(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode("ascii")
    ascii_name = ascii_name.replace("'", " ").replace(".", " ")
    ascii_name = re.sub(r"[-_/]", " ", ascii_name)
    parts = [part for part in re.sub(r"[^A-Za-z0-9 ]+", " ", ascii_name).lower().split() if part not in SUFFIXES]
    return " ".join(parts)


@dataclass(frozen=True)
class CanonicalPlayerIdentity:
    canonical_player_id: str
    full_name: str
    normalized_name: str
    position: str
    nfl_team_id: str
    provider_ids: dict[str, str] = field(default_factory=dict)
    season: int | None = None
    last_verified_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    resolved: bool = True
    ambiguous: bool = False
    reason: str = ""


def identity_from_player(player: Player, season: int | None = None, provider: str = "internal") -> CanonicalPlayerIdentity:
    provider_ids = {provider: player.id}
    return CanonicalPlayerIdentity(
        canonical_player_id=f"{season or 'all'}:{normalize_player_name(player.name)}:{player.position}:{normalize_team_id(player.team)}",
        full_name=player.name,
        normalized_name=normalize_player_name(player.name),
        position=player.position,
        nfl_team_id=normalize_team_id(player.team),
        provider_ids=provider_ids,
        season=season,
    )


def build_identity_index(players: Iterable[Player], season: int | None = None, provider: str = "internal") -> list[CanonicalPlayerIdentity]:
    return [identity_from_player(player, season=season, provider=provider) for player in players]


def resolve_player_identity(
    name: str,
    *,
    candidates: Iterable[CanonicalPlayerIdentity],
    position: str | None = None,
    nfl_team_id: str | None = None,
    provider_id: tuple[str, str] | None = None,
) -> CanonicalPlayerIdentity:
    candidates = list(candidates)
    if provider_id:
        provider, value = provider_id
        direct = [candidate for candidate in candidates if candidate.provider_ids.get(provider) == value]
        if len(direct) == 1:
            return direct[0]
        if len(direct) > 1:
            return _unresolved(name, position, nfl_team_id, "provider id matched multiple players", ambiguous=True)

    normalized = normalize_player_name(name)
    matches = [candidate for candidate in candidates if candidate.normalized_name == normalized]
    if position:
        matches = [candidate for candidate in matches if candidate.position == position]
    if nfl_team_id:
        team = normalize_team_id(nfl_team_id)
        team_matches = [candidate for candidate in matches if candidate.nfl_team_id == team]
        if team_matches:
            matches = team_matches

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return _unresolved(name, position, nfl_team_id, "name match is ambiguous", ambiguous=True)
    return _unresolved(name, position, nfl_team_id, "no canonical player match")


def _unresolved(name: str, position: str | None, nfl_team_id: str | None, reason: str, ambiguous: bool = False) -> CanonicalPlayerIdentity:
    return CanonicalPlayerIdentity(
        canonical_player_id="unresolved",
        full_name=name,
        normalized_name=normalize_player_name(name),
        position=position or "UNK",
        nfl_team_id=normalize_team_id(nfl_team_id),
        resolved=False,
        ambiguous=ambiguous,
        reason=reason,
    )
