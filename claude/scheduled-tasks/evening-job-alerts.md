---
name: evening-job-alerts
description: Light 6 PM check. Warn about strong-fit jobs closing within 48 hours and new postings at priority companies, track outreach, and queue new jobs for the morning run. No evaluations.
---

Run a light evening check on <<FIRST_NAME>>'s <<TERM>> job search. Do **not** run evaluations, generate resumes or cover letters, run the resume review, look up contacts, or research companies tonight. This check only finds urgent items, tracks outreach emails, puts every queued job into the sheet, and queues new jobs for the morning run.

## Context
- career-ops is at `<<CAREER_OPS>>`; work from that folder. Google Sheet `<<SHEET_ID>>`, tab `<<SHEET_TAB>>`. Row 1 holds section labels, row 2 the headers, and data starts at row 3. If a column letter ever looks wrong, find the column by its row-2 header.
- Columns used here:
  - B Company, C Role, D Job Link, E Fit Score, G Status, H Next Action
  - J Deadline, K Date Added, L Posted Date, N Track, P Term, V Location
  - BE Application Portal, BF Tailored Resume, BK Date Applied
  - BN Contact Name, BP Contact LinkedIn / Email, BQ Outreach Sent, BR Follow-up Date, BZ Notes, CA Alt Contact
  - Columns M, S and BL are formulas; never write to them.
- Read "## Priority Companies" and "## Strong-match extras" (section 4, Gmail tracking) in `<<CAREER_OPS>>/modes/_custom.md` first.

## Steps
1. **Deadline check.** Read `<<SHEET_TAB>>!A3:CA`. Flag every row where all of these hold:
   - Fit Score is 4.0 or higher;
   - Status is not Applied, Assessment, Interviewing, Offer, Accepted, Rejected, Withdrawn, Skipped or Closed;
   - Date Applied is empty;
   - Deadline falls within the next 48 hours (today counts).
2. **Gmail tracking**, exactly as section 4 of the Strong-match extras says (or run one `job-tracker` with `drafts: true`). Never send, reply or forward.
3. **New postings** (no AI evaluation):
   - `python3 -I <<DATA_REPO>>/scripts/new-internships.py --days 1 --json`
   - `python3 -I <<DATA_REPO>>/scripts/yc-internships.py --json`
   - `node scan.mjs --quiet` (it adds new matches to data/pipeline.md itself).
4. **Queue for the morning.** Append each new posting from step 3's scripts that isn't obviously disqualified (MBA/PhD/MS-only, citizenship or clearance required, wrong term, outside the US) to the Pending section of `data/pipeline.md` as `- [ ] {url} | {company} | {title} | {locations} | posted: {date}`.
5. **Sync every pending job into the sheet.** Read `<<SHEET_TAB>>!D3:D`. For **every** `- [ ]` line in Pending whose URL is not in column D yet, append a row:
   - B, C, D; G = "To review"; H = "Evaluate in the morning run"; K = today; L = posted date;
   - N = the track that fits the title; P = "<<TERM>>"; V = locations; BE = portal;
   - `null` for every other column.

   Never add a job that's already in the sheet.
6. **Priority matches.** Flag any newly added job whose company is on the priority list (case-insensitive; ignore suffixes like Inc/Labs/Group).
7. **Report and notify.**
   - If step 2 found a reply, or steps 1 or 6 flagged anything, send one push notification (PushNotification tool, if available), under 200 characters, replies first.
   - Then write a short summary: replies; follow-up drafts made; deadline jobs (company, role, score, deadline, link, resume path); priority matches; and how many rows were added for the morning run.
   - If nothing was flagged, end with one line, e.g. "Nothing urgent; added 4 jobs to the sheet for the morning run."

## Rules
- Never submit an application, send/reply/forward/schedule an email or message, or contact anyone. Gmail drafts are fine. Never commit or push. Never write to `<<RESUME_DIR>>`. Never spend Apollo credits.
- Don't change existing sheet rows except to append new ones and fill BQ, BR and Notes for outreach tracking.
- If the Sheets connector is unavailable, still run steps 3–4 and say the rest couldn't run. If Gmail is unavailable, skip step 2 and say so.
