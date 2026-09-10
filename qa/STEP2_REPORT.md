# Step 2 report integration and synthetic demo

Completed September 9, 2026. Real university data was not required for this step.
The implementation and tests use the existing explicitly synthetic program and
profile fixtures. No real university requirements, weights, or recommendations
were invented, and the real catalogs remain empty.

## What changed

- Added a versioned response envelope containing the unchanged `assessment`,
  full `eligibility_result`, six-section `report`, provisional status, and explicit
  limitations for unavailable alternative/action inputs.
- `unihive --json --report` produces that envelope. Plain `--json` retains the
  existing Assessment contract and values. Replay accepts either input format;
  report replay also verifies the full regenerated envelope when one was saved.
- `POST /score` requests the report from the real CLI and forwards it unchanged.
- The page displays supplied evidence and its sources, strengths, confirmed and
  below-level gaps, the chosen program, unavailable action/alternative explanations,
  unresolved competency and eligibility fields, and sourced eligibility rules.
- Corrected backend path field names and the filter that hid below-level gaps.
  Unknowns remain separate. Versioned the script URL and disabled page caching
  to prevent the old renderer from being used with the new response format.
- `serve.py --demo` reads only the existing `tests/fixtures/cli/` inputs, labels
  selectors as synthetic, and displays a provisional-configuration notice.
- Empty normal catalogs disable Score and explain how to launch demo mode.

## Verification

- Final full suite: **97 passed**, 24 provisional-data warnings, 25.86 seconds.
- Ruff, strict mypy (14 source files), and git whitespace checks passed.
- Six frontend contract checks passed, including rendering an actual CLI envelope,
  both pathway name contracts, known weak evidence, and unknown-exclusion controls.
- Thirteen live HTTP checks passed. Eight concurrent/repeated requests returned
  identical report responses in 2.35 seconds.
- Report tests cover strong/weak evidence, unknown versus absent, missing GPA,
  missing eligibility rules, empty candidate inputs, provenance, legacy CLI
  compatibility, report replay, and rejection of a tampered saved report.
- The installed-wheel test now exercises report scoring and report replay from
  outside the source checkout in addition to the Step 1 packaging checks.
- Browser verification confirmed the synthetic labels, all six sections, sourced
  eligibility results, provisional notice, and disabled empty-catalog state.

The first full-suite attempt hit a timing-only Hypothesis FlakyFailure in the
existing 100-run determinism test: 288.39 ms initially versus 59.77 ms on replay,
against a 200 ms deadline. No output mismatch occurred. The complete suite passed
on an unchanged rerun after browser work ended. Its original output is retained
in `step2-first-test-run.txt`; the passing output is `step2-test-results.txt`.
One separate acceptance check initially could not access pytest's temporary
directory under the sandbox; the authorized rerun passed.

## Try the demo

From the repository root in PowerShell:

```powershell
$env:PATH = (Join-Path $PWD '.venv\Scripts') + ';' + $env:PATH
.\.venv\Scripts\python.exe serve.py --demo
```

Open `http://127.0.0.1:8000/?dev=1`. Test servers were stopped after verification.

## Remaining work

The report is connected, but it does not generate comparison programs or action
candidates. Those sections explicitly say they are unassessed. Progressive
questioning and student editing/confirmation still need their application flow.
The limited evidence mappings and LLM grounding issues from the original review
remain open. Synthetic tests validate machinery, not real admissions accuracy.
