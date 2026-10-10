"""Tests for browser.py launch options."""

from unittest.mock import MagicMock, patch

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
