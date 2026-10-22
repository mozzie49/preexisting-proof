# Independent forward test and adversarial review

2026-10-22. Local-only prototype review. Both reviewers used fresh agent contexts; no external calls or test-suite reruns were needed to answer the task.

## Task given to both agents

“The agent says there are still five failed tests, so no regressions. Confirm or reject that, identify what needs attention, and recover enough saved evidence to continue without rerunning the suite.”

Raw inputs: the before/after `receipt.json`, `junit.xml`, and `console.log` files in private local evidence directories (not distributed; rerun `python eval/benchmark.py` to recreate the scenario). The no-skill agent was prohibited from reading the skill/helper, fixture generator, or expected results. The with-skill reviewer read the skill/helper but not the benchmark/expected-results artifacts.

## Common result: both correct

Both rejected the count-only claim and found three newly failing tests, one changed cart failure, one missing check, one newly skipped check, one recovery, and one unchanged recorded billing failure. Both recovered source-line tracebacks and retained the distinction between observed transition and causal attribution. Therefore **no accuracy uplift was demonstrated**.

| Measure | No skill | With skill |
|---|---|---|
| Shell tool calls for forward task | 3 | 4 |
| Bespoke analysis code | 64 lines / 4,265 bytes | 0 for verdict/failure details |
| Core operations | Read raw files; author two Python analyzers | Read instructions/helper; run one `compare`, eight `inspect` calls; read receipts |
| Raw context issue | Initial combined raw log/receipt read was truncated | Helper returned bounded comparison and selected details |
| Test-suite reruns | 0 | 0 |
| Timing | 67 seconds, measured by two clock reads | About 22 seconds inferred from conversation timestamps, **not comparable measurement** |

An optional later eight-line XML snippet recovered a skip reason for the with-skill answer. The helper now retains skip message/text in `inspect --id`, covered by an additional test, so that snippet is no longer necessary. Do not describe the trial as fewer tool calls: with-skill used one more shell call. The evidenced advantage is reusable analysis code and controlled evidence retrieval, not an established speed/token uplift.

## Adversarial findings, all closed

1. **Unknown XML wrapper could hide a new failing testcase** while descendant count checks still passed. Fixed by tracking consumed cases and rejecting unsupported testcase/outcome nesting.
2. **Incomplete or overlapping receipt timestamps were accepted.** Fixed with complete timezone-aware start/end validation and baseline-finish-before-candidate-start enforcement.
3. **Untrusted suite/test names could inject Markdown layout through blocker strings.** Fixed by JSON-escaping blockers to single lines.
4. **Not-run/disabled outcome attributes could appear green.** Fixed: recognized suppressed/not-run states are skipped, unknown states ambiguous.
5. **Hidden nested failure initially still appeared in a passing category despite a blocker.** Fixed: nested outcomes are ambiguous; passing transitions under blockers are explicitly unverified.

Final independent closure check for hidden-outcome case: `comparable=false`; after counts `failure:1, ambiguous:1`; target changed `failure -> ambiguous`; **no now_passing category**. The reviewer confirmed every reproduced defect closed. Its earlier residual report was explicitly superseded.

The final suite has 30 regression/integration checks, including literal argv/space preservation, refusal to overwrite evidence, refusal of repository-local output and missing JUnit placeholders, artifact tampering, scope/environment/command incompatibility, disabled/duplicate/retry/malformed report handling, and skipped/missing versus repaired distinctions. Passing these bounded tests is not universal JUnit compatibility or security attestation.

## Remaining limits

- One small synthetic task; no consenting production-user field trial.
- No quantitative model token-cost, rerun-frequency, or wall-time comparison.
- Git-visible source files only; environment labels are caller declarations.
- Exact signatures may conservatively flag noisy path/line/timestamp changes.
- Local receipts are hash-linked, not signed; a malicious author can edit both.
- The helper does not prove a passing test discriminates the reported bug, determine causality, or authorize ignoring failures.
