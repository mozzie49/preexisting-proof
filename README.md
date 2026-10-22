# preexisting-proof

**Before an AI says “that test was already broken,” keep the evidence.**

An Agent Skill and small Python helper for comparing saved JUnit failures across coding-agent sessions. It preserves the exact command, source state, report and log hashes, then produces a compact handoff without another test run.

Five failures before and five after do not mean no regressions. A still-failing test can have a new error; a missing or skipped test is not a fix.

## What it does

- Distinguishes new, changed, unchanged, now-passing, skipped and missing test outcomes.
- Refuses a pre-existing classification when run scope, command or declared environment differ, source changes during a run, artifacts change, or XML is ambiguous.
- Recovers one saved failure or skip reason by ID, rather than rerunning the suite to reconstruct lost context.
- Runs locally with **Python 3.11+ and Git**. No Python dependencies, account, telemetry or network calls in the helper.

The supplied test command retains its normal behavior and permissions. This tool is not a sandbox.

## Use

The directory is a self-contained Agent Skill: copy it into your agent's supported skill directory, or point the agent at [SKILL.md](SKILL.md). No hook or global configuration is installed automatically. The helper also works directly.

Wrap an **already-authorized** test command, preserving the project's runner/environment. Use a new evidence directory outside the source repository and the literal `{junit}` placeholder:

```bash
python scripts/preexisting.py capture \
  --out /tmp/task-evidence/before --cwd /path/to/project \
  --project my-project --scope unit-tests \
  --environment 'Node 24; lockfile SHA recorded; no external services' \
  -- npm test -- --reporter=junit --outputFile='{junit}'
```

The example is for a project whose test script supports those Vitest options; it is not a universal npm flag. For pytest, its corresponding report argument is `--junitxml='{junit}'`. Use the same command template and metadata for a later run, changing only `--out` to a new directory such as `/tmp/task-evidence/after`.

```bash
python scripts/preexisting.py compare /tmp/task-evidence/before /tmp/task-evidence/after
python scripts/preexisting.py inspect /tmp/task-evidence/after/junit.xml --id TEST_ID_PREFIX
```

`capture` executes argv once, without a shell, and never overwrites an evidence directory. `compare` and `inspect` do not run tests. `capture` exit 1 records a nonzero test exit; the original exit code is retained. **`compare` exit 0 means comparable evidence, not passing tests.** Exit 2 means evidence is unavailable or incompatible.

No baseline? Inspect existing XML, but say pre-existence is unverified. Do not switch, stash or reset the user's checkout just to manufacture a baseline.

## What is actually verified

- **30 local unit/integration checks pass.** Includes malformed/duplicate/retry XML, hidden outcomes, disabled cases, tampering, chronology, metadata mismatch, exact failure signatures, literal argv and overwrite refusal.
- **Native Vitest 4.1.11 JUnit, real project:** in an isolated copy of equation-rescue, 29 existing math checks passed; an injected XML-escaping fault produced 28 pass / 1 fail; a second injected variant changed the same failure; restoration returned to 29 pass. The helper classified `new_failure → changed_failure → now_passing` correctly. Original checkout unchanged. **These were controlled injected faults, not naturally occurring user bugs.** [Aggregate record](eval/real-runner-results.json)
- **Synthetic equal-count fixture:** two runs with five failures each yielded three new failures, one changed failure, one skipped check and one missing check. Reproduce with `python eval/benchmark.py`. [Aggregate record](eval/synthetic-results.json)
- **Independent agent comparison:** both the no-skill and with-skill agents answered correctly. No accuracy uplift was shown. The no-skill agent wrote 64 lines of bespoke analysis; the skill reused its helper. There is no controlled token/time improvement claim. [Review](eval/independent-review.md)

Raw real-project reports, logs, source, private paths and dependency directories are **not included** in this distribution. The CI workflow runs tests and the synthetic fixture; hosted run status is available under [Actions](https://github.com/mozzie49/preexisting-proof/actions). The evidence above describes local validation, not a claim about an unobserved CI run.

## Boundaries

“The same failure was observed earlier” is **not proof of causality**, a clean bill of health, or permission to ignore it. Required verification still runs. The tool does not determine whether a passing test actually exercises the reported bug.

Environment labels are declarations, not attestations. Ignored dependencies, services, environment variables and external files are not fingerprinted. Symlink/submodule/oversize source inventories block attribution. Exact signature matching retains numbers, paths and line information; harmless noise may require inspection. Hash-linked local receipts are not signed and cannot defend against an author changing both a report and its receipt.

Supported report shape is intentionally conservative; see [format details](references/format.md). Reports/logs can contain secrets and untrusted text. Keep them local and review before sharing. No automatic upload, test rewriting, result suppression, branch changes or dependency installation.

Generic compression and test dashboards already exist. This is a narrow evidence-handoff workflow, not a replacement for RTK, pyrept, TestNod or your test runner. [Demand evidence and alternatives](references/evidence.md)

## Development

```bash
python -m unittest discover -s tests -v
python eval/benchmark.py
python scripts/release_check.py
```

The release check uses an explicit file allowlist and scans for known private workspace paths and common credential patterns. It is a bounded hygiene check, not a guarantee that arbitrary content is safe to publish.

MIT licensed. Alpha quality: real-runner compatibility tested, naturally occurring user-failure and adoption validation still pending.
