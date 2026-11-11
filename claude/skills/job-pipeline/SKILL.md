---
name: job-pipeline
description: Run a pasted job link (or several) through <<FIRST_NAME>>'s job pipeline with the job-* expert agents (evaluate → tailored resume → one Grok review → recruiter contact + Gmail draft) and add it to the Google Sheet. Use when <<FIRST_NAME>> pastes a job posting URL and wants to apply, or types /job-pipeline <url>.
---

# Job pipeline (pasted links)

You are the lead. Follow "Expert pipeline" in `<<CAREER_OPS>>/modes/_custom.md`, starting at step 2, for the link(s) <<FIRST_NAME>> gave you. Read that section and the "sync sheet" column map first.

1. **Set up (you, not an expert):**
   - Skip a link already in the sheet (`<<SHEET_TAB>>!D3:D`) and say which row it's in.
   - Otherwise append a "To review" row (`<<SHEET_TAB>>!A{next}:L{next}`, sheet `<<SHEET_ID>>`).
   - Reserve report numbers: read the highest number in `<<CAREER_OPS>>/reports/` once, then count up from it, one per link.
   - If the link is in the Pending section of `data/pipeline.md`, move it after evaluation.
2. **Evaluate:** one `job-evaluator` per link, in parallel. Then add the tracker line to `<<CAREER_OPS>>/data/applications.md` and move the link to Processed in `data/pipeline.md`.
3. **Decide:**
   - `hard_stop` (citizenship, clearance, ITAR) → stop. Give <<FIRST_NAME>> the exact quote and mark the row Skipped.
   - 4.0+ → continue.
   - Below 4.0, or a work-authorization flag → give the score and the reason in two lines, and ask whether to continue.
4. **Build:** `job-tailor` → `job-reviewer` → `job-outreach`, one chain per link. Chains run in parallel, except same-company links, which go one after another. Pass job-tailor's `dir`, `tex_src`, `row` and `ats_present` to job-reviewer.
   - `apollo_credits_allowed: 1` only for a startup.
   - Same-company links share one contact and one draft.
   - If job-reviewer returns `needs_gemini`, call `gemini-advisor` once (at most 2 per run), then rerun `job-reviewer` with its reply. If that's not possible, note `Review: skipped (no reviewer)`.
   - If <<FIRST_NAME>> asks for the resume only, stop after job-reviewer.
5. **Report** in a few lines per job:
   - score and any flag;
   - resume path, ATS % and parse check;
   - what the review changed;
   - contact and Gmail draft subject (unsent; To is empty unless the email is known);
   - anything <<FIRST_NAME>> must decide (work-auth answers, revealing an email for 1 credit).

Never submit applications, send email, answer work-authorization questions for <<FIRST_NAME>>, or write to `<<RESUME_DIR>>`.
