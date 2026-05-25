from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from api.auth import AuthStore
from api.web_server import ConsoleApp
from workflows.storage import RunStorage


class AuthPermissionsTest(unittest.TestCase):
    def test_password_change_and_reset(self) -> None:
        with TemporaryDirectory() as temp_dir:
            auth = AuthStore(Path(temp_dir) / "app.db")
            user = auth.create_user("analyst", "old-pass")
            self.assertIsNotNone(auth.authenticate("analyst", "old-pass"))

            auth.change_password(int(user["id"]), "old-pass", "new-pass", keep_token="")
            self.assertIsNone(auth.authenticate("analyst", "old-pass"))
            self.assertIsNotNone(auth.authenticate("analyst", "new-pass"))

            auth.reset_password(int(user["id"]), "reset-pass")
            self.assertIsNone(auth.authenticate("analyst", "new-pass"))
            self.assertIsNotNone(auth.authenticate("analyst", "reset-pass"))

    def test_password_change_keeps_current_session_only(self) -> None:
        with TemporaryDirectory() as temp_dir:
            auth = AuthStore(Path(temp_dir) / "app.db")
            user = auth.create_user("editor", "old-pass")
            user_id = int(user["id"])
            current = auth.create_session(user_id)
            other = auth.create_session(user_id)

            auth.change_password(user_id, "old-pass", "new-pass", keep_token=current)

            self.assertIsNotNone(auth.user_for_session(current))
            self.assertIsNone(auth.user_for_session(other))

    def test_admin_can_access_all_runs_user_only_own(self) -> None:
        app = ConsoleApp()
        owner = {"id": 2, "role": "user"}
        other = {"id": 3, "role": "user"}
        admin = {"id": 1, "role": "admin"}
        run = {"user_id": 2}

        self.assertTrue(app.can_access_run(run, owner))
        self.assertFalse(app.can_access_run(run, other))
        self.assertTrue(app.can_access_run(run, admin))
        self.assertIsNone(app.visible_run_user_id(admin))
        self.assertEqual(app.visible_run_user_id(owner), 2)

    def test_run_storage_can_filter_by_user(self) -> None:
        with TemporaryDirectory() as temp_dir:
            storage = RunStorage(Path(temp_dir) / "runs")
            first = storage.new_run_dir()
            storage.write_run(first, {"user_id": 10, "research": {"hotspots": []}}, {})
            second = storage.new_run_dir()
            storage.write_run(second, {"user_id": 20, "research": {"hotspots": []}}, {})

            self.assertEqual(len(storage.list_runs(user_id=10)), 1)
            self.assertEqual(storage.list_runs(user_id=10)[0]["user_id"], 10)
            self.assertEqual(len(storage.list_runs(user_id=None)), 2)


if __name__ == "__main__":
    unittest.main()
