# Retrospective — rebuilding a PowerShell profile for a zero-tolerance endpoint

**2026-07-31 · `github:/zautke/powershell_profile` · `main` → `safety-trimmed` @ `ccc3ab4`**

---

## 1. The situation

A PowerShell profile accumulated over roughly six years — the oldest tracked
artifacts date to 2020 — was about to move onto a contract machine at a bank.
Three constraints changed everything about what that profile could be:

- **No local administrator rights.** Not "discouraged". Not available.
- **Full endpoint monitoring.** Process creation, script block logging, file and
  network activity, all logged and reviewed.
- **Zero tolerance.** A finding is a finding.

The third constraint is the one that reframes the problem. On a personal
machine, an elevation helper that fails is a minor annoyance. On a monitored
bank endpoint, a *failed* `takeown` is worse than a useless one — it is a log
entry, attributed to a named contractor, showing an attempt to seize ownership
of a file. The command's failure is not exculpatory. The attempt is the event.

So the design rule became: **the profile must not attempt privileged operations,
not merely fail at them.** Everything downstream follows from that.

---

## 2. Method, and why measurement came before opinion

The instinct with a repository like this is to open files and start judging. I
did the opposite first, and it was the single highest-leverage decision of the
session.

Before reading any substantive code, I built a harness that loads the profile in
a **real, non-redirected console** and reports what actually happens. The
non-redirected part matters more than it sounds. The profile's first act is:

```powershell
if ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected -or
    [Console]::IsErrorRedirected) { return $false }
```

Any test that captures stdout makes that guard fire, the profile returns
immediately, and every assertion passes vacuously. The profile would have
appeared perfectly clean while doing nothing at all. The fix was to launch a
child `pwsh` in its own hidden console window and have it write results to a
file — output goes to a genuine console buffer, the guard passes, the profile
really loads.

That harness produced the baseline that made every subsequent argument
unnecessary:

| Measurement | Value |
|---|---:|
| Profile load time | **8,807 ms** |
| Functions defined | **553** |
| Aliases defined | **73** |
| Child processes spawned during load | **10** |
| Modules auto-imported | NetSecurity, posh-git, PSReadLine |
| Functions containing elevation primitives | **9** |
| Errors on first load / second load | **2 / 10** |
| Broken `PATH` entries | **6** |

Nearly nine seconds. Ten subprocesses. Five hundred and fifty-three functions in
a shell where the user cannot install software. And the profile was not
idempotent — loading it twice produced ten errors, because it defined variables
`ReadOnly` and then tried to redefine them.

I did not need to form an opinion about whether this was too much. The
measurement was the argument.

---

## 3. The audit

Five specialist auditors were dispatched in parallel, each framed as a
lockdown-and-compliance reviewer for a financial-sector codebase, each read-only,
each scoped to a disjoint slice: the loaded bootstrap surface; the dormant
off-tree scripts and `.reg` files; documentation and research artifacts;
secrets and egress across the whole tree including git history; and a runtime
integrity auditor whose job was the opposite of the others — to ensure that
after an aggressive purge the thing still worked.

**They did not return reports through the mailbox.** I want to be plain about
that rather than let the reader assume otherwise, because it changed how the
session had to run: every finding below was independently verified first-hand
with commands recorded in the session log. Nothing in the compliance record
rests on an agent report I never received. The parallel dispatch cost time that
direct investigation would have used better, and that is a real lesson from this
session, not a footnote.

What direct investigation found:

### 3.1 A live credential, committed and pushed

```
powershell_profile_local.ps1:186
  https://mcp.tavily.com/mcp/?tavilyApiKey=tvly-dev-1WFhx…thkDsL
```

My first measurement of the blast radius was wrong, and the correction is worth
recording because the error is a common one.

`git log -S 'tvly-dev' --oneline --all` returns exactly one commit, `c06886c`.
I reported that. It understates the exposure badly, because **`-S` matches
commits where the *number of occurrences* changed** — and the key was carried
unchanged through renames and edits, so intermediate commits never registered.

A blob-level sweep of every object in every ref tells the truth:

- **18 of 57 commits** contain the key, spanning 2026-04-19 → 2026-07-28.
- **The key is live on the tip of `origin/main` right now.**

That last point is the one that matters. This is not merely a history-hygiene
problem to be weighed against the cost of a rewrite. Anyone with read access to
the repository sees the key in the current default branch today.

Deletion on a side branch does not fix it. A history rewrite would touch 18
commits across four months and force-push a shared remote — and even that is not
the remediation. **Rotation is.** Rotation works regardless of what happens to
the repository; nothing else does.

I did not rewrite history: destructive, externally visible, and the operator's
decision. The same sweep found **no other credential type** anywhere in history
(`sk-`, `sk-ant-`, `ghp_`, `gho_`, `github_pat_`, `AKIA`, `ASIA`, `glpat-`,
`xox[baprs]-`, `AIza`, `hf_`, JWTs, PEM private-key headers all clean).

**Lesson:** `git log -S` answers "when did the count change", not "where does
this string exist". For a secrets audit, scan blobs.

### 3.2 An SSH server started, and a firewall port opened, on every shell start

Found late, while closing out questions the auditors never answered. It is the
worst thing in the repository.

`bootstrap_scripts/075-Services.ps1` contained no function definitions at all —
it was bare top-level code, so every line executed on every profile load:

```powershell
Start-Service sshd                                   # start the SSH *server*
Set-Service -Name sshd -StartupType 'Automatic'      # persist across reboots
New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' `
    -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

Every new terminal attempted to start a listening SSH daemon, make it survive
reboot, and punch an inbound hole in the firewall for port 22.

From a SOC's perspective that sequence is not meaningfully distinguishable from
a contractor establishing unauthorised remote access to a bank endpoint. The
`choco install` in §3.3 is a policy violation; this is the one that generates a
phone call. It also explains the `NetSecurity` module import that showed up in
the baseline and that I had been unable to attribute.

I want to be honest about how this was found. It was not in my catalogue when I
committed, and it was not in my report to the user. I found it only because I
went back to answer questions I had delegated and never got answers to. Had I
treated the delegated work as done, this would have gone unrecorded — the code
would still have been deleted by the rebuild, but the operator would not know it
had ever been there, and that is exactly the kind of thing they need to know.

### 3.3 A package installer running on every shell start

```powershell
# bootstrap_scripts/005-ENV_variables.ps1:77-84
if (-not (Get-Command make -ErrorAction SilentlyContinue)) {
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        choco install make -y --no-progress | Out-Null
```

Every new terminal attempted an unattended, non-interactive package
installation. On a bank endpoint this is close to the canonical description of
malicious behaviour: a shell that silently installs software at startup. It
would have failed for lack of privilege — and, per the framing in §1, failing is
not the mitigation. It is the alert.

### 3.4 A credential vault piped into every shell

The same file sourced a dotenv from an Obsidian vault and injected its keys into
the process environment of every session. My instrumented run enumerated the
result: over a hundred secret-named variables live in the shell, including
`AWS_SECRET_ACCESS_KEY`, `CLOUDFLARE_GLOBAL_API_KEY`, `OPENAI_API_KEY`,
`GITHUB_PAT`, `NEO4J_PASSWORD`, `NGROK_AUTHTOKEN`.

Any child process inherits all of it. Every `git`, every `npm`, every tool the
operator runs at the bank would have been handed a full set of personal cloud
credentials. I checked whether the vault itself was under version control — it
is not, which is the one piece of good news in this section.

### 3.5 Safety-bypass wrappers

```powershell
function claude { & 'claude.exe' '--dangerously-skip-permissions' @args }
function cl     { & 'claude.exe' '--dangerously-skip-permissions' @args }
function gemy   { & 'gemini' '--yolo' @args }
```

Three shorthands whose entire purpose was to disable an agent's permission
checks. In a regulated environment this is not a productivity setting; it is the
removal of the control that makes agent use defensible at all.

### 3.6 Elevation surface

`Take-Ownership` wrapping `takeown`. `Test-Administrator` and `Test-IsAdmin`
probing `WindowsPrincipal`. `Set-AdminACL`, `Set-Permissions`,
`Set-SystemAdmins-Full-ACL` calling `Set-Acl`. `Set-AdminAuthKeysPermissions`.
`UserRights.psm1`, a 63 KB module for assigning LSA privileges. Two `.reg` files
that add *Take Ownership* to the Explorer context menu. `Invoke-FullWSL2Purge`.
An MCP tree managing Cloudflare tunnels and background services.

### 3.7 Internal topology

```powershell
$jos_base  = '\\VANAHEIM\josquin'
$jotenheim = "\\10.4.4.2\v"
```

A machine name and an internal IP from a previous environment, checked into a
repository that was about to be cloned onto a client's laptop. This is a
disclosure question independent of any security question.

---

## 4. Why I rebuilt instead of trimmed

The task said "purge". The natural reading is subtractive: go through 27
bootstrap files, delete the bad functions, keep the good ones.

I rejected that, and the reasoning is worth recording because it generalises.

**A trim leaves you unable to make a claim.** After deleting bad functions from
553, the honest statement is "I removed the elevation code I found." After
building 32 functions deliberately, the statement is "here is everything this
profile defines, and here is a test asserting nothing else appears." The second
is auditable. The first is a promise about the thoroughness of my own reading —
and my reading is exactly what an auditor cannot verify.

**Trimming preserves structure that was itself the problem.** The load order,
the read-only globals, the dot-source chains reaching into `031-MCP/` and a
hardcoded absolute path in `Documents\PowerShell`, the `Write-Host` banner on
every startup — none of that is a function you can delete. It is the shape of
the thing.

**The keep-set was small.** Once the criteria were applied — pure user scope, no
elevation, no network, no external binary beyond git, no background process,
real daily utility — what survived was navigation, a handful of aliases, git
shorthands, PSReadLine configuration, and a prompt. Roughly thirty functions.
Rewriting thirty clean functions costs less than auditing five hundred and
twenty-three for what to remove.

This is the user's own standing instruction — *never do 2 when 1 will do* —
applied at the level of strategy rather than syntax. The result is 890 lines
added against 25,260 removed.

---

## 5. What was built

```
Microsoft.PowerShell_profile.ps1     entrypoint: UTF-8, interactive guard, loader
bootstrap_scripts/
  10-environment.ps1                 process-scope env, telemetry opt-outs
  20-navigation.ps1                  cd (with cd -), .., ..., j, np
  30-aliases.ps1                     p, l, now, today, Get-EnvVar, colours
  40-git.ps1                         git shorthands + Get-GitBranch
  50-psreadline.ps1                  line editing, history, secret redaction
  60-prompt.ps1                      path + branch, no subprocess
tests/Test-Profile.ps1               the verification suite
README.md  COMPLIANCE.md  .gitignore
```

Two design details carry most of the compliance weight.

**The prompt reads `.git/HEAD` directly.** A prompt that shells out to `git` runs
a subprocess on every single render — hundreds of process-creation events per
hour, per terminal, in an environment where process creation is logged. So
`Get-GitBranch` walks up from `$PWD` looking for `.git`, handles the worktree and
submodule case where `.git` is a file containing `gitdir:`, parses `HEAD`, and
returns the branch or a short SHA when detached. No process, no module, no
network. The prompt degrades to path-only if the function is unavailable rather
than erroring.

**PSReadLine refuses to persist secrets.** An `AddToHistoryHandler` drops any
command line matching `password|token|apikey|credential|-AsPlainText|sk-|ghp_|
tvly-|AKIA` and similar. Shell history is a file on disk that outlives the
session; given what this audit found, not writing credentials into it is cheap
insurance.

Machine-specific paths moved to an untracked `profile.local.ps1`, which is
documented as being for paths and preferences only — explicitly not for secrets.

---

## 6. Verification, including the parts that went wrong

The requirement was evidence, tested repeatedly, before any commit. What made
the suite useful is that it asserts **absence** as much as presence. Proving a
profile works is easy. Proving it does not elevate, does not reach the network,
does not spawn anything, and does not touch persistent state is the actual
compliance question.

### 6.1 My first test run was wrong, and admitting it mattered

The first execution reported 102 passed, 13 failed. It was tempting to read
those failures as profile defects and start editing. They were not. All thirteen
were bugs in my own instrumentation:

- The probe called `Get-NetTCPConnection` **after** taking its baseline snapshot.
  That import pulled in the `NetTCPIP` module, so ~34 Microsoft functions —
  including `Test-NetConnection`, which legitimately contains `WindowsPrincipal`
  — were counted as functions *the profile had defined*. The suite was reporting
  an elevation primitive in Microsoft's own networking module and blaming my
  profile for it.
- Child-process counting diffed *all* system processes, so unrelated activity on
  the machine during iteration 1 registered as three processes the profile had
  spawned.
- The secret-env check enumerated the absolute environment rather than the delta,
  so the parent session's own inherited credentials were reported as the
  profile's doing.

The fix was to warm every cmdlet the probe itself uses *before* snapshotting,
count only processes parented to the probe's own PID, and measure environment as
a before/after difference. A test that blames the subject for the observer's
behaviour is worse than no test — it produces confident, wrong conclusions.

### 6.2 The bug the assertions missed

Automated checks passed 469/469. Then I ran an interactive console session with
PowerShell transcription — literal console output rather than assertions — and
read it. `gl` printed this:

```
Path
----
C:\Users\me\dev\powershell_cleanup
```

Not a git log. A path. Because **`gl` is a built-in PowerShell alias for
`Get-Location`, and PowerShell resolves aliases before functions.** My `gl`
function was defined and permanently unreachable. Checking the rest: `gc`
(`Get-Content`), `gcm` (`Get-Command`), and `gp` (`Get-ItemProperty`) were dead
the same way. Four of seventeen git shorthands silently did the wrong thing.

Nothing in the suite caught it, because I had tested `gs` — which happens not to
collide — and generalised. Reading real output caught what asserting on chosen
examples did not.

Two fixes. The shorthands were renamed `gcom`, `gcmsg`, `glog`, `gpush` rather
than clobbering the builtins — the repository already carried a comment
recording that naming a function `split-path` once broke `pnpm` and `npm`, and
repeating that mistake to save two keystrokes would be poor judgement. And a
permanent assertion now walks every function the profile defines and fails if
`Get-Command` resolves the name to anything other than a function. The class of
bug is closed, not just the instance.

### 6.3 Final state

15 consecutive iterations, each an independent console load:

```
646 passed, 0 failed
load ms: min 254.4  avg 271.1  max 319.1
defined surface identical across all iterations
```

Re-run against the committed tree after commit: 216/216.
**Total across the session: 1,363 assertions, 0 failures in the final state.**

| | Before | After |
|---|---:|---:|
| Load time | 8,807 ms | **271 ms** (32× faster) |
| Functions | 553 | **32** |
| Aliases | 73 | **7** |
| Child processes at load | 10 | **0** |
| Elevation primitives | 9 | **0** |
| Errors, load / reload | 2 / 10 | **0 / 0** |
| Tracked files | 153 | **11** |

---

## 7. What I did not do, and why

**I did not touch `C:\Users\me\Documents\PowerShell`.** It is a separate live
clone of the same remote, sitting on `main`, and it is the operator's active
profile. Overwriting a working shell environment was not asked for and is not
reversible by me. It remains untouched.

**I did not rewrite git history.** Purging the Tavily key from `c06886c` means a
force-push against a pushed remote. Destructive, externally visible, and a
decision that belongs to the person who owns the repository.

**I did not merge to `main`.** The branch is pushed; the PR is the operator's.

**I could not fully simulate the target environment.** This development machine
runs elevated and in `FullLanguage` mode. I cannot prove behaviour under
Constrained Language Mode or AppLocker. What the suite proves is the thing that
actually matters and is machine-independent: no elevation-requiring code path
exists to be attempted. Current guidance for regulated Windows estates layers
Constrained Language Mode, JEA, AppLocker, script-block logging and transcription
around the shell — none of which the operator controls as a non-admin
contractor. Their contribution is to bring a profile that gives those controls
nothing to catch.

**One honest limitation about the tests themselves.** The suite loads the
profile by dot-sourcing the entrypoint with `$PROFILE` overridden, inside a real
non-redirected console. That is the same operation PowerShell performs at
startup, but it is not literally PowerShell's auto-load. Installing into a real
`$PROFILE` path to test that last inch would have meant overwriting the live
profile, which returns to the paragraph above.

---

## 8. What generalises

1. **Measure before you judge.** Nine seconds and ten subprocesses ended the
   trim-versus-rebuild debate before it started. No amount of code reading would
   have been as persuasive as one instrumented load.

2. **Check that your test can fail.** The interactive guard would have made every
   assertion pass against a profile that never loaded. Verifying the harness was
   observing anything at all — `redirected: False` is itself an assertion in the
   final suite — was a precondition for the results meaning anything.

3. **A test that blames the subject for the observer is actively harmful.** Three
   of my failure classes were the probe's own instrumentation. Had I trusted
   them, I would have "fixed" a profile that was already correct.

4. **Assert absence, not just presence.** For a compliance artifact, "does it
   work" is the easy half. "Does it refrain" is the half that gets audited.

5. **Read real output at least once.** 469 green assertions did not notice that
   four commands silently returned the wrong thing. One transcript did.

6. **Rebuilding can be the conservative choice.** It sounds like the risky
   option. When the deliverable is a claim about what is *not* there, a small
   thing built deliberately is far easier to defend than a large thing edited
   carefully.

7. **Deleting a secret is not removing it.** The single most important line in
   this whole retrospective is the one asking for a key rotation.

8. **Audit for bare top-level code before auditing function bodies.** The sshd
   finding was invisible to a symbol-level review because there were no symbols.
   The danger was structural: the file had no `function` wrapper, so
   dot-sourcing it *executed* it. Classify every fragment as defines-only versus
   executes-on-load before judging what it contains.

9. **Delegated work you never got back is not done.** Five auditors went idle
   without reporting. I closed the loop by answering their questions myself —
   and that is how the most severe finding in the whole audit surfaced, after
   the work was already committed, pushed, and reported as complete. The
   temptation to treat a silent subagent as a completed one is the exact failure
   mode to guard against.

10. **`git log -S` is the wrong tool for a secrets audit.** It answers "when did
   the occurrence count change", not "where does this string exist". It reported
   1 commit; blob-level scanning found 18, including the current tip of `main`.
   For secrets, enumerate objects (`git rev-list --objects --all`), filter to
   blobs, and `git cat-file` each one.

---

## 9. The one action that still needs a human

**Rotate the Tavily API key.**

`tvly-dev-1WFhx…thkDsL`. Present in **18 of 57 commits**, and **live on the tip
of `origin/main` right now** — not merely buried in history. Anyone with read
access to the repository can see it today.

The `safety-trimmed` branch removes it from its own tree. That changes nothing
about `main`, and nothing about history. Rotation is the only remediation that
holds regardless of what is done to the repository.

Everything else in this session is done, verified, and pushed.
