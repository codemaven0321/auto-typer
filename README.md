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
2. Tune CPM, jitter, mistake chance, correction delay, and typing breaks.
3. Click **Start typing**, then focus the destination text field during the 2s countdown.
4. Flip **Stop** to halt mid-run.

## Notes

- The app must run with permission to send keystrokes (normal user is fine; some elevated apps won’t accept input from a non-elevated typer).
- `human-typer` ships with a broken import on some installs; this app loads it via a compatibility shim.
- Default mistake chance is `0` — raise it slightly (1–3%) for more human slips.
