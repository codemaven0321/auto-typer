# auto-typer

Windows desktop app that types text like a person — variable speed, adjacent-key typos, self-corrections, and natural pauses. Built on the [`human-typer`](https://pypi.org/project/human-typer/) package.

## Setup

```powershell
pip install -r requirements.txt
```

## Run

```powershell
python -m app
```

Or double-click `run.bat`.

## Usage

1. Paste or type the text you want typed out.
2. For multi-field forms, put special keys **in the text** as `{TOKEN}` (use **Insert key…** or type them):

```text
John{TAB}Doe{TAB}john@email.com{ENTER}
```

| Token | Key |
|---|---|
| `{TAB}` | Tab (next field) |
| `{ENTER}` | Enter |
| `{LEFT}` `{RIGHT}` `{UP}` `{DOWN}` | Arrows |
| `{BACKSPACE}` `{DELETE}` | Edit keys |
| `{HOME}` `{END}` `{ESC}` `{SPACE}` | Other |

3. Tune CPM, jitter, mistake chance, correction delay, and typing breaks.
4. Click **Start**, then focus the first field during the 2s countdown.
5. Flip **Stop** to halt mid-run.
6. **Keys** = per-key sounds from `app/sounds` (synced). **Alert** = done/error beep.

## Notes

- The app must run with permission to send keystrokes (normal user is fine; some elevated apps won’t accept input from a non-elevated typer).
- **Remote desktop (RDP, Parsec, TeamViewer, etc.):** typing uses hardware scan codes so letters reach the remote session. Older builds used Unicode injection, which many remotes ignore (only Space worked).
- `human-typer` ships with a broken import on some installs; this app loads it via a compatibility shim.
- Default mistake chance is `3`% — set to `0` for perfect typing.
