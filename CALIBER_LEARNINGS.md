# Caliber Learnings

Accumulated patterns and anti-patterns from development sessions.
Auto-managed by [caliber](https://github.com/caliber-ai-org/ai-setup) — do not edit manually.

- **[gotcha]** When a GSD executor subagent is dispatched with a worktree path (e.g., `.claude/worktrees/agent-XXXX/`), the worktree may not exist or may have been cleaned up. Always fall back to reading `.planning/` files from the main project directory (`/Users/trekkie/projects/OVID/.planning/`) if the worktree path fails.
- **[pattern]** Web tests run via `npx vitest run <path> --reporter=verbose` in the `web/` directory. Full suite via `rtk vitest run --reporter=verbose`. Both complete in under 15 seconds.
- **[pattern]** When adding new TypeScript interfaces to `web/lib/api.ts`, place `*Response` interfaces before the parent interface that references them (e.g., `ChapterResponse` before `TitleResponse`) and `*Create` interfaces before their parent `*Create` interface.
