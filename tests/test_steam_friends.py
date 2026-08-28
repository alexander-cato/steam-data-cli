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

    def test_empty_json_and_csv_are_valid_outputs(self):
        json_output = io.StringIO()
        steam_friends.write_output([], "json", json_output, show_rel=False)
        self.assertEqual(json.loads(json_output.getvalue()), [])

        csv_output = io.StringIO()
        steam_friends.write_output([], "csv", csv_output, show_rel=False)
        self.assertEqual(csv_output.getvalue(), "added,friend_since,steamid,name\n")


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
