# Schema (auto-generated)

Source: `demo` · dialect: **SQLite** · profiled 2026-11-25

Regenerate with `python -m helpers.schema`. Hand-written meaning, joins and
gotchas live in `quirks.md` and `metrics.md` — read those too.

## `bugs` — 8,706 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| bug_id | INTEGER | 0.0 | 8,706 | 1 … 8706 |
| bug_key | TEXT | 0.0 | 8,706 | ADM-101 … WEB-999 |
| product_id | INTEGER | 0.0 | 6 | `4` (3,136), `2` (2,138), `3` (1,223), `1` (1,197), `6` (745), `5` (267) |
| component_id | INTEGER | 6.1 | 26 | 1 … 26 |
| title | TEXT | 0.0 | 60 | Apple Pay sheet not dism … Wrong axis label |
| severity | TEXT | 0.0 | 8 | `S3` (3,019), `S4` (1,924), `S2` (1,559), `Minor` (775), `Trivial` (537), `S1` (393), `Major` (393), `Critical` (106) |
| priority | TEXT | 0.0 | 4 | `P2` (3,565), `P3` (2,427), `P1` (1,980), `P0` (734) |
| status | TEXT | 0.0 | 6 | `closed` (5,500), `resolved` (2,375), `duplicate` (286), `wont_fix` (264), `open` (176), `in_progress` (105) |
| source | TEXT | 0.0 | 5 | `customer_report` (2,465), `qa` (2,125), `automated_test` (1,890), `monitoring` (1,345), `internal` (881) |
| environment | TEXT | 0.0 | 3 | `production` (6,498), `staging` (1,489), `dev` (719) |
| is_regression | INTEGER | 0.0 | 2 | `0` (7,551), `1` (1,155) |
| found_in_release_id | INTEGER | 0.0 | 255 | 1 … 256 |
| fixed_in_release_id | INTEGER | 10.7 | 248 | 2 … 257 |
| assignee_team_id | INTEGER | 0.0 | 6 | `4` (3,136), `2` (2,138), `3` (1,223), `1` (1,197), `6` (745), `5` (267) |
| reopened_count | INTEGER | 0.0 | 5 | `0` (7,743), `1` (738), `2` (138), `3` (48), `4` (39) |
| customer_tickets | INTEGER | 0.0 | 52 | 0 … 113 |
| created_at | TIMESTAMP | 0.0 | 8,677 | 2024-07-01 00:07:00 … 2026-11-24 21:57:00 |
| resolved_at | TIMESTAMP | 3.2 | 8,393 | 2024-07-03 01:21 … 2026-11-24 22:37 |

## `components` — 26 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| component_id | INTEGER | 0.0 | 26 | 1 … 26 |
| product_id | INTEGER | 0.0 | 6 | `4` (6), `2` (5), `1` (5), `3` (4), `6` (3), `5` (3) |
| component_name | TEXT | 0.0 | 26 | audit-log … webhooks |
| kloc | REAL | 0.0 | 22 | `9.0` (3), `18.0` (2), `12.0` (2), `64.0` (1), `60.0` (1), `52.0` (1), `48.0` (1), `45.0` (1), `41.0` (1), `38.0` (1), `33.0` (1), `30.0` (1), `27.0` (1), `25.0` (1), `22.0` (1), `20.0` (1), `16.0` (1), `15.0` (1), `14.0` (1), `13.0` (1), `11.0` (1), `8.0` (1) |

## `product_usage_monthly` — 174 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| product_id | INTEGER | 0.0 | 6 | `1` (29), `2` (29), `3` (29), `4` (29), `5` (29), `6` (29) |
| month | DATE | 0.0 | 29 | 2024-07-01 … 2026-11-01 |
| monthly_active_users | INTEGER | 0.0 | 172 | 920 … 727029 |
| deploys | INTEGER | 0.0 | 15 | `6` (28), `7` (21), `4` (20), `5` (14), `9` (12), `16` (11), `10` (11), `3` (11), `8` (10), `15` (8), `13` (7), `11` (7), `12` (6), `14` (5), `2` (3) |

## `products` — 6 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| product_id | INTEGER | 0.0 | 6 | `1` (1), `2` (1), `3` (1), `4` (1), `5` (1), `6` (1) |
| product_name | TEXT | 0.0 | 6 | `Web Dashboard` (1), `Search` (1), `Payments API` (1), `Mobile App` (1), `Data Pipeline` (1), `Admin Console` (1) |
| platform | TEXT | 0.0 | 3 | `backend` (3), `web` (2), `ios/android` (1) |
| owner_team_id | INTEGER | 0.0 | 6 | `6` (1), `5` (1), `4` (1), `3` (1), `2` (1), `1` (1) |
| launched_at | DATE | 0.0 | 6 | `2023-06-01` (1), `2023-01-10` (1), `2022-11-01` (1), `2022-03-01` (1), `2021-09-15` (1), `2020-05-01` (1) |

## `releases` — 257 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| release_id | INTEGER | 0.0 | 257 | 1 … 257 |
| product_id | INTEGER | 0.0 | 6 | `4` (65), `2` (65), `3` (42), `1` (33), `6` (31), `5` (21) |
| version | TEXT | 0.0 | 94 | v0.5 … v9.8 |
| released_at | DATE | 0.0 | 242 | 2024-06-11 … 2026-11-24 |

## `teams` — 6 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| team_id | INTEGER | 0.0 | 6 | `1` (1), `2` (1), `3` (1), `4` (1), `5` (1), `6` (1) |
| team_name | TEXT | 0.0 | 6 | `Web Platform` (1), `Search & Discovery` (1), `Payments Eng` (1), `Mobile Eng` (1), `Internal Tools` (1), `Data Platform` (1) |
| headcount | INTEGER | 0.0 | 6 | `14` (1), `11` (1), `9` (1), `8` (1), `7` (1), `3` (1) |

## `v_defects` — 8,156 rows

| column | type | null % | distinct | range / values |
|---|---|---|---|---|
| bug_id | INTEGER | 0.0 | 8,156 | 1 … 8706 |
| bug_key | TEXT | 0.0 | 8,156 | ADM-101 … WEB-999 |
| product_id | INTEGER | 0.0 | 6 | `4` (2,952), `2` (1,993), `3` (1,142), `1` (1,121), `6` (692), `5` (256) |
| component_id | INTEGER | 6.1 | 26 | 1 … 26 |
| title | TEXT | 0.0 | 60 | Apple Pay sheet not dism … Wrong axis label |
| severity | TEXT | 0.0 | 8 | `S3` (2,838), `S4` (1,787), `S2` (1,460), `Minor` (724), `Trivial` (503), `S1` (378), `Major` (366), `Critical` (100) |
| priority | TEXT | 0.0 | 4 | `P2` (3,350), `P3` (2,255), `P1` (1,855), `P0` (696) |
| status | TEXT | 0.0 | 4 | `closed` (5,500), `resolved` (2,375), `open` (176), `in_progress` (105) |
| source | TEXT | 0.0 | 5 | `customer_report` (2,311), `qa` (1,971), `automated_test` (1,782), `monitoring` (1,258), `internal` (834) |
| environment | TEXT | 0.0 | 3 | `production` (6,087), `staging` (1,390), `dev` (679) |
| is_regression | INTEGER | 0.0 | 2 | `0` (7,071), `1` (1,085) |
| found_in_release_id | INTEGER | 0.0 | 255 | 1 … 256 |
| fixed_in_release_id | INTEGER | 4.6 | 248 | 2 … 257 |
| assignee_team_id | INTEGER | 0.0 | 6 | `4` (2,952), `2` (1,993), `3` (1,142), `1` (1,121), `6` (692), `5` (256) |
| reopened_count | INTEGER | 0.0 | 5 | `0` (7,193), `1` (738), `2` (138), `3` (48), `4` (39) |
| customer_tickets | INTEGER | 0.0 | 51 | 0 … 113 |
| created_at | TIMESTAMP | 0.0 | 8,132 | 2024-07-01 00:07:00 … 2026-11-24 21:57:00 |
| resolved_at | TIMESTAMP | 3.4 | 7,846 | 2024-07-03 02:02 … 2026-11-24 22:37 |
| severity_norm |  | 0.0 | 4 | `S3` (3,562), `S4` (2,290), `S2` (1,826), `S1` (478) |
| product_name | TEXT | 0.0 | 6 | `Web Dashboard` (2,952), `Mobile App` (1,993), `Search` (1,142), `Payments API` (1,121), `Data Pipeline` (692), `Admin Console` (256) |
| component_name |  | 0.0 | 27 | (untriaged) … webhooks |
| kloc | REAL | 6.1 | 22 | `9.0` (1,003), `64.0` (598), `48.0` (551), `18.0` (537), `25.0` (502), `None` (498), `12.0` (492), `30.0` (428), `41.0` (410), `14.0` (329), `27.0` (323), `38.0` (321), `33.0` (319), `20.0` (316), `45.0` (275), `8.0` (241), `60.0` (224), `15.0` (202), `52.0` (157), `11.0` (131), `22.0` (116), `16.0` (104), `13.0` (79) |
| created_month |  | 0.0 | 29 | 2024-07-01 … 2026-11-01 |
| is_fixed |  | 0.0 | 2 | `1` (7,875), `0` (281) |
| is_open |  | 0.0 | 2 | `0` (7,875), `1` (281) |
| days_to_resolve |  | 3.4 | 7,540 | 0.33263888861984015 … 344.5812500002794 |
