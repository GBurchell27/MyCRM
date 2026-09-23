# Rolling catch-up brief for recurring 1:1s

Design research for: *"summarise everything since the last time I saw Morgan, and roll
unfinished todos forward."*

Written against the codebase as of 2026-08-09.

---

## Implementation status

| Phase | Status |
|-------|--------|
| 0 — Extract recording section, fix duplicate placeholders | ✅ Complete |
| 1 — Task links, window resolver, carry-forward | ✅ Complete |
| 2 — Catch-up pack + panel (no AI) | ✅ Complete |
| 3 — AI brief, model entry, caching/staleness | ✅ Complete |
| 4 — Copy/export, per-series toggle, carried ×N flagging | ✅ Complete |
| 5 — Generalising beyond one person, plus tooltips | ✅ Complete |

**All phases complete.** 64 automated tests plus 4 GUI smoke suites passing. The schema
migration has been applied to `crm_data.db` (additive only; all 14 meetings, 25 tasks and
9 contacts intact, and the existing Morgan series picked up `catchup_enabled=1`).
Outstanding decisions for you are gathered in §13.

### ✅ Phase 0 — completed

- [x] `dialogs/meeting_recording_section.py` created — owns recorder, capture session,
      record/retry buttons, capture-option checkboxes, indicator, and the whole
      transcription pipeline.
- [x] `dialogs/meeting_dialog.py` reduced **677 → 491 lines**, back under the 700 ceiling
      with room to grow.
- [x] `dialogs/meeting_close_guard.py` updated to talk to `dialog.recording` rather than
      reaching into `_pending_segment` / `retry_btn` directly.
- [x] Duplicate-placeholder bug fixed in `recurring_meetings.py` — `_fill_occurrences`
      now checks for an existing meeting with that person on that date (case-insensitive,
      whitespace-tolerant) before inserting, and logs the occurrence either way so a
      skipped date is never retried.
- [x] `tests/` harness added (`support.py` — temp DB per test via `db.DB_PATH` patching).
- [x] 5 tests covering placeholder generation and the dedupe fix — all passing.
- [x] GUI smoke test run: dialog builds, buttons wire up, busy-state toggling and the
      close guard all work through the new section.

### ✅ Phase 1 — completed

- [x] `widgets/agenda_checklist.py` captures the id returned by
      `TaskManager.create_task` on both the per-row and bulk buttons, so an item knows
      which task it created (§2 blocker #1).
- [x] Checklist round-trips **any** key it doesn't own via an `extra` bag, so
      carry-forward provenance survives being loaded into entry boxes and snapshotted
      back out. Without this, history would silently vanish on the first save.
- [x] `TaskManager.states_for(ids)` — bulk lookup that distinguishes *completed* from
      *deleted*; `TaskManager.completed_between(start, end)` with the `< next_day`
      upper bound from §9.
- [x] `meeting_window.py` — `resolve_window()` (pure, testable) + `load_window()`.
      Implements every anchor rule from §3: content filter, duplicate preference,
      person-not-series keying, 14-day cap that still keeps the anchor for carry-forward,
      7-day fallback when there's no previous meeting.
- [x] `carry_over.py` — `CarryOverManager.split_anchor_items()` returns
      (carried, closed) per the §5 table; `merge_into()` folds carried items into an
      agenda idempotently and lets an existing row adopt the carried item's history.
- [x] Historic notes are never rewritten — confirmed by test.
- [x] **30 tests passing** across window resolution, carry-forward, checklist
      round-tripping and placeholder generation, including a replay of the real
      07 Aug window (anchor 04 Aug, four interim meetings, duplicate placeholder ignored).

### ✅ Phase 2 — completed

- [x] `catchup_pack.py` — assembles last meeting, closed items, tasks completed in the
      window, still-open items, and every meeting since, then renders it as readable
      text. No network call anywhere in it.
- [x] Per-meeting content clamped to 3000 chars, preferring `ai_summary` → `notes` →
      `transcript`, so one long transcript can't crowd out four other meetings.
- [x] An item is reported once, not twice — a task closed in the window that's already
      covered by a closed agenda item is not repeated in the tasks list, and the anchor's
      raw agenda is left out in favour of the closed / still-open split.
- [x] `meeting_store.py` — targeted single-column writes to a meetings row.
- [x] `catchup_brief` / `catchup_meta` columns added in `db.py`, in the existing
      `PRAGMA table_info` style. Additive, no migration.
- [x] `widgets/catchup_panel.py` — headline, notice line, Brief / What-happened tabs,
      Copy, refresh, and a pull-items button that names the count.
- [x] `dialogs/meeting_catchup_section.py` — watches the person/date fields and rebuilds
      when they change; pulls open items into the checklist; copies to clipboard.
- [x] Auto-pull on open, in the narrow safe case only (saved note, empty agenda), then
      **persisted straight to the row with the editor's baseline moved with it** — so
      opening a note never leaves it looking unsaved (§10).
- [x] Wired into `MeetingDialog` as a third column: Catch-up | AI summary | My notes.
- [x] **42 tests passing**, plus an end-to-end GUI smoke test proving the whole Tuesday
      scenario: anchor found, open items carried with their history aged, an item
      completed in Tasks reported as closed rather than carried, agenda persisted, dialog
      still clean, and a second pull adding nothing.

### ✅ Phase 3 — completed

- [x] `ai_client.py` — shared key lookup, client construction, JSON parsing and list
      coercion, factored out of `ai_summarizer` (which shrank from 197 to 156 lines and
      re-exports `has_api_key` so nothing else had to change).
- [x] **Bug found and fixed while extracting it:** the list coercion ran
      `str(x).strip()` over raw model output, so a `null` in `action_items` became an
      agenda item literally titled `"None"`. Nulls are now dropped. This affected the
      existing meeting summarizer, not just the new code.
- [x] `ai_catchup.py` — the briefing prompt from §7, with every rule it specifies:
      mandatory source attribution, "an empty list beats an invented item", full coverage
      of open items including "no movement", and carried items flagged as risk.
- [x] `normalise()` defends against whatever comes back — wrong types, missing fields,
      bare strings where objects were asked for, nulls in lists.
- [x] `render()` lays the brief out as: opening line → what's happened → where last
      time's items stand → what I need from you → risks → suggested agenda.
- [x] `CATCHUP` entry added to `config/ai_models.py`, defaulting to `gpt-5.6-terra`
      while summaries stay on `luna`. It appears in the AI settings dialog automatically
      (whose fixed height was raised to fit the fourth row).
- [x] `catchup_brief.py` — persists the brief with `generated_at`, `anchor_meeting_id`,
      `source_meeting_ids`, `window` and `model`, and turns that into staleness detection:
      new meetings logged, a meeting deleted, or having met the person again since.
- [x] Generation runs off-thread with the panel showing progress; failures report the
      reason and offer "Try again" rather than dying silently.
- [x] The brief is written to its own column and **never resets the editor's baseline**,
      so generating one mid-meeting can't mark your in-progress typing as saved.
- [x] **55 tests passing**, plus a second GUI smoke test covering the whole brief
      lifecycle against a real Tk mainloop: generate → render → persist → reload on
      reopen → flag stale when a new meeting appears → copy to clipboard, and the
      no-API-key path where the panel still shows everything the pack knows.

### ✅ Phase 4 — completed

- [x] `catchup_enabled` column on `recurring_meetings` (default on), with a checkbox in
      the Add Recurring Meeting dialog explaining what it does.
- [x] **Auto-generation** for standing meetings, guarded so it can only ever fire once
      per note: saved occurrence of a series that asked for briefs, no brief written yet,
      API key present, and something to brief on. Verified by a smoke test that counts
      model calls across five scenarios — 1 call for the standing meeting, 0 for
      reopening it, 0 for a series with briefs off, 0 for a one-off meeting, 0 with no key.
- [x] Carried items wear a `↻3 since 24 Jul` badge on the agenda row, so a commitment
      that keeps rolling is visible without reading the brief.
- [x] Catch-up brief added as a column to both the CSV and Excel meeting exports,
      tolerant of rows saved before the column existed.
- [x] Copy button puts whichever tab you're reading on the clipboard (shipped in phase 2).
- [x] **64 tests passing** and all four GUI smoke suites green.

### ✅ Phase 5 — completed

**The window was already person-keyed, so it needed no change to work for anyone.**
Example: Chris Baker and Jordan Lee have no series at all and both
resolve a proper window. Only *automatic* generation was tied to a series — so the gap
was discovery, not capability.

- [x] `meeting_cadence.py` — reads how often you actually meet someone off your notes:
      count, average gap, and the weekday pattern (days you've met on more than once,
      falling back to the commonest single day so fortnightly patterns still suggest
      something sensible). Empty placeholders don't count toward a pattern.
- [x] The panel offers *"You've met Taylor Reed 4 times, about weekly on Mondays. Set
      this up as a recurring meeting?"* with a Set up button that opens the recurring
      dialog **pre-filled with the detected person and days**. Shown only when there's no
      series yet, so it withdraws the moment you accept.
- [x] Run against your real data, the detector independently rediscovers the Morgan
      pattern — 6 meetings, `[1, 4]`, Tuesdays and Fridays — matching the series you set
      up by hand, and doesn't false-positive on any one-off meeting.
- [x] `dialogs/recurring_meetings_manager.py` — lists every standing meeting with its
      days, an Auto-brief toggle, and Stop. Closes the gap noted in §13 where
      `deactivate` existed but nothing called it. The Meeting Notes button became
      "Recurring meetings…" and opens this, with Add inside it.
- [x] `widgets/tooltip.py` — delayed hover popups matching the existing row previews.
      Text may be a callable, so a tooltip can describe current state.
- [x] `help_text.py` — every tooltip's wording in one file, so the explanations can be
      read and reworded as a set rather than hunted down widget by widget.
- [x] Tooltips attached across the meeting window (record, summarize, retry, capture
      options, date, person, save), the agenda checklist (tick, To Tasks, remove, add,
      bulk, and the ↻ carried badge), the whole catch-up panel, the recurring dialogs,
      the Tasks tab (including the cryptic `→ Claude` and `✉ Email`), and the Meeting
      Notes toolbar.
- [x] `MeetingDateField` gained a `widget` property rather than having callers reach
      into `.combo`.
- [x] **78 tests passing** and five GUI smoke suites, including one that fires a real
      tooltip and checks it appears and disappears.

### What you get, end to end

Opening Tuesday's Morgan note now: the window resolves to the previous Friday, open items
roll forward with their history and are saved immediately, the panel headlines
*"Since 2026-08-07 — 1 meeting · 2 open items · 3 closed"*, the brief writes itself in the
background, and anything completed in the Tasks tab shows up as "closed since then"
rather than being asked about again.

---

## 1. Your requirement, restated as rules

| # | Rule |
|---|------|
| R1 | When I open a meeting note with a person I meet regularly, show me everything that happened since the previous time I met them. |
| R2 | "Since last time" means *all* my meetings in that gap — not just meetings with that person. |
| R3 | The gap boundary is the **day** of the last meeting, inclusive (Tuesday's brief covers the previous Friday, the weekend, and Monday). |
| R4 | Agenda/action items from the last meeting that aren't ticked roll into this meeting. |
| R5 | Items that *were* completed — including ones ticked off in the Tasks tab — must not roll forward; they become the "here's what I got done" part of the update. |
| R6 | The result is (a) something an AI can analyse, and (b) something I can read and talk from. |

R3 is inferred from your two examples. It's also the only defensible rule, because
`meetings.date` stores a date with no time — the app cannot know whether Friday's
Riley Hart meeting happened before or after Friday's Morgan meeting, so it must
include the whole day and let you skim.

---

## 2. What already exists vs. what's missing

**Exists and is reusable:**

- `recurring_meetings.py` — `RecurringMeetingManager` generates placeholder meeting
  rows 7 days ahead from a person + weekday pattern. Your series is `person='Morgan',
  weekdays=[1,4]` (Tue/Fri), and placeholders already exist for 2026-08-11 and 2026-08-14.
- `meetings` table already carries `agenda_items` (JSON list of
  `{text, detail, checked, in_tasks}`), `ai_summary`, `notes`, `transcript`.
- `helpers.parse_agenda_items` tolerates missing/corrupt JSON, so **adding new keys to
  agenda items is backwards compatible** — no migration needed for the item payload.
- `tasks` table has `created_at` / `completed_at` as `"%Y-%m-%d %H:%M"` strings, which
  sort and range-compare correctly as strings.
- The dialog already has the exact patterns this feature needs: background work via
  `threading.Thread` + `self.after(0, …)`, `BusySpinner`, and small coordinator objects
  bolted onto `MeetingDialog` (`MeetingCloseGuard`, `MeetingAttachmentTranscriber`).
- `config/ai_models.py` is a registry — adding a new AI purpose is a 6-line entry and it
  appears in the AI settings dialog automatically.

**Missing:**

1. **No link from an agenda item to the task it created.** `AgendaChecklist.add_row_to_tasks`
   calls `TaskManager.create_task(...)` and throws away the returned id. Without that id,
   R5 is unimplementable — you cannot tell whether an unticked item was actually done in
   the Tasks tab.
2. **No concept of "the previous meeting with this person."** Nothing queries backwards.
3. **No storage for a generated brief.** Putting it in `ai_summary` would collide with the
   per-meeting summary.
4. **Placeholder generation doesn't dedupe** (see §9 — this actively breaks R1).

---

## 3. Core concept: the catch-up window

Everything else falls out of one resolution step.

```
resolve_window(person, meeting_date) -> CatchupWindow
    anchor          the previous real meeting with `person`
    start_date      anchor.date          (inclusive — R3)
    end_date        meeting_date         (inclusive)
    interim[]       every other meeting in [start_date, end_date] with content
```

**Anchor selection rules** (each one earns its place):

| Rule | Why |
|------|-----|
| Most recent meeting with the same person, `date < meeting_date` | The natural definition of "last time I saw him". |
| Match person case-insensitively on trimmed text | Matches `people_memory.find_contact_by_name`'s existing `COLLATE NOCASE` behaviour. |
| **Skip meetings with no content** (notes, summary, agenda and transcript all empty) | Otherwise a never-filled-in placeholder — or a week you cancelled — silently truncates the window to zero and you get an empty brief. |
| If two rows share person+date, prefer the one with content, then the higher id | This case exists in your DB *right now* (see §9). |
| Key on **person, not `recurring_id`** | An ad-hoc coffee with Morgan on Wednesday should reset the window. Keying on the series would ignore it. |
| Cap the lookback at 14 days; if no anchor is found, use `meeting_date - 7 days` and say so in the UI | Stops a first-ever meeting, or a long holiday, from dragging in two months of context. |

**Interim selection:** every meeting in the window, excluding meetings with the anchor
person themselves (the anchor is displayed separately, in its own role) and excluding
empty rows. Future-dated placeholders for other people are empty, so they drop out for free.

---

## 4. Worked examples

**Friday 2026-08-07, Morgan** (this one has real data, so it shows the shape):

```
anchor    2026-08-04 Morgan  id=9        <- id=30 is the empty duplicate, correctly ignored
window    2026-08-04 .. 2026-08-07
interim   2026-08-04 Jordan Lee           id=11
          2026-08-05 Robin van Dijk id=49
          2026-08-06 Riley Hart        id=51
          2026-08-06 Chris Baker       id=52
```

Four meetings' worth of summaries and action items — exactly the material for a Friday
update.

**Tuesday 2026-08-11, Morgan** (the live upcoming one, id=32):

```
anchor    2026-08-07 Morgan  id=31
window    2026-08-07 .. 2026-08-11
interim   2026-08-11 Casey Smit      id=12
carried   "ProjectAtlas" (unticked on 08-07, and linked to open task #37)
```

Note what this exposes: today is Sunday 09 Aug, so **Monday's meetings don't exist yet**.
A brief generated today would be missing them. That's why the brief must record which
meeting ids it covered and offer to regenerate — see §6.

**Friday 2026-08-14** shows the fallback: its anchor would be the 08-11 note, but that note
is currently empty. If you never fill it in, the anchor skips back to 08-07 and the window
widens to cover eight days rather than producing nothing.

---

## 5. Carry-forward rules for open items

For each item on the anchor meeting's agenda:

```
checked == True                         -> don't roll. Report under "closed since last time".
in_tasks && task completed              -> don't roll. Report under "closed since last time",
                                           with the completion timestamp.
in_tasks && task still active           -> roll forward, keep the same task_id.
in_tasks && task row deleted            -> roll forward, drop the dangling task_id.
plain unticked item                     -> roll forward.
```

Rolled items carry provenance so a stale commitment is visible rather than buried:

```json
{
  "text": "ProjectAtlas",
  "detail": "Waiting on the vendor go-live date",
  "checked": false,
  "in_tasks": true,
  "task_id": 37,
  "first_raised": "2026-07-28",
  "carried_count": 3,
  "source_meeting_id": 31
}
```

`carried_count` is the payload: *"this has been on the agenda three times"* is precisely
the kind of thing a 1:1 exists to surface, and it lets the AI flag drift as a risk rather
than repeating the item flatly.

**Deliberate decision: never mutate the historic meeting.** If a task got completed in the
Tasks tab, we do *not* go back and tick the box on the 07 Aug note. That note is a record
of what was true on 07 Aug. The completion is reported forwards, in the new brief.

**Idempotency:** rolling is deduped against items already on the target meeting by
casefolded title, so opening the same note twice never duplicates rows. This matters
because `MeetingDialog._apply_ai_result` also appends AI-extracted action items to the
same checklist.

---

## 6. Data model changes

All additive, all in the existing `init_db()` `PRAGMA table_info` style:

```sql
ALTER TABLE meetings ADD COLUMN catchup_brief TEXT DEFAULT '';   -- the rendered brief
ALTER TABLE meetings ADD COLUMN catchup_meta  TEXT DEFAULT '';   -- JSON, see below
ALTER TABLE recurring_meetings ADD COLUMN catchup_enabled INTEGER DEFAULT 1;
```

`catchup_meta` holds:

```json
{
  "generated_at": "2026-08-11 08:40",
  "anchor_meeting_id": 31,
  "source_meeting_ids": [12],
  "window": ["2026-08-07", "2026-08-11"],
  "model": "gpt-5.6-terra"
}
```

`source_meeting_ids` gives **staleness detection for free**: on open, re-resolve the window
and compare id sets. Different → banner reading *"2 meetings have happened since this brief
was written — Regenerate"*. Without this, a brief generated on Sunday for Tuesday's meeting
is quietly wrong and you'd never know.

Agenda item JSON gains the optional keys shown in §5. Old items simply lack them and every
reader uses `.get()`, so nothing needs migrating.

---

## 7. The AI layer

**Design principle: the deterministic pack is the product; the AI is a layer on top.**

`CatchupPack` is assembled with plain SQL and no network call — anchor, interim meetings,
carried items, tasks closed in the window. It renders to readable text on its own. If there's
no API key, or the call fails, you still get a usable "here's what happened since Friday"
panel. That mirrors how `MeetingDialog` already degrades when `has_api_key()` is false.

The AI call takes that pack and returns:

```json
{
  "since_last_time":  ["2-4 sentences of narrative — the verbal update"],
  "updates":          [{"headline": "...", "detail": "...", "source": "Chris Baker, 06 Aug"}],
  "open_items_status":[{"item": "ProjectAtlas", "status": "no movement|progressed|blocked|done",
                        "evidence": "Chris confirmed the vendor timeline is still unset"}],
  "decisions_needed": ["Things I need Morgan to decide or unblock"],
  "risks":            ["Slipping commitments, items carried 3+ times"],
  "suggested_agenda": [{"text": "...", "detail": "..."}]
}
```

Notes on the prompt:

- Reuse the `response_format={"type": "json_object"}` + `chat_completion_kwargs` +
  `supports_custom_temperature` shape from `ai_summarizer.summarize_meeting`. It works; don't
  reinvent it.
- Hard rule in the system prompt: **every update must cite its source meeting (person + date)**,
  and anything unsupported by the pack must be omitted rather than inferred. The existing
  `CONTACT_DETAILS_SYSTEM` already takes this line ("an empty string is always better than a
  made-up one") — carry the same discipline over. A hallucinated update to your boss is a
  materially worse failure than a thin one.
- `open_items_status` is the highest-value field and the reason the pack merges both halves:
  it answers "did anything in the last three days actually move this?"
- Add a `CATCHUP` entry to `config/ai_models.py` rather than reusing `SUMMARY`. This is your
  most important output and worth pointing at `gpt-5.6-terra:max` while per-meeting summaries
  stay on `luna`. It costs 6 lines and appears in the AI settings dialog automatically.

**Size:** a 4-meeting window is roughly 8k characters of summaries — about 2-3k tokens.
Non-issue. Cap each meeting's contribution at ~3000 chars (prefer `ai_summary`, fall back to
`notes`, use `transcript` only when both are empty) so one 40-minute transcript can't dominate.

---

## 8. Module layout

Following your file-size and single-responsibility rules. Every unit below is a new file
under 150 lines, and the logic layer is pure enough to test without a DB or a GUI.

| File | Lines | Responsibility |
|------|-------|----------------|
| `meeting_window.py` | ~90 | Resolve anchor + window. `resolve_window(person, date, rows)` is pure; a thin loader does the SQL. |
| `carry_over.py` | ~110 | `CarryOverManager` — apply §5 rules, stamp provenance, dedupe into an existing agenda. |
| `catchup_pack.py` | ~130 | Assemble the deterministic pack; render to text for the AI and for display. |
| `ai_catchup.py` | ~90 | Prompt + `summarize_catchup(pack_text)`. |
| `ai_client.py` | ~35 | Shared `client()` / `has_api_key()`, refactored out of `ai_summarizer._client`. |
| `catchup_brief.py` | ~90 | `CatchupBriefManager` — persist/load brief + meta, staleness check. |
| `widgets/catchup_panel.py` | ~150 | Display: window summary, carried items, brief, Regenerate / Copy buttons. |
| `dialogs/meeting_catchup_section.py` | ~110 | Coordinator wiring panel ↔ managers ↔ `AgendaChecklist`, off-thread generation. |

Edits to existing files are small: `db.py` (+3 columns), `widgets/agenda_checklist.py`
(capture `task_id` — about 10 lines), `recurring_meetings.py` (dedupe fix + the new flag),
`dialogs/recurring_meeting_dialog.py` (one checkbox).

**⚠️ One blocker on your own rules:** `dialogs/meeting_dialog.py` is **677 lines**. Wiring in
the catch-up section adds ~10 and puts it at the 700 ceiling with nowhere to go. Extract the
recording/transcription pipeline (`_start_recording` → `_on_transcribed`, ~130 lines) into
`dialogs/meeting_recording_section.py` **first**, following the existing
`MeetingAttachmentTranscriber` pattern. That drops the dialog to ~550 and buys room for this
feature and the next one.

---

## 9. Bugs found that block this

**Duplicate placeholders.** `RecurringMeetingManager._fill_occurrences` inserts a placeholder
without checking whether a meeting for that person+date already exists. Your DB has the
result: **2026-08-04 has both id=9 (real, 2302-char summary) and id=30 (empty placeholder)**.

This isn't cosmetic here — it's the single most likely way the anchor resolves to the wrong
row and you get a blank brief for a day you had a real conversation. The §3 "prefer the row
with content" rule defends against it, but the generator should also stop creating them:
check for an existing meeting on that person+date before inserting, and still log the
occurrence so the day isn't retried.

Two smaller ones worth knowing:

- **Task date ranges.** `completed_at` is `"2026-08-11 09:30"`, so `completed_at <= '2026-08-11'`
  excludes everything completed that day. Range queries must use `< next_day`.
- **Agenda items sent to Tasks twice.** `in_tasks` is per-item and never re-checked, so a
  rolled-forward item can be re-sent to Tasks and create a duplicate task. Carrying `task_id`
  forward fixes this too — the button reads "In Tasks" if the linked task still exists.

---

## 10. UX flow

Opening the Tuesday note with Morgan:

1. Window resolves instantly (one SQL query). Panel header: **"Since Fri 07 Aug — 1 meeting,
   2 open items, 3 tasks closed."**
2. Carried items appear in the existing `AgendaChecklist`, tagged `↻ carried ×3 since 28 Jul`.
3. If a brief is cached and current, it's shown. If it's stale, a banner offers Regenerate.
   If there's none and the series has `catchup_enabled`, generation starts in the background
   with the `BusySpinner`.
4. **Copy brief** puts it on the clipboard for Teams. `email_drafter.py` / `EmailDialog`
   already exist if you later want it mailed.

**Persistence decision:** the brief and the rolled items are written straight to the meetings
row when generated, *not* routed through the dialog's dirty-state tracking. Otherwise merely
opening a note marks it unsaved and `MeetingCloseGuard` nags you on close. Derived data
shouldn't make a document dirty. For a brand-new unsaved meeting there's no row yet, so
rolling is offered as an explicit "Pull in open items from last meeting" button instead.

---

## 11. Edge cases and how each is handled

| Case | Behaviour |
|------|-----------|
| First ever meeting with this person | No anchor → 7-day lookback, panel says "no previous meeting found". |
| Previous meeting was cancelled / left blank | Skipped by the content rule; window widens to the one before it. |
| Two meetings with Morgan in one week (extra ad-hoc) | Anchor is the most recent — the ad-hoc correctly resets the window. |
| Holiday — 3 weeks since last 1:1 | 14-day cap applies; panel states the window actually used. |
| Same person+date duplicated | Prefer content, then higher id (§3). |
| Brief generated Sunday, meeting Tuesday | Stale-source detection prompts a regenerate on open. |
| No API key / API failure | Deterministic pack still renders — carried items, meeting list, closed tasks. |
| Item completed in Tasks after the brief was written | Next regeneration reads live task state; the historic note is left untouched. |
| Sensitive 1:1 you don't want summarised to your boss | **Not handled in v1.** Every meeting in the window goes to the model. See §13. |

---

## 12. Build order

Each phase is independently useful and independently shippable.

| Phase | Content | Value on its own |
|-------|---------|------------------|
| 0 | Extract `meeting_recording_section.py`; fix the duplicate-placeholder bug | Unblocks the file-size ceiling; stops corrupting anchor data |
| 1 | `task_id` on agenda items; window resolver; carry-forward | Open items roll Tue→Fri→Tue with no AI at all |
| 2 | `CatchupPack` + panel, no AI | "Here's what happened since Friday" is already most of the value |
| 3 | `ai_catchup.py` + `CATCHUP` model entry + caching/staleness | The written update you talk from |
| 4 | Copy/export, per-series toggle, `carried ×N` risk flagging | Polish |

Phases 1 and 2 involve no API calls, no cost, and no latency. I'd want them working and
lived-in for a week before layering the model on top — if the pack is wrong, the AI output
will be confidently wrong.

## 13. Human tasks — the things I can't do for you

Nothing here blocks using the feature. Run the tests any time with
`python -m unittest discover -s tests -t tests` from the repo root.

### Needs you at the keyboard

- [ ] **Run it against a real Tuesday.** Open the 11 Aug Morgan note with the app running
      and your API key set. Everything below the model call is covered by tests; the
      quality of the brief itself is a judgement only you can make.
- [ ] **Delete the duplicate 04 Aug Morgan note if you want it gone.** Meeting id=30 is an
      empty placeholder sitting alongside your real note (id=9, 2302-char summary). The
      resolver ignores it and the generator can no longer create another, but I've left
      the row alone rather than deleting data on your behalf. Meeting Notes tab → select
      the empty 04 Aug Morgan row → Delete.
- [ ] **Judge the cadence thresholds.** A pattern is "regular" at 3+ meetings averaging
      1–21 days apart. If it nags about people you don't want standing meetings with, or
      stays quiet about someone you do, those two numbers at the top of
      `meeting_cadence.py` are the dials.
- [ ] **Check the catch-up model choice.** It defaults to `gpt-5.6-terra` — deliberately
      a step up from the `gpt-5.6-luna` used for summaries, since this is the output you
      actually act on. File → AI settings → "Catch-up briefs" if you'd rather it matched.
- [ ] **Commit when you're happy.** Nothing has been committed; the working tree also
      still holds the unrelated in-progress work that was there before this started.

### Decisions that would change the build

- [ ] **Anchor day inclusive?** Currently yes — Tuesday's brief covers the whole of the
      previous Friday, so you re-see meetings that happened before Friday's 1:1. Making it
      exact needs a `time` column on meetings and more typing every day. Say the word and
      I'll switch it.
- [ ] **Do you want a "keep this out of briefings" flag?** Right now every meeting in the
      window goes to the model. If any of your 1:1s are ones you'd never relay upward,
      this is a per-meeting checkbox plus one filter in `resolve_window` — small, but I
      didn't want to invent a privacy model you hadn't asked for.
- [ ] **Is one brief per standing meeting the right cadence?** Auto-generation fires once
      per note and caches. If you'd rather it never spent money without being asked, turn
      the checkbox off on the series and use the Generate button.

### Known gaps, deliberately not built

- Name variants would break anchor matching. Your meetings all say `Morgan` today
  (alternate spellings live only inside AI-extracted text from other people's meetings),
  so nothing is wrong now — but there's no alias table if that changes.
