# Evidence contract and limits

Python 3.11+; standard library only. Git is needed for source identity. No install, network, model API, or external service is used by the helper itself. The explicitly supplied test command may have side effects and remains governed by the user's authorization and repo instructions.

`capture --out DIR --cwd REPO --project LABEL --scope LABEL --environment LABEL -- COMMAND {junit}` creates `receipt.json`, `junit.xml` (by the runner), and `console.log`. Out must not already exist and must be outside the source repository. A literal report placeholder is required so a stale report cannot be mistaken for a fresh run. Report flags may embed it, e.g. `--junitxml={junit}`. The helper waits once, with a configurable `--timeout` in seconds (600 by default), then terminates its own launched process group on POSIX.

`compare BEFORE AFTER [--json]` is read-only. Exit 0 means receipts are structurally comparable, **not that tests passed**. Exit 2 means evidence is unavailable/incomparable. `capture` maps nonzero test exits to helper exit 1; the original exit is retained in its receipt. Exceptions to normal test exits 0/1 are conservative blockers.

Supported XML: UTF-8 JUnit `testsuite`/`testsuites`, nested suites and XML namespaces; direct testcase `failure`, `error`, `skipped`. Identity is suite ancestry + classname + file + name. Cases with duplicate identity or retry/flaky elements are not silently merged. DTD/entities and reports over 32 MiB are refused. Count mismatches and suite-level errors block attribution. Unsupported extensions may need a dedicated adapter, not a claim of compatibility.

Failure signature hashes the full ordered `(kind, type, message, text)` tuples, normalizing only CRLF to LF in text. It does not strip assertions, expected/actual values, paths, timestamps, or line numbers. Conservative false changes are preferable to silently hiding a new failure. `inspect --id` returns the saved full detail for human/agent adjudication.

Source identity hashes tracked and nonignored untracked files plus HEAD and staged diff; no source contents are retained. Submodules, symlinks, unavailable Git state, or inventories above 128 MiB cause an attribution blocker. Ignored files, environment variables, dependencies, services, and tools outside the repo are **not** covered. The environment label must describe meaningful state; it is not independently verified. Hashes detect accidental report/log changes, not a malicious author editing both the artifact and its receipt. The tool is not an attestation/security boundary.

Validation:

```bash
python -m unittest discover -s tests -v
python eval/benchmark.py
```

Run from the skill directory. The benchmark creates a disposable Git repository and evidence directories under a temporary directory. It compares synthetic but actually executed stdlib-unittest checks; it does not touch the user's repo or contact services.
