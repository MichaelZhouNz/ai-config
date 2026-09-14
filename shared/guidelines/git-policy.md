# Git Commit Policy (ALWAYS APPLIES)

- **NEVER run `git commit` (or amend, or any command that creates a commit) without my explicit approval each time.** This applies at all times, in every workflow — including `/ce-work`, multi-step skills, and automated pipelines. Pipeline/skill authorization does NOT imply commit authorization.
- I review all changes before any commit. When work is ready, **stop and show me the diff / a summary of what changed, then wait for me to explicitly say to commit.**
- Do not stage-and-commit as a "finishing" step. Staging for review is fine; committing is not, until I approve.
- The same rule applies to `git push`, force-push, and opening PRs — always ask first.
