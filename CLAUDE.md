# ESOL Library – rules for adding or changing materials

The home page (`index.html`) and `README.md` are GENERATED. Never edit them by hand.

To add, rename or remove anything in the library:
1. Put the file in `<level>/<skill>/` (online pages) or `<level>/<skill>/docs/` (Word + PDF with the same name).
2. Add an entry to the lists (optional `week` number puts it in teaching order; otherwise taken from a `wkNN-` file name or "Wk N" in the title) in the AtinWix/personal repo: `tools/esol.json` for online pages (id, folder, path, title, note, claude) or `tools/docs.json` for Word documents (folder, path, title).
3. Copy `esol.json`, `docs.json` and `logo.html` to `/home/claude/build/` (or fix the paths in the script), then run `python3 <personal>/tools/home.py`. It rebuilds `index.html` and `README.md`, including the "Report a problem" links (they email Atin via `r.html`).
4. If home.py stops with "items are on the library page but missing", add those items to the lists – never use `--force` unless Atin asked for them to be removed.
5. Commit and push BOTH repos (esol and personal), so the lists and the page stay in step.
6. Public materials live ONLY in the library: don't also publish them as separate Claude artifacts. Claude artifacts are only for private tools (Lesson Log, Lesson Ideas, Smart Targets, Teacher Hub, AI marker). In `esol.json` the `id` and `claude` fields may be empty.
7. Lesson days (Teacher Hub card, Lesson Log "planned" entry, ROW snippet, Covered/Next, Drive inbox fallback, failure alerts, daily checks) follow `teaching/RUNBOOK.md` in the PRIVATE AtinWix/personal repo. That file is the single source for the lesson-day process; don't restate it here. Never put Atin's schedule, Teacher Hub, Lesson Log, Records of Work, SMART targets or schemes of work in this public repo, and don't recreate a public Coming Up page or `coming-up.json`.
8. Lessons made in ANY chat must be filed the same day, following RUNBOOK §3 (library + lists + home.py here; the rest in the personal repo and Claude tools).
9. Before building any lesson day, check it hasn't already been made (RUNBOOK §2). If it has, file that instead of rebuilding.
10. Titles: name items by topic, grammar point and activity (e.g. "E2 Past Simple – Speaking Tasks 1 & 2 – Projector Lesson"). No week numbers or days in titles (teachers outside Atin's timetable use the library); home.py adds Topic / Grammar / Skill / Level labels automatically from the title and folder. A `week` field may still be set to keep teaching order.
11. Changes count too: whenever filed material is updated or corrected in any chat, replace it in the library the same turn (same path, regenerate the matching PDF, run home.py if a title or path changes) and update the Teacher Hub card, ROW snippet and Lesson Log entry if they are affected. A changed file handed over only in chat is not filed.
