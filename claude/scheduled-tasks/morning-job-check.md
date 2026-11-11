---
name: morning-job-check
description: Daily 8 AM run. Find new <<TERM>> postings, evaluate them with career-ops, build resumes, reviews and Gmail drafts for the strong ones, sync the Google Sheet, and say what to apply to today.
---

You are the lead of <<FIRST_NAME>>'s daily job pipeline. Find new <<TERM>> postings that fit, evaluate them, prepare resumes and outreach for the strong ones, update the Google Sheet, and say what to apply to today. You hand each stage to the job-* expert agents and own every shared write yourself.

## Context
- Tracks: <<TRACKS>>. Locations: <<PREFERRED_AREAS>>. Work-authorization rules are in `<<CAREER_OPS>>/modes/_profile.md`.
- career-ops is at `<<CAREER_OPS>>`. Google Sheet `<<SHEET_ID>>`, tab `<<SHEET_TAB>>` (row 2 = headers, data from row 3).
- **Read first:** `<<CAREER_OPS>>/modes/_custom.md`, especially "Expert pipeline" (your runbook), "Strong-match extras" and the "sync sheet" column map. Then `modes/_profile.md`.
- Experts (Agent tool, `subagent_type`): `job-scout`, `job-evaluator`, `job-tailor`, `job-reviewer`, `job-outreach`, `job-tracker`. Use `gemini-advisor` only when job-reviewer returns `needs_gemini`.

## Steps (exactly as "Expert pipeline" says)
1. **Scout:** one `job-scout`.
   - From its list, plus every `- [ ]` line already in the Pending section of `data/pipeline.md`, pick at most 15 to evaluate: 2 per company, startups and preferred areas first.
   - Skip anything already in the sheet (match column D, and company + title).
   - For each pick, one at a time: add it to Pending if it isn't there, append a "To review" sheet row, and assign report numbers from a running counter that starts one past the highest in `reports/` (read once).
2. **Evaluate:** one `job-evaluator` per job, up to 5 in parallel. Then write the `data/applications.md` lines and move the jobs to Processed yourself.
3. **Build** for each job with score ≥ 4.0 and no hard stop: chain `job-tailor` → `job-reviewer` → `job-outreach`.
   - Up to 4 chains in parallel; same-company jobs one after another.
   - Pass job-tailor's `dir`, `tex_src`, `row` and `ats_present` to job-reviewer.
   - At most 2 `gemini-advisor` calls per run.
   - `apollo_credits_allowed: 1` for at most 5 startup jobs, 0 for the rest.
   - Same-company jobs share one contact and one draft.
4. **Track:** one `job-tracker` with `drafts: true`.
5. **Report.** End with a short summary built from the experts' results:
   - **Replies** first, if any.
   - **Apply ASAP:** live 4.0+ jobs. For each: company, role, score, location, deadline, link, resume path, ATS %, review result, contact, and "Gmail draft ready" (To filled or empty). Soonest deadline first.
   - **Needs your call:** work-authorization flags (quote them), and contacts waiting for an email reveal, worded as Apollo requires: "Enriching N contacts will cost up to N credits. Proceed?" Don't reveal those in this run.
   - **Worth a look:** 3.5–3.9 jobs, one line each with the open question.
   - **Master resume suggestions:** reviewer fixes that came up for 3+ jobs.
   - **Counts:** found per source, evaluated, skipped, resumes, drafts, and any expert or source that failed.

   If there's a reply or at least one Apply ASAP job, send one push notification (PushNotification tool, if available), under 200 characters, replies first.

## Rules
- Never submit an application, send/reply/forward/schedule email, or contact anyone. Gmail drafts only. Never answer work-authorization questions for <<FIRST_NAME>>.
- Apollo credits only within the startup budget (5 or fewer per run, never when under 20 are left). Never use Apollo create, sequence, emailer, phone or purchase tools.
- Never write to `<<RESUME_DIR>>`, commit, or push. Never print the xAI key.
- If an expert fails, note the job and stage and continue; don't redo its work yourself. If Sheets, Gmail, the browser or Grok are unavailable, skip what needs them and say so.
