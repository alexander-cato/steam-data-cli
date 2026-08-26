# steam-data-cli

Command-line tools for the Steam Web API. One so far: `steam-friends`,
which lists a Steam account's friends sorted by when they were added.

One file, Python 3.7+, standard library only.

## Setup

Get an API key at <https://steamcommunity.com/dev/apikey>. Accounts that have
never spent $5 can't create one.

Then set the account's "My friends list" to Public, under Profile → Edit
Profile → Privacy Settings. This one trips up everyone, me included. Steam
keeps friends-list privacy separate from profile privacy, so a fully public
profile still returns HTTP 401 here. Holding the API key doesn't exempt you
either, even on your own account. Switch it back once you have the data.

## Usage

```sh
./steam-friends                                # prompts for what it needs
./steam-friends --id yourvanityname                 # vanity name
./steam-friends --id 76561198000000000         # SteamID64
./steam-friends --id https://steamcommunity.com/id/yourvanityname/
```

```
--oldest                  oldest friendships first
--format csv -o out.csv   also tsv, json, table (default)
--relationship all        include pending invites
--limit 20                first 20 rows
--utc                     UTC instead of local time
--no-names                skip the persona-name lookup
--save                    write the key and id to the config file
```

Credentials come from `--key`/`--id`, then `STEAM_API_KEY`/`STEAM_ID`, then
`~/.config/steam-friends/config.json`, then a prompt.

## Details

Date added comes from `friend_since`. Steam reports `0` for some friendships,
mostly old ones. Those rows read `unknown` and sort to the end in both
directions instead of showing up as 1970.

Names come from `GetPlayerSummaries`, 100 ids per call. If a batch fails you
lose those names. The run finishes anyway and those rows show the raw id.

The tool retries on rate limits, 5xx, and network errors, waiting longer each
time. Bad keys and privacy refusals fail on the first try, because retrying
can't fix either one.

Data goes to stdout. Progress and warnings go to stderr.

## Exit codes

`0` success, `1` error, `2` bad usage, `130` interrupted.
