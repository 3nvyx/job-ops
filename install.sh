#!/usr/bin/env bash
# Fill the kit's <<PLACEHOLDERS>> from kit.env, then (with --apply) copy the files into place.
#
#   ./install.sh            preview: renders everything into ./build and lists what would be copied
#   ./install.sh --apply    copies files that don't exist yet; existing ones are skipped
#   ./install.sh --apply --force   also replaces existing files (each one is backed up first to <file>.bak, or a dated .bak if that exists)
set -euo pipefail
cd "$(dirname "$0")"

APPLY=0; FORCE=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --force) FORCE=1 ;;
    *) echo "unknown option: $arg" >&2; exit 1 ;;
  esac
done
[ -f kit.env ] || { echo "Copy kit.env.example to kit.env and fill it in first." >&2; exit 1; }

rm -rf build
python3 -I - <<'PY'
import os, re, shlex, shutil, sys

def load(path):
    vals = {}
    for n, raw in enumerate(open(path, encoding="utf-8"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            sys.exit("kit.env line %d: expected KEY=value" % n)
        k, v = line.split("=", 1)
        v = v.strip()
        if v[:1] in "\"'" and v[-1:] == v[:1]:
            v = v[1:-1]
        if '"' in v or "\\" in v:
            sys.exit("kit.env %s: no quotes or backslashes inside values" % k)
        vals[k.strip()] = v
    return vals

vals = load("kit.env")
for k in ("CAREER_OPS", "DATA_REPO", "MASTER_TEX", "RESUME_DIR"):
    if k in vals:
        vals[k] = os.path.abspath(os.path.expanduser(os.path.expandvars(vals[k])))
need = ["NAME", "FIRST_NAME", "CV_PREFIX", "SIGNOFF_TAGLINE", "ABOUT_YOU", "TERM", "TRACKS",
        "PREFERRED_AREAS", "CAREER_OPS", "DATA_REPO", "MASTER_TEX", "RESUME_DIR", "SHEET_ID", "SHEET_TAB"]
missing = [k for k in need if not vals.get(k)]
if missing:
    sys.exit("kit.env is missing: " + ", ".join(missing))
vals.setdefault("REDACT_TERMS", "")
unknown = sorted(set(vals) - set(need) - {"REDACT_TERMS"})
if unknown:
    print("WARNING: kit.env has keys the kit doesn't use (typo?): " + ", ".join(unknown))
if not vals["REDACT_TERMS"].strip():
    print("WARNING: REDACT_TERMS is empty. Your handles and personal site will NOT be redacted "
          "before your resume goes to Grok (name, email, phone, address, LinkedIn and GitHub still are).")

PH = re.compile(r"<<([A-Z_]+)>>")
left = []
for src in ("claude", "career-ops", "scripts", "templates"):
    for root, _, files in os.walk(src):
        for f in files:
            s = os.path.join(root, f)
            d = os.path.join("build", s)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            text = open(s, encoding="utf-8").read()
            text = PH.sub(lambda m: vals.get(m.group(1), m.group(0)), text)
            left += ["%s: %s" % (s, m) for m in set(PH.findall(text))]
            with open(d, "w", encoding="utf-8") as out:
                out.write(text)
            shutil.copymode(s, d)
if left:
    sys.exit("unfilled placeholders:\n  " + "\n  ".join(sorted(left)))
with open("build/.paths", "w") as f:
    f.write("CAREER_OPS=%s\nDATA_REPO=%s\n" % (shlex.quote(vals["CAREER_OPS"]), shlex.quote(vals["DATA_REPO"])))
PY

# shellcheck disable=SC1091
. build/.paths
echo "Rendered into ./build"

place() {  # place <src> <dest>
  local src="$1" dest="$2"
  if [ -e "$dest" ] && [ "$FORCE" -eq 0 ]; then
    echo "  skip (exists)  $dest"; return
  fi
  if [ "$APPLY" -eq 0 ]; then
    if [ -e "$dest" ]; then echo "  would replace  $dest"; else echo "  would create   $dest"; fi
    return
  fi
  mkdir -p "$(dirname "$dest")"
  if [ -e "$dest" ]; then
    local bak="$dest.bak"
    [ -e "$bak" ] && bak="$dest.bak.$(date +%Y%m%d-%H%M%S)"
    cp -p "$dest" "$bak"
  fi
  cp -p "$src" "$dest"
  echo "  wrote          $dest"
}

echo "Claude agents and skill:"
for f in build/claude/agents/*.md; do place "$f" "$HOME/.claude/agents/$(basename "$f")"; done
place build/claude/skills/job-pipeline/SKILL.md "$HOME/.claude/skills/job-pipeline/SKILL.md"
echo "career-ops house rules:"
place build/career-ops/modes/_custom.md "$CAREER_OPS/modes/_custom.md"
echo "Scripts and prompt templates:"
for f in build/scripts/* build/templates/*; do place "$f" "$DATA_REPO/${f#build/}"; done

if [ "$APPLY" -eq 1 ] && [ ! -e "$DATA_REPO/.env" ]; then
  mkdir -p "$DATA_REPO"
  ( umask 077; printf 'XAI_API_KEY=\n' > "$DATA_REPO/.env" )
  echo "  created        $DATA_REPO/.env (paste your xAI key after XAI_API_KEY=)"
fi

echo
echo "Scheduled-task prompts are in ./build/claude/scheduled-tasks (see README, step 7)."
[ "$APPLY" -eq 1 ] || echo "This was a preview. Run ./install.sh --apply to copy the files."
