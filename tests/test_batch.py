"""Tests for batch.py: action file parsing and batch execution."""

import pytest

from ostickethelper.batch import BatchAction, load_actions, run_batch


def _write(tmp_path, text):
    path = tmp_path / "actions.yaml"
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadActions:
    def test_parses_all_action_kinds(self, tmp_path):
        path = _write(tmp_path, """
- {ticket: 1, action: resolve, message: "Fixed"}
- {ticket: "2", action: reply, message: "More info?"}
- {ticket: 3, action: close, message: "Closing"}
- {ticket: 4, action: note, message: "Fixed in abc123"}
""")
        assert load_actions(path) == [
            BatchAction("1", "resolve", "Fixed"),
            BatchAction("2", "reply", "More info?"),
            BatchAction("3", "close", "Closing"),
            BatchAction("4", "note", "Fixed in abc123"),
        ]

    def test_multiline_message_kept_without_trailing_newline(self, tmp_path):
        path = _write(tmp_path, """
- ticket: 1
  action: reply
  message: |
    Hello,

    thanks!
""")
        assert load_actions(path)[0].message == "Hello,\n\nthanks!"

    def test_reports_every_invalid_item_with_its_position(self, tmp_path):
        path = _write(tmp_path, """
- {ticket: 1, action: resolve, message: "ok"}
- {ticket: 2, action: delete, message: "x"}
- {action: reply, message: "x"}
- {ticket: 4, action: note, message: "   "}
- {ticket: 5, action: reply, message: "x", extra: 1}
""")
        with pytest.raises(ValueError) as exc:
            load_actions(path)
        text = str(exc.value)
        assert "item 2" in text and "delete" in text
        assert "item 3" in text and "ticket" in text
        assert "item 4" in text and "message" in text
        assert "item 5" in text and "extra" in text
        assert "item 1" not in text

    def test_rejects_non_list_file(self, tmp_path):
        path = _write(tmp_path, "ticket: 1\naction: reply\nmessage: x\n")
        with pytest.raises(ValueError, match="list"):
            load_actions(path)

    def test_rejects_empty_file(self, tmp_path):
        with pytest.raises(ValueError, match="no actions"):
            load_actions(_write(tmp_path, ""))


class FakeBrowser:
    """Records calls; tickets listed in `fail` return False, in `explode` raise."""

    def __init__(self, fail=(), explode=()):
        self.calls = []
        self.fail = set(fail)
        self.explode = set(explode)

    def _outcome(self, ticket_id):
        if ticket_id in self.explode:
            raise RuntimeError(f"boom {ticket_id}")
        return ticket_id not in self.fail

    def reply_ticket(self, ticket_id, message, status=None):
        self.calls.append(("reply", ticket_id, message, status))
        return self._outcome(ticket_id)

    def post_internal_note(self, ticket_id, message):
        self.calls.append(("note", ticket_id, message))
        return self._outcome(ticket_id)


class TestRunBatch:
    def test_dispatches_each_action_to_the_right_browser_call(self):
        browser = FakeBrowser()
        run_batch(browser, [
            BatchAction("1", "reply", "a"),
            BatchAction("2", "resolve", "b"),
            BatchAction("3", "close", "c"),
            BatchAction("4", "note", "d"),
        ])
        assert browser.calls == [
            ("reply", "1", "a", None),
            ("reply", "2", "b", "Resolved"),
            ("reply", "3", "c", "Closed"),
            ("note", "4", "d"),
        ]

    def test_continues_after_failures_and_reports_each_result(self):
        browser = FakeBrowser(fail={"2"}, explode={"3"})
        actions = [
            BatchAction("1", "resolve", "a"),
            BatchAction("2", "resolve", "b"),
            BatchAction("3", "note", "c"),
            BatchAction("4", "reply", "d"),
        ]
        results = run_batch(browser, actions)

        assert len(browser.calls) == 4
        assert [r.ok for r in results] == [True, False, False, True]
        assert [r.action for r in results] == actions
        assert "boom 3" in results[2].error
        assert results[0].error is None


class TestBatchCommand:
    """CLI wiring: validation and --dry-run must never decrypt the password (load_config)."""

    VALID = "- {ticket: 1, action: resolve, message: Fixed}\n- {ticket: 2, action: note, message: abc}\n"

    def _invoke(self, tmp_path, text, *args, browser=None):
        from unittest.mock import MagicMock, patch
        from click.testing import CliRunner
        from ostickethelper.cli import cli

        path = _write(tmp_path, text)
        load_config = MagicMock()
        load_config.return_value.strings = {}
        browser_cls = MagicMock()
        browser_cls.return_value.__enter__.return_value = browser or FakeBrowser()
        with patch("ostickethelper.cli.load_config", load_config), \
                patch("ostickethelper.cli.OSTicketBrowser", browser_cls):
            result = CliRunner().invoke(cli, ["batch", str(path), *args])
        return result, load_config, browser_cls

    def test_dry_run_prints_plan_without_logging_in(self, tmp_path):
        result, load_config, browser_cls = self._invoke(tmp_path, self.VALID, "--dry-run")
        assert result.exit_code == 0
        assert "resolve" in result.output and "#1" in result.output and "Fixed" in result.output
        load_config.assert_not_called()
        browser_cls.assert_not_called()

    def test_invalid_file_fails_before_logging_in(self, tmp_path):
        result, load_config, _ = self._invoke(tmp_path, "- {ticket: 1, action: nope, message: x}\n")
        assert result.exit_code == 1
        assert "item 1" in result.output
        load_config.assert_not_called()

    def test_runs_all_actions_in_one_login(self, tmp_path):
        browser = FakeBrowser()
        result, load_config, browser_cls = self._invoke(tmp_path, self.VALID, browser=browser)
        assert result.exit_code == 0
        load_config.assert_called_once()
        browser_cls.assert_called_once()
        assert [c[0] for c in browser.calls] == ["reply", "note"]

    def test_exit_code_1_when_any_action_fails(self, tmp_path):
        result, _, _ = self._invoke(tmp_path, self.VALID, browser=FakeBrowser(fail={"2"}))
        assert result.exit_code == 1
        assert "FAILED" in result.output


class TestLoadActionsStrictness:
    def test_ticket_must_be_a_numeric_id(self, tmp_path):
        path = _write(tmp_path, """
- {ticket: abc, action: reply, message: x}
- {ticket: true, action: reply, message: x}
- {ticket: 12.5, action: reply, message: x}
- {ticket: "42", action: reply, message: x}
""")
        with pytest.raises(ValueError) as exc:
            load_actions(path)
        text = str(exc.value)
        assert "item 1" in text and "item 2" in text and "item 3" in text
        assert "item 4" not in text

    def test_non_string_message_says_to_quote_it(self, tmp_path):
        path = _write(tmp_path, "- {ticket: 1, action: reply, message: yes}\n")
        with pytest.raises(ValueError, match="quote"):
            load_actions(path)


class TestRunBatchReporting:
    def test_reports_each_outcome_as_it_happens(self):
        seen = []
        browser = FakeBrowser(fail={"2"})
        run_batch(browser, [BatchAction("1", "reply", "a"), BatchAction("2", "note", "b")],
                  on_done=lambda r: seen.append((r.action.ticket, r.ok, len(browser.calls))))
        assert seen == [("1", True, 1), ("2", False, 2)]

    def test_unconfirmed_submit_is_marked_as_unknown_state(self):
        from ostickethelper.browser import SubmitUnconfirmedError

        class SlowBrowser(FakeBrowser):
            def reply_ticket(self, ticket_id, message, status=None):
                raise SubmitUnconfirmedError("no navigation")

        [result] = run_batch(SlowBrowser(), [BatchAction("1", "resolve", "a")])
        assert not result.ok
        assert result.unknown
        [plain] = run_batch(FakeBrowser(explode={"1"}), [BatchAction("1", "resolve", "a")])
        assert not plain.unknown


class TestBatchCommandInterrupted:
    def test_results_are_printed_even_if_closing_the_browser_fails(self, tmp_path):
        from unittest.mock import MagicMock, patch
        from click.testing import CliRunner
        from ostickethelper.cli import cli

        path = _write(tmp_path, TestBatchCommand.VALID)
        browser_cls = MagicMock()
        browser_cls.return_value.__enter__.return_value = FakeBrowser()
        browser_cls.return_value.__exit__.side_effect = RuntimeError("close failed")
        load_config = MagicMock()
        load_config.return_value.strings = {}
        with patch("ostickethelper.cli.load_config", load_config), \
                patch("ostickethelper.cli.OSTicketBrowser", browser_cls):
            result = CliRunner().invoke(cli, ["batch", str(path)])
        assert result.exit_code == 1
        assert "OK resolve #1" in result.output
        assert "OK note #2" in result.output
        assert "close failed" in result.output
