# Architecture

## Data Layer

### Sources (public endpoints)
- `bootstrap-static/` — players, teams, game settings
- `fixtures/` — season fixtures (with FDR)
- `event/{gw}/live/` — optional, per-GW live
- `element-summary/{player_id}/` — optional, per-player history (use sparingly)

### File layout
data/
raw/
fpl/
bootstrap-static.json
fixtures.json
event_gwXX_live.json         # optional
element_summaries/.json     # optional
http_cache/.json              # HTTP cache (by URL sha1)
interim/
players.parquet
teams.parquet
fixtures.parquet
players_clean.parquet
fixtures_clean.parquet
processed/
# reserved for features / predictions
