# ESPN connection and token lifecycle

## Working Streamlit flow

1. A user pastes an HTTPS ESPN fantasy-football league URL.
2. Fourth Down parses the league ID and season without putting either session
   value into a URL.
3. Public leagues load directly. Private leagues use the collapsed advanced
   fallback after the user signs into ESPN normally.
4. ESPN returns a normalized `League`; the user confirms their team.
5. Fourth Down builds one metadata-only `ActiveLeagueState` for every page.
6. Sync now refreshes only on explicit action and uses a five-minute private
   session cache to avoid repeated ESPN calls on Streamlit reruns.
7. Disconnect ESPN clears the active league, sync context, candidates, caches,
   draft/session state, and session authentication values.

Fourth Down never asks for an ESPN password and performs read-only requests.

## Data provenance

League size uses ESPN `settings.size`, then a validated unique-team count, then
explicit user confirmation. A disagreement is never silently resolved. Draft
position uses only ESPN's published draft order, live first-round picks, or an
explicit user selection. Team ID, standings, and response order are never draft
position evidence.

ESPN may return league name, season, settings, scoring, slots, teams, rosters,
schedule, draft order/results, and a player pool. Transactions, traded picks,
keepers, and account-wide league discovery are not claimed unless the endpoint
response actually contains them. A player-pool failure creates a partial active
connection instead of deleting the league.

## One-click extension boundary

ESPN has no supported OAuth flow for discovering private leagues from an email.
The repository includes a disabled MV3 scaffold only. Enabling it requires the
separately deployed service described in `docs/deployment.md`; no cookies may be
sent through Streamlit query parameters, browser history, clipboard, or logs.
