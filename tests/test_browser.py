"""Tests for browser.py launch options."""

from unittest.mock import MagicMock, patch

import pytest

from ostickethelper.browser import OSTicketBrowser

from conftest import make_config


def _launch_kwargs(config):
    playwright = MagicMock()
    with patch("ostickethelper.browser.sync_playwright") as sync_pw, \
            patch.object(OSTicketBrowser, "_login"):
        sync_pw.return_value.start.return_value = playwright
        with OSTicketBrowser(config):
            pass
    return playwright.chromium.launch.call_args.kwargs


def test_launch_without_channel_uses_bundled_chromium(tmp_path):
    kwargs = _launch_kwargs(make_config(tmp_path))
    assert "channel" not in kwargs


def test_launch_passes_configured_channel(tmp_path):
    config = make_config(tmp_path)
    config.browser_channel = "chrome"
    kwargs = _launch_kwargs(config)
    assert kwargs["channel"] == "chrome"


def _browser_with_page(tmp_path):
    browser = OSTicketBrowser(make_config(tmp_path))
    page = MagicMock()
    page.url = "https://example.com/scp/tickets.php?id=7"
    browser._page = page
    return browser, page


def test_reply_without_status_keeps_current_status(tmp_path):
    browser, page = _browser_with_page(tmp_path)
    assert browser.reply_ticket("7", "hi") is True
    page.locator.return_value.select_option.assert_not_called()
    page.get_by_role.assert_called_with("button", name="Post Reply")


def test_reply_with_status_selects_it_in_reply_form(tmp_path):
    browser, page = _browser_with_page(tmp_path)
    browser.reply_ticket("7", "bye", status="Closed")
    page.locator.assert_any_call('select[name="reply_status_id"]')
    page.locator.return_value.select_option.assert_called_once_with(["Closed"])


def test_resolve_ticket_still_returns_false_on_failure(tmp_path):
    browser, page = _browser_with_page(tmp_path)
    page.wait_for_function.side_effect = TimeoutError("no navigation")
    assert browser.resolve_ticket("7", "hi") is False


def test_internal_note_opens_note_tab_and_posts_note(tmp_path):
    browser, page = _browser_with_page(tmp_path)
    assert browser.post_internal_note("7", "fixed in abc") is True
    page.click.assert_any_call("#post-note-tab")
    page.wait_for_selector.assert_any_call("textarea#internal_note", state="attached", timeout=10000)
    assert page.evaluate.call_args.args[1] == {"selector": "textarea#internal_note", "html": "<p>fixed in abc</p>"}
    page.locator.return_value.select_option.assert_not_called()
    page.get_by_role.assert_called_with("button", name="Post Note")


def test_message_html_escapes_markup_and_keeps_paragraphs():
    from ostickethelper.browser import message_html
    assert message_html("a & b, 1 < 2\nline 2\n\n\nnext") == (
        "<p>a &amp; b, 1 &lt; 2<br>line 2</p><p>next</p>"
    )


def test_message_html_breaks_tag_lookalikes_with_zero_width_space():
    # osTicket decodes entities repeatedly before stripping tags, so escaping alone loses
    # "<String>"; a zero-width space after "<" keeps it from looking like a tag.
    from ostickethelper.browser import message_html
    assert message_html("List<String> </b> <!x> <?p") == (
        "<p>List&lt;\u200bString&gt; &lt;\u200b/b&gt; &lt;\u200b!x&gt; &lt;\u200b?p</p>"
    )


def test_submit_timeout_is_reported_as_unconfirmed(tmp_path):
    from ostickethelper.browser import SubmitUnconfirmedError
    browser, page = _browser_with_page(tmp_path)
    page.wait_for_function.side_effect = TimeoutError("no navigation")
    with pytest.raises(SubmitUnconfirmedError):
        browser.reply_ticket("7", "hi")


def test_note_tab_is_opened_before_the_note_is_filled(tmp_path):
    browser, page = _browser_with_page(tmp_path)
    browser.post_internal_note("7", "x")
    names = [c[0] for c in page.method_calls]
    assert names.index("click") < names.index("evaluate")
