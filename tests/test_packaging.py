"""Exercise distribution artifacts and the real installed console command."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
import tarfile
import venv
from pathlib import Path
from zipfile import ZipFile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for key in ("PYTHONPATH", "PYTHONHOME", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
        env.pop(key, None)
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result


@pytest.fixture(scope="module")
def installed_package(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Build through sdist, then install in an isolated disposable environment."""
    base = tmp_path_factory.mktemp("distribution")
    source = base / "source"
    source.mkdir()
    for name in ("pyproject.toml", "cli.py", "README.md"):
        shutil.copyfile(ROOT / name, source / name)
    shutil.copytree(
        ROOT / "src/unihive",
        source / "src/unihive",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    for directory in ("taxonomy", "schemas"):
        shutil.copytree(ROOT / "data" / directory, source / "data" / directory)
    for name in (
        "__init__.py",
        "bands.yaml",
        "questions.yaml",
        "portfolio.yaml",
        "program_data_policy.yaml",
    ):
        shutil.copyfile(ROOT / "data" / name, source / "data" / name)
    # Catalogs are user inputs; never accidentally distribute student profiles.
    for directory, filename in (
        ("profiles", "profile.json"),
        ("programs", "p.yaml"),
        ("reviews", "confirmation.json"),
    ):
        folder = source / "data" / directory
        folder.mkdir()
        (folder / filename).write_text("PRIVATE_SENTINEL", encoding="utf-8")
    run(
        [
            sys.executable,
            "-c",
            "from setuptools.build_meta import build_sdist; build_sdist('dist')",
        ],
        source,
    )
    archive = next((source / "dist").glob("*.tar.gz"))
    unpacked = base / "sdist"
    with tarfile.open(archive) as contents:
        assert not any(
            any(f"/{kind}/" in n for kind in ("profiles", "programs", "reviews"))
            for n in contents.getnames()
        )
        contents.extractall(unpacked, filter="data")
    build_root = next(unpacked.iterdir())
    wheels = base / "wheels"
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            ".",
            "--no-deps",
            "--no-index",
            "--no-build-isolation",
            "--no-cache-dir",
            "--wheel-dir",
            str(wheels),
        ],
        build_root,
    )
    wheel = next(wheels.glob("*.whl"))
    with ZipFile(wheel) as contents:
        assert "cli.py" in contents.namelist()
        for path in (ROOT / "data").rglob("*"):
            relative = path.relative_to(ROOT / "data")
            if path.is_file() and (
                relative.parts[0] in {"taxonomy", "schemas"}
                or relative.as_posix()
                in {"bands.yaml", "questions.yaml", "portfolio.yaml"}
            ):
                assert (
                    contents.read("unihive/_data/" + relative.as_posix())
                    == path.read_bytes()
                )
        for path in (ROOT / "src/unihive/llm/prompts").glob("*.txt"):
            assert (
                contents.read("unihive/llm/prompts/" + path.name) == path.read_bytes()
            )

    environment = base / "installed"
    venv.EnvBuilder(with_pip=False).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    site = Path(
        run(
            [
                str(python),
                "-c",
                "import sysconfig; print(sysconfig.get_path('purelib'))",
            ],
            base,
        ).stdout.strip()
    )
    # Reuse already-installed dependencies without network or source-package
    # editable hooks: .pth files inside this added directory are not processed.
    (site / "test_dependencies.pth").write_text(
        sysconfig.get_path("purelib") + "\n",
        encoding="utf-8",
    )
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "--python",
            str(python),
            "install",
            "--no-index",
            "--no-deps",
            str(wheel),
        ],
        base,
    )
    run_dir = base / "outside-checkout"
    run_dir.mkdir()
    for name in ("profile.json", "program.yaml"):
        shutil.copyfile(ROOT / "tests/fixtures/cli" / name, run_dir / name)
    return python, run_dir


def test_installed_console_scores_and_replays(
    installed_package: tuple[Path, Path],
) -> None:
    python, cwd = installed_package
    command = python.parent / ("unihive.exe" if os.name == "nt" else "unihive")
    scored = run(
        [
            str(command),
            "--score-only",
            "--profile",
            "profile.json",
            "--program",
            "program.yaml",
            "--as-of",
            "2026-01-01",
            "--json",
        ],
        cwd,
    )
    payload = json.loads(scored.stdout)
    assert payload["pathway_readiness"] == "STRONG"
    assert payload["data_confidence"] == "HIGH"
    assert "Provisional configs in use:" in scored.stderr
    (cwd / "assessment.json").write_text(scored.stdout, encoding="utf-8")
    replayed = run(
        [
            str(command),
            "replay",
            "--audit",
            "assessment.json",
            "--json",
        ],
        cwd,
    )
    assert replayed.stdout == scored.stdout


def test_installed_loaders_and_prompts_use_installed_files(
    installed_package: tuple[Path, Path],
) -> None:
    python, cwd = installed_package
    script = """
from pathlib import Path
import sys
import cli
import unihive
from unihive.resources import DATA_ROOT
from unihive.questions import load_question_bank
from unihive.portfolio import load_portfolio_configuration
from unihive.program_quality import load_program_data_policy
from unihive.llm.extractor import (
    load_prompt_template, DEFAULT_EXTRACTION_PROMPT, DEFAULT_RETRY_PROMPT,
)
from unihive.llm.narrator import DEFAULT_NARRATOR_PROMPT
for path in (Path(cli.__file__), Path(unihive.__file__), DATA_ROOT,
             DEFAULT_EXTRACTION_PROMPT, DEFAULT_RETRY_PROMPT, DEFAULT_NARRATOR_PROMPT):
    assert path.is_relative_to(Path(sys.prefix)), path
assert load_question_bank().values.questions
assert load_portfolio_configuration().values.minimum_size == 8
assert load_program_data_policy().values.maximum_age_days > 0
for path in (DEFAULT_EXTRACTION_PROMPT, DEFAULT_RETRY_PROMPT, DEFAULT_NARRATOR_PROMPT):
    assert load_prompt_template(path).text
print('Installed resources verified')
"""
    assert (
        "Installed resources verified" in run([str(python), "-c", script], cwd).stdout
    )


def test_installed_report_command_and_replay(
    installed_package: tuple[Path, Path],
) -> None:
    python, cwd = installed_package
    command = python.parent / ("unihive.exe" if os.name == "nt" else "unihive")
    response = run(
        [
            str(command),
            "--score-only",
            "--profile",
            "profile.json",
            "--program",
            "program.yaml",
            "--as-of",
            "2026-01-01",
            "--json",
            "--report",
        ],
        cwd,
    )
    payload = json.loads(response.stdout)
    assert payload["assessment"]["pathway_readiness"] == "STRONG"
    assert len(payload["report"]) == 6
    assert payload["report"]["strengths"][0]["evidence_ids"] == ["ml-paper"]
    assert payload["eligibility_result"]["rule_breakdown"][0]["outcome"] == "PASS"
    (cwd / "report.json").write_text(response.stdout, encoding="utf-8")
    replayed = run(
        [
            str(command),
            "replay",
            "--audit",
            "report.json",
            "--json",
            "--report",
        ],
        cwd,
    )
    assert replayed.stdout == response.stdout


def test_editable_install_reads_authoritative_data_directory() -> None:
    from unihive.resources import DATA_ROOT

    assert DATA_ROOT.resolve() == (ROOT / "data").resolve()
