# Step 1 packaging and installed resource loading

Completed September 9, 2026. The installed `unihive` command now works, and the
local HTTP wrapper successfully invokes it without a PYTHONPATH workaround.

## Changes

- Explicit setuptools mappings include the root `cli.py`, the engine package,
  and the existing `data/` directory as `unihive._data`.
- Distributions include versioned YAML, JSON schemas, and LLM prompt files.
  Student profile and program catalogs remain external inputs.
- Default configuration loaders use package resources. Editable installs still
  read the authoritative source YAML directly; installed wheels use bundled files.
- The development extra includes the backend dependencies needed for offline
  packaging regression tests. The local editable install was refreshed.
- A root README documents installation, scoring, replay, and the local server.

## Verified results

- Full suite: **89 passed**, with the same 6 provisional-data warnings.
- Ruff: passed. Strict mypy: passed, 13 source files.
- Built a source distribution, built its wheel, installed it into a disposable
  environment, and ran its executable from a separate directory.
- Installed scoring and replay produced byte-identical output. All configuration
  loaders and all three prompt files resolved inside that installation.
- Bundled configuration and prompt bytes match the authoritative source files.
- Synthetic private catalog entries were excluded from the source distribution.
- The formerly failing installed-command acceptance check now passes.
- Live HTTP: all 13 smoke checks passed; 8 concurrent/repeated scoring requests
  returned byte-identical results in 2.82 seconds without a launch workaround.
- The assessment for the original fixed-date fixture equals the pre-fix baseline.

New regression coverage is in `tests/test_packaging.py` and the real-command
integration test in `tests/test_serve.py`. Captured outputs are in
`step1-test-results.txt` and `step1-http-results.txt`.

The live test server and temporary synthetic catalog files were removed after
verification. Existing unrelated working-tree changes were preserved.

## Next step

Connect the six-section report and eligibility rule breakdown to the response
contract. Current successful HTTP responses still omit both. The remaining
data-coverage, student-workflow, rendering, and LLM validation findings from the
original review remain open.
