- ~~fix the upload # limit on file uploads~~
- ~~add a select all button for PDF selection in PDF miner~~
- ~~"Force Recreate" -> "Overwrite Existing"~~
- ~~normalize csv headers when importing that table~~
- ~~expand number of results in the results section~~
- find way to set pagination num per page
- ~~no more temp creating tables on each run (use CTEs where possible that arent persistent)~~ (just stopped showing them in available tables)
- ~~select all should toggle ~~
- ~~columns pane in PDF to Table should take full height of parent~~
- ~~add a price display to the app as a whole~~
- ~~custom widening of data table columns~~
- ~~name join results with custom table name~~
- ~~clean up the token / cost counting logic~~

### General

---

- Redo state architecture, some thoughts:
  - do per-session or per-user engine
- persistent DuckDB in filesystem?
- users? magic link for now?
- GPT 4 Mini? Larger context window?
- Test a different model for different types of VTFs? (at least try 4.1 long context for the PDF2Table functionality)

### PDF TO TABLE STUFF

---

- make it so that pdf to table can handle bigger pdfs by splitting up (make the chunk size configurable -- more dense versus less dense)
- error on bad text read (OCR required)
- note on the PDF to table tool that the PDFs are handled independently and therefore the LLM is not able to reason over multiple documents at once

### Error Backlog

---

- should not be allowed to create columns with spaces
- make the test sample rows stay the same through multiple test runs unless explicitly recalc'd / shuffled
- ERROR:root:✗ Query error: OpenAI API error: Unterminated string starting at: line 1 column 87380 (char 87379) (potentially happens when you try to write a new schema to an existing table?)

### QOL Backlog

---

- find way to set pagination num per page
- duplicate execute buttons at the bottom
