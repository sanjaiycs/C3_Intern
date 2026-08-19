
# Syllabus → Textbook Page Mapper

Extracts modules/topics from a syllabus PDF and maps each topic to the page
range in your actual textbook files (PDF, or scanned/OCR PDF) where it's
covered — output as a CSV in the format:

```
id, subject_code, subject_name, module_no, module_title, topic, sub_topic,
book_title, author, edition, publisher, year, book_type, chapter,
page_start, page_end, coverage_notes
```

Each **topic** (a semicolon-separated segment of the syllabus unit text) is
broken into its **sub-topics** (the comma-separated phrases within it), and
each sub-topic gets its own page range mapped independently — so you get
one row per sub-topic, not just one row per topic.

## How it works

1. **`syllabus_parser.py`** — regex-parses the syllabus PDF into
   Subject → Module/Unit → Topics → Sub-topics, plus the Text Book/Reference
   Book citations listed for each subject and each subject's semester. No
   LLM needed for this step; the syllabus format is structured enough for
   pattern matching. It auto-detects two unit styles and splits accordingly:
   - **Language/communication-skill units** (Reading/Writing/Listening/
     Speaking/Language Development/Vocabulary Development) → one Topic per
     skill section, sub-topics are that section's content.
   - **Technical units** → topics split on semicolons/en-dashes, with a
     colon inside a segment treated as "Topic: sub-topic, sub-topic" rather
     than a new topic boundary.
   Every syllabus item is preserved (no arbitrary per-module cap), exact
   duplicate fragments are removed, and orphaned short fragments left over
   from ambiguous punctuation are folded into the preceding topic instead of
   showing up as noise.
2. **`book_indexer.py`** — extracts text per page from your actual book
   PDF. If a page has almost no extractable text (i.e. it's a scanned
   image), it automatically falls back to OCR (`pdf2image` + `pytesseract`).
   Results are cached to `<book>.index.json` so re-runs are instant.
3. **`topic_mapper.py`** — for each topic, first does a **cheap fuzzy-match
   pre-filter** across all pages (no LLM) to shortlist ~8 candidate pages,
   then sends *only those excerpts* to a local LLM (**Ollama**, e.g.
   `llama3.1`) which picks the actual page_start/page_end, chapter, and a
   coverage note ("primary" / "supplementary" / "brief mention"). This
   keeps LLM calls fast and cheap even on 500+ page books, since the model
   never has to read the whole book at once.
4. **`main.py`** — orchestrates all three and writes the final CSV.

## Setup

**Recommended: Gemini API** (better accuracy on messy/OCR'd text, cheap at
this scale, no local hardware needed):

```bash
pip install PyMuPDF pdfplumber pdf2image pytesseract rapidfuzz google-genai

# system dependencies for OCR:
#   macOS:   brew install tesseract poppler
#   Ubuntu:  sudo apt install tesseract-ocr poppler-utils
#   Windows: install Tesseract-OCR and poppler, add both to PATH

# get a free API key at https://aistudio.google.com/apikey, then:
export GEMINI_API_KEY="your-key-here"
```

**Alternative: Ollama** (fully local/offline, free, but weaker on noisy OCR
text unless you run a large model):

```bash
pip install ollama   # instead of google-genai
ollama pull llama3.1
python main.py ... --backend ollama --model llama3.1
```

`--backend openai` is also available if you'd rather use OpenAI/Azure/a
local OpenAI-compatible server — set `OPENAI_API_KEY`.

**Also available: OmniRoute** (open-source AI gateway — one endpoint in
front of 290+ providers, with automatic fallback if one provider hits a
rate limit mid-run):

```bash
pip install openai   # OmniRoute speaks the OpenAI-compatible API

# run OmniRoute (see https://github.com/pitbaden/omniroute), then:
export OMNIROUTE_BASE_URL="http://localhost:20128/v1"
export OMNIROUTE_API_KEY="<your dashboard key>"

python main.py ... --backend omniroute --model gemini-2.5-flash
```

Useful if you're mapping a large book and don't want a run to die halfway
through because you hit Gemini's free-tier quota — OmniRoute will fail over
to another connected provider automatically instead of erroring out.

## Usage

**Step 1 — see what subjects/codes the parser finds in your syllabus:**

```bash
python syllabus_parser.py your_syllabus.pdf          # overview: first 2 subjects
python syllabus_parser.py your_syllabus.pdf HS4101    # full detail for one subject code
```

**Step 2 — map each subject's citation to the actual PDF file you own:**

Copy `book_files.sample.json` → `book_files.json` and fill in real file
paths, keyed by subject_code (see the sample file for the exact shape).
You only need to do this once per subject/book.

**Step 3 — run the pipeline:**

```bash
# quick test on one subject, capped at 3 topics/module, to sanity check output
python main.py --syllabus your_syllabus.pdf --book-files book_files.json \
    --subjects CS3301 --max-topics-per-module 3 --out test.csv

# full run for one subject
python main.py --syllabus your_syllabus.pdf --book-files book_files.json \
    --subjects CS3301 --out mapped_topics.csv

# full run for every subject that has a book_files.json entry
python main.py --syllabus your_syllabus.pdf --book-files book_files.json \
    --out mapped_topics.csv
```

Useful flags:
- `--printed-page-offset N` — if the book's printed page numbers don't match
  the PDF's physical page numbers (e.g. front matter adds 12 pages before
  "page 1"), set this so the CSV reports printed page numbers.
- `--top-k N` — how many candidate pages get sent to the LLM per topic
  (default 8; raise for very long/diffuse topics, lower for speed).
- `--model` — any Ollama model tag you have pulled (`llama3.1`, `qwen2.5`,
  `mistral`, etc). Bigger models = better page-range judgement, slower.

## Notes / limitations

- **Topic/sub-topic splitting** is heuristic, not a full NLP parser. It
  handles the two unit styles this format actually uses (section-keyword
  language units and dash/colon-punctuated technical units) well, but if
  your college's syllabus phrases things very differently, skim
  `python syllabus_parser.py your.pdf <code>` for a subject or two first and
  adjust `split_topics()` / `SECTION_KEYWORDS` in `syllabus_parser.py` if
  needed.
- **Semester detection** is derived by scanning each "SEMESTER &lt;roman&gt;"
  heading's own course-code table in the syllabus, not by nearest-heading
  proximity (the latter silently mis-attributed subjects when a document
  mixes "SEMESTER I" and "SEMESTER–I" heading styles). Electives / open
  courses that aren't listed under a fixed per-semester table come back
  with `semester: None` rather than a guessed value — check
  `book_files.json`'s subject_code keys against
  `python syllabus_parser.py your.pdf` output if you need those mapped too.
- Some source PDFs have missing spaces between words (a copy/paste-into-Word
  artifact, e.g. "MichaelT.Goodrich" or "ofelasticity"). A heuristic recovers
  spaces at lowercase→Uppercase and letter→digit boundaries, which fixes
  most author names; it can't recover spaces lost between two lowercase
  words without a dictionary, so the occasional "ofelasticity"-type glued
  word can remain — this reflects a defect in the source PDF's own text
  layer, not the parser.
- **Citation parsing** (author/title/edition/publisher/year from the raw
  "TEXT BOOKS" list) is best-effort regex — publisher catalog formatting is
  inconsistent across books. It's mainly there as a starting point; the
  `book_files.json` entries you fill in by hand are the authoritative
  source used in the final CSV.
- **Scanned books**: OCR is only as good as the scan quality. For a poor
  scan, consider pre-processing (deskew/contrast) before indexing, or bump
  `ocr_dpi` in `build_book_index()`.
- LLM adjudication is capped to the candidate pages found in stage 1 — it
  cannot invent a page number that wasn't shortlisted, which keeps
  hallucinated page numbers out of the output.


  # LLM Models & Routing Architecture

## 1. LLM Backends

### Gemini 2.5 Flash ("gemini-2.5-flash")
- **Role:** Primary cloud-default LLM backend.
- **Integration:** Invoked through the "google-genai" SDK.
- **Purpose:** High-speed processing of OCR-extracted textbook text with native structured JSON output constraints.

### Llama 3.1 ("llama3.1")
- **Role:** Offline / local LLM alternative.
- **Integration:** Invoked through "Ollama".
- **Purpose:** Provides zero-cost, fully local execution without sending textbook data to external APIs.
- **Supported alternatives:** Other local Ollama models such as "qwen2.5" and "mistral" can also be configured.

### GPT-4o Mini ("gpt-4o-mini")
- **Role:** Alternate commercial cloud backend.
- **Integration:** Invoked through the OpenAI SDK.
- **Purpose:** Provides high-precision page-range adjudication through OpenAI-compatible endpoints.

---

## 2. Router & Fallback Layer

### OmniRoute AI Gateway ("omniroute")
- **Role:** Multi-provider API routing gateway.
- **Interface:** OpenAI API-compatible client interface.
- **Purpose:** Routes LLM requests across connected providers and available free tiers.
- **Failover:** Acts as a fallback buffer when a provider reaches token or rate limits during long-running textbook processing jobs.
- **Benefit:** Prevents large-scale syllabus-to-textbook mapping runs from failing because of temporary provider limits.

---


![image alt](https://github.com/sanjaiycs/C3_Intern/blob/e061fb2fc8808bb9decfc09827d26082d92ec37f/parsing.png)

