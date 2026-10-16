import os
import tempfile
import time
import unittest

os.environ["PROFILE_STORE"] = "off"

import player
import storage
from test_player import state


class StorageTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.saved = storage.ENABLED, storage.FILE, storage.URL, storage.TOKEN
        storage.ENABLED, storage.FILE = True, os.path.join(self.dir.name, "profiles.json")
        storage.URL = storage.TOKEN = None
        storage._last_save[0] = 0.0

    def tearDown(self):
        storage.ENABLED, storage.FILE, storage.URL, storage.TOKEN = self.saved
        self.dir.cleanup()

    def wait_for_file(self):
        for _ in range(100):
            if os.path.exists(storage.FILE):
                return
            time.sleep(0.01)

    def test_file_round_trip(self):
        storage.save_soon({"bot|1": {"hands": 3}})
        self.wait_for_file()
        self.assertEqual(storage.load(), {"bot|1": {"hands": 3}})

    def test_saves_are_throttled(self):
        storage.save_soon({"a": {}})
        self.wait_for_file()
        storage.save_soon({"b": {}})
        time.sleep(0.05)
        self.assertEqual(storage.load(), {"a": {}})

    def test_missing_or_broken_store_loads_empty(self):
        self.assertEqual(storage.load(), {})
        with open(storage.FILE, "w") as f:
            f.write("not json")
        self.assertEqual(storage.load(), {})

    def test_unreachable_redis_loads_empty(self):
        storage.URL, storage.TOKEN = "http://127.0.0.1:9", "x"
        self.assertEqual(storage.load(), {})

    def test_env_file(self):
        path = os.path.join(self.dir.name, ".env")
        with open(path, "w") as f:
            f.write("# comment\nTEST_STORAGE_A=one\nTEST_STORAGE_B = \"two\"\n")
        os.environ["TEST_STORAGE_A"] = "already set"
        try:
            storage.load_env(path)
            self.assertEqual(os.environ["TEST_STORAGE_A"], "already set")
            self.assertEqual(os.environ["TEST_STORAGE_B"], "two")
        finally:
            os.environ.pop("TEST_STORAGE_A", None)
            os.environ.pop("TEST_STORAGE_B", None)


class ProfileTest(unittest.TestCase):
    def setUp(self):
        player.OPPONENTS.clear()
        player.PROFILES.clear()
        player.ROUNDS.clear()

    def play(self, game_id, rnd, other_bet):
        gs = state(["7h", "2d"], current_buy_in=other_bet)
        gs.update(game_id=game_id, round=rnd)
        gs["players"][0].update(bet=other_bet, version="v1")
        player.Player().betRequest(gs)
        return gs

    def test_hands_are_saved_once_per_round(self):
        self.play("g", 0, 100)
        self.play("g", 0, 100)  # second bet request in the same hand
        gs = self.play("g", 1, 20)
        player.Player().showdown(gs)
        player.Player().showdown(gs)  # repeated showdown must not double count
        self.assertEqual(player.PROFILES["other|v1"], {"hands": 2, "raises": 1, "shoves": 0})

    def test_profile_survives_a_new_game(self):
        for rnd in range(3):
            self.play("g1", rnd, 100)
        self.play("g2", 0, 20)
        self.assertEqual(player.PROFILES["other|v1"]["hands"], 2)  # last hand of g1 had no showdown
        gs = state(["7h", "2d"])
        gs.update(game_id="g3")
        gs["players"][0]["version"] = "v1"
        self.assertEqual(player.stats_for(gs, gs["players"][0])["raises"], 2)


if __name__ == "__main__":
    unittest.main()
