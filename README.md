# MyCRM

A local-first Windows desktop app (Python + Tkinter) for keeping a personal CRM,
meeting notes and a task list in one place, with optional meeting recording and
AI summaries.

- **CRM:** contacts with team, office, role, manager and how you met, plus a
  relationship board that maps who works with whom.
- **Meeting notes:** dated notes per person or group, each with a tickable agenda
  and action list. Unfinished items carry over to the next meeting with that person.
  Recurring meetings create their notes ahead of time.
- **Tasks:** a tagged task list. You can add tasks straight from a meeting's agenda,
  and ticking one off closes the agenda item.
- **Meeting capture:** records the mic, and optionally system audio (the other side
  of a call) and the screen.
- **AI features** (needs an OpenAI API key):
  - Whisper transcription and summaries with action items
  - A catch-up brief before you meet someone
  - Progress reports and email drafts
  - Filling in a new contact's details

All your data stays on your machine. Nothing is stored in the repo.

## Requirements

- **Windows 10 or 11.** Recording, Outlook drafts and the Claude Code launcher use
  Windows-only features. The core CRM and notes may run elsewhere, but only
  Windows is tested.
- **Python 3.10 or newer** (developed on 3.12), with Tkinter. Tkinter comes with
  the python.org installer.
- **Optional:** an [OpenAI API key](https://platform.openai.com/api-keys) for
  transcription and all AI features.
- **Optional:** Microsoft Outlook (desktop) to open drafted emails. Without it, the
  app falls back to a `mailto:` link.
- **Optional:** [Claude Code](https://claude.com/claude-code) on your `PATH` to use
  "send task to Claude Code".

## Getting started

```bash
git clone https://github.com/GBurchell27/MyCRM.git
cd MyCRM

python -m venv .venv
.venv\Scripts\activate          # PowerShell / cmd
# source .venv/Scripts/activate  # Git Bash

pip install -r requirements.txt
python main.py
```

On first run the app creates an empty `crm_data.db` next to `main.py`. There's no
sign-up or seed data; start by adding a contact on the CRM tab.

### Dependencies

Only `python-dotenv` is needed to start the app. The rest are optional: without
them the app still runs and turns off the features whose packages are missing.

| Package | Used for |
|---|---|
| `openai` | Transcription, summaries and all other AI features |
| `python-dotenv` | Loading your API key from `.env` |
| `sounddevice`, `numpy` | Microphone recording |
| `soundcard` | Recording system audio (the other side of a call) |
| `opencv-python`, `mss` | Screen video capture |
| `imageio-ffmpeg` | H.264 video and merging audio into MP4s (includes its own ffmpeg) |
| `openpyxl` | Excel export of meetings |

## Configuration

### OpenAI API key

Choose one of these:

1. **`.env` file (recommended):** copy the example and fill in your key.

   ```bash
   copy .env.example .env
   ```

   ```ini
   OPENAI_API_KEY=sk-...
   ```

2. **Environment variable:** set `OPENAI_API_KEY` in your shell or system settings.
3. **In the app:** open settings with the **⚙** button at the right of the tab bar,
   or `Ctrl+,`, and paste the key. It's saved in `crm_data.db`, and overrides the
   environment variable while set.

`OPENAI_API_KEY` is the only environment variable the app reads.

### Other settings

Everything else is set in the app's settings window and saved in `crm_data.db`:

- The model and reasoning effort behind each AI job
- How far back catch-up briefs look
- How far ahead recurring meeting notes are created
- The default contents of a new meeting note

## Your data

| Path | What it holds |
|---|---|
| `crm_data.db` | Contacts, meetings, tasks, settings (SQLite). **Back this up.** |
| `recordings/` | Audio/video recordings of meetings |
| `.env` | Your API key |

All three are in `.gitignore`. Don't commit them: they contain your contacts,
meeting content and credentials. To move to a new machine, copy `crm_data.db` and
`recordings/` next to `main.py`.

When AI features are on, meeting audio, transcripts and notes are sent to OpenAI
to be processed.

## Running the tests

```bash
python -m unittest discover -s tests
```

The tests use a temporary database and never touch `crm_data.db`.

## Building a standalone .exe

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py
```

The exe lands in `dist/`.

## More detail

[.docs/.run.md](.docs/.run.md) covers recording options, system audio, video
encoding and repairing old recordings.

## License

[MIT](LICENSE)
