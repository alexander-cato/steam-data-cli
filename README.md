# steam-data-cli

Command-line tools for the Steam Web API. Currently, the repository contains
`steam-friends`, which lists a Steam account's friends by the date they were
added.

The command is a single executable file, supports Python 3.7+, and uses only
the standard library.

## Setup

Get an API key at <https://steamcommunity.com/dev/apikey>. Limited accounts
(those that have never spent $5) cannot create one.

Set the account's “My friends list” visibility to Public under Profile → Edit
Profile → Privacy Settings. Steam manages friends-list privacy separately from
profile privacy, so a public profile can still return HTTP 401. An API key does
not bypass this setting, even for your own account. You can restore the setting
after exporting the data.

## Usage

```sh
./steam-friends                                         # prompts for required values
./steam-friends --id yourvanityname                     # vanity name
./steam-friends --id 76561198000000000                  # SteamID64
./steam-friends --id https://steamcommunity.com/id/yourvanityname/
```

```text
--oldest                  oldest friendships first
--format csv -o out.csv   also tsv, json, table (default)
--columns name,game       select and order exported fields
--relationship all        include pending invites
--match alice             match names or SteamIDs (case-insensitive)
--since 2024-01-01        added on/after a date; pair with --until
--state online            filter by Steam presence state
--country US              filter by two-letter profile country code
--playing [portal]        friends in a game, optionally matching its name
--sort name --reverse     sort by name, status, last logoff, or account creation
--details                 include status, profile, game, identity, and account details
--limit 20                first 20 rows
--utc                     UTC instead of local time
--no-names                skip the persona-name lookup
--no-summary              omit the per-year summary
--save                    write the key and id to the config file
--track [FILE]            report changes since the last tracked run
```

Credentials come from `--key`/`--id`, then `STEAM_API_KEY`/`STEAM_ID`, then
`~/.config/steam-friends/config.json`, then a prompt.

## Details

The date added comes from `friend_since`. Steam reports `0` for some
friendships, mostly older ones. Those rows display `unknown` and sort to the
end in either direction instead of appearing as dates in 1970.

Names come from `GetPlayerSummaries`, with up to 100 IDs per call. If a batch
fails, the command finishes and displays the affected Steam IDs without names.
The same response powers `--details` and `--state`; both are incompatible with
`--no-names`, which deliberately skips those requests. Profile-backed filters
and sorting are incompatible with `--no-names` for the same reason.

`--sort added` shows newest friendships first by default. Name and status sorts
are ascending, while last-logoff and account-creation sorts show the newest
dates first. `--reverse` flips the selected order. Missing dates and names stay
at the end in either direction; `--oldest` remains a shorthand for reversing
the default added-date sort.

Use `--columns` to choose fields and their order in any output format. It
accepts `added`, `friend_since`, `steamid`, `name`, `relationship`, `status`,
`last_logoff`, `country`, `game`, `real_name`, `account_created`, `visibility`,
and `profile_url`. Hyphens can be used in place of underscores. The option
overrides the usual compact or `--details` column preset.

The tool retries on rate limits, 5xx, and network errors, waiting longer each
time. Bad keys and privacy refusals fail on the first try, because retrying
won't fix either one.

Data is written to standard output. Progress and warnings are written to
standard error, so redirecting or piping the data remains safe.

`--since` and `--until` are inclusive and use the selected output timezone
(local by default, UTC with `--utc`). Friendships without a recorded date are
left out when either date filter is active.

## Tracking changes

Use `--track` to save a baseline, then repeat the same command later to see
added, removed, and renamed friends. Change reports go to standard error, so
the selected table, CSV, TSV, or JSON output remains clean.

```sh
./steam-friends --id yourvanityname --track
./steam-friends --id yourvanityname --track
./steam-friends --id yourvanityname --track ./friends-snapshot.json
```

The default snapshots live under
`~/.local/state/steam-friends/snapshots/` (or `$XDG_STATE_HOME`) and are kept
separately for `friend` and `all` relationship modes. Snapshot updates are
atomic, use mode `0600`, and never contain the API key. A custom snapshot path
is useful for backups or comparing on another machine.

## Exit codes

`0` success, `1` error, `2` bad usage, `130` interrupted.

## Development

The test suite uses only the Python standard library:

```sh
python3 -m unittest discover -s tests -v
```
