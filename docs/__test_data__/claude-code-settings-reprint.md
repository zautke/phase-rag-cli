```jsonc
// ─────────────────────────────────────────────────────────────────────────────
// Claude Code — Complete settings.json Reference (JSONC format)
// ─────────────────────────────────────────────────────────────────────────────
//
// Sources: code.claude.com/docs/en/settings (v2.1.200+, July 2026),
//          mculp/cc-settings-json-full.md gist (April 2026, ~125+ keys),
//          shanraisshan/claude-code-best-practice (June 2026, v2.1.181),
//          source-map research / binary inspection (March–April 2026).
//
// Scope precedence (highest → lowest):
//   1. Managed  — /Library/Application Support/ClaudeCode/managed-settings.json
//                  (macOS), /etc/claude-code/ (Linux/WSL), MDM plist, registry
//   2. CLI args  — temporary, session-only
//   3. Local     — .claude/settings.local.json  (gitignored, per-repo personal)
//   4. Project   — .claude/settings.json        (committed, shared with team)
//   5. User      — ~/.claude/settings.json       (global personal defaults)
//
// Array settings (permissions.allow/deny, hooks, etc.) are CONCATENATED and
// deduplicated across scopes — not replaced. Scalar settings follow last-writer-
// wins at the field level. Object settings are deep-merged.
//
// Keys marked [managed-only] are IGNORED unless present in the managed tier.
// Keys marked [deprecated] still work but may be removed in a future release.
// Keys marked [undocumented] were discovered via source inspection / changelog
// and do not appear on the official settings page.
//
// JSONC format: this file uses // comments for annotation. Strip them before
// using as an actual settings.json (or use a JSONC-aware editor).
//
// Add this $schema line to your real settings.json for IDE autocompletion:
{
  // Description: JSON Schema URI for editor validation and autocomplete.
  // Values: URL string
  // Default: (unset)
  "$schema": "https://json.schemastore.org/claude-code-settings.json",

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 1 — CORE / GENERAL
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Default model for all sessions. Accepts model aliases or full
  //   model IDs. --model and ANTHROPIC_MODEL override this for one session.
  //   Press 'd' in the /model picker to persist a selection here.
  //   Change mid-session with /model (does not write back to this file).
  // Values: "default" | "sonnet" | "opus" | "haiku" | "sonnet[1m]" | "opus[1m]"
  //         | "opusplan" | "fable" | any full model ID string
  //         (e.g. "claude-opus-4-8", "claude-sonnet-4-6")
  // Default: "default"
  "model": "claude-sonnet-4-6",

  // Description: Run the main conversation thread as a named subagent. Value is
  //   the agent name from .claude/agents/ or ~/.claude/agents/. Also sets the
  //   default agent when dispatching from `claude agents`. Applies the subagent's
  //   system prompt, tool restrictions, and model.
  // Values: any string matching an agent YAML filename (without .yml extension)
  // Default: (unset)
  "agent": "code-reviewer",

  // Description: Claude's preferred response language. Also sets the voice
  //   dictation recognition language (v2.1.118) and the auto-generated session
  //   title language (v2.1.176). When unset, Claude responds in the language
  //   of the user's input.
  // Values: natural-language name string: "english" | "japanese" | "spanish"
  //         | "french" | "german" | "chinese" | "korean" | …
  // Default: (unset — responds in input language)
  "language": "english",

  // Description: Number of days before session transcripts, auto-memory entries,
  //   and orphaned subagent worktrees are deleted at startup. As of v2.1.117,
  //   the sweep also covers ~/.claude/tasks/, shell-snapshots/, and backups/.
  //   Setting to 0 is rejected with a validation error.
  //   To disable transcript writes in -p mode: --no-session-persistence or
  //   persistSession: false SDK option.
  // Values: positive integer (minimum 1)
  // Default: 30
  "cleanupPeriodDays": 30,

  // Description: Release channel for auto-updates. "stable" is ~1 week behind
  //   "latest" and skips versions with major regressions. To disable updates
  //   entirely: DISABLE_AUTOUPDATER=1 or DISABLE_UPDATES=1 in env.
  // Values: "latest" | "stable"
  // Default: "latest"
  "autoUpdatesChannel": "latest",

  // Description: Prevent the auto-updater from downgrading below this version.
  //   Set automatically when switching from "latest" to "stable" and choosing
  //   to stay on the current version. Soft floor — blocks downgrade but does
  //   not prevent startup. For a hard startup floor, see requiredMinimumVersion.
  // Values: version string (e.g. "2.1.100")
  // Default: (unset)
  "minimumVersion": "2.1.150",

  // Description: Enable extended thinking (reasoning) by default for all
  //   sessions. Controlled interactively via /config as "Always think".
  //   To force thinking OFF regardless: MAX_THINKING_TOKENS=0 in env.
  //   On Fable 5 thinking cannot be disabled.
  // Values: true | false
  // Default: false
  "alwaysThinkingEnabled": false,

  // Description: Show extended thinking summaries inline in the chat transcript.
  //   When false (default), thinking blocks are API-redacted and shown as a
  //   collapsed stub. Redaction only affects display, not model generation.
  //   Has no effect in -p / SDK / IDE extension modes (summaries always shown).
  // Values: true | false
  // Default: false
  "showThinkingSummaries": false,

  // Description: Skip the WebFetch domain safety preflight — a request sent to
  //   api.anthropic.com before fetching to verify the domain is not on a blocklist.
  //   Set to true in environments that block Anthropic egress (Bedrock/Vertex/
  //   Foundry with restrictive outbound rules). When true, WebFetch attempts any URL.
  // Values: true | false
  // Default: false
  "skipWebFetchPreflight": false,

  // Description: Rendering mode for the main chat interface.
  //   "fullscreen" = alt-screen rendering (reduced flicker, flat memory in long
  //   sessions). "default" = classic main-screen renderer (native scrollback,
  //   Cmd+F, tmux copy mode). Switchable mid-session via /tui fullscreen or /tui default.
  //   Env var overrides: CLAUDE_CODE_NO_FLICKER=1 (fullscreen),
  //   CLAUDE_CODE_DISABLE_ALTERNATE_SCREEN=1 (forces default, takes precedence).
  // Values: "fullscreen" | "default"
  // Default: "default"
  "tui": "default",

  // Description: Default transcript view mode on startup. Overrides the sticky
  //   Ctrl+O selection for new sessions.
  // Values: "default" | "verbose" | "focus"
  // Default: (unset — uses last Ctrl+O selection)
  "viewMode": "default",

  // Description: Auto-scroll to the bottom of the conversation as new output
  //   arrives in fullscreen rendering mode. Permission prompts still scroll into
  //   view even when false.
  // Values: true | false
  // Default: true
  "autoScrollEnabled": true,

  // Description: Show a one-line session recap when you return to the terminal
  //   after being away for a few minutes. Same as CLAUDE_CODE_ENABLE_AWAY_SUMMARY.
  // Values: true | false
  // Default: true
  "awaySummaryEnabled": true,

  // Description: Automatically compact the conversation when context approaches
  //   the model's limit. Also controllable via DISABLE_AUTO_COMPACT env var.
  // Values: true | false
  // Default: true
  "autoCompactEnabled": true,

  // Description: Snapshot files before each edit so /rewind can restore them.
  //   Disabling saves disk space but removes rewind capability.
  //   Also: CLAUDE_CODE_DISABLE_FILE_CHECKPOINTING=1 in env.
  // Values: true | false
  // Default: true
  "fileCheckpointingEnabled": true,

  // Description: Include built-in commit and PR workflow instructions and the
  //   git status snapshot in Claude's system prompt. Set false when supplying
  //   your own git workflow skills to avoid duplication.
  //   Env var CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS takes precedence over this.
  // Values: true | false
  // Default: true
  "includeGitInstructions": true,

  // Description: Whether the @ file picker respects .gitignore patterns.
  //   When true, files matching .gitignore are excluded from suggestions.
  //   Does not affect Glob tool results (see CLAUDE_CODE_GLOB_NO_IGNORE).
  // Values: true | false
  // Default: true
  "respectGitignore": true,

  // Description: Show turn duration messages after each response, e.g.
  //   "Cooked for 1m 6s". Toggleable via /config as "Show turn duration".
  // Values: true | false
  // Default: true
  "showTurnDuration": true,

  // Description: Show the "clear context" option on the plan accept screen.
  //   This was removed from the default UI in v2.1.81; restore it with true.
  // Values: true | false
  // Default: false
  "showClearContextOnPlanAccept": false,

  // Description: Require per-session opt-in to Fast Mode (Penguin Mode internally).
  //   When true, each session starts with fast mode off; users enable with /fast.
  //   The user's preference is still persisted between uses within a session.
  // Values: true | false
  // Default: false
  "fastModePerSessionOptIn": false,

  // Description: Whether typing "ultracode" in a prompt triggers a dynamic
  //   workflow automatically. Set false to require explicit /workflows invocation.
  //   Renamed from "workflow" to "ultracode" trigger keyword in v2.1.160.
  //   Appears in /config as "Workflow keyword trigger".
  // Values: true | false
  // Default: true
  "workflowKeywordTriggerEnabled": true,

  // Description: Disable dynamic workflows (/workflows) and bundled workflow
  //   slash commands. Can be set at any scope.
  //   Equivalent to CLAUDE_CODE_DISABLE_WORKFLOWS env var.
  // Values: true | false
  // Default: false
  "disableWorkflows": false,

  // Description: Disable background agents, agent view (claude agents, --bg,
  //   /background, on-demand supervisor). Can be set at any scope; typically
  //   placed in managed settings for enforcement.
  //   Equivalent to CLAUDE_CODE_DISABLE_AGENT_VIEW=1.
  // Values: true | false
  // Default: false
  "disableAgentView": false,

  // Description: Conceal Claude Code's built-in skills and workflows from the
  //   model. When true, the model cannot invoke bundled skills, but built-in
  //   slash commands like /init remain typeable (hidden from model discovery).
  //   Skills from plugins, .claude/skills/, .claude/commands/ are unaffected.
  //   Equivalent to CLAUDE_CODE_DISABLE_BUNDLED_SKILLS=1.
  // Values: true | false
  // Default: false
  "disableBundledSkills": false,

  // Description: Disable inline shell execution for !`...` and ```! blocks in
  //   skills and custom commands. Commands replaced with a policy message.
  //   Bundled and managed skills are not affected.
  // Values: true | false
  // Default: false
  "disableSkillShellExecution": false,

  // Description: Disable all hooks (PreToolUse, PostToolUse, Stop, etc.) and
  //   any custom status line. Also disables allowedHttpHookUrls enforcement.
  // Values: true | false
  // Default: false
  "disableAllHooks": false,

  // Description: Disable the Artifact tool (publishes session output as a
  //   private web page on claude.ai). Equivalent to CLAUDE_CODE_DISABLE_ARTIFACT=1.
  // Values: true | false
  // Default: false (when Artifact feature is available on your plan)
  "disableArtifact": false,

  // Description: Enable or disable the Artifact tool for this user scope.
  //   When unset, follows plan availability. Ignored in project/local settings.
  //   A managed disableArtifact or org admin setting takes precedence. (v2.1.196+)
  // Values: true | false
  // Default: (unset — follows plan availability)
  "enableArtifact": true,

  // Description: Disable claude.ai MCP connectors so they are not auto-fetched
  //   or connected. true in any settings scope takes precedence over false.
  //   Servers via --mcp-config are unaffected. (v2.1.182+)
  // Values: true | false
  // Default: false
  "disableClaudeAiConnectors": false,

  // Description: Prevent Claude Code from registering the claude-cli:// protocol
  //   handler at OS startup. Deep links let external tools open a session with
  //   a pre-filled prompt via claude-cli://open?q=...
  // Values: "disable" | (unset)
  // Default: (unset — registers the protocol handler)
  "disableDeepLinkRegistration": "disable",

  // Description: Probability (0–1) that the session quality survey appears when
  //   eligible. Set 0 to suppress entirely.
  //   Also: CLAUDE_CODE_DISABLE_FEEDBACK_SURVEY=1 in env.
  // Values: number 0–1 (e.g. 0.05 = 5%)
  // Default: (varies by account type; ~0.05 for API key users)
  "feedbackSurveyRate": 0.05,

  // Description: How agent team teammates are displayed when running multi-agent
  //   sessions. "in-process" = same terminal window (overlay). "tmux" = split
  //   panes in tmux. "auto" = tmux/iTerm2 when available, otherwise in-process.
  //   "iterm2" = iTerm2 split panes (requires it2 on PATH).
  // Values: "in-process" | "auto" | "tmux" | "iterm2"
  // Default: "in-process"
  "teammateMode": "in-process",

  // Description: Idle time before an unanswered AskUserQuestion dialog auto-
  //   continues with the already-selected options. Only read from user settings.
  //   Not read from project or local settings. (v2.1.200+)
  // Values: "60s" | "5m" | "10m" | "never"
  // Default: "never"
  "askUserQuestionTimeout": "never",

  // Description: Whether Claude responds after an input-box ! shell command runs.
  //   Set false to add command output to context without triggering a response. (v2.1.186+)
  // Values: true | false
  // Default: true
  "respondToBashCommands": true,

  // Description: Render screen-reader–friendly output: flat text without
  //   decorative borders or animations. Forces classic renderer (tui has no effect
  //   while active). Env var CLAUDE_AX_SCREEN_READER and --ax-screen-reader flag
  //   take precedence. (v2.1.181+)
  // Values: true | false
  // Default: false
  "axScreenReader": false,

  // Description: On Windows/WSL2, inherit Windows managed settings (HKLM registry
  //   + C:\Program Files\ClaudeCode\managed-settings.json) in addition to
  //   /etc/claude-code. Only honored from the HKLM registry or Windows file-based
  //   managed settings. (v2.1.118+)  [managed-only on Windows]
  // Values: true | false
  // Default: false
  "wslInheritsWindowsSettings": false,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 2 — MODEL CONFIGURATION
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Restrict which models users can select in /model, --model,
  //   Config tool, or ANTHROPIC_MODEL. Does not constrain the "Default" option
  //   unless enforceAvailableModels is also true. As of v2.1.172, also constrains
  //   subagent and advisor model pickers.
  // Values: array of model aliases or full model IDs
  // Default: (unset — all models available)
  "availableModels": ["sonnet", "haiku", "opus"],

  // Description: [managed-only] Extend the availableModels allowlist to the
  //   "Default" model option. When true, the Default slot resolves to the first
  //   allowlisted model the org default would select, if that model is not already
  //   in the allowlist. Has no effect when availableModels is unset or empty. (v2.1.175+)
  // Values: true | false
  // Default: false
  "enforceAvailableModels": false,

  // Description: Map model picker entries to provider-specific model IDs.
  //   Useful for Bedrock inference profile ARNs, Vertex endpoint IDs, etc.
  //   Key = model alias or picker label; value = provider model ID string.
  // Values: object { "picker-label": "provider-model-id" }
  // Default: (unset)
  "modelOverrides": {
    "claude-opus-4-6": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/anthropic.claude-opus-4-6-v1:0",
    "claude-sonnet-4-6": "arn:aws:bedrock:us-east-1:123456789012:inference-profile/anthropic.claude-sonnet-4-6-v1:0"
  },

  // Description: Model for the server-side advisor tool (the /advisor command).
  //   Written automatically when you run /advisor. Unset to disable the advisor.
  //   Accepts model alias or full model ID. (v2.1.98+)
  //   From v2.1.170+, also accepts "fable".
  // Values: "opus" | "sonnet" | "haiku" | "fable" | full model ID string | (unset)
  // Default: (unset — advisor disabled)
  "advisorModel": "opus",

  // Description: Persist the effort level for supported models across sessions.
  //   Written automatically when you run /effort <level>. The --effort flag and
  //   CLAUDE_CODE_EFFORT_LEVEL env var override this for one session.
  //   Supported on: Opus 4.6, Sonnet 4.6, Opus 4.7, Opus 4.8 (default high).
  //   Unsupported levels fall back to the highest supported on the active model.
  // Values: "low" | "medium" | "high" | "xhigh"
  // Default: (unset — model's own default applies)
  "effortLevel": "high",

  // Description: Fallback model chain tried in order when the primary model is
  //   overloaded or unavailable. Claude Code shows a notice and switches for
  //   the rest of the turn. "default" expands to the account default model.
  //   Chains are capped at 3; extra entries are ignored.
  //   Unlike most array settings, this is NOT merged across scopes —
  //   the highest-precedence file that defines it supplies the entire chain.
  //   The --fallback-model CLI flag overrides this for one session. (v2.1.166+)
  // Values: array of up to 3 model aliases or full model IDs
  // Default: (unset — no fallback)
  "fallbackModel": ["claude-sonnet-4-6", "claude-haiku-4-5-20251001"],

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 3 — PERMISSIONS
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Array fields (allow, deny, ask, additionalDirectories) are CONCATENATED
  // across all settings scopes, not replaced. deny rules are checked first,
  // then ask, then allow — first match wins regardless of specificity.
  //
  // Tool permission syntax:
  //   Bash(pattern)        — e.g. Bash(npm run *), Bash(git *)
  //   PowerShell(pattern)  — e.g. PowerShell(Get-ChildItem *)
  //   Read(path)           — e.g. Read(.env), Read(~/.zshrc)
  //   Edit(path)           — e.g. Edit(src/**), Edit(*.ts)
  //   Write(path)          — e.g. Write(*.md)
  //   NotebookEdit(path)   — e.g. NotebookEdit(*)
  //   WebFetch(domain:pat) — e.g. WebFetch(domain:example.com)
  //   WebSearch            — global web search
  //   Task(agent-name)     — e.g. Task(Explore), Task(my-agent)
  //   Agent(name)          — e.g. Agent(researcher)
  //   Skill(name)          — e.g. Skill(weather-fetcher), Skill(weather *)
  //   mcp__server__tool    — e.g. mcp__memory__*, mcp__github__*
  //   MCP(server:tool)     — e.g. MCP(github:*)
  //   Tool(param:value)    — e.g. Agent(model:opus), Bash(cmd:npm run *)
  //   Cd(path)             — e.g. Cd(/home/*), Cd(~/projects/*)
  //   *                    — (in deny array only) matches ALL tools
  //
  // Path prefix rules for Read/Edit/Write:
  //   //path   → absolute from filesystem root
  //   ~/path   → relative to home directory
  //   /path    → relative to project root
  //   ./path   → relative path (current directory)
  //
  // Bash wildcard notes:
  //   * can appear at any position: prefix/suffix/middle
  //   Bash(ls *) [space before *] matches "ls -la" but NOT "lsof"
  //   Bash(ls*) [no space] matches both
  //   Compound commands (&&, ||, ;, |) are split — each subcommand must match independently
  //   Process wrappers (timeout, time, nice, nohup, stdbuf, xargs) are stripped before matching
  //
  "permissions": {

    // Description: Allow rules — tools matching these patterns execute without prompting.
    //   First matching deny/ask/allow wins. See syntax guide above.
    // Values: array of rule strings
    // Default: [] (empty — all tools prompt)
    "allow": [
      "Read(*)",
      "Edit(*)",
      "Write(*)",
      "Bash(npm run *)",
      "Bash(pnpm run *)",
      "Bash(pnpm *)",
      "Bash(git status)",
      "Bash(git diff *)",
      "Bash(git log *)",
      "Bash(git add *)",
      "Bash(git commit *)",
      "Bash(git checkout *)",
      "Bash(git branch *)",
      "Bash(git stash *)",
      "Bash(git pull)",
      "Bash(node *)",
      "Bash(ts-node *)",
      "Bash(bun *)",
      "Bash(npx *)",
      "Bash(cat *)",
      "Bash(ls *)",
      "Bash(find *)",
      "Bash(grep *)",
      "Bash(echo *)",
      "Bash(mkdir *)",
      "Bash(touch *)",
      "Bash(cp *)",
      "Bash(mv *)",
      "WebFetch(domain:*)",
      "WebSearch",
      "mcp__*"
    ],

    // Description: Ask rules — tools matching these patterns require confirmation
    //   before executing. Checked after deny, before allow.
    // Values: array of rule strings
    // Default: []
    "ask": [
      "Bash(rm *)",
      "Bash(git push *)",
      "Bash(git rebase *)",
      "Bash(git reset *)",
      "Bash(sudo *)",
      "Bash(chmod *)",
      "Bash(chown *)",
      "Bash(curl *)",
      "Bash(wget *)"
    ],

    // Description: Deny rules — tools matching these patterns are blocked entirely.
    //   Checked first; highest safety precedence. Cannot be overridden by allow rules.
    //   In managed settings, use "*" in deny array to block ALL tools as a global deny.
    // Values: array of rule strings
    // Default: []
    "deny": [
      "Read(./.env)",
      "Read(./.env.*)",
      "Read(./secrets/**)",
      "Read(~/.ssh/**)",
      "Read(~/.aws/credentials)",
      "Bash(rm -rf /)",
      "Bash(rm -rf ~)",
      "Bash(curl * | bash)",
      "Bash(wget * | bash)"
    ],

    // Description: Extra directories outside the project root that Claude can
    //   read from and write to. Accepts absolute or ~/- prefixed paths.
    //   Merged across all settings scopes.
    // Values: array of path strings
    // Default: []
    "additionalDirectories": [
      "../shared-libs/",
      "~/dotfiles/"
    ],

    // Description: Default permission mode that applies when no other mode is
    //   explicitly set. In Remote (cloud) environments only "acceptEdits" and
    //   "plan" are honored; others are ignored. (v2.1.70+)
    //   Modes:
    //     "default"           — standard prompting for unrecognized tool calls
    //     "acceptEdits"       — auto-accepts file edits and common FS commands
    //                           in working dir; build-tool config files always prompt
    //     "plan"              — read-only exploration; writes blocked even with allow rules (v2.1.136)
    //     "auto"              — ML classifier auto-approves safe calls; falls back to prompting
    //     "bypassPermissions" — skip ALL permission checks (dangerous)
    //     "dontAsk"           — auto-deny unless pre-approved via allow rules
    // Values: "default" | "acceptEdits" | "plan" | "auto" | "bypassPermissions" | "dontAsk"
    // Default: "default"
    "defaultMode": "acceptEdits",

    // Description: Prevent auto mode from being activated. Removes "auto" from
    //   the Shift+Tab cycle and rejects --permission-mode auto at startup.
    //   Most useful in managed settings where users cannot override.
    // Values: "disable" | (unset)
    // Default: (unset — auto mode is available)
    "disableBypassPermissionsMode": "disable",

    // Description: Skip the confirmation dialog shown before entering
    //   bypassPermissions mode via --dangerously-skip-permissions or
    //   defaultMode:"bypassPermissions". Ignored when set in project settings
    //   (.claude/settings.json) to prevent repo injection.
    // Values: true | false
    // Default: false
    "skipDangerousModePermissionPrompt": false

    // Note: additional permission keys at top level (auto mode, disableAutoMode,
    //   useAutoModeDuringPlan, etc.) are documented under SECTION 13 — AUTO MODE
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 4 — HOOKS
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Hooks are shell commands or HTTP requests that fire at lifecycle events.
  // All hooks receive a JSON payload on stdin. Exit codes control behavior:
  //   0    — success, proceed normally
  //   2    — block (PreToolUse/Stop/SubagentStop: deny the action or block turn end)
  //   non-0 non-2 — error (logged; does not block)
  //
  // Hook events:
  //   PreToolUse       — before every tool call; can block/modify
  //   PostToolUse      — after every tool call (informational)
  //   Stop             — when Claude is about to stop responding; can block
  //   SubagentStop     — when a subagent stops; can block
  //   Notification     — when a desktop notification would fire
  //   SessionStart     — at session initialization
  //   ConfigChange     — when settings files change mid-session
  //   CwdChanged       — when working directory changes
  //   FileChanged      — when files change outside Claude's edits
  //   PreCompact       — before compaction; exit 2 to block (v2.1.172+)
  //
  // Hook matcher syntax:
  //   tool_name: "Bash" | "Edit" | "Read" | "mcp__server__tool" | …
  //   type: "command" | "http"
  //   For HTTP hooks, allowedHttpHookUrls must include the URL pattern.
  //
  "hooks": {
    // Description: Commands run BEFORE each tool call. Can block (exit 2) or
    //   modify the tool call via stdout JSON. stdin = tool call JSON payload.
    "PreToolUse": [
      {
        // Description: Array of hook entries per event
        "hooks": [
          {
            // Description: Shell command to execute. Receives tool payload on stdin.
            // Values: any shell command string
            "type": "command",
            "command": "~/.claude/hooks/pre-tool-use.sh",
            // Description: Filter this hook to specific tools only.
            //   Accepts glob patterns: "Bash(*)" "mcp__*" "Edit(**/.env)"
            // Values: array of tool permission pattern strings
            // Default: (unset — runs for ALL tool calls)
            "matcher": ["Bash(*)", "Edit(*)", "Write(*)"],
            // Description: Maximum seconds to wait for this hook before aborting.
            // Values: positive integer (seconds)
            // Default: 60
            "timeout": 30
          }
        ]
      }
    ],

    // Description: Commands run AFTER each tool call (informational — exit code
    //   has no effect on tool execution, but non-zero is logged as an error).
    "PostToolUse": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/post-tool-use.sh"
          }
        ]
      }
    ],

    // Description: Commands run when Claude is about to stop responding.
    //   Exit 2 to block the stop (forces Claude to continue processing).
    //   CLAUDE_CODE_STOP_HOOK_BLOCK_CAP limits consecutive blocks (default: 8).
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/stop.sh"
          }
        ]
      }
    ],

    // Description: Commands run when a subagent is about to stop responding.
    //   Exit 2 to block the stop. Subject to the same block cap as Stop.
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/subagent-stop.sh"
          }
        ]
      }
    ],

    // Description: Commands run when a desktop notification would fire.
    //   Useful for custom notification routing (Slack, PagerDuty, etc.).
    "Notification": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/notify.sh"
          }
        ]
      }
    ],

    // Description: Commands run at session initialization.
    //   Can inject environment variables via CLAUDE_ENV_FILE.
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/session-start.sh"
          }
        ]
      }
    ],

    // Description: Commands run when settings files change mid-session.
    //   Receives changed file info on stdin.
    "ConfigChange": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/config-change.sh"
          }
        ]
      }
    ],

    // Description: Commands run when the working directory changes via /cd.
    //   Can inject new env vars for the new directory via CLAUDE_ENV_FILE.
    "CwdChanged": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/cwd-changed.sh"
          }
        ]
      }
    ],

    // Description: Commands run when files change outside Claude's edits.
    //   Useful for detecting external changes to files Claude is tracking.
    "FileChanged": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/file-changed.sh"
          }
        ]
      }
    ],

    // Description: Commands run before compaction. Exit 2 to block compaction. (v2.1.172+)
    //   Also: returning {"decision": "block"} from stdout blocks compaction.
    "PreCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "~/.claude/hooks/pre-compact.sh"
          }
        ]
      }
    ]
  },

  // Description: Allowlist of URL patterns that HTTP hooks may target. Supports
  //   * as a wildcard. When set, hooks with non-matching URLs are blocked.
  //   Undefined = no restrictions, [] = block all HTTP hooks.
  //   Arrays merge across settings scopes.
  // Values: array of URL pattern strings with optional * wildcards
  // Default: (unset — no restrictions)
  "allowedHttpHookUrls": [
    "https://hooks.example.com/*",
    "https://api.internal.example.com/claude/*"
  ],

  // Description: Allowlist of environment variable names HTTP hooks may
  //   interpolate into request headers. When set, each hook's effective
  //   allowedEnvVars is the intersection with this list.
  //   Undefined = no restriction. Arrays merge across settings scopes.
  // Values: array of env var name strings
  // Default: (unset — no restriction)
  "httpHookAllowedEnvVars": [
    "HOOK_SECRET",
    "INTERNAL_API_KEY"
  ],

  // Description: [managed-only] Only managed hooks, SDK hooks, and hooks from
  //   force-enabled managed plugins are loaded. User, project, and plugin hooks
  //   are blocked.
  // Values: true | false
  // Default: false
  "allowManagedHooksOnly": false,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 5 — MCP SERVERS
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // NOTE: MCP server definitions for user scope live in ~/.claude.json, not in
  //   settings.json. Project-scope definitions live in .mcp.json.
  //   Use enabledMcpjsonServers / disabledMcpjsonServers to control which
  //   servers from .mcp.json are actually loaded.
  //
  //   As of v2.1.139: .mcp.json hot-reloads via /mcp Reconnect without restart.
  //   As of v2.1.139: CLAUDE_PROJECT_DIR is injected into stdio MCP server env.
  //   Reserved server name: "workspace" (v2.1.128) — rename any conflicting server.
  //   OAuth servers (v2.1.111) that expose /.well-known/oauth-protected-resource
  //   authenticate automatically — no apiKeyHelper needed.
  //
  // MCP server config shape (for .mcp.json / --mcp-config, not settings.json):
  //
  //   {
  //     "mcpServers": {
  //       "my-server": {
  //         "type": "stdio",           // "stdio" | "http" | "sse"
  //         "command": "npx",
  //         "args": ["@my/mcp-server"],
  //         "env": { "API_KEY": "..." },
  //         "alwaysLoad": false,       // (v2.1.121) bypass deferred loading
  //         "timeout": 30000           // per-server tool call timeout (ms); min 1000
  //       },
  //       "remote-server": {
  //         "type": "http",
  //         "url": "https://mcp.example.com",
  //         "alwaysLoad": false
  //       }
  //     }
  //   }
  //
  //   alwaysLoad: true bypasses deferred tool loading (ENABLE_TOOL_SEARCH) for
  //   this server — all tools load upfront at session start. Use sparingly.

  // Description: Auto-approve all MCP servers defined in project .mcp.json
  //   without the per-server trust prompt. As of v2.1.196, claude mcp list and
  //   mcp get honor this in untrusted folders only from non-repo-committed settings.
  // Values: true | false
  // Default: false (each server requires individual approval)
  "enableAllProjectMcpServers": false,

  // Description: Allowlist of specific server names from .mcp.json to approve.
  //   Takes precedence over the per-server trust prompt for listed names.
  //   As of v2.1.196, honored in untrusted folders from non-committed settings.
  // Values: array of server name strings
  // Default: []
  "enabledMcpjsonServers": ["memory", "github", "basic-memory"],

  // Description: Blocklist of specific server names from .mcp.json to reject,
  //   even if globally approved or in enabledMcpjsonServers.
  // Values: array of server name strings
  // Default: []
  "disabledMcpjsonServers": ["experimental-server"],

  // Description: [managed-only] Allowlist of MCP servers users can configure.
  //   Undefined = no restrictions, [] = lockdown all MCP.
  //   Matching by serverName, serverCommand, or serverUrl (glob patterns).
  //   Denylist (deniedMcpServers) takes precedence.
  // Values: array of { serverName?: string, serverCommand?: string, serverUrl?: string }
  // Default: (unset — no restrictions)
  "allowedMcpServers": [
    { "serverName": "github" },
    { "serverCommand": "npx @modelcontextprotocol/*" },
    { "serverUrl": "https://mcp.internal.example.com/*" }
  ],

  // Description: [managed-only] Denylist of MCP servers that are explicitly
  //   blocked across all scopes including managed. Takes precedence over allowlist.
  //   An individual invalid entry is stripped; wholly invalid value is dropped.
  // Values: array of { serverName?: string, serverCommand?: string, serverUrl?: string }
  // Default: (unset — no denials)
  "deniedMcpServers": [
    { "serverName": "dangerous-server" }
  ],

  // Description: [managed-only] Only managed allowedMcpServers are respected.
  //   Users can still add MCP servers but only managed-allowlisted ones connect.
  //   deniedMcpServers still merges from all sources.
  // Values: true | false
  // Default: false
  "allowManagedMcpServersOnly": false,

  // Description: [managed-only] Load claude.ai cloud MCP connectors alongside a
  //   deployed managed-mcp.json. Without this, managed-mcp.json takes exclusive
  //   control and suppresses claude.ai connectors.
  // Values: true | false
  // Default: false
  "allowAllClaudeAiMcps": false,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 6 — SANDBOX
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Sandbox isolates bash commands at the OS level (bwrap on Linux/WSL2,
  // macOS sandbox profiles on macOS). NOT related to permission rules, which
  // operate at the application layer.
  //
  "sandbox": {

    // Description: Enable bash command sandboxing. When enabled, Bash tool
    //   executes commands inside an OS-level sandbox.
    // Values: true | false
    // Default: false
    "enabled": false,

    // Description: Exit with an error if the sandbox fails to start rather than
    //   falling back to unsandboxed execution. Use in enterprise policies requiring
    //   strict sandboxing. (v2.1.83+)
    // Values: true | false
    // Default: false
    "failIfUnavailable": false,

    // Description: Auto-approve Bash tool calls when sandbox is enabled, so they
    //   don't also require a permission prompt. As of v2.1.139, shell-expansion
    //   forms ($VAR, $(cmd)) are correctly auto-approved.
    // Values: true | false
    // Default: true
    "autoAllowBashIfSandboxed": true,

    // Description: Commands excluded from the sandbox (run in host environment).
    //   Match by command name or glob pattern.
    // Values: array of strings
    // Default: []
    "excludedCommands": ["git", "docker", "gh"],

    // Description: Allow the dangerouslyDisableSandbox escape hatch per-command.
    //   When false, all commands must run sandboxed (or be in excludedCommands).
    // Values: true | false
    // Default: true
    "allowUnsandboxedCommands": true,

    // Description: [Linux/WSL2 only] Enable a weaker nested sandbox suitable for
    //   unprivileged Docker environments. Reduces security compared to full bwrap.
    // Values: true | false
    // Default: false
    "enableWeakerNestedSandbox": false,

    // Description: [macOS only] Allow sandboxed commands to send Apple Events.
    //   Required for tools using `open`, `osascript`, or browser OAuth flows
    //   that depend on Apple Events IPC. (v2.1.181+)
    // Values: true | false
    // Default: false
    "allowAppleEvents": false,

    // Description: [managed-only, Linux/WSL2] Absolute path to the bubblewrap
    //   (bwrap) binary. Overrides automatic PATH detection. (v2.1.133+)
    // Values: absolute path string
    // Default: (auto-detected from PATH)
    "bwrapPath": "/opt/admin/bwrap",

    // Description: [managed-only, Linux/WSL2] Absolute path to socat binary
    //   used for the sandbox network proxy. (v2.1.133+)
    // Values: absolute path string
    // Default: (auto-detected from PATH)
    "socatPath": "/opt/admin/socat",

    // Description: Sandbox network configuration.
    "network": {

      // Description: Outbound domain allowlist for sandboxed commands.
      //   Supports glob patterns (e.g. "*.example.com").
      //   Merged across all settings scopes.
      // Values: array of domain pattern strings
      // Default: []
      "allowedDomains": ["*.npmjs.org", "registry.yarnpkg.com", "api.github.com"],

      // Description: Network domain denylist. Takes precedence over wildcards
      //   in allowedDomains. Supports glob patterns. (v2.1.113+)
      // Values: array of domain pattern strings
      // Default: []
      "deniedDomains": ["*.ads.example.com"],

      // Description: [macOS only] Specific Unix socket paths accessible in the
      //   sandbox. On Linux/WSL2 use allowAllUnixSockets instead (seccomp
      //   cannot inspect paths).
      // Values: array of Unix socket path strings
      // Default: []
      "allowUnixSockets": ["/var/run/docker.sock"],

      // Description: Allow all Unix domain sockets in the sandbox.
      //   On Linux/WSL2 this is the only way to permit Unix sockets.
      //   Overrides allowUnixSockets.
      // Values: true | false
      // Default: false
      "allowAllUnixSockets": false,

      // Description: Allow the sandbox to bind to localhost ports (macOS).
      // Values: true | false
      // Default: false
      "allowLocalBinding": false,

      // Description: HTTP proxy port for sandbox network traffic (1–65535).
      // Values: integer port number
      // Default: (unset)
      "httpProxyPort": 8080,

      // Description: SOCKS5 proxy port for sandbox network traffic (1–65535).
      // Values: integer port number
      // Default: (unset)
      "socksProxyPort": 1080,

      // Description: [managed-only] Only allow domains from the managed
      //   allowedDomains list; user/project domain entries are ignored.
      // Values: true | false
      // Default: false
      "allowManagedDomainsOnly": false,

      // Description: [macOS only] Additional XPC/Mach service names the sandbox
      //   may look up. Supports a single trailing * for prefix matching. Needed
      //   for tools using XPC (iOS Simulator, Playwright, etc.).
      // Values: array of Mach service name strings
      // Default: []
      "allowMachLookup": ["com.apple.coresimulator.*"]
    },

    // Description: Sandbox filesystem access configuration.
    "filesystem": {

      // Description: Paths where sandboxed commands can write. Merged across
      //   all settings scopes. Also merged with Edit(...) allow permission rules.
      //   Path prefixes: / = absolute, ~/ = home, ./ or none = project-relative.
      // Values: array of path strings
      // Default: []
      "allowWrite": ["/tmp/**", "~/workspace/**"],

      // Description: Paths where sandboxed commands cannot write. Merged across
      //   all settings scopes. Also merged with Edit(...) deny permission rules.
      // Values: array of path strings
      // Default: []
      "denyWrite": ["~/.ssh/**", "~/.aws/**"],

      // Description: Paths where sandboxed commands cannot read. Merged across
      //   all settings scopes. Also merged with Read(...) deny permission rules.
      // Values: array of path strings
      // Default: []
      "denyRead": ["~/.ssh/id_*", "~/.gnupg/**"],

      // Description: Paths to re-allow read access within denyRead regions.
      //   Takes precedence over denyRead. Merged across all settings scopes.
      // Values: array of path strings
      // Default: []
      "allowRead": ["~/.ssh/known_hosts"],

      // Description: [managed-only] Only allowRead paths from managed settings
      //   are respected. User/project/local allowRead entries are ignored.
      // Values: true | false
      // Default: false
      "allowManagedReadPathsOnly": false
    }
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 7 — PLUGINS & MARKETPLACES
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Plugins are versioned bundles that can ship skills, subagents, commands,
  // hooks, output styles, and MCP server definitions together as one installable
  // unit. Install with /plugin, manage with /plugin list.
  //

  // Description: Enable or disable specific plugins per marketplace.
  //   Key format: "plugin-name@marketplace-name"
  //   Value: true (enabled) | false (disabled)
  // Values: object { "plugin@marketplace": boolean }
  // Default: (unset)
  "enabledPlugins": {
    "code-formatter@official": true,
    "security-scanner@acme-tools": true,
    "legacy-helper@acme-tools": false
  },

  // Description: Register additional plugin marketplaces beyond the built-in
  //   official marketplace. Use for team-shared or self-hosted plugin registries.
  //   Supported source types: github, git, directory, settings, url, npm, file.
  //   Use source: "settings" to declare plugins inline without a hosted registry.
  // Values: object { marketplace-name: { source: { ... } } }
  // Default: (unset)
  "extraKnownMarketplaces": {
    "acme-tools": {
      "source": {
        "source": "github",
        "repo": "acme-corp/claude-plugins"
      }
    },
    "inline-tools": {
      "source": {
        "source": "settings",
        "name": "inline-tools",
        "plugins": [
          {
            "name": "code-formatter",
            "source": { "source": "github", "repo": "acme-corp/code-formatter" }
          }
        ]
      }
    }
  },

  // Description: [managed-only] Allowlist of plugin marketplace sources.
  //   Undefined = no restrictions, [] = block all plugin marketplace additions.
  //   Enforced on add and on install/update/refresh/auto-update, so a marketplace
  //   added before the policy was set cannot be used to fetch new plugins.
  //   Blocked sources are checked before downloading — never touch filesystem.
  //   Supports: github, git, directory, settings, url, npm, file, hostPattern, pathPattern.
  // Values: array of source spec objects
  // Default: (unset — no restrictions)
  "strictKnownMarketplaces": [
    { "source": "github", "repo": "acme-corp/approved-plugins" },
    { "source": "github", "repo": "acme-corp/security-tools", "ref": "v2.0" }
  ],

  // Description: [managed-only] Blocklist of marketplace sources. Blocked before
  //   download (never reaches filesystem). Enforced on all plugin operations.
  //   Supports hostPattern (regex) and pathPattern (regex) matchers. (v2.1.119+)
  // Values: array of source spec objects
  // Default: (unset)
  "blockedMarketplaces": [
    { "source": "github", "repo": "untrusted/plugins" },
    { "hostPattern": ".*\\.malicious\\.example\\.com" }
  ],

  // Description: [managed-only] Block skills, agents, hooks, and MCP servers
  //   from user and project sources — they can only come from plugins or managed
  //   settings. true locks all four surfaces; an array names specific ones.
  // Values: true | ["skills"] | ["hooks"] | ["agents"] | ["mcp"] | any combination
  // Default: false
  "strictPluginOnlyCustomization": ["skills", "hooks"],

  // Description: [managed-only] Allowlist of marketplace names whose plugins
  //   may appear as contextual install suggestions during a session. Requires
  //   the marketplace to be registered and its source declared in managed settings. (v2.1.152+)
  // Values: array of marketplace name strings
  // Default: (unset — no suggestions)
  "pluginSuggestionMarketplaces": ["official", "acme-tools"],

  // Description: [managed-only] Custom message appended to the plugin trust
  //   warning shown before installation. Add org-specific context.
  // Values: string
  // Default: (unset)
  "pluginTrustMessage": "All plugins from our marketplace are vetted by the security team.",

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 8 — MEMORY & CONTEXT
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Enable auto memory — Claude automatically persists important
  //   information from conversations for future sessions.
  //   Toggle mid-session with /memory. Also: CLAUDE_CODE_DISABLE_AUTO_MEMORY env var.
  // Values: true | false
  // Default: true
  "autoMemoryEnabled": true,

  // Description: Custom directory for auto-memory storage. Accepts absolute or
  //   ~/- prefixed paths. NOT accepted in project settings (.claude/settings.json)
  //   to prevent redirecting memory writes to sensitive locations. OK in user,
  //   local, and managed settings.
  // Values: absolute path or ~/- prefixed path string
  // Default: (built-in memory directory)
  "autoMemoryDirectory": "~/my-memory-dir",

  // Description: Enable Auto Dream — background consolidation and deduplication
  //   of auto-memory entries. Keeps the memory store clean over time.
  //   Internally: "tengu_onyx_plover" GrowthBook gate. [undocumented in official settings page]
  // Values: true | false
  // Default: false
  "autoDreamEnabled": false,

  // Description: Directory where /plan outputs are stored. Path is relative to
  //   project root when set in project settings.
  // Values: path string (absolute, ~/, or project-relative)
  // Default: "~/.claude/plans"
  "plansDirectory": "./plans",

  // Description: Fraction of the model's context window reserved for the skill
  //   listing Claude sees each turn (0.01 = 1%). When exceeded, least-used
  //   skill descriptions collapse to bare names. (v2.1.105+)
  // Values: float 0.0–1.0
  // Default: 0.01
  "skillListingBudgetFraction": 0.01,

  // Description: Per-skill character cap on combined description + when_to_use
  //   text in the skill listing. Text longer than this is truncated. (v2.1.105+)
  // Values: positive integer
  // Default: 1536
  "skillListingMaxDescChars": 1536,

  // Description: Per-skill visibility overrides. Key = skill name (without .md).
  //   Value: "on" (full visibility), "name-only" (listed but no description),
  //   "user-invocable-only" (hidden from model but user can /invoke it),
  //   "off" (fully hidden). Does not apply to plugin skills. (v2.1.129+)
  // Values: object { "skill-name": "on" | "name-only" | "user-invocable-only" | "off" }
  // Default: (unset — all skills visible)
  "skillOverrides": {
    "legacy-context": "name-only",
    "deploy": "off",
    "debug-verbose": "user-invocable-only"
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 9 — WORKTREE
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Configure how --worktree creates and manages git worktrees.
  // To copy gitignored files into new worktrees (e.g. .env), use a
  // .worktreeinclude file in your project root.
  //
  "worktree": {

    // Description: Directories to symlink from the main repository into each new
    //   worktree to avoid duplicating large directories on disk.
    // Values: array of directory name strings (relative to project root)
    // Default: []
    "symlinkDirectories": ["node_modules", ".cache", ".pnpm-store"],

    // Description: Directories to sparse-checkout in each new worktree (cone mode).
    //   Only the listed paths are written to disk.
    // Values: array of path strings
    // Default: []
    "sparsePaths": ["packages/my-app", "shared/utils"],

    // Description: Which ref new worktrees branch from.
    //   "fresh" = origin/<default-branch> (clean, matches remote).
    //   "head"  = current local HEAD (includes uncommitted-but-tracked changes). (v2.1.133+)
    // Values: "fresh" | "head"
    // Default: "fresh"
    "baseRef": "fresh",

    // Description: Isolation mode for background sessions using --worktree.
    //   "worktree" = Edit/Write in main checkout blocked until EnterWorktree called.
    //   "none"     = background jobs can edit working copy directly. (v2.1.143+)
    // Values: "worktree" | "none"
    // Default: "worktree"
    "bgIsolation": "worktree"
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 10 — ATTRIBUTION & GIT
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Customize how Claude attributes its contributions in git commits
  //   and pull requests. Set either field to "" to hide that attribution entirely.
  // Values: object { commit: string, pr: string }
  // Default: { commit: "Co-Authored-By: Claude <noreply@anthropic.com>", pr: "Generated with Claude Code" }
  "attribution": {
    // Description: Git commit attribution trailer. Set to "" to disable entirely.
    "commit": "🤖 Generated with Claude Code\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
    // Description: Pull request description attribution. Set to "" to disable entirely.
    "pr": "Generated with [Claude Code](https://claude.ai/code)"
  },

  // Description: URL template for the "PR" badge in the footer and tool-result
  //   summaries. Substitutes {host}, {owner}, {repo}, {number}, {url} from
  //   the gh-reported PR URL. Useful for self-hosted GitLab/Bitbucket/GHE. (v2.1.119+)
  // Values: URL template string with {placeholder} substitutions
  // Default: (unset — uses standard github.com PR URL)
  "prUrlTemplate": "https://reviews.example.com/{owner}/{repo}/pull/{number}",

  // Description: [deprecated] Legacy alias for attribution.commit.
  //   Use the attribution object instead.
  // Values: true | false
  // Default: true
  "includeCoAuthoredBy": true,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 11 — AUTHENTICATION & API
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Custom command that outputs an auth token sent as X-Api-Key and
  //   Authorization: Bearer headers for model requests.
  //   Run via system shell (/bin/sh on macOS/Linux, cmd on Windows).
  //   Refresh interval: CLAUDE_CODE_API_KEY_HELPER_TTL_MS env var.
  // Values: shell command string
  // Default: (unset — uses stored API key or OAuth)
  "apiKeyHelper": "/usr/local/bin/generate_temp_api_key.sh",

  // Description: Custom script that refreshes GCP Application Default Credentials
  //   when they expire or cannot be loaded. Run before retrying auth.
  //   Useful with short-lived ADC that require an org-specific helper to renew.
  // Values: shell command string
  // Default: (unset)
  "gcpAuthRefresh": "gcloud auth application-default login --no-browser",

  // Description: Custom script that modifies ~/.aws to refresh AWS credentials.
  //   Run before Bedrock API calls when existing credentials are expired.
  // Values: shell command string
  // Default: (unset)
  "awsAuthRefresh": "aws sso login --profile myprofile",

  // Description: Custom script that outputs JSON with AWS credentials. Alternative
  //   to awsAuthRefresh when the helper produces credential JSON directly.
  // Values: shell command string that outputs AWS credentials JSON
  // Default: (unset)
  "awsCredentialExport": "/bin/generate_aws_grant.sh",

  // Description: Restrict login to a specific method. When set in managed settings,
  //   sessions using ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN, or apiKeyHelper are
  //   blocked. Third-party providers (Bedrock, Vertex, Foundry) are not blocked.
  //   "gateway" restricts to a Claude apps gateway.
  // Values: "claudeai" | "console" | "gateway"
  // Default: (unset — all methods allowed)
  "forceLoginMethod": "claudeai",

  // Description: Pre-fills and locks the gateway URL on the /login Cloud gateway
  //   screen. Honored only at the managed policy tier.
  //   Pair with forceLoginMethod: "gateway". (v2.1.127+)
  // Values: URL string
  // Default: (unset)
  "forceLoginGatewayUrl": "https://claude-gateway.example.com",

  // Description: Require login to a specific Anthropic organization.
  //   Single UUID: also pre-selects that org during login.
  //   Array of UUIDs: any listed org is accepted without pre-selection.
  //   Empty array: fails closed (blocks login with misconfiguration message).
  //   When set in managed settings: login fails if org doesn't match.
  //   Invalid value in managed settings: blocks login until fixed.
  // Values: UUID string | array of UUID strings
  // Default: (unset — any org)
  "forceLoginOrgUUID": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",

  // Description: [managed-only] Block CLI startup until remote managed settings
  //   are freshly fetched from the server. If the fetch fails, CLI exits (fail-closed).
  //   Use where policy enforcement must be current before any session. (v2.1.92+)
  // Values: true | false
  // Default: false
  "forceRemoteSettingsRefresh": false,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 12 — ENVIRONMENT VARIABLES
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Any environment variable from the env vars reference can be set here to
  // apply it persistently across all sessions and to subprocesses Claude spawns.
  // As of v2.1.143: NO_COLOR and FORCE_COLOR set here pass to subprocesses but
  //   don't change Claude Code's own interface colors (set those in your shell).
  // As of v2.1.195: identity vars set by hosting environments (CLAUDE_CODE_REMOTE,
  //   CLAUDE_CODE_ACCOUNT_UUID) are ignored when set here.
  //
  "env": {
    // ── Telemetry (see full OTel reference in env vars doc) ──────────────────
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
    "OTEL_EXPORTER_OTLP_ENDPOINT": "http://otel-collector:4317",
    // Required for distributed traces (beta — span schema may still change):
    // "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
    // "OTEL_TRACES_EXPORTER": "otlp",
    "OTEL_METRIC_EXPORT_INTERVAL": "60000",
    "OTEL_LOGS_EXPORT_INTERVAL": "5000",
    // Fix VictoriaMetrics silent delta→cumulative drop:
    "OTEL_EXPORTER_OTLP_METRICS_TEMPORALITY_PREFERENCE": "cumulative",

    // ── Timeouts ─────────────────────────────────────────────────────────────
    "API_TIMEOUT_MS": "600000",
    "BASH_DEFAULT_TIMEOUT_MS": "120000",
    "BASH_MAX_TIMEOUT_MS": "600000",
    "TASK_MAX_OUTPUT_LENGTH": "32000",
    "CLAUDE_CODE_MAX_RETRIES": "10",
    "MCP_TIMEOUT": "30000",
    "MCP_TOOL_TIMEOUT": "100000000",
    "MCP_CONNECT_TIMEOUT_MS": "5000",

    // ── Model / Thinking ─────────────────────────────────────────────────────
    "MAX_THINKING_TOKENS": "10000",

    // ── Prompt caching ───────────────────────────────────────────────────────
    "ENABLE_PROMPT_CACHING_1H": "1",

    // ── Disable toggles (uncomment as needed) ────────────────────────────────
    // "DISABLE_AUTOUPDATER": "1",
    // "DISABLE_ERROR_REPORTING": "1",
    // "DISABLE_TELEMETRY": "1",
    // "DISABLE_PROMPT_CACHING": "1"
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 13 — AUTO MODE
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // Auto mode uses an ML classifier to auto-approve tool calls that appear safe
  // based on the conversation transcript. Falls back to prompting after 3
  // consecutive or 20 total classifier blocks.
  //
  // NOT READ from shared project settings (.claude/settings.json) — only from
  // user, local, and managed settings (prevents repo injection attacks).
  //

  // Description: Configure what the auto mode classifier blocks and allows.
  //   Contains arrays: environment (trusted infrastructure prose), allow
  //   (exceptions to block rules), soft_deny (block rules), hard_deny
  //   (unconditional blocks that allow exceptions cannot override). (v2.1.118+)
  //   Include "$defaults" string in an array to inherit built-in rules at that position.
  //   Run: claude auto-mode defaults  to see all built-in rules before customizing.
  //   Setting allow or soft_deny REPLACES the built-in list unless "$defaults" is included.
  // Values: object { environment?: string[], allow?: string[], soft_deny?: string[], hard_deny?: string[] }
  // Default: (unset — all built-in classifier rules apply)
  "autoMode": {
    "environment": ["This is a development machine. All commands are safe."],
    "allow": ["$defaults", "Run terraform plan (but not apply)"],
    "soft_deny": ["$defaults", "Never run terraform apply", "Do not delete production databases"],
    "hard_deny": ["Never exfiltrate credentials or API keys"]
  },

  // Description: Whether auto mode is active during plan mode (/plan).
  //   NOT read from shared project settings.
  // Values: true | false
  // Default: true
  "useAutoModeDuringPlan": true,

  // Description: When true, suspends ALL Bash/PowerShell allow rules during
  //   auto mode, routing all shell commands through the classifier regardless
  //   of pre-approved allow rules. (v2.1.193+)
  // Values: true | false
  // Default: false
  "autoMode.classifyAllShell": false,

  // Description: Prevent auto mode from being activated at all. Removes auto
  //   from the Shift+Tab permission-mode cycle and rejects --permission-mode auto.
  //   Most useful in managed settings. Can be set at any scope.
  // Values: "disable" | (unset)
  // Default: (unset — auto mode available)
  "disableAutoMode": "disable",

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 14 — UI & DISPLAY
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: UI theme. Applied via /config or direct edit.
  // Values: "dark" | "light" | "system"
  // Default: "dark"
  "theme": "dark",

  // Description: Key binding mode for the input prompt.
  //   Toggleable via /config as "Editor mode".
  // Values: "normal" | "vim"
  // Default: "normal"
  "editorMode": "normal",

  // Description: Preferred notification method for task-complete and
  //   permission-prompt notifications. "auto" sends desktop notifications in
  //   iTerm2, Ghostty, and Kitty; does nothing in other terminals.
  //   Appears in /config as "Notifications".
  // Values: "auto" | "terminal_bell" | "iterm2" | "iterm2_with_bell"
  //         | "kitty" | "ghostty" | "notifications_disabled"
  // Default: "auto"
  "preferredNotifChannel": "iterm2",

  // Description: Show tips in the spinner while Claude is processing.
  //   Set false for a cleaner interface.
  // Values: true | false
  // Default: true
  "spinnerTipsEnabled": true,

  // Description: Override or supplement spinner tips with custom strings.
  //   excludeDefault: true = only show custom tips (replace built-in tips).
  //   excludeDefault: false = merge custom tips with built-in tips.
  // Values: { tips: string[], excludeDefault?: boolean }
  // Default: (unset — uses built-in tips only)
  "spinnerTipsOverride": {
    "excludeDefault": false,
    "tips": ["Run pnpm test before committing", "Check CLAUDE_NOTES.md first"]
  },

  // Description: Customize the action verbs shown while a turn is in progress
  //   (the rotating "Thinking…", "Processing…" verbs in the spinner).
  //   mode: "replace" = use only your verbs. "append" = add to defaults.
  // Values: { mode: "replace" | "append", verbs: string[] }
  // Default: (unset — built-in verbs)
  "spinnerVerbs": {
    "mode": "append",
    "verbs": ["Pondering", "Cooking", "Crafting", "Engineering"]
  },

  // Description: Custom status line at the bottom of the CLI showing session
  //   metadata (model, cwd, context usage) or any custom data from a script.
  //   Optional fields: padding (boolean), refreshInterval (ms), hideVimModeIndicator (boolean).
  // Values: { type: "command", command: string, padding?: boolean,
  //           refreshInterval?: number, hideVimModeIndicator?: boolean }
  //         | (unset — built-in status line)
  // Default: (unset)
  "statusLine": {
    "type": "command",
    "command": "~/.claude/statusline.sh",
    "padding": true,
    "refreshInterval": 5000,
    "hideVimModeIndicator": false
  },

  // Description: Configure an output style to adjust Claude's response style
  //   via a SKILL.md-style system prompt addition. Style is part of the system
  //   prompt — applies on /clear or restart (not mid-session via reload).
  // Values: name of a skill/output-style file, or path string
  // Default: (unset)
  "outputStyle": "Explanatory",

  // Description: Disable syntax highlighting in diffs, code blocks, and file
  //   previews. Useful when the terminal has rendering issues with highlighted output.
  //   Note: CLAUDE_CODE_SYNTAX_HIGHLIGHT=false env var only disables diff highlighting.
  // Values: true | false
  // Default: false
  "syntaxHighlightingDisabled": false,

  // Description: Reduce or disable UI animations (spinners, shimmer, flash effects)
  //   for accessibility or low-bandwidth terminals.
  // Values: true | false
  // Default: false
  "prefersReducedMotion": false,

  // Description: [managed-only] Announcement strings shown to users at startup.
  //   If multiple are provided, they cycle through at random.
  // Values: array of strings
  // Default: []
  "companyAnnouncements": [
    "Welcome to Acme Corp! See our coding guidelines at wiki.acme.com",
    "Reminder: All PRs require code review before merge",
    "New security policy effective today — check the wiki"
  ],

  // Description: Render extra clickable badges in the footer when a regex matches
  //   turn output. Each entry: { type: "regex", pattern: string, url: string, label?: string }.
  //   {name} in url is replaced by named capture groups from the pattern.
  //   Read from user, --settings flag, and managed settings only. (v2.1.176+)
  // Values: array of { type: "regex", pattern: string, url: string, label?: string }
  // Default: (unset)
  "footerLinksRegexes": [
    {
      "type": "regex",
      "pattern": "\\b(?<key>PROJ-\\d+)\\b",
      "url": "https://issues.example.com/browse/{key}",
      "label": "{key}"
    }
  ],

  // Description: Custom file suggestion command for @ file autocomplete.
  //   Type "command" runs a shell script; output is the list of file suggestions.
  // Values: { type: "command", command: string }
  // Default: (unset — built-in file discovery)
  "fileSuggestion": {
    "type": "command",
    "command": "~/.claude/file-suggestion.sh"
  },

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 15 — VOICE & REMOTE CONTROL
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Voice dictation configuration. Written automatically when you
  //   run /voice. Requires a Claude.ai account. (v2.1.118+ expanded structure)
  //   mode: "hold" = push-to-talk. "tap" = tap-to-toggle.
  //   autoSubmit: send transcript immediately when dictation ends.
  // Values: { enabled: boolean, mode: "hold" | "tap", autoSubmit: boolean }
  // Default: (unset — voice disabled)
  "voice": {
    "enabled": false,
    "mode": "hold",
    "autoSubmit": false
  },

  // Description: [deprecated] Legacy alias for voice.enabled.
  //   Use the voice object instead.
  // Values: true | false
  "voiceEnabled": false,

  // Description: Connect Remote Control automatically when each interactive session
  //   starts, instead of waiting for /remote-control.
  //   true = always auto-connect. false = never auto-connect.
  //   Appears in /config as "Enable Remote Control for all sessions". (v2.1.119+)
  // Values: true | false | (unset — follows org default)
  // Default: (unset)
  "remoteControlAtStartup": false,

  // Description: Disable Remote Control feature entirely — blocks claude remote-control,
  //   the --remote-control flag, auto-start, and in-session toggle.
  //   Typically in managed settings for per-device MDM enforcement. (v2.1.128+)
  // Values: true | false
  // Default: false
  "disableRemoteControl": false,

  // Description: When Remote Control is connected, allow Claude to send proactive
  //   push notifications (e.g. task complete).
  //   Appears in /config as "Push when Claude decides". (v2.1.119+)
  // Values: true | false
  // Default: false
  "agentPushNotifEnabled": false,

  // Description: When Remote Control is connected, send a push notification when a
  //   permission prompt or question is waiting for input.
  //   Appears in /config as "Push when actions required". (v2.1.119+)
  // Values: true | false
  // Default: false
  "inputNeededNotifEnabled": false,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 16 — CHANNELS
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: [managed-only] Allow channels for Team and Enterprise plans.
  //   When unset or false, channel message delivery is blocked regardless of
  //   --channels flag. For Console (API key auth) accounts: channels allowed by
  //   default unless managed settings are deployed and this is false.
  // Values: true | false
  // Default: false (for Team/Enterprise plans)
  "channelsEnabled": true,

  // Description: [managed-only] Allowlist of channel plugins that may push messages.
  //   Replaces the default Anthropic allowlist when set.
  //   Undefined = fall back to default. [] = block all channel plugins.
  //   Requires channelsEnabled: true. Each entry has marketplace + plugin fields.
  // Values: array of { marketplace: string, plugin: string }
  // Default: (unset — Anthropic default allowlist)
  "allowedChannelPlugins": [
    { "marketplace": "claude-plugins-official", "plugin": "telegram" },
    { "marketplace": "acme-tools", "plugin": "slack-notifier" }
  ],

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 17 — SSH & DESKTOP CONNECTIONS
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: SSH connections pre-configured for the Desktop environment
  //   dropdown. Each entry requires id, name, and sshHost. Optional: sshPort,
  //   sshIdentityFile, startDirectory. When set in managed settings, connections
  //   are read-only for users. Read from managed and user settings only.
  // Values: array of SSH connection config objects
  // Default: []
  "sshConfigs": [
    {
      "id": "dev-vm",
      "name": "Dev VM (East)",
      "sshHost": "user@dev-east.example.com",
      "sshPort": 22,
      "sshIdentityFile": "~/.ssh/id_rsa_dev",
      "startDirectory": "~/workspace"
    },
    {
      "id": "staging",
      "name": "Staging Server",
      "sshHost": "deploy@staging.example.com"
    }
  ],

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 18 — OPENTELEMETRY HELPER
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Script that generates dynamic OpenTelemetry headers (e.g. fresh
  //   auth tokens for your OTel collector). Runs at startup and periodically.
  //   Refresh interval: CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS (default: 29 min).
  //   Script should output "Key: Value" lines to stdout (newline-separated).
  // Values: shell command string
  // Default: (unset)
  "otelHeadersHelper": "/usr/local/bin/generate_otel_headers.sh",

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 19 — ENTERPRISE / MANAGED-ONLY KEYS
  // ═══════════════════════════════════════════════════════════════════════════
  //
  // These keys are ONLY honored when present in the managed settings tier.
  // They are silently ignored in user, project, and local settings files.
  //

  // Description: [managed-only] CLAUDE.md-style instructions injected as
  //   organization-wide managed memory. Loaded alongside any per-project CLAUDE.md.
  //   Only honored from managed or policy settings.
  // Values: string (markdown content)
  // Default: (unset)
  "claudeMd": "Always run pnpm lint before committing. Use TypeScript strict mode.",

  // Description: [managed-only] Minimum Claude Code version required to start.
  //   CLI exits with an error and instructs users to update if below this floor.
  //   claude update, claude install, and claude doctor still work below the floor.
  //   Differs from minimumVersion which only prevents downgrade without blocking startup.
  //   Versions predating this setting ignore it.
  // Values: version string (e.g. "2.1.150")
  // Default: (unset)
  "requiredMinimumVersion": "2.1.150",

  // Description: [managed-only] Maximum Claude Code version allowed to start.
  //   CLI exits at startup if running version is newer. Background updates and
  //   claude update skip versions above the ceiling.
  //   claude update, claude install, and claude doctor keep working above the ceiling.
  //   Versions predating this setting ignore it.
  // Values: version string (e.g. "2.1.165")
  // Default: (unset)
  "requiredMaximumVersion": "2.1.165",

  // Description: [managed-only] Controls whether managed settings from an embedding
  //   host process (Agent SDK, IDE extension) apply when an admin-deployed managed
  //   tier is also present.
  //   "first-wins" = parent-supplied settings dropped, only admin tier applies.
  //   "merge"      = parent settings apply under admin tier, filtered to tighten not loosen.
  //   Has no effect when no admin tier is deployed. (v2.1.133+)
  // Values: "first-wins" | "merge"
  // Default: "first-wins"
  "parentSettingsBehavior": "first-wins",

  // Description: [managed-only] Admin-deployed executable that computes managed
  //   settings dynamically at startup. Only honored from MDM or system managed-
  //   settings.json. Helper output is merged into the managed tier on every startup.
  //   Requires v2.1.136+.
  // Values: { path: string }
  // Default: (unset)
  "policyHelper": {
    "path": "/usr/local/bin/claude-policy-helper"
  },

  // Description: [managed-only] Block skills, agents, hooks, and MCP servers from
  //   user/project sources. Only allow them from plugins or managed settings.
  //   true locks all four surfaces; an array names specific ones.
  //   (Duplicate for managed-only context; also documented in SECTION 7)
  // Values: true | ["skills"] | ["hooks"] | ["agents"] | ["mcp"] | any combination
  // Default: false
  // "strictPluginOnlyCustomization": true,

  // Description: [managed-only] Prevent user and project settings from defining
  //   allow, ask, or deny permission rules. Only managed permission rules apply.
  // Values: true | false
  // Default: false
  "allowManagedPermissionRulesOnly": false,

  // Description: [managed-only] Only allow MCP servers from the managed
  //   allowedMcpServers list. Users can add servers but only allowlisted ones connect.
  // Values: true | false
  // Default: false
  // "allowManagedMcpServersOnly": false,

  // Description: [managed-only] Disable the Claude Code Artifact tool org-wide.
  //   Equivalent to CLAUDE_CODE_DISABLE_ARTIFACT=1 env var.
  // Values: true | false
  // Default: false
  // "disableArtifact": false,

  // Description: [managed-only] Block the --plugin-dir, --plugin-url, --agents,
  //   and --mcp-config CLI flags at startup. Users could otherwise bypass
  //   strictKnownMarketplaces with these flags for a single run.
  //   --mcp-config with in-process "type: sdk" entries is still accepted.
  //   Pair with allowedMcpServers for full MCP control. (v2.1.193+)
  // Values: true | false
  // Default: false
  "disableSideloadFlags": false,

  // Description: [managed-only, Windows] When true, Claude Code on WSL reads managed
  //   settings from Windows policy chain in addition to /etc/claude-code.
  //   Only honored from HKLM registry or Windows file-based managed settings.
  // Values: true | false
  // Default: false
  // "wslInheritsWindowsSettings": false,

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 20 — CLAUDE.MD EXCLUDES
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Glob patterns or absolute paths of CLAUDE.md files to skip
  //   when loading memory. Patterns match against absolute file paths. Only applies
  //   to user, project, and local memory — managed policy files cannot be excluded.
  // Values: array of glob pattern strings or absolute path strings
  // Default: []
  "claudeMdExcludes": [
    "**/vendor/**/CLAUDE.md",
    "**/node_modules/**/CLAUDE.md",
    "~/.claude/CLAUDE.md"
  ],

  // ═══════════════════════════════════════════════════════════════════════════
  // SECTION 21 — SHELL CONFIGURATION
  // ═══════════════════════════════════════════════════════════════════════════

  // Description: Default shell for input-box ! commands.
  //   "powershell" routes ! commands through PowerShell on Windows (requires
  //   CLAUDE_CODE_USE_POWERSHELL_TOOL=1). As of v2.1.126, when PowerShell is
  //   enabled it's treated as primary shell instead of fallback.
  // Values: "bash" | "powershell"
  // Default: "bash" (or "powershell" on Windows when Bash unavailable)
  "defaultShell": "bash"
}
```
