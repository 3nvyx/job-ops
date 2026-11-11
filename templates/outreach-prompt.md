Write ONE cold email for a candidate applying to the {{ROLE}} role at {{COMPANY}}. Email type: {{KIND}}.

VOICE
The candidate is <<ABOUT_YOU>>, writing this themselves. Casual, warm, slightly funny, refreshing, never salesy, never corporate. It should sound like a sharp student typing a quick note, not a template. Lowercase-ish is fine for the subject.

CONTENT RULES
- Name the exact role ({{ROLE}}) and ONE project from the resume that is most relevant to the job description. Say what it did in a few plain words. Use only facts that appear in the resume text below. Do not invent anything.
- Under 110 words in the body. Subject of 8 words or fewer.
- Start the body with exactly: Hi {first_name},
- Write the company name as the literal placeholder {company} wherever you mention it. Keep the curly braces. Do not fill in either placeholder.
- No dashes of any kind: no long dash, no short dash, no hyphen used as punctuation, no double hyphen. Use commas, periods, or new sentences.
- Do not use any of these phrases or words: "hope this finds you well", "hope this email finds you", "passionate", "leverage", "excited to apply", "I am writing to", "I'm reaching out to express", "synergy", "delve", "thrilled".
- Never mention visas, F-1, OPT, work authorization, or sponsorship.
- No sign-off and no name at the end. A signature is added later. End on the ask or a short friendly line.
- No links, URLs, or domain names (write "my hackathon site", not myhackathon.com).
- No square brackets and no other curly-brace placeholders besides {first_name} and {company}.
- Personal details in the resume are redacted (shown as [Candidate], [email], and so on). Ignore that and never copy those tokens.

THE ASK, depending on the email type
- recruiter: they just applied. Ask them to confirm the application came through. Keep it light.
- hiring: they have applied. Ask one short, genuine question about the team's culture or what makes someone a great fit there. Do not ask for a job or a referral.
- followup: 2 to 3 lines only. A light nudge on the earlier note, then the same ask as before (confirm the application came through). No guilt, no pressure.

OUTPUT FORMAT (nothing else, no commentary, no code fences):
Subject: <subject line>

<body>

=== JOB DESCRIPTION ({{COMPANY}}: {{ROLE}}) ===
{{JD}}

=== RESUME ===
{{RESUME}}
