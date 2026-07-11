---
name: dispatch
description: Dispatch exactly one metadata-complete OpenSpec task to a fresh Codex MCP session. Use when the user invokes `/dispatch CHANGE TASK_NUMBER` or asks Claude to dispatch a numbered task from an OpenSpec change.
---

# Dispatch

Dispatch one existing OpenSpec task without rewriting the shared prompt constraints.

## Validate the request and task

1. Require exactly two arguments: `<change>` and `<task编号>`. Stop and show the expected syntax if either is missing.
2. Resolve the project root with `git rev-parse --show-toplevel`. Use that absolute path for every following file lookup and for the Codex `cwd`.
3. Read `.dual-agent/state.md` and `.dual-agent/index.md` completely. Stop if either file is missing.
4. Open `openspec/changes/<change>/tasks.md`. Find exactly one task whose numbered heading matches `<task编号>`; include its description and indented metadata lines up to the next task heading.
5. Extract exactly one non-empty `域:` value and exactly one non-empty `验证:` value from that task block. Accept only `python`, `frontend`, or `misc` for `域:`. Preserve the complete validation value, including a command, `人工:`/`人工：`, or `不适用:`/`不适用：` reason.
6. Stop before any Codex call if the change or task does not exist, the task match is ambiguous, either metadata field is missing or duplicated, the domain is unsupported, or the validation value is empty. Name the defect and require correcting `tasks.md` first; do not infer metadata.

## Assemble the prompt

1. Read `.dual-agent/dispatch/common.md` completely.
2. Read only `.dual-agent/dispatch/<域>.md` for the selected domain.
3. Build the prompt in this order, preserving both template bodies verbatim:

```text
<contents of .dual-agent/dispatch/common.md>

<contents of .dual-agent/dispatch/<域>.md>

# 本次任务
- Change: <change>
- Task: <task编号> <task description>
- 域: <域>
- 验证: <完整验证值>
- 任务文件: openspec/changes/<change>/tasks.md
```

Do not copy shared constraints into the domain template, edit either template during dispatch, or invent additional task requirements.

## Start a fresh Codex session

Call `mcp__codex-pro__codex` (the Pro-plan entry, CODEX_HOME=`~/.codex-pro`) once with the assembled prompt:

```json
{
  "prompt": "<assembled prompt>",
  "cwd": "<absolute project root>",
  "model": "gpt-5.6-sol",
  "approval-policy": "never",
  "sandbox": "danger-full-access"
}
```

Do not fall back to the Plus-plan `mcp__codex__codex` unless the user says so. Always start a new session for the dispatched task. Do not use `codex-reply` for the initial dispatch. Return the Codex session/thread identifier and its immediate result so same-phase review corrections can explicitly continue that session later via `mcp__codex-pro__codex-reply`.
