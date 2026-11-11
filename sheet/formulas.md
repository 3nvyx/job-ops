# Sheet formulas

Make a Google Sheet with one tab named `Jobs`. Paste `jobs-headers.tsv` into cell A1: row 1 holds the section labels, row 2 the column headers (A to CA). Data starts at row 3.

Then put these three formulas in row 3. Each fills its whole column, so the agents always send `null` for M, S and BL.

| Cell | Column | Formula |
|---|---|---|
| M3 | Recruiter Contact | `=ARRAYFORMULA(IF(BN3:BN="","",BN3:BN&" · "&BO3:BO&IFERROR(" · "&REGEXEXTRACT(BP3:BP,"\S+@\S+"),"")))` |
| S3 | Duration (weeks) | `=ARRAYFORMULA(IF((Q3:Q="")+(R3:R=""),"",IFERROR(ROUND((R3:R-Q3:Q)/7),"")))` |
| BL3 | Days Since Applied | `=ARRAYFORMULA(IF(BK3:BK="","",IFERROR(TODAY()-BK3:BK,"")))` |

Set columns S and BL to **Format → Number → Number** so they don't show as dates.

Nice to have: freeze rows 1–2 and columns A–C, and add a filter on row 2.
