# Capability map: step, expert, Action, effect, approval

Source: the public capability catalog, version 2.0.0, in the starter kit. Effects and approval values are generation-time facts. Each instruction names the Action in words and passes no parameter flags; the expert chooses and runs its own workflow.

| Step | Expert | CLI and Action | Effect | Approval |
|---|---|---|---|---|
| 2 | file-agent | file-workflow get-user-dir | read | none |
| 2, 4, 7 | file-agent | ug-filesystem find | read | none |
| 2 | file-agent | ug-filesystem cat | read | none |
| 2 | security-monitor-agent | ug-surveillance cameras | read | none |
| 3 | file-agent | ug-filesystem mkdir | state-change | gateway |
| 3, 12 | file-agent | ug-filesystem echo (append) | state-change | gateway |
| 4, 6 | photo-agent | ug-photo search-screen (4) | read | none |
| 6 | photo-agent | ug-photo search-picture | read | none |
| 4, 6 | photo-agent | ug-photo vision-ocr | read | none |
| 6 | photo-agent | ug-photo meta | read | none |
| 4, 6, 10 | knowledge-agent | ug-knowledge audio-transcription | read | none |
| 4, 8 | security-monitor-agent | ug-surveillance event-timeline | read | none |
| 5 | knowledge-agent | ug-knowledge collect-evidence | read | none |
| 7 | document-agent | ug-document extract | read | none |
| 7 | document-agent | ug-document reconcile | read | none |
| 8 | security-monitor-agent | ug-surveillance event-evidence | read | none |
| 8 | security-monitor-agent | ug-surveillance vehicle-plates | read | none |
| 8 | security-monitor-agent | ug-surveillance vehicle-plate-detail | read | none |
| 12 | file-agent | ug-filesystem cpmv (copy only) | state-change | gateway |
| 12 | file-agent | ug-filesystem sha256sum | read | none |
| 12 | file-agent | ug-filemgr tag-add | state-change | gateway |
| 12 | file-agent | ug-filemgr tag-add-file | state-change | conditional |
| 12 | document-agent | ug-document writing | mixed | gateway |
| 12 | knowledge-agent | ug-knowledge save-text | state-change | workflow |

Counts: 5 experts, 7 CLIs, 24 distinct Actions (find, audio-transcription, vision-ocr, event-timeline and echo are used in more than one step).

## Actions this Skill never uses

del, restore, rename, chtimes, touch, share-mkdir, batch-del, batch-move, and the move form of cpmv. Originals are never changed. Nothing is shared.

## Unsupported in the catalog

| Need | Status |
|---|---|
| A bank statement schema | None exists; extract uses the automatic schema |
| Contacting a bank, the police or anyone | Not offered; the person sends the letters |
| Recovering money or tracing a caller | Not offered |
| Checking that a bank letter is genuine | Not offered; no number is taken from a letter |

## Unknown until a real NAS run

- Whether echo in append mode creates a missing file. Fallback: save-text for the first line.
- Whether cpmv can copy event-evidence snapshots. Fallback: CAMERA.md lists the snapshots for export from the camera app.
- Whether photo search can be limited to a folder. Fallback: results outside the approved folders are dropped and counted.
- Whether a NAS camera exists. Without one, the camera part is "not read".
- How approvals group when many copies are written.
- Whether search-screen categories screen and card mean screenshots and photographed cards. Assumed from their names.
