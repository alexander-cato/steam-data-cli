import importlib.machinery
import importlib.util
import io
import json
import pathlib
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader(
    "steam_friends", str(ROOT / "steam-friends")
)
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
steam_friends = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(steam_friends)


class IdentityParsingTests(unittest.TestCase):
    def test_accepts_supported_identity_forms(self):
        steam_id = "76561198000000000"
        self.assertEqual(steam_friends.parse_identity(steam_id), ("id64", steam_id))
        self.assertEqual(
            steam_friends.parse_identity("your.name"), ("vanity", "your.name")
        )
        self.assertEqual(
            steam_friends.parse_identity(
                "https://steamcommunity.com/id/your.name/games/"
            ),
            ("vanity", "your.name"),
        )
        self.assertEqual(
            steam_friends.parse_identity(
                "steamcommunity.com/profiles/76561198000000000/"
            ),
            ("id64", steam_id),
        )

    def test_rejects_misleading_hosts_and_invalid_url_values(self):
        invalid = (
            "https://steamcommunity.com.example.test/id/name",
            "https://example.test/id/name",
            "https://steamcommunity.com/id/not%20valid",
            "https://steamcommunity.com/profiles/not-an-id",
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                steam_friends.parse_identity(value)


class RowBuildingTests(unittest.TestCase):
    def test_sorts_dated_rows_and_parks_unknown_dates_at_the_end(self):
        friends = [
            {"steamid": "3", "friend_since": "bad"},
            {"steamid": "2", "friend_since": 200},
            {"steamid": "1", "friend_since": 100},
            {"steamid": "4", "friend_since": -1},
        ]

        newest = steam_friends.build_rows(friends, {}, utc=True, oldest_first=False)
        oldest = steam_friends.build_rows(friends, {}, utc=True, oldest_first=True)

        self.assertEqual([row["steamid"] for row in newest], ["2", "1", "3", "4"])
        self.assertEqual([row["steamid"] for row in oldest], ["1", "2", "3", "4"])
        self.assertEqual(newest[2]["added"], "")

    def test_empty_output_is_valid_in_every_format(self):
        table_output = io.StringIO()
        steam_friends.write_output([], "table", table_output, show_rel=False)
        self.assertEqual(table_output.getvalue(), "")

        json_output = io.StringIO()
        steam_friends.write_output([], "json", json_output, show_rel=False)
        self.assertEqual(json.loads(json_output.getvalue()), [])

        csv_output = io.StringIO()
        steam_friends.write_output([], "csv", csv_output, show_rel=False)
        self.assertEqual(csv_output.getvalue(), "added,friend_since,steamid,name\n")

    def test_filters_by_name_or_id_case_insensitively(self):
        rows = [
            {"added": "2024-01-02 12:00", "steamid": "111", "name": "Alpha Fox"},
            {"added": "2023-08-09 12:00", "steamid": "222", "name": "Beta"},
            {"added": "", "steamid": "333", "name": "Gamma"},
        ]

        self.assertEqual(
            [row["steamid"] for row in steam_friends.filter_rows(rows, query="FOX")],
            ["111"],
        )
        self.assertEqual(
            [row["steamid"] for row in steam_friends.filter_rows(rows, query="22")],
            ["222"],
        )

    def test_filters_by_inclusive_date_range_and_omits_unknown_dates(self):
        rows = [
            {"added": "2024-01-02 12:00", "steamid": "111", "name": "Alpha"},
            {"added": "2023-08-09 12:00", "steamid": "222", "name": "Beta"},
            {"added": "", "steamid": "333", "name": "Gamma"},
        ]

        filtered = steam_friends.filter_rows(
            rows, since="2023-08-09", until="2024-01-02"
        )

        self.assertEqual([row["steamid"] for row in filtered], ["111", "222"])

    def test_rejects_invalid_filter_dates(self):
        for value in ("2024-02-30", "02/20/2024", "2024-2-20"):
            with self.subTest(value=value), self.assertRaises(
                steam_friends.argparse.ArgumentTypeError
            ):
                steam_friends.parse_date(value)

    def test_includes_optional_player_details(self):
        friends = [{"steamid": "111", "friend_since": 100}]
        players = {
            "111": {
                "personaname": "Alpha",
                "personastate": 3,
                "lastlogoff": 200,
                "loccountrycode": "US",
                "gameextrainfo": "Portal 2",
                "profileurl": "https://steamcommunity.com/id/alpha/",
                "realname": "Alice Example",
                "timecreated": 300,
                "communityvisibilitystate": 3,
            }
        }

        row = steam_friends.build_rows(
            friends, players, utc=True, oldest_first=False
        )[0]

        self.assertEqual(row["name"], "Alpha")
        self.assertEqual(row["status"], "away")
        self.assertEqual(row["last_logoff"], "1970-01-01 00:03")
        self.assertEqual(row["country"], "US")
        self.assertEqual(row["game"], "Portal 2")
        self.assertEqual(row["real_name"], "Alice Example")
        self.assertEqual(row["account_created"], "1970-01-01 00:05")
        self.assertEqual(row["visibility"], "public")

    def test_filters_by_presence_state(self):
        rows = [
            {"added": "", "steamid": "111", "name": "A", "status": "online"},
            {"added": "", "steamid": "222", "name": "B", "status": "away"},
        ]

        filtered = steam_friends.filter_rows(rows, state="away")

        self.assertEqual([row["steamid"] for row in filtered], ["222"])

    def test_filters_by_country_and_current_game(self):
        rows = [
            {"added": "", "steamid": "111", "name": "A", "status": "online",
             "country": "US", "game": "Portal 2"},
            {"added": "", "steamid": "222", "name": "B", "status": "away",
             "country": "GB", "game": ""},
            {"added": "", "steamid": "333", "name": "C", "status": "online",
             "country": "US", "game": "Half-Life"},
        ]

        in_game = steam_friends.filter_rows(rows, country="US", playing="")
        matching_game = steam_friends.filter_rows(rows, playing="PORTAL")

        self.assertEqual([row["steamid"] for row in in_game], ["111", "333"])
        self.assertEqual([row["steamid"] for row in matching_game], ["111"])

    def test_sorts_profile_fields_and_keeps_missing_values_last(self):
        rows = [
            {"steamid": "111", "friend_since": 100, "name": "Zulu",
             "status": "away", "last_logoff": "2024-01-01 00:00",
             "account_created_timestamp": 200},
            {"steamid": "222", "friend_since": 300, "name": "alpha",
             "status": "online", "last_logoff": "",
             "account_created_timestamp": 100},
            {"steamid": "333", "friend_since": 0, "name": "",
             "status": "offline", "last_logoff": "2025-01-01 00:00",
             "account_created_timestamp": 0},
        ]

        by_name = steam_friends.sort_rows(rows, "name")
        by_recent_logoff = steam_friends.sort_rows(rows, "last-logoff")
        by_oldest_account = steam_friends.sort_rows(
            rows, "account-created", reverse=True
        )
        by_status = steam_friends.sort_rows(rows, "status")

        self.assertEqual([row["steamid"] for row in by_name], ["222", "111", "333"])
        self.assertEqual(
            [row["steamid"] for row in by_recent_logoff], ["333", "111", "222"]
        )
        self.assertEqual(
            [row["steamid"] for row in by_oldest_account], ["222", "111", "333"]
        )
        self.assertEqual(
            [row["steamid"] for row in by_status], ["222", "111", "333"]
        )

    def test_hides_player_details_unless_requested(self):
        row = {
            "added": "", "friend_since": 0, "steamid": "111", "name": "A",
            "relationship": "friend", "status": "online", "last_logoff": "",
            "country": "US", "game": "", "profile_url": "https://example.test/",
            "real_name": "", "account_created": "", "visibility": "public",
        }
        compact = io.StringIO()
        detailed = io.StringIO()

        steam_friends.write_output([row], "json", compact, show_rel=False)
        steam_friends.write_output(
            [row], "json", detailed, show_rel=False, show_details=True
        )

        self.assertNotIn("status", json.loads(compact.getvalue())[0])
        self.assertEqual(json.loads(detailed.getvalue())[0]["status"], "online")


class PlayerFetchingTests(unittest.TestCase):
    def test_preserves_full_player_summaries_across_batches(self):
        ids = [str(index) for index in range(101)]

        def fake_call(endpoint, key, params):
            self.assertEqual(endpoint, "ISteamUser/GetPlayerSummaries/v2/")
            players = [
                {"steamid": steam_id, "personaname": f"Player {steam_id}"}
                for steam_id in params["steamids"].split(",")
            ]
            return {"response": {"players": players}}

        with redirect_stderr(io.StringIO()), mock.patch.object(
            steam_friends, "call", side_effect=fake_call
        ) as call:
            players = steam_friends.fetch_players(ids, "a" * 32)

        self.assertEqual(call.call_count, 2)
        self.assertEqual(players["100"]["personaname"], "Player 100")


class SnapshotTests(unittest.TestCase):
    def test_tracks_added_removed_and_renamed_friends(self):
        original = [
            {"steamid": "111", "friend_since": 100, "name": "Alpha",
             "relationship": "friend"},
            {"steamid": "222", "friend_since": 200, "name": "Beta",
             "relationship": "friend"},
        ]
        changed = [
            {"steamid": "111", "friend_since": 100, "name": "Alpha Prime",
             "relationship": "friend"},
            {"steamid": "333", "friend_since": 300, "name": "Gamma",
             "relationship": "friend"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "friends.json"
            baseline = steam_friends.update_snapshot(
                str(path), "76561198000000000", "friend", original
            )
            first = steam_friends.load_snapshot(
                str(path), "76561198000000000", "friend"
            )
            report = steam_friends.update_snapshot(
                str(path), "76561198000000000", "friend", changed
            )

            self.assertEqual(
                steam_friends.stat.S_IMODE(path.stat().st_mode), 0o600
            )

        self.assertIn("snapshot baseline saved: 2 friends", baseline)
        self.assertEqual(first["friends"][0]["name"], "Alpha")
        self.assertIn("1 added, 1 removed, 1 renamed", report)
        self.assertIn("+ Gamma (333)", report)
        self.assertIn("- Beta (222)", report)
        self.assertIn("Alpha → Alpha Prime (111)", report)

    def test_preserves_known_names_when_a_profile_lookup_is_missing(self):
        previous = {
            "friends": [
                {"steamid": "111", "friend_since": 100, "name": "Alpha",
                 "relationship": "friend"}
            ]
        }
        current = [
            {"steamid": "111", "friend_since": 100, "name": "",
             "relationship": "friend"}
        ]

        rows = steam_friends.prepare_snapshot_rows(current, previous)

        self.assertEqual(rows[0]["name"], "Alpha")

    def test_skips_friends_without_a_steamid_so_the_snapshot_stays_readable(self):
        rows = [
            {"steamid": "111", "friend_since": 100, "name": "Alpha",
             "relationship": "friend"},
            {"steamid": "", "friend_since": 200, "name": "",
             "relationship": "friend"},
        ]

        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "friends.json"
            steam_friends.update_snapshot(
                str(path), "76561198000000000", "friend", rows
            )
            report = steam_friends.update_snapshot(
                str(path), "76561198000000000", "friend", rows
            )
            saved = steam_friends.load_snapshot(
                str(path), "76561198000000000", "friend"
            )

        self.assertEqual([f["steamid"] for f in saved["friends"]], ["111"])
        self.assertIn("0 added, 0 removed, 0 renamed", report)

    def test_rejects_a_snapshot_for_a_different_account(self):
        rows = [
            {"steamid": "111", "friend_since": 100, "name": "Alpha",
             "relationship": "friend"}
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "friends.json"
            steam_friends.update_snapshot(
                str(path), "76561198000000000", "friend", rows
            )

            with self.assertRaises(steam_friends.SnapshotError):
                steam_friends.load_snapshot(
                    str(path), "76561198000000001", "friend"
                )


class MainTests(unittest.TestCase):
    def test_empty_friend_list_still_writes_output_and_saves_when_requested(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        steam_id = "76561198000000000"
        argv = ["steam-friends", "--format", "json", "--no-names", "--save"]

        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(steam_friends.sys, "argv", argv))
            stack.enter_context(mock.patch.object(steam_friends.sys, "stdout", stdout))
            stack.enter_context(mock.patch.object(steam_friends.sys, "stderr", stderr))
            stack.enter_context(mock.patch.object(
                steam_friends,
                "gather_credentials",
                return_value=("a" * 32, steam_id, False),
            ))
            stack.enter_context(
                mock.patch.object(steam_friends, "resolve", return_value=steam_id)
            )
            stack.enter_context(
                mock.patch.object(steam_friends, "fetch_friends", return_value=[])
            )
            save_config = stack.enter_context(
                mock.patch.object(steam_friends, "save_config")
            )
            result = steam_friends.main()

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(stdout.getvalue()), [])
        save_config.assert_called_once_with("a" * 32, steam_id)

    def test_tracking_snapshots_the_full_list_before_output_filters(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        steam_id = "76561198000000000"
        friend = {"steamid": "76561198000000001", "friend_since": 100,
                  "relationship": "friend"}

        with tempfile.TemporaryDirectory() as directory:
            snapshot = pathlib.Path(directory) / "friends.json"
            argv = [
                "steam-friends", "--no-names", "--no-summary", "--match",
                "not-present", "--track", str(snapshot),
            ]
            with ExitStack() as stack:
                stack.enter_context(mock.patch.object(steam_friends.sys, "argv", argv))
                stack.enter_context(mock.patch.object(steam_friends.sys, "stdout", stdout))
                stack.enter_context(mock.patch.object(steam_friends.sys, "stderr", stderr))
                stack.enter_context(mock.patch.object(
                    steam_friends, "gather_credentials",
                    return_value=("a" * 32, steam_id, False),
                ))
                stack.enter_context(mock.patch.object(
                    steam_friends, "resolve", return_value=steam_id
                ))
                stack.enter_context(mock.patch.object(
                    steam_friends, "fetch_friends", return_value=[friend]
                ))
                result = steam_friends.main()

            saved = steam_friends.load_snapshot(str(snapshot), steam_id, "friend")

        self.assertEqual(result, 0)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(len(saved["friends"]), 1)
        self.assertIn("snapshot baseline saved: 1 friend", stderr.getvalue())


class ConfigTests(unittest.TestCase):
    def test_ignores_non_string_config_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "config.json"
            path.write_text(
                json.dumps({"api_key": 123, "steam_id": "valid-id", "extra": True}),
                encoding="utf-8",
            )
            old_path = steam_friends.CONFIG_PATH
            steam_friends.CONFIG_PATH = str(path)
            try:
                with redirect_stderr(io.StringIO()):
                    config = steam_friends.load_config()
            finally:
                steam_friends.CONFIG_PATH = old_path

        self.assertEqual(config, {"steam_id": "valid-id"})


if __name__ == "__main__":
    unittest.main()
