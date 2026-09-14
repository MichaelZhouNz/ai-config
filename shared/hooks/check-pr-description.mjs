// PreToolUse(Bash) hook: deny `gh pr create` unless the PR body has the four required sections.
import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

let input = {};
try { input = JSON.parse(readFileSync(0, "utf8")); } catch { process.exit(0); }
const cmd = input?.tool_input?.command ?? "";
// Only fire when `gh pr create` is in command position, not when merely mentioned in text.
if (!/(?:^|[;&|(\n]\s*)(?:rtk\s+)?gh\s+pr\s+create\b/.test(cmd)) process.exit(0);

// Body source: --body-file/-F <path>, or inline (--body/-b/heredoc) which lives in the command text.
let body = cmd;
const bf = cmd.match(/(?:--body-file|-F)(?:=|\s+)(["']?)([^"'\s]+)\1/);
if (bf) {
  const p = resolve(input.cwd ?? process.cwd(), bf[2]);
  body = existsSync(p) ? readFileSync(p, "utf8") : "";
}

const required = [
  { name: "## TLDR",                  re: /(?<=^|["'\s])##\s*TL;?DR\b/im },
  { name: "## Technical Description", re: /(?<=^|["'\s])##\s*Techni(?:cal|que)\s+Description\b/im },
  { name: "## Affected Projects",     re: /(?<=^|["'\s])##\s*Affected\s+Projects\b/im },
  { name: "## Testing (with a table)", re: /(?<=^|["'\s])##\s*Testing\b[\s\S]*?^\s*\|[^\n]*\|\s*\n\s*\|[\s:-]*-[\s:|-]*\|/im },
];
const missing = required.filter(r => !r.re.test(body)).map(r => r.name);
if (missing.length === 0) process.exit(0);

const reason =
  `PR description is missing required section(s): ${missing.join(", ")}. ` +
  `Invoke the Skill "generate-pr-description", write the body using its template ` +
  `(TLDR, Technical Description, Affected Projects, Testing table), then re-run gh pr create.`;
process.stdout.write(JSON.stringify({
  hookSpecificOutput: { hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: reason }
}));
