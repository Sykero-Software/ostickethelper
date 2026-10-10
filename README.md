# OSTicket Helper

A CLI tool for managing [OSTicket](https://osticket.com/) tickets via browser automation. Supports listing and reading tickets (with attachment download and PDF receipt generation), replying, resolving, closing, and internal notes, also many at once in a single login.

## How it works

OSTicket does not provide a public REST API for agent operations (listing, reading, replying to and resolving tickets). This tool works around that limitation by automating the staff control panel (SCP) web interface using [Playwright](https://playwright.dev/python/) (headless Chromium).

This approach has trade-offs compared to a proper API:

- **Fragile**: UI changes in OSTicket updates may break the scraping logic.
- **Slower**: each operation involves full page loads and DOM parsing.
- **Auth**: login is done via form submission with username/password (no token-based auth).

Tested and working with **OSTicket 1.17.5**. Other versions may work but are not guaranteed.

## Features

- **List** open/closed tickets, grouped by user
- **Read** tickets: download attachments, generate a combined PDF receipt (Typst summary page + attachment pages)
- **Resolve** tickets with a message
- **Batch** replies, resolves, closes and internal notes in one login (one password decryption)
- **Fully localizable**: all user-facing strings are configurable via YAML

## Requirements

- Python 3.10+
- A Chromium browser for [Playwright](https://playwright.dev/python/): either Playwright's own
  (`playwright install chromium`) or an installed Google Chrome (`browser_channel: chrome`, see below)
- [Typst](https://typst.app/), only for PDF receipts (`read` without `--no-pdf`)
- GPG, only for a `.gpg` password file

## Installation

As a command-line tool on your `PATH`, with [uv](https://docs.astral.sh/uv/) (or the same URL with
`pipx install`):

```bash
uv tool install git+https://github.com/Sykero-Software/ostickethelper
# Only if you don't use an installed Chrome (browser_channel: chrome):
uv tool run --from git+https://github.com/Sykero-Software/ostickethelper playwright install chromium
```

For development, from a clone (uses [Poetry](https://python-poetry.org/)):

```bash
poetry install
poetry run playwright install chromium
poetry run pytest
```

## Configuration

Create a YAML config file and pass it with `--config` on every run (there is no usable default
location). `src/ostickethelper/defaults.yaml` holds the defaults:

```yaml
osticket:
  url: "https://your-osticket-instance.com"
  username: "agent"
  work_dir: "/home/me/osticket"         # optional: base for the relative paths below
  password: "your-password"              # option 1: direct password
  # secrets_file: "secrets/password.txt" # option 2: plain text file
  # secrets_file: "secrets/pw.txt.gpg"   # option 3: GPG-encrypted file
  headless: true
  slow_mo: 0
  browser_channel: "chrome"             # optional: use the installed Chrome
  inbox_dir: "inbox/osticket"
  logo_path: "resources/logo.png"       # optional
  temp_dir: ".tmp"                      # optional, default: ".tmp"
  template_path: "my-template.typ"      # optional, default: built-in template
```

Relative paths (`secrets_file`, `inbox_dir`, `logo_path`, `temp_dir`, `template_path`) are resolved
against `work_dir` if set, otherwise against the directory you run the command in. Set `work_dir` to
run the tool from anywhere.

### Authentication

The password can be provided in several ways (first match wins):

1. **Environment variable**: `OSTICKET_PASSWORD=secret ostickethelper list`
2. **Config field**: `password: "your-password"` in the config file
3. **Plain text file**: `secrets_file: "path/to/password.txt"` — reads the file contents
4. **GPG-encrypted file**: `secrets_file: "path/to/password.txt.gpg"` — decrypts with `gpg --decrypt`

At least one of these must be configured.

### Configuration fields

| Field | Required | Description |
|-------|----------|-------------|
| `url` | Yes | OSTicket base URL |
| `username` | Yes | Agent username |
| `work_dir` | No | Base directory for relative paths (default: the current directory) |
| `password` | No* | Password (plain text in config) |
| `secrets_file` | No* | Path to password file (plain text or `.gpg`) |
| `headless` | No | Run browser headless (default: `true`) |
| `slow_mo` | No | Slow down browser actions in ms (default: `0`) |
| `browser_channel` | No | Use an installed browser instead of Playwright's Chromium, e.g. `chrome` (then `playwright install chromium` is not needed) |
| `inbox_dir` | No | Where `read` writes tickets, attachments and receipts (default: `inbox/osticket`) |
| `logo_path` | No | Logo image for PDF receipts (omit for no logo) |
| `temp_dir` | No | Temporary directory for Typst compilation (default: `.tmp`) |
| `template_path` | No | Custom Typst template (default: built-in `template.typ`) |

\*One of `password`, `secrets_file`, or `OSTICKET_PASSWORD` env var is required.

## String customization (localization)

All user-facing strings can be overridden in the config file under the `strings` section. The tool ships with English defaults (`defaults.yaml`). To localize, add a `strings` section to your config:

```yaml
strings:
  formatter:
    no_open_tickets: "Ei avoimia tikettejä."
    open_tickets_header: "Avoimet tiketit"
    total: "Yhteensä: {count} tikettiä"
  cli:
    logging_in: "Kirjaudutaan OSTicketiin..."
  pdf:
    title: "TOSITE"
    lang: "fi"
```

Only override the strings you want to change; the rest will use English defaults. See `src/ostickethelper/defaults.yaml` for the full list of available string keys.

## Usage

Tickets are addressed by their **internal ID**: the `[id=...]` that `list` prints, the same as in
the staff URL `tickets.php?id=...`. It is not the ticket number shown in the web UI and in emails.

Write commands (`resolve`, and `batch` actions other than `note`) email the ticket's user, just as
replying in the web UI does.

```bash
# List open tickets
ostickethelper --config config.yaml list

# List closed tickets
ostickethelper --config config.yaml list --status closed

# List only tickets from a specific user
ostickethelper --config config.yaml list --user "John Doe"

# Read tickets: writes inbox_dir/<id>/ticket.json and attachments, and the PDF receipt
# inbox_dir/<id>.pdf; prints the tickets
ostickethelper --config config.yaml read 339 340

# Read without generating PDF
ostickethelper --config config.yaml read 339 --no-pdf

# Re-read and overwrite an already-generated PDF
ostickethelper --config config.yaml read 339 --force

# Resolve tickets
ostickethelper --config config.yaml resolve 339 340 --message "Paid"

# Run many actions with a single login
ostickethelper --config config.yaml batch actions.yaml --dry-run   # validate, print plan
ostickethelper --config config.yaml batch actions.yaml
```

### Batch file

Each login decrypts the password once, which with a GPG hardware key means one touch. `batch` runs
any number of actions in one login. The file is a YAML list:

```yaml
- ticket: 339
  action: resolve          # reply + status Resolved
  message: |
    Fixed in version 1.2.3.

    Thanks for the report!
- ticket: 340
  action: reply            # reply, status unchanged
  message: "Which version are you using?"
- ticket: 341
  action: close            # reply + status Closed
  message: "Closing as duplicate of #339."
- ticket: 342
  action: note             # internal note, not emailed to the user
  message: "Root cause found, fix pending."
```

`ticket` is the internal ID (as in `tickets.php?id=...`). The whole file is validated before logging
in, so a typo never costs a login. A failing action does not stop the rest; the exit code is 1 if any
action failed. Each outcome is printed as soon as it is known: `OK`, `FAILED`, or `UNKNOWN` (submitted
but not confirmed, so it may have been sent). Actions are not idempotent: before re-running a file,
remove the items that succeeded and check the `UNKNOWN` tickets, or users get duplicate replies.

Messages are plain text. osTicket strips anything that looks like an HTML tag, even when escaped, so
the tool puts an invisible zero-width space after a `<` that would start a tag (`List<String>` stays
readable).

`--no-headless` is a global option (place it before the subcommand) that runs Chromium with a visible window — useful for debugging when the SCP scraping breaks after an OSTicket update:

```bash
ostickethelper --config config.yaml --no-headless read 339
```

## PDF template customization

The default PDF template (`template.typ`) uses `string.Template` syntax with `$variable` placeholders. You can provide your own template via the `template_path` config option.

Available template variables:

| Variable | Description |
|----------|-------------|
| `$document_title` | Document title (page/PDF metadata, e.g. `OSTicket #339`) |
| `$title_block` | Rendered title heading (Typst markup, includes `strings.pdf.title` if set) |
| `$ticket_id` | Ticket ID |
| `$ticket_number` | Ticket number |
| `$ticket_url` | Ticket URL |
| `$logo_block` | Typst `#image(...)` block, or empty if no logo |
| `$subject` | Ticket subject (Typst-escaped) |
| `$user_name` | Sender name (Typst-escaped) |
| `$date_display` | Creation date |
| `$today_display` | Processing date |
| `$message` | Ticket message (Typst-escaped) |
| `$attachments_block` | Typst-formatted attachment list |
| `$lang` | Language code (from `strings.pdf.lang`) |
| `$lbl_ticket` | Label: "Ticket" |
| `$lbl_subject` | Label: "Subject" |
| `$lbl_sender` | Label: "Sender" |
| `$lbl_created` | Label: "Created" |
| `$lbl_processed` | Label: "Processed" |
| `$lbl_message` | Label: "Message" |
| `$lbl_attachments` | Label: "Attachments" |

## Disclaimer

This project was built with the help of [Claude Code](https://docs.anthropic.com/en/docs/claude-code). The code has only been cursorily reviewed by the author. Use at your own risk.

## License

GPL-3.0 — see [LICENSE](LICENSE).
