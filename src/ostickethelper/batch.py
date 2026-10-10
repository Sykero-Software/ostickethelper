"""Batch processing: run many ticket actions in one login (one password decryption)."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

# Action name -> ticket status set by the reply (None keeps the current status).
REPLY_STATUSES = {"reply": None, "resolve": "Resolved", "close": "Closed"}
ACTIONS = (*REPLY_STATUSES, "note")
_KEYS = {"ticket", "action", "message"}


@dataclass(frozen=True)
class BatchAction:
    """One action from a batch file."""
    ticket: str
    action: str
    message: str


@dataclass(frozen=True)
class BatchResult:
    """Outcome of one batch action; `error` holds the exception text, if any."""
    action: BatchAction
    ok: bool
    error: Optional[str] = None


def _parse_item(item) -> tuple[Optional[BatchAction], list[str]]:
    if not isinstance(item, dict):
        return None, ["must be a mapping with ticket, action and message"]
    problems = []
    unknown = sorted(set(item) - _KEYS)
    if unknown:
        problems.append(f"unknown keys: {', '.join(unknown)}")
    ticket = item.get("ticket")
    if ticket is None or str(ticket).strip() == "":
        problems.append("missing ticket")
    action = item.get("action")
    if action not in ACTIONS:
        problems.append(f"unknown action {action!r} (expected one of: {', '.join(ACTIONS)})")
    message = item.get("message")
    if not isinstance(message, str) or not message.strip():
        problems.append("missing or empty message")
    if problems:
        return None, problems
    return BatchAction(str(ticket).strip(), action, message.strip()), []


def load_actions(path: Path) -> list[BatchAction]:
    """
    Load and validate a batch file: a YAML list of {ticket, action, message} items.

    Every item is checked before anything runs, so a mistake in the file never costs a login.

    Raises:
        ValueError: listing every invalid item by its 1-based position.
    """
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if data is None:
        raise ValueError(f"{path}: no actions")
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a list of actions")
    if not data:
        raise ValueError(f"{path}: no actions")

    actions, errors = [], []
    for index, item in enumerate(data, start=1):
        action, problems = _parse_item(item)
        if problems:
            errors.append(f"item {index}: {'; '.join(problems)}")
        else:
            actions.append(action)
    if errors:
        raise ValueError(f"{path}: invalid batch file\n" + "\n".join(errors))
    return actions


def run_batch(browser, actions: list[BatchAction], on_start=None) -> list[BatchResult]:
    """
    Run actions in order on a logged-in browser. A failing action does not stop the batch.

    Args:
        browser: An OSTicketBrowser (or anything with reply_ticket/post_internal_note).
        actions: Validated actions from load_actions().
        on_start: Optional callback called with each action before it runs (progress output).
    """
    results = []
    for action in actions:
        if on_start:
            on_start(action)
        try:
            if action.action == "note":
                ok = browser.post_internal_note(action.ticket, action.message)
            else:
                ok = browser.reply_ticket(action.ticket, action.message,
                                          status=REPLY_STATUSES[action.action])
            results.append(BatchResult(action, bool(ok)))
        except Exception as e:
            results.append(BatchResult(action, False, str(e)))
    return results
