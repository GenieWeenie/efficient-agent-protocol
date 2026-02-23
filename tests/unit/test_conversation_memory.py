import os
import tempfile
import unittest

from eap.protocol import MemoryStrategy, StateManager


class ConversationMemoryTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-memory-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_session_create_get_and_list(self) -> None:
        created = self.manager.create_session(
            memory_strategy=MemoryStrategy.WINDOW,
            window_turn_limit=5,
            metadata={"owner": "test"},
        )
        self.assertTrue(created["session_id"].startswith("sess_"))
        fetched = self.manager.get_session(created["session_id"])
        self.assertEqual(fetched["memory_strategy"], "window")
        self.assertEqual(fetched["window_turn_limit"], 5)

        sessions = self.manager.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["session_id"], created["session_id"])

    def test_append_and_list_turns(self) -> None:
        session = self.manager.create_session(session_id="sess_test")
        turn_1 = self.manager.append_turn(
            session_id=session["session_id"],
            role="user",
            content="Analyze this file",
            pointer_ids=["ptr_a1"],
        )
        turn_2 = self.manager.append_turn(
            session_id=session["session_id"],
            role="assistant",
            content="Done.",
            pointer_ids=["ptr_b2"],
            macro_run_id="run_123",
        )

        self.assertEqual(turn_1["role"], "user")
        self.assertEqual(turn_2["macro_run_id"], "run_123")

        turns = self.manager.list_turns(session["session_id"])
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0]["content"], "Analyze this file")
        self.assertEqual(turns[1]["content"], "Done.")
        self.assertEqual(turns[1]["pointer_ids"], ["ptr_b2"])

        updated_session = self.manager.get_session(session["session_id"])
        self.assertGreaterEqual(updated_session["updated_at_utc"], updated_session["created_at_utc"])

    def test_delete_session_removes_turns(self) -> None:
        session = self.manager.create_session(session_id="sess_delete")
        self.manager.append_turn(session_id=session["session_id"], role="user", content="hello")
        self.manager.delete_session(session["session_id"])

        with self.assertRaises(KeyError):
            self.manager.get_session(session["session_id"])
        with self.assertRaises(KeyError):
            self.manager.list_turns(session["session_id"])

    def test_append_turn_to_missing_session_fails(self) -> None:
        with self.assertRaises(KeyError):
            self.manager.append_turn(session_id="sess_missing", role="user", content="x")


if __name__ == "__main__":
    unittest.main()
