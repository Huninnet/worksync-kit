# WorkSync Kit · Keep "the same AI" consistent across multiple computers

> The problem: AI coding assistants (WorkBuddy, Claude Code, etc.) keep session state
> on a single machine. Switch computers, and "I" lose all memory.
> This kit = **sync tool + handover protocol templates + mechanical verification** —
> three layers of defense for multi-machine workflows.

**Language**: [简体中文](README.md) · [English](README.en.md)

## Why you need this

What gets synced is **not** chat history (the vendor's cloud handles that), but the things lost when switching machines:

| Item | If lost |
|---|---|
| SOUL.md / IDENTITY.md / USER.md | The AI becomes a stranger who doesn't know you |
| memory/ (working memory) | All accumulated project context and preferences reset to zero |
| skills/ (custom skills) | Custom skills must be reinstalled |
| Status pages / protocol templates | No handover entry point; realign from scratch every time |

But **file sync alone is not enough**. A real incident (see [docs/case-study-交接翻车复盘.md](docs/case-study-交接翻车复盘.md)):
an AI fixed code in a temp directory, deployed it, then sat waiting — writing nothing back.
The next machine's AI found zero traces in all documents and **redid the same work from stale code**.
So this kit adds protocols and mechanical verification on top of sync.

## Three layers of defense

| Layer | Measure | Prevents |
|---|---|---|
| Behavior | **Wrap up on completion**: the moment a task is done, run the 5-step wrap-up (write back → update status page → sync → drift check → report) without waiting for the user to say "done for today" | Wrap-up never happens because the user is away |
| Action | **Auto deploy log + mandatory package md5 verification** | Deployed but not documented; extracting a stale package |
| Verification | **Drift check**: file-by-file md5 between the live server code and the local workspace | The safety net when every documentation trace is missing |

One-line principle: **Never rely on the discipline of writing docs. If the docs say "no work happened," don't believe them — trust the code running on the server.**

## Quick start (3 steps)

```powershell
# 1. Retrieve the tool (adjust the cloud-drive path to yours, usually $env:OneDrive)
New-Item -ItemType Directory -Force "$env:USERPROFILE\WorkBuddy\WorkSync" | Out-Null
Copy-Item "$env:OneDrive\WorkBuddySync\_tool\*" "$env:USERPROFILE\WorkBuddy\WorkSync\"

# 2. Pull the latest state from the cloud hub
cd "$env:USERPROFILE\WorkBuddy\WorkSync"
python sync.py pull

# 3. Register automatic sync (at logon + every 30 minutes)
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Then copy `config.example.json` to `config.json` and edit two things:
`hub` (your cloud-drive folder) and `status_pages` (paths to your project status pages).

## Common commands

```bash
python sync.py resume    # First thing after switching machines: pull + print handover briefing
python sync.py status    # Show differences only, touch nothing (run this first)
python sync.py sync      # Two-way sync
python sync.py pull      # Pull only
python sync.py push      # Push only
python sync.py sync --dry  # Dry run: print what would happen, write nothing
```

## Transport

`hub` points to a cloud-drive folder present on both machines (default `$OneDrive/WorkBuddySync`) —
the cloud client does the transport; the script never talks to the network itself.
Works with any two-way sync service (OneDrive, Nutstore, etc.) — just change `hub`.

## Safety principles (the script's iron rules)

1. **Never delete files**
2. **Back up before overwriting**, to `.backup/<timestamp>/`
3. **Files changed on both sides = conflict**: keep local, save the remote copy to `.conflicts/` for a human to decide
4. **Three-way merge**: last-synced hash as the base; auto-apply only when exactly one side changed

The one exception: purely appended `.md`/`.txt` (one side's content is a prefix of the other) —
the fuller version is taken automatically; that is not treated as a conflict.

## Templates & protocol

- [`templates/00-当前状态.md`](templates/00-当前状态.md) — project status page template (5 sections + recent changes)
- [`templates/接班协议.md`](templates/接班协议.md) — handover protocol: opening checks, wrap-up steps, deploy discipline
- [`templates/check-drift.sh`](templates/check-drift.sh) — drift-check template; three edits to adapt
- [`docs/case-study-交接翻车复盘.md`](docs/case-study-交接翻车复盘.md) — real incident retrospective; why each rule exists

## Source-of-truth priority (hard-won lesson)

**Memory is a snapshot and goes stale; for long-running projects the source of truth is `00-当前状态.md` in the project root.**

`resume` pins the status page to the top of the briefing (paths configured via `status_pages`)
and warns "memory may be stale" if the status page is 2+ hours newer than `MEMORY.md`.
Fixed opening order: `resume` → **read the status page** → then memory.

## When things go wrong

- Pre-overwrite versions live in `.backup/<timestamp>/`
- On conflict, the remote copy is saved to `.conflicts/<timestamp>/` for you to review
- Until a conflict is resolved, that file stays pending and **will never be silently overwritten**
- Execution log: `logs/sync.log`

## Disable automatic sync

```powershell
Unregister-ScheduledTask -TaskName "WorkBuddy WorkSync" -Confirm:$false
```

## Notes

- By default only identity, memory, and skills groups are synced. The `workspaces` group (workspace
  artifacts) is off by default — code projects should use Git, not drive sync (`.git` and
  `node_modules` over a sync drive invite corruption).
- Battle-tested for months on Windows 10/11 + OneDrive + WorkBuddy (daily automatic sync,
  two-machine handover).

## Configuration (everything lives in one `config.json`)

| What you want to change | Where |
|---|---|
| Use another cloud drive (OneDrive → Nutstore, Baidu Netdisk, …) | `hub` — point it to your drive folder |
| Sync frequency | `interval_minutes` (minutes), then re-run `install.ps1` |
| What gets synced / group toggles | `groups[].enabled` plus each group's `patterns` / `exclude` globs |
| Add or remove synced directories | `roots[].src` inside the relevant group |
| Status page paths (pinned to `resume` briefing) | `status_pages` array, multiple entries allowed |

## Maintenance: best-effort

A personal tool built for the author's own two-machine workflow, open-sourced as-is.
Issues are welcome; **no guaranteed response or fix timeline**. PRs are very welcome.

## License

[MIT](LICENSE)
