---
name: outreach-reply-check
description: Every 2 hours, 9 AM to 9 PM. Check Gmail for sent outreach and recruiter replies for jobs in the sheet; update the sheet and push an alert on replies.
---

Quick, read-only Gmail check for <<FIRST_NAME>>'s job outreach. No evaluations, no drafts, no contact lookups.

## Context
Google Sheet `<<SHEET_ID>>`, tab `<<SHEET_TAB>>`. Row 2 holds headers; data starts at row 3. Columns:
- B Company, C Role
- BP Contact LinkedIn / Email (the better contact)
- BQ Outreach Sent, BR Follow-up Date, BZ Notes
- CA Alt Contact (second contact, same format)

If a letter looks wrong, find the column by its row-2 header.

## Steps
1. Read `<<SHEET_TAB>>!B3:CA`. Collect every email address in BP or CA (ignore "not revealed" and "none found").
2. If there are none, end with one line: "No outreach contacts yet."
3. For each address, using Gmail `search_threads` only:
   - **Sent:** if BQ is empty and `in:sent to:<email>` finds a message, set BQ = that message's date (`YYYY-MM-DD`) and BR = that date + 7 days.
   - **Reply:** if `from:<email>` finds a message dated after BQ, and BZ doesn't already contain `REPLIED`, append `REPLIED <date>` to BZ (keep what was there).
4. If there's a new reply, send one push notification (PushNotification tool, if available) under 200 characters, e.g. "Acme recruiter replied! Check Gmail." End with a one-line summary.

## Rules
- Read Gmail only. Never send, reply, forward, draft, label, archive or delete anything.
- In the sheet, write only BQ, BR and BZ, and only as described.
- If the Sheets or Gmail connector is unavailable, say so in one line and stop.
