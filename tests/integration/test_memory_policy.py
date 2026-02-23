import os
import tempfile
import unittest

from eap.protocol import MemoryStrategy, StateManager


class MemoryPolicyIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(prefix="eap-memory-policy-", suffix=".db")
        os.close(fd)
        self.manager = StateManager(db_path=self.db_path)

    def tearDown(self) -> None:
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_window_strategy_trims_to_limit(self) -> None:
        session = self.manager.create_session(
            session_id="sess_window",
            memory_strategy=MemoryStrategy.WINDOW,
            window_turn_limit=3,
        )
        for idx in range(5):
            self.manager.append_turn(
                session_id=session["session_id"],
                role="user",
                content=f"window-turn-{idx}",
            )

        turns = self.manager.list_turns(session["session_id"])
        self.assertEqual(len(turns), 3)
        self.assertEqual([turn["content"] for turn in turns], ["window-turn-2", "window-turn-3", "window-turn-4"])

    def test_summary_strategy_compacts_old_turns(self) -> None:
        session = self.manager.create_session(
            session_id="sess_summary",
            memory_strategy=MemoryStrategy.SUMMARY,
        )
        for idx in range(6):
            self.manager.append_turn(
                session_id=session["session_id"],
                role="assistant" if idx % 2 else "user",
                content=f"summary-turn-{idx}",
                pointer_ids=[f"ptr_{idx}"],
            )

        # Force a smaller keep window for deterministic assertions.
        result = self.manager.apply_memory_policy(
            session_id=session["session_id"],
            keep_recent_turns=2,
            max_summary_chars=400,
        )
        self.assertTrue(result["summary_updated"])

        turns = self.manager.list_turns(session["session_id"])
        self.assertEqual(len(turns), 2)
        self.assertEqual([turn["content"] for turn in turns], ["summary-turn-4", "summary-turn-5"])

        updated_session = self.manager.get_session(session["session_id"])
        self.assertIsNotNone(updated_session["summary_text"])
        self.assertIn("summary-turn-0", updated_session["summary_text"])
        self.assertIn("ptr_0", updated_session["summary_text"])

    def test_summary_text_is_bounded(self) -> None:
        session = self.manager.create_session(
            session_id="sess_summary_bound",
            memory_strategy=MemoryStrategy.SUMMARY,
        )
        for idx in range(12):
            self.manager.append_turn(
                session_id=session["session_id"],
                role="user",
                content=f"{idx}-" + ("very-long-content-" * 20),
            )

        self.manager.apply_memory_policy(
            session_id=session["session_id"],
            keep_recent_turns=2,
            max_summary_chars=120,
        )
        updated_session = self.manager.get_session(session["session_id"])
        self.assertLessEqual(len(updated_session["summary_text"]), 120)


if __name__ == "__main__":
    unittest.main()
