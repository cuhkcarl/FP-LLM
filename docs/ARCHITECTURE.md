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
### Players (clean)
| column                         | type     | note                                   |
|-------------------------------|----------|----------------------------------------|
| id                            | int      | player id                              |
| web_name                      | string   | short display name                     |
| first_name / second_name      | string   |                                        |
| team_id                       | int      | FPL team id                            |
| team_name / team_short        | string   | merged from teams                      |
| position                      | string   | {GK, DEF, MID, FWD} from element_type  |
| price_now                     | float    | `now_cost / 10.0` (£m)                 |
| status                        | string   | 'a'=available, etc.                    |
| minutes                       | int      | season minutes                         |
| total_points                  | int      | season points                          |
| form                          | float    | numeric                                 |
| selected_by_pct               | float    | from `selected_by_percent`              |
| chance_of_playing_next_round  | int/NA   |                                        |
| news                          | string   | raw news                               |

### Fixtures (clean)
| column       | type      | note                         |
|--------------|-----------|------------------------------|
| id           | int       | fixture id                   |
| event        | int?      | GW number                    |
| kickoff_time | datetime  | UTC                          |
| finished     | bool      |                              |
| team_h/team_a| int       | ids                          |
| home_team    | string    | merged name                  |
| away_team    | string    | merged name                  |
| home_short   | string    |                              |
| away_short   | string    |                              |
| home_fdr     | int?      | from team_h_difficulty       |
| away_fdr     | int?      | from team_a_difficulty       |

### Quickstart
```bash
# fetch raw
python scripts/fetch_fpl.py --out-dir data/raw/fpl --force-refresh
# normalize + clean
python scripts/build_features.py
# outputs in data/interim/*.parquet
