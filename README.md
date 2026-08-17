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
   Subject → Module/Unit → Topics, plus the Text Book/Reference Book
   citations listed for each subject. No LLM needed for this step;
   the syllabus format is structured enough for pattern matching.
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
python syllabus_parser.py your_syllabus.pdf
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

- **Topic splitting** is heuristic (splits the syllabus unit's paragraph on
  `;` and `,`). Syllabus prose varies a lot, so skim the parser's output
  first and adjust `split_topics()` in `syllabus_parser.py` if it's
  over/under-splitting for your college's format.
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
