#!/usr/bin/env python3
"""ATS parse check: can an applicant tracking system read this resume PDF?

Runs Resume Matcher's deterministic checker (srbhr/Resume-Matcher, Apache-2.0) on each PDF:
text layer, garbled glyphs, columns, tables, contact info, section headings, dates. It scores
readability, not fit; `keyword-match.mjs` still handles keywords.

Offline and private: PDFs are only read inside a deny-by-default macOS sandbox (sandbox-exec).
It has no network and can run nothing but its own Python. It can read only the PDFs, this
script, the checker source, the Python runtime, system libraries and its own temp folder, and
it can write only to a scratch folder in that temp folder (file metadata such as stat stays
visible, contents don't). The app's LLM, prompts and schema modules are replaced with stubs.
Network is used only before that, with no resume data: the first run downloads the source,
pinned to one commit, to ~/.cache/resume-matcher/<commit>, and uv installs the Python packages,
frozen to what existed at EXCLUDE_NEWER, into a throwaway venv in the temp folder. Anything
that goes wrong fails closed: no sandbox, no check.

Usage: python3 -I ats-parse-check.py <pdf> [<pdf> ...]
Prints a JSON list: {"file", "extraction_layout", "content", "pages", "passed", "problems"}.

Exit codes: 0 every PDF passed; 1 bad input (missing file); 2 at least one PDF has problems;
3 the checker itself is unavailable (no uv, git or sandbox, download failed, bad report).
A PDF passes with both scores at MIN_SCORE or above, one page, and no check at "fail".
Python 3.9 compatible (runs as /usr/bin/python3 -I), stdlib only.
"""
import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import types

REPO_URL = "https://github.com/srbhr/Resume-Matcher.git"
PIN = "8c6a1b75c6f4eb2e7b9d49986dc5d0a80d5a4234"
PYTHON = "3.13"
# Versions from the pinned commit's apps/backend/pyproject.toml; anyio is what uv resolved.
DEPS = ["pdfminer.six==20260107", "pydantic==2.14.0", "python-docx==1.2.0", "anyio==4.15.1"]
EXCLUDE_NEWER = "2026-10-31T00:00:00Z"  # freezes transitive packages too
# Deny everything, then allow only what one parse needs. Each (param ...) is filled with a real
# path (symlinks resolved) because the sandbox matches resolved paths. Metadata (stat, readlink)
# stays allowed everywhere since Python resolves paths with it; it never exposes file contents.
SANDBOX_PROFILE = """(version 1)
(deny default)
(deny network*)
(allow process-exec (literal (param "PYTHON")))
(allow sysctl-read)
(allow file-read-metadata)
(allow file-read* (literal "/") (subpath "/usr/lib") (subpath "/System") (subpath "/private/var/db/dyld")
  (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))
(allow file-read* (subpath (param "RUNTIME")) (subpath (param "VENV")) (subpath (param "SOURCE"))
  (literal (param "CHECKER")) (subpath (param "SCRATCH")))
(allow file-write* (subpath (param "SCRATCH")) (literal "/dev/null"))
"""
PDF_RULE = '(allow file-read* (literal (param "PDF%d")))\n'
PROBE = "import json, os, sys; print(json.dumps([os.path.realpath(sys.executable), os.path.realpath(sys.base_prefix)]))"
MIN_SCORE = 90
TIMEOUT = 300
EXTRA_TOOL_DIRS = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]


class Unavailable(Exception):
    """The checker can't run; the resume hasn't been judged."""


def find_tool(name):
    path = shutil.which(name)
    if path:
        return path
    for folder in EXTRA_TOOL_DIRS:
        candidate = os.path.join(folder, name)
        if os.access(candidate, os.X_OK):
            return candidate
    raise Unavailable("%s not found" % name)


def cache_root():
    return os.path.expanduser("~/.cache/resume-matcher")


def _clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}


def _git(git, src, *args):
    """Git pinned to src's own .git and work tree, so it can never walk up to a parent repo."""
    cmd = [git, "--git-dir=" + os.path.join(src, ".git"), "--work-tree=" + src] + list(args)
    return subprocess.run(
        cmd, capture_output=True, text=True, errors="replace", timeout=TIMEOUT, env=_clean_env()
    )


def _at_pin(git, src):
    head = _git(git, src, "rev-parse", "HEAD")
    status = _git(git, src, "status", "--porcelain")
    return head.stdout.strip() == PIN and status.returncode == 0 and not status.stdout.strip()


def _download(git, root, final):
    """Build the checkout in a new temp folder and move it into place. Nothing is reset or deleted."""
    os.makedirs(root, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".tmp-", dir=root)
    try:
        init = subprocess.run(
            [git, "init", "-q", tmp], capture_output=True, text=True, errors="replace",
            timeout=TIMEOUT, env=_clean_env(),
        )
        if init.returncode != 0:
            raise Unavailable("git init failed")
        for args in (("fetch", "-q", "--depth", "1", REPO_URL, PIN), ("checkout", "-q", "--detach", PIN)):
            if _git(git, tmp, *args).returncode != 0:
                raise Unavailable("could not download Resume Matcher (git %s failed)" % args[0])
        if not _at_pin(git, tmp):
            raise Unavailable("downloaded Resume Matcher is not at the pinned commit")
        try:
            os.rename(tmp, final)
        except OSError:
            if not os.path.isdir(final):  # otherwise a parallel run got there first, which is fine
                raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def ensure_source():
    """Return a clean checkout of PIN in our own cache folder. Raises Unavailable."""
    git = find_tool("git")
    root = cache_root()
    final = os.path.join(root, PIN)
    try:
        if os.path.islink(final) or os.path.islink(root):
            raise Unavailable("Resume Matcher cache is a symlink")
        if not os.path.isdir(final):
            _download(git, root, final)
        if not _at_pin(git, final):
            raise Unavailable("Resume Matcher cache was modified; delete %s to re-download" % final)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unavailable("could not prepare Resume Matcher: %s" % type(exc).__name__)
    return final


def valid_report(report):
    """A report must carry an error, or both scores and a page count. Anything else fails closed."""
    if not isinstance(report, dict):
        return False
    if isinstance(report.get("error"), str):
        return True
    numbers = (report.get("extraction_layout"), report.get("content"), report.get("pages"))
    return all(type(n) is int for n in numbers) and isinstance(report.get("failed_checks"), list)


def judge(report):
    """Turn the inner report for one PDF into the pass/fail entry this script prints."""
    problems = list(report.get("failed_checks") or [])
    if report.get("error"):
        problems.append("unreadable: %s" % report["error"])
    else:
        for label, key in (("extraction/layout", "extraction_layout"), ("content", "content")):
            if report[key] < MIN_SCORE:
                problems.append("%s score %s is under %s" % (label, report[key], MIN_SCORE))
        if report["pages"] != 1:
            problems.append("%s pages, expected 1" % report["pages"])
    return {
        "file": report.get("file"),
        "extraction_layout": report.get("extraction_layout"),
        "content": report.get("content"),
        "pages": report.get("pages"),
        "passed": not problems,
        "problems": problems,
    }


def prepare_python(uv, work):
    """Make work/venv with the pinned packages (network allowed, no resume data involved).

    Returns (venv python, its real executable, the real runtime folder). Raises Unavailable.
    """
    venv = os.path.join(work, "venv")
    python = os.path.join(venv, "bin", "python")
    steps = (
        [uv, "venv", "-q", "--no-project", "--managed-python", "--python", PYTHON, venv],
        [uv, "pip", "install", "-q", "--python", python, "--exclude-newer", EXCLUDE_NEWER] + DEPS,
        [python, "-I", "-c", PROBE],
    )
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    for cmd in steps:
        # cwd is the empty temp folder, so nothing in the repo or the job folder is read as config.
        step = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, errors="replace", timeout=TIMEOUT)
        if step.returncode != 0:
            raise Unavailable("could not install the checker's packages")
    try:
        executable, runtime = json.loads(step.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError, TypeError):
        raise Unavailable("could not locate the checker's Python")
    if not all(isinstance(p, str) and os.path.isabs(p) for p in (executable, runtime)):
        raise Unavailable("could not locate the checker's Python")
    # The whole runtime folder becomes readable in the sandbox, so it must be a Python install,
    # not something broad like / or the home folder (possible with UV_PYTHON_INSTALL_DIR).
    home = os.path.realpath(os.path.expanduser("~"))
    if runtime == "/" or _inside(home, runtime) or _inside(work, runtime):
        raise Unavailable("the checker's Python lives in too broad a folder: %s" % runtime)
    return python, executable, runtime


def _inside(path, folder):
    """True if path is folder or anywhere under it (both real paths)."""
    return path == folder or path.startswith(folder.rstrip("/") + "/")


def sandbox_command(sandbox, python, params, src, paths):
    """sandbox-exec argv: the profile, one read rule per PDF, and every path as a -D parameter."""
    profile = SANDBOX_PROFILE + "".join(PDF_RULE % i for i in range(len(paths)))
    params = dict(params, CHECKER=os.path.realpath(__file__), SOURCE=os.path.realpath(src))
    for i, path in enumerate(paths):
        params["PDF%d" % i] = os.path.realpath(path)
    cmd = [sandbox, "-p", profile]
    for key in sorted(params):
        cmd += ["-D", "%s=%s" % (key, params[key])]
    return cmd + [python, "-I", "-B", os.path.abspath(__file__), "--inner", params["SOURCE"]] + [
        os.path.abspath(p) for p in paths
    ]


def run_checker(paths):
    """Run this file in a fresh venv, sandboxed, with the pinned packages. Raises Unavailable."""
    uv = find_tool("uv")
    sandbox = find_tool("sandbox-exec")
    src = ensure_source()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            work = os.path.realpath(tmp)
            python, executable, runtime = prepare_python(uv, work)
            scratch = os.path.join(work, "scratch")
            os.mkdir(scratch)
            params = {"PYTHON": executable, "RUNTIME": runtime, "VENV": os.path.join(work, "venv"), "SCRATCH": scratch}
            done = subprocess.run(
                sandbox_command(sandbox, python, params, src, paths),
                cwd=scratch, env={"PATH": "/usr/bin:/bin", "HOME": scratch, "TMPDIR": scratch},
                capture_output=True, text=True, errors="replace", timeout=TIMEOUT,
            )
    except (OSError, subprocess.SubprocessError) as exc:
        raise Unavailable("checker did not run: %s" % type(exc).__name__)
    if done.returncode != 0:
        # stderr can quote PDF contents, so it isn't repeated here.
        raise Unavailable("checker exited with code %s" % done.returncode)
    try:
        reports = json.loads(done.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Unavailable("checker returned no report")
    if not isinstance(reports, list) or len(reports) != len(paths) or not all(valid_report(r) for r in reports):
        raise Unavailable("checker returned an incomplete report")
    return reports


def inner(root, paths):
    """Runs under Python 3.13 in the throwaway venv, inside the sandbox (no network, narrow file access)."""

    def blocked(*args, **kwargs):
        raise RuntimeError("LLM is disabled during the ATS parse check")

    app_root = os.path.join(root, "apps", "backend", "app")
    # Skip the package __init__ files, which pull in Playwright, FastAPI and LiteLLM.
    for name, path in (
        ("app", app_root),
        ("app.services", os.path.join(app_root, "services")),
        ("app.services.ats_parse", os.path.join(app_root, "services", "ats_parse")),
    ):
        module = types.ModuleType(name)
        module.__path__ = [path]
        sys.modules[name] = module
    llm = types.ModuleType("app.llm")
    for name in ("complete_json", "get_llm_config", "get_model_name", "get_safe_max_tokens"):
        setattr(llm, name, blocked)
    sys.modules["app.llm"] = llm
    schemas = types.ModuleType("app.schemas")
    schemas.ResumeData = dict
    sys.modules["app.schemas"] = schemas
    prompts = types.ModuleType("app.prompts")
    prompts.PARSE_RESUME_PROMPT = ""
    prompts.__path__ = []
    sys.modules["app.prompts"] = prompts
    templates = types.ModuleType("app.prompts.templates")
    templates.RESUME_SCHEMA_EXAMPLE = ""
    sys.modules["app.prompts.templates"] = templates
    markitdown = types.ModuleType("markitdown")
    markitdown.MarkItDown = object
    sys.modules["markitdown"] = markitdown

    from app.services.ats_parse.checks import run_checks, score
    from app.services.ats_parse.extract import extract_document
    from app.services.parser import DocumentValidationError

    reports = []
    for path in paths:
        entry = {"file": path}
        # Read outside the try: a PDF the sandbox won't let us read means the checker didn't run.
        with open(path, "rb") as handle:
            data = handle.read()
        try:
            doc = asyncio.run(extract_document(data, os.path.basename(path)))
            checks = run_checks(doc, {"locale": None, "template": None, "cv_mode": False})
            entry["extraction_layout"] = score(checks, {"extraction", "layout"})
            entry["content"] = score(checks, {"content"})
            entry["pages"] = doc.page_count
            entry["failed_checks"] = [c.id for c in checks if c.status == "fail"]
        except DocumentValidationError as exc:
            entry["error"] = str(exc)[:200]
        except (OSError, ImportError, MemoryError):
            # Denied file access, a missing module or no memory is the sandbox or setup failing,
            # not the PDF: crash so the outer run reports exit 3 (not judged) instead of exit 2.
            raise
        except Exception as exc:  # a PDF that breaks the parser is a failed PDF, not a missing tool
            entry["error"] = "parser crashed (%s)" % type(exc).__name__
        reports.append(entry)
    print(json.dumps(reports))
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "--inner":
        return inner(argv[1], argv[2:])
    if not argv:
        print(__doc__, file=sys.stderr)
        return 1
    missing = [p for p in argv if not os.path.isfile(p)]
    if missing:
        print("not a file: %s" % ", ".join(missing), file=sys.stderr)
        return 1
    try:
        results = [judge(report) for report in run_checker(argv)]
    except Exception as exc:  # exit 3 means "not judged", so nothing here may read as a pass or bad input
        reason = exc if isinstance(exc, Unavailable) else type(exc).__name__
        print("ATS parse check unavailable: %s" % reason, file=sys.stderr)
        return 3
    print(json.dumps(results, indent=2))
    return 0 if all(result["passed"] for result in results) else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
