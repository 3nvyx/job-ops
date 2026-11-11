#!/usr/bin/env python3
"""Resume review + cold-email helper: Grok (xAI API) roasts a tailored resume and drafts outreach.

Flow: Grok roasts the tailored resume for the role, Claude applies fact-checked fixes, Gemini
reviews too (Claude calls Gemini itself; `log` just records its reply), then Grok drafts a
short cold email that Claude saves as a Gmail draft. The resume text is redacted before it
leaves this machine (email, phone, street address, linkedin/github/site URLs, name).

Usage (python3 -I resume-review.py <command> ...):
  prep <app-folder> [--jd FILE]
      Extract + redact the resume text, pick the JD, write <app-folder>/review/
      {resume-redacted.txt, jd.txt, prompt.txt}. No API call.
  grok <app-folder> --round N [--extra FILE] [--max-tokens N]
      Re-run prep from the current PDF, send the prompt to Grok, save review/grok-round-N.md,
      append to review/review.md, print {"verdict": "APPROVE|REVISE|UNKNOWN", "reply": path}.
  log <app-folder> --reviewer gemini|grok|claude --round N --verdict APPROVE|REVISE|NOTE --file FILE
      Append a dated section to review/review.md (Gemini replies, Claude's rejected-suggestion notes).
  email <app-folder> --kind recruiter|hiring|followup --first-name NAME [--fix] [--max-tokens N]
      Draft a cold email with Grok, fill {first_name}/{company}, append the sign-off, write
      outreach-email.md (followup: outreach-followup.md) and lint it. If lint fails, re-run
      with --fix: the previous draft plus the lint issues go back to Grok once.
  email-lint <file>
      Check a drafted email (dashes, stock phrases, length, subject, placeholders, visa words).

The API key comes from the XAI_API_KEY env var, else XAI_API_KEY= in <repo>/.env. It is never
printed or written. XAI_MODEL overrides the model.

Exit codes: 0 ok; 1 bad input (missing folder/PDF/file); 2 email lint failed; 3 key missing;
4 auth/billing/quota problem (401, 402, 403, 429, or body mentioning credits/spending limit);
5 other API or network error.
Python 3.9 compatible (runs as /usr/bin/python3 -I), stdlib only.
"""
import argparse
import datetime
import glob
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(HERE)
ENV_PATH = os.path.join(REPO, ".env")
TEMPLATES = os.path.join(REPO, "templates")
PDF_TEXT_SWIFT = os.path.join(HERE, "pdf-text.swift")

API_URL = "https://api.x.ai/v1/chat/completions"
DEFAULT_MODEL = "grok-4.7"  # TODO confirm the exact model id; XAI_MODEL env overrides
# Reasoning model: hidden reasoning tokens may count against the cap, so keep it generous.
MAX_TOKENS = 8000
# Optional fallback when the xAI API fails: Cursor's agent CLI (your Cursor login) running Grok, read-only.
CURSOR_AGENT = os.path.expanduser("~/.local/bin/cursor-agent")
CURSOR_MODEL = os.environ.get("CURSOR_GROK_MODEL") or "grok-4.7-medium-fast"
TIMEOUT = 300
USER_AGENT = "job-search-kit-resume-review/1.0 (+python-urllib)"
JD_MAX_CHARS = 8000

# No links: saving a draft through the Gmail connector rewrites every URL or bare
# domain into visible google.com/url?q=... redirect text (seen on 2026-11-06).
# Filled in by install.sh from kit.env.
CANDIDATE_NAME = "<<NAME>>"
SIGNOFF = CANDIDATE_NAME + "\n" + "<<SIGNOFF_TAGLINE>>"
# Comma-separated handles and personal domains to redact before anything goes to Grok,
# e.g. "janedoe.dev,janedoe,jdoe-gh". LinkedIn/GitHub URLs, emails and phones are always redacted.
REDACT_TERMS = [t.strip() for t in "<<REDACT_TERMS>>".split(",") if t.strip() and not t.strip().startswith("<<")]

# Link-like text the Gmail connector would rewrite: URLs, www. and bare domains.
# Names that only look like domains (companies, frameworks) are allowed by name.
LINK_RE = re.compile(r"https?://|\bwww\.|\b[\w-]+\.(?:com|org|net|io|dev|app|me|co|ai|edu|gov|xyz|ly)\b", re.I)
# Add your own employer or project names that only look like domains (e.g. "acme.so").
LINK_ALLOW = {"id.me", "asp.net", "socket.io", "c3.ai"}

EXIT_BAD_INPUT, EXIT_LINT, EXIT_NO_KEY, EXIT_AUTH, EXIT_API = 1, 2, 3, 4, 5


class ReviewError(Exception):
    def __init__(self, code, message):
        Exception.__init__(self, message)
        self.code = code
        self.message = message


# ---------------------------------------------------------------- key loading

def parse_dotenv(text):
    """Parse KEY=VALUE lines: comments, `export `, single/double quotes."""
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if value[:1] in ("'", '"'):
            end = value.find(value[0], 1)
            value = value[1:end] if end != -1 else value[1:]
        else:
            value = re.split(r"\s+#", value, 1)[0].strip()
        out[key] = value
    return out


def load_key(environ=None, env_path=None):
    environ = os.environ if environ is None else environ
    key = (environ.get("XAI_API_KEY") or "").strip()
    if key:
        return check_key(key)
    path = ENV_PATH if env_path is None else env_path
    try:
        with open(path, encoding="utf-8") as f:
            key = parse_dotenv(f.read()).get("XAI_API_KEY", "").strip()
    except (OSError, UnicodeDecodeError):
        key = ""
    return check_key(key)


def check_key(key):
    if not key:
        raise ReviewError(EXIT_NO_KEY, "XAI_API_KEY not set (env var or .env)")
    if not re.match(r"^[\x21-\x7e]+$", key):
        raise ReviewError(EXIT_NO_KEY, "XAI_API_KEY looks malformed (spaces, line breaks or non-ASCII); re-paste it")
    return key


def scrub(text, key):
    """Remove the key from any text that might be printed."""
    if not key:
        return text
    return text.replace(key, "***").replace(repr(key)[1:-1], "***")


# ----------------------------------------------------------------- redaction

_STREET_WORDS = (
    "Street St Avenue Ave Road Rd Boulevard Blvd Drive Dr Lane Ln Way Court Ct "
    "Place Pl Circle Cir Terrace Ter Parkway Pkwy Highway Hwy"
).split()
_STREET_SUFFIX = "|".join(sorted({w for s in _STREET_WORDS for w in (s, s.upper())}, key=len, reverse=True))
STREET_RE = re.compile(
    r"\b\d{1,6}\s+(?:[A-Z0-9][\w.'-]*\s+){1,4}(?:" + _STREET_SUFFIX + r")\b\.?"
    r"(?:,?\s*(?:Apt|Unit|Suite|Ste|#)\.?\s*\w+)?"
)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE_RE = re.compile(r"(?<![\w])(?:\+?1[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]*\d{3}[\s.-]*\d{4}(?!\d)")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/[^\s|,;)>\]]*", re.I)
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[^\s|,;)>\]]*", re.I)
_DOMAINS = [t for t in REDACT_TERMS if "." in t]
_HANDLES = [t for t in REDACT_TERMS if "." not in t]
SITE_RE = (re.compile(r"(?:https?://)?(?:www\.)?(?:" + "|".join(map(re.escape, _DOMAINS)) + r")[^\s|,;)>\]]*", re.I)
           if _DOMAINS else None)
HANDLE_RE = (re.compile(r"@?\b(?:" + "|".join(map(re.escape, _HANDLES)) + r")\b", re.I) if _HANDLES else None)
NAME_RE = re.compile(r"\b" + r"\s+".join(map(re.escape, CANDIDATE_NAME.split())) + r"\b", re.I)


def redact(text):
    text = LINKEDIN_RE.sub("[linkedin]", text)
    text = GITHUB_RE.sub("[github]", text)
    if SITE_RE:
        text = SITE_RE.sub("[website]", text)
    text = EMAIL_RE.sub("[email]", text)
    if HANDLE_RE:
        text = HANDLE_RE.sub("[handle]", text)
    text = PHONE_RE.sub("[phone]", text)
    text = STREET_RE.sub("[address]", text)
    text = NAME_RE.sub("[Candidate]", text)
    return text


# ------------------------------------------------------------ job + resume IO

def need_folder(folder):
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder):
        raise ReviewError(EXIT_BAD_INPUT, "not a folder: " + folder)
    return folder


def read_text(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError as e:
        raise ReviewError(EXIT_BAD_INPUT, "cannot read %s: %s" % (path, e.strerror))


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def parse_job(folder):
    """Return (company, role, evaluation_report_path or None) from job.md."""
    text = read_text(os.path.join(folder, "job.md"))
    m = re.search(r"^#\s+(.+?):\s+(.+?)\s*$", text, re.M)
    if not m:
        raise ReviewError(EXIT_BAD_INPUT, "job.md has no '# Company: Role' title")
    rep = re.search(r"^\s*-\s*\*\*Evaluation report:\*\*\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip(), m.group(2).strip(), (rep.group(1) if rep else None)


def find_pdf(folder):
    pdfs = sorted(glob.glob(os.path.join(folder, "<<CV_PREFIX>>-*.pdf")))
    if not pdfs:
        raise ReviewError(EXIT_BAD_INPUT, "no <<CV_PREFIX>>-*.pdf in " + folder)
    return pdfs[0]


def extract_pdf_text(pdf):
    """PDF text via scripts/pdf-text.swift (PDFKit)."""
    swift = shutil.which("swift") or "/usr/bin/swift"
    try:
        r = subprocess.run([swift, PDF_TEXT_SWIFT, pdf], capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.SubprocessError) as e:
        raise ReviewError(EXIT_BAD_INPUT, "pdf text extraction failed: %s" % e)
    if r.returncode != 0 or not r.stdout.strip():
        raise ReviewError(EXIT_BAD_INPUT, "pdf text extraction failed for " + pdf)
    return r.stdout


def clean_text(text):
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def jd_from_report(text):
    """The report ends with the archived JD; use that section when present, else the whole file."""
    m = re.search(r"^##\s+Job Description[^\n]*\n", text, re.M)
    if m:
        text = text[m.end():]
    return clean_text(text)[:JD_MAX_CHARS]


def get_jd(folder, jd_file, report):
    if jd_file:
        return clean_text(read_text(os.path.expanduser(jd_file)))[:JD_MAX_CHARS]
    if not report:
        raise ReviewError(EXIT_BAD_INPUT, "no --jd given and job.md has no Evaluation report path")
    return jd_from_report(read_text(os.path.expanduser(report)))


def fill_template(name, values):
    """Replace {{KEY}} in one pass so inserted text is never re-scanned."""
    tpl = read_text(os.path.join(TEMPLATES, name))
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), m.group(0)), tpl)


def build_context(folder, jd_file=None, reuse_jd=False):
    """Return dict(company, role, resume, jd) with redacted resume + JD."""
    company, role, report = parse_job(folder)
    resume = redact(clean_text(extract_pdf_text(find_pdf(folder))))
    jd_path = os.path.join(folder, "review", "jd.txt")
    if reuse_jd and not jd_file and os.path.exists(jd_path):
        jd = read_text(jd_path)
    else:
        jd = redact(get_jd(folder, jd_file, report))
    return {"company": company, "role": role, "resume": resume, "jd": jd}


def prep(folder, jd_file=None, reuse_jd=False):
    ctx = build_context(folder, jd_file, reuse_jd)
    rdir = os.path.join(folder, "review")
    write_text(os.path.join(rdir, "resume-redacted.txt"), ctx["resume"] + "\n")
    write_text(os.path.join(rdir, "jd.txt"), ctx["jd"] + "\n")
    prompt = fill_template("review-prompt.md", {
        "ROLE": ctx["role"], "COMPANY": ctx["company"], "JD": ctx["jd"], "RESUME": ctx["resume"],
    })
    write_text(os.path.join(rdir, "prompt.txt"), prompt)
    ctx["prompt"] = prompt
    return ctx


# ------------------------------------------------------------------ API call

def classify_http_error(status, body):
    if status in (401, 402, 403, 429) or re.search(r"credit|spending limit|billing|api key|unauthori[sz]ed|permission", body, re.I):
        return EXIT_AUTH
    return EXIT_API


def call_grok(prompt, key, max_tokens=MAX_TOKENS):
    model = os.environ.get("XAI_MODEL") or DEFAULT_MODEL
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            body = ""
        body = scrub(body, key)
        snippet = re.sub(r"\s+", " ", body).strip()[:160]
        raise ReviewError(classify_http_error(e.code, body), "xAI API HTTP %s: %s" % (e.code, snippet))
    except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as e:
        raise ReviewError(EXIT_API, scrub("network error: %s" % e, key))
    try:
        data = json.loads(raw)
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content") or ""
        finish = choice.get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError):
        raise ReviewError(EXIT_API, "unexpected API response shape")
    if not content.strip():
        if finish == "length":
            raise ReviewError(EXIT_API, "output cap too small: reasoning used all %d tokens, "
                                        "retry with a larger --max-tokens" % max_tokens)
        raise ReviewError(EXIT_API, "empty reply from API (finish_reason=%s)" % finish)
    if finish == "length":
        sys.stderr.write("warning: reply hit the output cap and may be cut off\n")
    return content


def call_cursor(prompt):
    """Ask Grok through cursor-agent in read-only ask mode, from an empty folder."""
    if not os.path.exists(CURSOR_AGENT):
        raise ReviewError(EXIT_API, "cursor-agent not installed")
    with tempfile.TemporaryDirectory() as cwd:
        try:
            out = subprocess.run(
                # --trust only covers the fresh empty temp folder; --sandbox keeps it boxed in.
                [CURSOR_AGENT, "-p", "--mode", "ask", "--trust", "--sandbox", "enabled",
                 "--output-format", "text", "--model", CURSOR_MODEL, prompt],
                cwd=cwd, capture_output=True, text=True, timeout=TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ReviewError(EXIT_API, "cursor-agent failed: %s" % e.__class__.__name__)
    if out.returncode != 0 or not out.stdout.strip():
        raise ReviewError(EXIT_API, "cursor-agent exit %d: %s" % (
            out.returncode, re.sub(r"\s+", " ", out.stderr).strip()[:160]))
    return out.stdout


def ask_grok(prompt, max_tokens=MAX_TOKENS):
    """xAI API first; on a missing key, auth/billing or API error, Grok via cursor-agent."""
    try:
        return call_grok(prompt, load_key(), max_tokens)
    except ReviewError as api_err:
        if api_err.code not in (EXIT_NO_KEY, EXIT_AUTH, EXIT_API):
            raise
        sys.stderr.write("xAI API unavailable (%s); trying Grok via cursor-agent\n" % api_err)
        try:
            return call_cursor(prompt)
        except ReviewError as cursor_err:
            sys.stderr.write("cursor-agent fallback failed too: %s\n" % cursor_err)
            raise api_err


# ------------------------------------------------------------------- verdicts

# A verdict line holds nothing else, so "VERDICT: APPROVE only after fixes" does not count.
VERDICT_RE = re.compile(r"^[\s>*_#`-]*verdict\W*(approve|revise)[\s*_`.!]*$", re.I | re.M)


def parse_verdict(reply):
    found = VERDICT_RE.findall(reply)
    return found[-1].upper() if found else "UNKNOWN"


def append_review(folder, reviewer, rnd, verdict, text):
    path = os.path.join(folder, "review", "review.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as f:
        if new:
            f.write("# Review log\n")
        f.write("\n## %s | %s | round %s | %s\n\n%s\n" % (
            datetime.date.today().isoformat(), reviewer, rnd, verdict, text.strip()))
    return path


# --------------------------------------------------------------------- email

def split_signoff(text):
    """Return (before_signoff, had_signoff)."""
    ms = list(re.finditer(r"^" + re.escape(CANDIDATE_NAME) + r"[ \t]*$", text, re.M))
    if ms:
        return text[:ms[-1].start()].rstrip(), True
    return text.rstrip(), False


def parse_email(text):
    """Return (subject or '', body without subject line and sign-off)."""
    text, _ = split_signoff(text)
    lines = text.strip().splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^[\s*_#>`]*subject\s*:\s*(.*)$", line, re.I)
        if m:
            subject = m.group(1).strip().strip("*_`").strip()
            return subject, "\n".join(lines[i + 1:]).strip()
        if line.strip() and not line.strip().startswith("```"):
            break
    return "", "\n".join(lines).strip()


def parse_reply(reply):
    """Grok reply -> (subject, body); drops code fences."""
    reply = re.sub(r"^```\w*\s*$", "", reply, flags=re.M)
    return parse_email(reply)


def fill_placeholders(text, first_name, company):
    text = re.sub(r"\{\s*first[_ ]?name\s*\}", lambda m: first_name, text, flags=re.I)
    return re.sub(r"\{\s*company\s*\}", lambda m: company, text, flags=re.I)


def compose_email(subject, body, first_name, company):
    subject = fill_placeholders(subject, first_name, company)
    body = fill_placeholders(body, first_name, company)
    return "Subject: %s\n\n%s\n\n%s\n" % (subject, body.strip(), SIGNOFF)


BANNED_PHRASES = [
    "hope this finds you well", "hope this email finds you", "passionate", "leverage",
    "excited to apply", "i am writing to", "i'm reaching out to express", "synergy", "delve", "thrilled",
]
MAX_BODY_WORDS = 120
MAX_SUBJECT_WORDS = 8


def lint_text(text):
    """Return a list of issue strings (empty = clean)."""
    issues = []
    subject, body = parse_email(text)
    whole = subject + "\n" + body
    if "—" in whole:
        issues.append("em dash found")
    if "–" in whole:
        issues.append("en dash found")
    if "―" in whole or "−" in whole:
        issues.append("other dash character found")
    if " - " in whole:
        issues.append("spaced hyphen ' - ' found")
    if "--" in whole:
        issues.append("double hyphen found")
    low = whole.lower()
    for phrase in BANNED_PHRASES:
        if phrase in low:
            issues.append("stock phrase: '%s'" % phrase)
    if not body.strip():
        issues.append("body missing")
    elif not re.match(r"\s*(hi|hey|hello)\b", body, re.I):
        issues.append("body should start with a greeting (Hi ...)")
    words = len(body.split())
    if words > MAX_BODY_WORDS:
        issues.append("body is %d words (max %d)" % (words, MAX_BODY_WORDS))
    if not subject:
        issues.append("subject missing")
    elif len(subject.split()) > MAX_SUBJECT_WORDS:
        issues.append("subject is %d words (max %d)" % (len(subject.split()), MAX_SUBJECT_WORDS))
    for m in re.finditer(r"\{[^{}]*\}|\[[^\[\]]*\]", whole):
        issues.append("leftover placeholder: %s" % m.group(0))
    if re.search(r"\bF-?1\b", whole, re.I) or re.search(r"\bOPT\b", whole):
        issues.append("mentions F-1/OPT")
    if re.search(r"\bvisa\b", whole, re.I):
        issues.append("mentions visa")
    # Visa sponsorship only: "raised $20,000 in sponsorship" (event sponsors) is fine.
    if re.search(r"\bH-?1B\b|work authori[sz]ation|(visa|immigration) sponsor|sponsor(ship)? (for|of) (a |my )?(visa|work)|\bsponsor me\b|(need|needs|require|requires|requiring)\s+(visa\s+)?sponsorship|authori[sz]ed to work|international student|\bF1\b", whole, re.I):
        issues.append("mentions sponsorship")
    for m in LINK_RE.finditer(whole):
        if m.group(0).lower() in LINK_ALLOW:
            continue
        found = whole[m.start():m.end() + 40].split()[0].rstrip(".,;:!?)")
        issues.append("link or domain found (Gmail rewrites it into a redirect; describe it in words): %s" % found)
    return issues


def fix_prompt(base_prompt, draft, issues):
    return (
        base_prompt
        + "\n\n=== PREVIOUS DRAFT (needs fixing) ===\n" + draft.strip()
        + "\n\n=== LINT ISSUES TO FIX ===\n" + "\n".join("- " + i for i in issues)
        + "\n\nRewrite the email so every issue above is gone and everything else still follows "
          "the rules. Keep the same voice and project. Keep `Hi {first_name},` and the {company} "
          "placeholder. Output only the Subject line, a blank line, and the body.\n"
    )


def email_filename(kind):
    return "outreach-followup.md" if kind == "followup" else "outreach-email.md"


def run_email(folder, kind, first_name, fix, max_tokens):
    out_path = os.path.join(folder, email_filename(kind))
    ctx = build_context(folder, reuse_jd=True)
    prompt = fill_template("outreach-prompt.md", {
        "KIND": kind, "ROLE": ctx["role"], "COMPANY": ctx["company"],
        "JD": ctx["jd"], "RESUME": ctx["resume"],
    })
    if fix:
        if not os.path.exists(out_path):
            raise ReviewError(EXIT_BAD_INPUT, "--fix needs an existing draft: " + out_path)
        prev = read_text(out_path)
        issues = lint_text(prev)
        if not issues:
            sys.stderr.write("previous draft already passes lint; nothing to fix\n")
            return out_path, []
        subject, body = parse_email(prev)
        prompt = fix_prompt(prompt, "Subject: %s\n\n%s" % (subject, body), issues)
    reply = ask_grok(prompt, max_tokens)
    subject, body = parse_reply(reply)
    final = compose_email(subject, body, first_name, ctx["company"])
    write_text(out_path, final)
    return out_path, lint_text(final)


# ------------------------------------------------------------------ commands

def cmd_prep(a):
    folder = need_folder(a.folder)
    prep(folder, a.jd)
    print(os.path.join(folder, "review", "prompt.txt"))
    return 0


def cmd_grok(a):
    folder = need_folder(a.folder)
    ctx = prep(folder, reuse_jd=True)
    prompt = ctx["prompt"]
    if a.extra:
        prompt += "\n\n=== NOTE FOR THIS ROUND ===\n" + redact(clean_text(read_text(os.path.expanduser(a.extra)))) + "\n"
    reply = ask_grok(prompt, a.max_tokens)
    verdict = parse_verdict(reply)
    path = os.path.join(folder, "review", "grok-round-%d.md" % a.round)
    write_text(path, reply.strip() + "\n")
    append_review(folder, "grok", a.round, verdict, reply)
    print(json.dumps({"verdict": verdict, "reply": path}))
    return 0


def cmd_log(a):
    folder = need_folder(a.folder)
    text = read_text(os.path.expanduser(a.file))
    append_review(folder, a.reviewer, a.round, a.verdict, text)
    print(os.path.join(folder, "review", "review.md"))
    return 0


def cmd_email(a):
    folder = need_folder(a.folder)
    path, issues = run_email(folder, a.kind, a.first_name, a.fix, a.max_tokens)
    if issues:
        for i in issues:
            print("LINT: " + i)
        sys.stderr.write("email lint failed (%d issue%s)%s\n" % (
            len(issues), "" if len(issues) == 1 else "s", "" if a.fix else "; re-run with --fix"))
        return EXIT_LINT
    print(path)
    return 0


def cmd_email_lint(a):
    issues = lint_text(read_text(os.path.expanduser(a.file)))
    for i in issues:
        print("LINT: " + i)
    if issues:
        return EXIT_LINT
    print("ok")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description="Grok resume review and outreach helper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("prep", help="redact resume, pick JD, write review/ files")
    p.add_argument("folder")
    p.add_argument("--jd")
    p.set_defaults(func=cmd_prep)

    p = sub.add_parser("grok", help="send review prompt to Grok")
    p.add_argument("folder")
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--extra")
    p.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    p.set_defaults(func=cmd_grok)

    p = sub.add_parser("log", help="append a reviewer note to review/review.md")
    p.add_argument("folder")
    p.add_argument("--reviewer", required=True, choices=["gemini", "grok", "claude"])
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--verdict", required=True, choices=["APPROVE", "REVISE", "NOTE"])
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_log)

    p = sub.add_parser("email", help="draft a cold email with Grok")
    p.add_argument("folder")
    p.add_argument("--kind", required=True, choices=["recruiter", "hiring", "followup"])
    p.add_argument("--first-name", required=True)
    p.add_argument("--fix", action="store_true")
    p.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    p.set_defaults(func=cmd_email)

    p = sub.add_parser("email-lint", help="lint a drafted email")
    p.add_argument("file")
    p.set_defaults(func=cmd_email_lint)
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ReviewError as e:
        sys.stderr.write("error: %s\n" % e.message)
        return e.code


if __name__ == "__main__":
    sys.exit(main())
