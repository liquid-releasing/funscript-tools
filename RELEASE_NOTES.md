## What's New in v2.3.2

### New Features (merged from contributor PR #10 + follow-up fixes)

**Canvas Timeline (Custom Event Builder)**
1. Replaced the basic event list with a fully interactive canvas timeline — drag blocks to reposition, drag right edge to resize event duration
2. Zoom with Ctrl+scroll, pan with scroll or drag background
3. Snap-to-grid (Off / 0.5s / 1s / 5s / 10s / 30s / 1m)
4. Undo / Redo support
5. Funscript waveform overlay — auto-loads matching `.funscript` when opening an events file
6. Playhead indicator
7. Conflict detection — overlapping events warn before save/apply
8. Category-coloured event blocks (mcb / clutch / test / general)

**Video Playback & Timeline**
9. Synchronized video playback window (ffpyplayer) with timeline scrubbing
10. Arrow key frame stepping and spacebar play/pause on timeline; keys work when video window is focused
11. Seek bar in video window syncs timeline playhead
12. "Show waveform" checkbox in Options bar to hide/show funscript track
13. Timeline ruler minor tick subdivisions and two-level grid
14. Timeline zoom extended to support long videos (>15 min)
15. Auto-load matching video file when opening events for same source

**Dark Mode**
16. Dark/light mode toggle button in main toolbar (sv_ttk theme)
17. Dark mode preference is now persisted in config and restored on next launch

### Dependencies added
- `ffpyplayer>=4.3.0`
- `Pillow>=10.0.0`
- `sv-ttk>=2.6.0`
