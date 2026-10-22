# Why this narrow skill exists

Research and local validation: 2026-10-22. Status: **public alpha; local validation only**. No claim of market validation, unique invention, production savings, or measured token reduction.

## Direct demand evidence

1. A Cursor cloud-agent user reported returning after hours to find 45 tests on the same bug, and resorting to disabling testing. This is a firsthand report, not a measured prevalence estimate. It supports the broader repeated-verification pain; this skill does not solve browser exploration or choose routes. [Cursor forum, 2026-03-22](https://forum.cursor.com/t/cursor-doing-an-infinite-number-of-tests/155514)
2. A Claude Code user described a repeated sequence: code change, context compaction, newly broken tests labelled existing, sometimes ignored, then additional token spend and manual correction. Replies independently describe similar attribution failures. This directly supports the selected evidence-handoff workflow. [Firsthand discussion](https://www.reddit.com/r/ClaudeCode/comments/1qp7qbe/claude_code_loves_breaking_stuff_and_then/)
3. Another user reported 712 mentions of pre-existence over 139 sessions in a month, and repeated attribution/deferment behavior despite written rules. These are the author's self-reported figures, not independently audited logs. The comments also explain why forcing an agent to fix every external failure would be unsafe; this skill preserves scope rather than adopting that remedy. [Firsthand report](https://www.reddit.com/r/ClaudeCode/comments/1t2bgg0/my_claudemd_says_every_error_is_yours_to_fix_not/)

**Product inference:** a durable, exact failure comparison could reduce repeated evidence recovery and unsupported attribution after compaction. Demand for this exact implementation, frequency of avoided reruns, and willingness to adopt are **unproven**.

## Alternatives and actual differentiator

| Existing approach | What it already covers | This prototype's narrower addition |
|---|---|---|
| [Superpowers verification-before-completion](https://github.com/obra/superpowers/blob/main/skills/verification-before-completion/SKILL.md?plain=1) | Evidence before completion, fresh verification, checking exits/output, and red-green validation. | Durable hash-linked before/after reports for the *pre-existing attribution* claim, plus exact same-test signature changes. Does not replace fresh completion verification. |
| [RTK test commands](https://github.com/rtk-ai/rtk/blob/develop/docs/usage/FEATURES.md) | Compact test output, failure-focused filtering, and output recovery. | Not another generic compressor: conservative cross-run evidence compatibility and skip/disappearance handling. |
| [pyrept](https://pypi.org/project/pyrept/1.3.1/) | Baseline comparison, new failures/fixed/still-failing/removed tests, HTML/JSON summaries. Its docs match tests by name. | Bind raw results to the exact command template and source-state receipt; flag changed failure text within a still-failing identity. Generic baseline comparison is not novel. |
| [TestNod](https://testnod.com/docs) | Hosted JUnit history, run-to-baseline changes and failure-pattern grouping. | Zero-service local artifact handoff with explicit refusal when run evidence is incompatible; no uploads or account setup. This is a deployment/workflow distinction, not a claim TestNod lacks correctness safeguards. |
| [pytest last-failed](https://pytest.org/en/7.0.x/how-to/cache.html) | Re-run previously failing tests first or exclusively. | Recover and compare evidence *without* another run. It is not a test selector or permission to omit regression checks. |

Other close tools discovered include assaylab's documented JUnit handoff and baseline CLI, and `testland/qa`'s JUnit analysis skill. They reinforce that **parsing, diffing, compact summaries and agent handoffs are already served**. No exhaustive implementation audit was performed. The proposed wedge is the combination of strict evidence compatibility, same-test changed-error detection, and refusal to turn missing/skipped checks into “fixed” while retaining exact source artifacts. Consider integrating this into an established tool if user adoption does not justify another standalone skill.

## Measured deterministic fixture

Reproduce from the skill root: `python eval/benchmark.py` (creates a new temporary output directory). Aggregate results are in `eval/synthetic-results.json`. Raw run artifacts are intentionally not distributed; the benchmark creates a fresh equivalent fixture.

- Two actually executed **synthetic** stdlib-unittest runs: 305 → 304 cases, five failures each.
- Count-only baseline: 0 additional failures detected.
- Failed-test-ID set baseline: 3 new failed identities.
- Signature-aware comparison: those 3 plus 1 changed failure within an already-failing identity.
- Separately flags 1 failed→skipped and 1 failed→absent; neither is a repair.
- Preserves 1 genuine failed→passed and 1 exact same earlier failure.
- Raw JUnit input: 339,502 bytes; compact handoff: 1,122 bytes (**99.67% fewer artifact bytes**). The fixture includes simulated application logs, so this is deliberately **not** a production compression ratio or a model-token/time saving.
- Comparing and recovering details does not execute tests. That demonstrates the capability, not how many real reruns a user would otherwise perform.

The benchmark writes `metrics.json`, `comparison.json`, `handoff.md`, and both raw reports/receipts/logs locally. Published aggregates omit local paths. The source fixture is `tests/fixtures/runner.py`. These are not live user code or external project outcomes.

## Independent baseline and forward test

Two independent agents received the same realistic request: determine whether five failures in both runs establish no regressions, identify needed work, recover evidence without rerunning tests. The no-skill agent could access only the six raw run artifacts, not this skill or its outputs. The with-skill agent used the skill/helper plus those raw artifacts; its later adversarial review was separate.

**The no-skill agent also got the substantive answer right.** It found all relevant transitions, checked hashes and compared metadata. Thus this trial shows **no accuracy uplift**. It took 67 seconds of observed investigation, three shell calls, and 64 lines / 4,265 bytes of bespoke Python in two scripts; an initial raw-output read was truncated. Timing is one tiny, uncontrolled trial, not a general speed estimate.

The with-skill forward test recovered the same categories and exact changed error using the bundled helper without suite reruns. Its separate adversarial review found meaningful holes in the first prototype: unknown nesting could hide a testcase, receipt chronology was under-validated, and untrusted blocker strings could inject Markdown layout. These were fixed, with regression tests. Disabled/not-run outcome attributes were also corrected to avoid false pass classification. Details and final review are recorded separately in `eval/independent-review.md`.

**Real-runner validation completed:** an isolated copy of equation-rescue with native Vitest JUnit and explicitly injected faults; see `eval/real-runner-results.json`. **Next validation needed:** a naturally occurring user failure and one compacted/handoff continuation. Measure unnecessary reruns, custom analysis code, output volume, and unresolved attribution—not only happy-path fixture accuracy. No outreach or live production integration has been performed.
