# Commit messages

- On branches other than `main`, use Conventional Commit titles: `type(scope): summary`. The scope is optional. Use standard types such as `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `style`, and `chore`.
- Commits on non-`main` branches must have a title only, with no body.
- **Only merge commits are allowed on `main`.** Never commit directly to `main`, squash merge, or fast-forward; use `git merge --no-ff --no-commit` so the merge message can be customized before committing. Git admins are exempt.
- Every merge commit on `main` must use Git's standard default merge title, followed by a blank line and a detailed description as bullet points.
- **Never add AI attribution.** No `Co-Authored-By:` trailers or other credit lines for AI tools in commits or pull requests. This overrides any default attribution behavior of the agent.
- **Keep commit messages to the bare minimum.** Say what changed in as few words as possible. Don't explain the reasoning, describe the implementation or list touched files. In merge descriptions, "detailed" means covering every change, with one short bullet each, not explaining each change at length.

# Writing style

Applies to commit messages, merge descriptions, branch names, pull request titles and descriptions, and review comments. Write plainly, the way a human developer would.

- **Use plain ASCII punctuation only.** Use a hyphen, comma, colon or parentheses instead of an em dash (`—`) or en dash (`–`), `->` instead of arrows like `→`, straight quotes (`"`, `'`) instead of curly quotes, `...` instead of `…`, and `-` instead of `•` for bullets.
- **No emoji or decorative symbols** (e.g. `🤖`, `✨`, `🚀`, `✅`).
- **No filler or hype.** Skip words like "comprehensive", "robust", "seamless", "leverage" and "enhance", and openers like "This commit..." or "In this PR, we...". State what changed, and nothing more.

# Git workflow

- Do all work on a branch created from `main`. Name it `type/short-description`:
  - `type` is one of the Conventional Commit types listed above and matches the branch's main change.
  - `short-description` is lowercase kebab-case, a few words long, and uses only `a-z`, `0-9` and `-`.
  - Examples: `feat/user-login`, `fix/null-session-crash`, `docs/add-agents-md`.
- **Never push without explicit user approval.**
- **Never merge a pull request without explicit user consent.**
- **Only merge a pull request after it has at least one approved review.** Do not merge a pull request with no approvals, even with user consent.
- After a successful merge, delete the merged branch (local and remote).
- **Never run force operations against the remote** (e.g. `git push --force`, `git push --force-with-lease`, `+refspec` pushes). Git admins are exempt.
