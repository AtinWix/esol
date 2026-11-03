# ESOL Library – rules for adding or changing materials

The home page (`index.html`) and `README.md` are GENERATED. Never edit them by hand.

To add, rename or remove anything in the library:
1. Put the file in `<level>/<skill>/` (online pages) or `<level>/<skill>/docs/` (Word + PDF with the same name).
2. Add an entry to the lists (optional `week` number puts it in teaching order; otherwise taken from a `wkNN-` file name or "Wk N" in the title) in the AtinWix/personal repo: `tools/esol.json` for online pages (id, folder, path, title, note, claude) or `tools/docs.json` for Word documents (folder, path, title).
3. Copy `esol.json`, `docs.json` and `logo.html` to `/home/claude/build/` (or fix the paths in the script), then run `python3 <personal>/tools/home.py`. It rebuilds `index.html` and `README.md`, including the "Report a problem" links (they email Atin via `r.html`).
4. If home.py stops with "items are on the library page but missing", add those items to the lists – never use `--force` unless Atin asked for them to be removed.
5. Commit and push BOTH repos (esol and personal), so the lists and the page stay in step.
6. Public materials live ONLY in the library: don't also publish them as separate Claude artifacts. Claude artifacts are only for private tools (Lesson Log, Lesson Ideas, Smart Targets, Teacher Hub, AI marker). In `esol.json` the `id` and `claude` fields may be empty.
7. Add the lesson day to Atin's Teacher Hub: ArtifactData "set" on https://claude.ai/artifact/Ko1Xu9t4cmaH4Hc9kYWa4q, collection "upcoming", doc_id "<YYYY-MM-DD>_<class key e1|e2|e3>", data {date, cls, title, morning, afternoon, print, prep, links:[{label,url}]} (https links only). The old ESOL Materials Catalogue artifact is retired – do not update it. Put the same object in `coming-up.json` at the root of AtinWix/esol (one entry per date and class – replace an existing one; keep only the last 6 weeks), which feeds https://atinwix.github.io/esol/coming-up.html.
