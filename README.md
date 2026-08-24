# Syllabus → Textbook Page Mapper

A Python pipeline that maps topics from a college syllabus to the **actual page ranges in locally available textbook PDFs**.

The project is designed for syllabus documents such as the uploaded **B.Tech Artificial Intelligence and Data Science – Regulation 2022, CBCS, I–VIII Semesters** curriculum. The syllabus parser converts the curriculum into a structured hierarchy of:

```text
Subject
└── Module / Unit
    └── Topic
        └── Sub-topic
```

The mapper then searches the local textbook PDFs and produces a CSV containing the textbook chapter and page range most likely to cover each syllabus topic.

---

## 1. What the project does

The complete pipeline is:

```text
                 ┌──────────────────────┐
                 │     Syllabus PDF     │
                 │      AI_DS.pdf       │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │   syllabus_parser    │
                 │ Regex-based parsing  │
                 └──────────┬───────────┘
                            │
                            ▼
                 ┌──────────────────────┐
                 │ Subject → Module →   │
                 │ Topic → Sub-topic    │
                 └──────────┬───────────┘
                            │
                 ┌──────────┴───────────┐
                 │                      │
                 ▼                      ▼
        ┌─────────────────┐    ┌─────────────────┐
        │ book_files.json │    │   Local Books   │
        │ Subject → PDFs  │───►│  Text / Scanned │
        └─────────────────┘    └────────┬────────┘
                                        │
                                        ▼
                              ┌──────────────────┐
                              │   book_indexer   │
                              │ Text extraction  │
                              │ + OCR fallback   │
                              │ + JSON cache      │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │  topic_mapper    │
                              │ Candidate search │
                              │ + LLM validation │
                              └────────┬─────────┘
                                       │
                                       ▼
                              ┌──────────────────┐
                              │  mapped_topics   │
                              │       .csv       │
                              └──────────────────┘
```

The important design decision is that the LLM **does not read the entire textbook**. The system first retrieves likely pages using local text matching and fuzzy similarity, then sends only the best candidate page excerpts to the LLM for adjudication.

---

## 2. Current implementation

The uploaded project contains these main components:

| File | Responsibility |
|---|---|
| `main.py` | Orchestrates the complete pipeline and writes the final CSV |
| `syllabus_parser.py` | Parses syllabus subjects, modules, topics, sub-topics and book citations |
| `book_indexer.py` | Creates a per-page text/OCR index for each textbook |
| `topic_mapper.py` | Retrieves candidate pages and asks an LLM to select the best page range |
| `book_files.json` | Maps subject codes to the local textbook/reference PDFs |
| `requirements.txt` | Python dependencies |
| `AI_DS.pdf` | Input curriculum/syllabus PDF |
| `sample_1book.csv` | Example output from a one-book mapping run |

The current source files use the names above. The uploaded copies in this workspace were named with version suffixes, but the code itself expects the normal project names.

---

## 3. Source syllabus

The supplied curriculum is:

**B.Tech Artificial Intelligence and Data Science**  
**Regulation 2022**  
**Choice Based Credit System (CBCS)**  
**I–VIII Semesters**

The syllabus itself defines the department vision, mission, PEOs, POs and PSOs before the semester-wise curriculum. The curriculum starts with Semester I and continues through Semester VIII.

The parser was executed against the supplied syllabus during documentation and produced:

- **58 subjects**
- **273 modules/units**
- **1,232 parsed topics**

These numbers describe the current parser output for the supplied PDF; they are not hard-coded project assumptions.

---

# 4. Component 1 — Syllabus Parser

## Purpose

`syllabus_parser.py` converts the syllabus PDF into structured Python data.

It uses:

- PyMuPDF when available
- `pdfplumber` as a fallback
- Regular expressions
- Dataclasses

No LLM is required for syllabus parsing.

The parser recognizes the general structure:

```text
SUBJECT
    ↓
UNIT I / UNIT II / ...
    ↓
Topics
    ↓
Sub-topics

TEXT BOOKS
REFERENCE BOOKS
```

### Data model

The parser defines:

```python
BookRef
TopicItem
Module
Subject
```

A `Subject` contains:

```text
subject_code
subject_name
semester
modules
text_books
reference_books
```

A `Module` contains:

```text
module_no
module_title
hours
raw_text
topics
```

A `TopicItem` contains:

```text
topic
subtopics
```

---

## 5. Semester detection

The syllabus contains multiple semester headings and also contains later cumulative course listings.

A simple "nearest previous semester heading" strategy can incorrectly assign a subject to the wrong semester.

The current implementation therefore:

1. Finds every `SEMESTER I`, `SEMESTER II`, etc. heading.
2. Examines the table span belonging to that semester.
3. Extracts subject codes from that span.
4. Keeps the first correct assignment for each subject code.
5. Ignores oversized spans that are likely to be cumulative listings.

This is important because semester detection affects the metadata of every parsed subject.

---

# 6. Topic and sub-topic extraction

The syllabus PDFs are not perfectly consistent about separators.

The parser handles:

- semicolons
- en-dashes
- em-dashes
- commas
- colon-based topic/sub-topic structures
- PDF-glued words
- repeated topic fragments
- short orphan fragments

For technical subjects, a structure such as:

```text
Torsion pendulum: theory and experiment
```

can become:

```text
Topic:
    Torsion pendulum

Sub-topics:
    theory
    experiment
```

For communication/English-style subjects, the parser has a special mode for recurring sections such as:

```text
Reading
Writing
Listening
Speaking
Grammar
Pronunciation
Vocabulary development
Language development
```

When at least three of these section markers are detected, they are treated as the topic structure rather than applying the normal technical-topic splitter.

---

# 7. Book citation extraction

The syllabus can contain textbook and reference-book citations.

The parser attempts to extract:

```text
author
title
edition
publisher
year
book_type
```

The citation parser is intentionally heuristic because publisher/reference formats vary.

Example internal representation:

```json
{
  "title": "Think Python: How to Think Like a Computer Scientist",
  "author": "Allen B. Downey",
  "edition": "2nd",
  "publisher": "Green Tea Press",
  "year": "2015",
  "book_type": "textbook"
}
```

---

# 8. Component 2 — Book Indexer

## Purpose

`book_indexer.py` converts every textbook PDF into a page-level searchable index.

This supports both:

1. digitally generated PDFs with selectable text
2. scanned/image-only PDFs

### Extraction strategy

For every page:

```text
Try direct text extraction
        │
        ├── sufficient text → use extracted text
        │
        └── very little text
                ↓
              OCR
                ↓
        store OCR text
```

The current threshold is:

```python
MIN_CHARS_FOR_TEXT_PAGE = 30
```

Pages with fewer than 30 extracted characters are treated as likely scanned/image pages.

### OCR stack

OCR uses:

```text
pdf2image
PIL
pytesseract
```

with a default OCR resolution of:

```text
200 DPI
```

---

# 9. Book index cache

OCR can be expensive, especially for large books.

The indexer therefore creates:

```text
<book-name>.index.json
```

next to the textbook PDF.

The cache stores information such as:

```json
{
  "pdf_path": "...",
  "num_pages": 350,
  "pages": [
    {
      "page_num": 1,
      "text": "...",
      "source": "text"
    },
    {
      "page_num": 2,
      "text": "...",
      "source": "ocr"
    }
  ]
}
```

`source` can identify whether the page came from:

```text
text
ocr
empty
```

If the cache already exists and caching is enabled, the indexer loads it instead of rebuilding the entire book index.

This is especially useful for 300–500+ page scanned textbooks.

---

# 10. Physical page vs printed page

The indexer uses the **physical PDF page number**, starting at 1.

This can differ from the page number printed inside the textbook because of:

- cover pages
- copyright pages
- prefaces
- tables of contents
- front matter

The main pipeline therefore supports:

```text
--printed-page-offset
```

For example:

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --printed-page-offset 5
```

If the physical page is 20, the output page becomes 25.

Use this only after checking the actual book's printed numbering.

---

# 11. Component 3 — Topic Mapper

`topic_mapper.py` performs the actual topic-to-page mapping.

It uses a two-stage approach.

## Stage 1 — Candidate retrieval

No LLM is used here.

Every indexed page receives a relevance score based on:

- keyword overlap
- fuzzy text similarity
- keyword coverage

`rapidfuzz` is used when available.

The default number of candidate pages is:

```text
top_k = 8
```

Only the top candidate pages are sent to the LLM.

Conceptually:

```text
Syllabus topic
      ↓
Extract keywords
      ↓
Compare against every indexed page
      ↓
Rank pages
      ↓
Keep top 8
```

This greatly reduces the amount of textbook text sent to the model.

---

# 12. Stage 2 — LLM adjudication

The LLM receives:

```text
Subject
Module
Book
Topic
Candidate page numbers
Candidate page excerpts
```

It must return structured JSON containing:

```json
{
  "found": true,
  "page_start": 42,
  "page_end": 46,
  "chapter": "3",
  "coverage": "primary",
  "notes": "..."
}
```

The model is explicitly instructed to:

- use only candidate page numbers
- select contiguous relevant pages
- return `found: false` if the candidates do not actually cover the topic
- classify coverage
- provide a chapter when inferable
- provide a concise note

Supported coverage values are:

```text
primary
supplementary
brief mention
not found
```

---

# 13. LLM backends

The mapper supports four backends.

## Gemini

Recommended cloud backend:

```bash
--backend gemini
```

Default model:

```text
gemini-2.5-flash
```

Required package:

```text
google-genai
```

Environment variable:

```bash
export GEMINI_API_KEY="your_key"
```

---

## Ollama

Local/offline option:

```bash
--backend ollama --model llama3.1
```

Required package:

```bash
pip install ollama
```

This is useful when you want the LLM inference to stay local.

---

## OpenAI-compatible backend

The mapper can also use an OpenAI-compatible API:

```bash
--backend openai --model gpt-4o-mini
```

Required package:

```text
openai
```

The same function can also work with compatible local servers when a suitable base URL is supplied in the implementation.

---

## OmniRoute

The project includes an OmniRoute backend:

```bash
--backend omniroute
```

OmniRoute is accessed through its OpenAI-compatible interface.

The implementation defaults to:

```text
http://localhost:20128/v1
```

and reads:

```text
OMNIROUTE_BASE_URL
OMNIROUTE_API_KEY
```

The backend can route to connected providers and can provide fallback behavior when a provider is unavailable or rate-limited, depending on the OmniRoute configuration.

Example:

```bash
export OMNIROUTE_BASE_URL="http://localhost:20128/v1"
export OMNIROUTE_API_KEY="your_dashboard_key"

python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --backend omniroute \
  --model auto/best-coding
```

---

# 14. Automatic backend selection

`main.py` checks environment variables when choosing its default backend.

Current priority:

```text
OMNIROUTE_API_KEY
        ↓
    OmniRoute

otherwise

OPENAI_API_KEY
        ↓
     OpenAI

otherwise

Gemini
```

The built-in defaults are:

```text
Gemini:
    backend = gemini
    model   = gemini-2.5-flash

OmniRoute:
    backend = omniroute
    model   = auto/best-coding

OpenAI:
    backend = openai
    model   = gpt-4o-mini
```

You can always override these with `--backend` and `--model`.

---

# 15. Component 4 — book_files.json

The syllabus only tells the program which books are cited.

It does not reliably tell the program where the actual PDF is stored on the computer.

`book_files.json` solves this problem.

The mapping is:

```text
subject code
    ↓
one or more local textbook/reference PDFs
```

Example:

```json
{
  "GE4105": [
    {
      "file": "books/7.THINK PYTHON_HOW TO THINK LIKE A COMPUTER SCIENTIST.pdf",
      "title": "Think Python: How to Think Like a Computer Scientist",
      "author": "Allen B. Downey",
      "edition": "2nd",
      "publisher": "Green Tea Press",
      "year": "2015",
      "book_type": "textbook"
    }
  ]
}
```

The current supplied `book_files.json` contains:

- **15 subject mappings**
- **38 book entries**
- **36 unique PDF file paths**

The mapping must point to files that actually exist relative to the directory from which the program is run.

---

# 16. Why manual book mapping is used

Automatic filename matching is intentionally avoided.

For example, the syllabus may contain:

```text
Cormen, Introduction to Algorithms, 3rd ed., MIT Press, 2009
```

while the local file may be named:

```text
64.Cormen Introduction to Algorithms.pdf
```

or something completely different.

`book_files.json` creates an explicit and reliable connection between:

```text
syllabus subject
        ↓
book metadata
        ↓
actual PDF path
```

This mapping only needs to be configured once for a given book collection.

---

# 17. Main orchestration

`main.py` coordinates everything.

The execution flow is:

```text
1. Load environment variables
2. Parse syllabus
3. Load book_files.json
4. Filter subjects if requested
5. For every selected subject:
      a. Load configured books
      b. Build/load each book index
      c. Iterate through modules
      d. Iterate through topics/sub-topics
      e. Retrieve candidate pages
      f. Ask selected LLM to adjudicate
      g. Write result to CSV
```

The same textbook index is kept in memory during the run so that the same PDF does not need to be indexed repeatedly.

---

# 18. Output CSV

The output is designed as a row-based mapping table.

Current columns:

```text
id
subject_code
subject_name
module_no
module_title
topic
sub_topic
book_title
author
edition
publisher
year
book_type
chapter
page_start
page_end
coverage
notes
```

Example:

```csv
id,subject_code,subject_name,module_no,module_title,topic,sub_topic,book_title,author,edition,publisher,year,book_type,chapter,page_start,page_end,coverage,notes
AD_M1_T1_S1,AD4351,FOUNDATIONS OF DATA SCIENCE,1,INTRODUCTION,Data Science,Benefits and uses,Introducing Data Science...,Davy Cielen...,1st,Manning Publications,2016,reference,1,2,3,primary,Detailed explanation...
```

The supplied sample output demonstrates mappings with:

- primary coverage
- supplementary coverage
- brief mention
- not found

The `not found` case intentionally leaves page/chapter fields empty when no suitable coverage was identified.

---

# 19. Row IDs

The main program generates IDs from the subject code, module, topic and optional sub-topic.

Pattern:

```text
XX_M<module>_T<topic>
```

or:

```text
XX_M<module>_T<topic>_S<subtopic>
```

Example:

```text
AD_M1_T1_S1
```

The subject-code prefix is reduced to alphabetic characters and the first two letters are used.

---

# 20. Command-line usage

## Full syllabus

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --out mapped_topics.csv
```

This processes all subjects that have entries in `book_files.json`.

---

## One subject

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --out ad4351_mapping.csv
```

This is recommended for testing before running a large job.

---

## One subject and one book

Use:

```bash
--max-books-per-subject 1
```

Example:

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --max-books-per-subject 1 \
  --out sample_1book.csv
```

---

## Limit topics for a quick test

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --max-books-per-subject 1 \
  --max-topics-per-module 2 \
  --out test.csv
```

This is useful for checking configuration and model behavior before a long run.

---

## Select a backend explicitly

Gemini:

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --backend gemini \
  --model gemini-2.5-flash
```

Ollama:

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --backend ollama \
  --model llama3.1
```

OpenAI-compatible:

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --backend openai \
  --model gpt-4o-mini
```

OmniRoute:

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --backend omniroute \
  --model auto/best-coding
```

---

# 21. Installation

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```bash
pip install -r requirements.txt
```

The supplied requirements include:

```text
PyMuPDF
pdfplumber
pdf2image
pytesseract
rapidfuzz
google-genai
```

Optional backend packages:

```bash
pip install ollama
pip install openai
```

For OCR, `pytesseract` also requires the Tesseract executable to be installed on the system, and `pdf2image` may require the PDF rendering utilities used by the environment.

---

# 22. Environment variables

Create a `.env` file if desired:

```env
GEMINI_API_KEY=your_gemini_key
OPENAI_API_KEY=your_openai_key

OMNIROUTE_BASE_URL=http://localhost:20128/v1
OMNIROUTE_API_KEY=your_omniroute_key
```

`main.py` contains a small `.env` loader and does not overwrite an environment variable that is already set.

Do not commit real API keys to Git.

Recommended:

```gitignore
.env
*.index.json
```

---

# 23. Recommended project structure

```text
syllabus-textbook-mapper/
│
├── AI_DS.pdf
├── book_files.json
├── requirements.txt
│
├── syllabus_parser.py
├── book_indexer.py
├── topic_mapper.py
├── main.py
│
├── books/
│   ├── textbook_1.pdf
│   ├── textbook_2.pdf
│   └── ...
│
├── indexes/
│   └── optional cached indexes
│
├── output/
│   ├── mapped_topics.csv
│   └── test.csv
│
├── .env
└── README.md
```

The current indexer actually writes cache files next to the source PDF by default, using:

```text
<book-name>.index.json
```

The `indexes/` directory above is therefore an organizational suggestion rather than a requirement of the current implementation.

---

# 24. Performance strategy

The expensive part of this project is not syllabus parsing.

The main cost comes from:

```text
number of topics
×
number of books
×
LLM calls
```

If one topic is compared against multiple books, each topic/book pair can result in an LLM adjudication call.

For that reason, test runs should start small.

Recommended sequence:

```text
1. One subject
2. One book
3. 1–2 topics per module
4. Inspect CSV
5. Increase topic count
6. Increase book count
7. Run full subject
8. Run complete collection
```

---

# 25. Candidate retrieval tuning

The default:

```text
--top-k 8
```

means up to eight candidate pages are passed to the LLM.

Increasing it can improve recall when the relevant page is difficult to retrieve, but it also increases the amount of context sent to the model.

Example:

```bash
--top-k 12
```

Use a smaller value for faster testing.

The retrieval score currently combines:

```text
60% keyword-hit contribution
40% fuzzy similarity contribution
+ keyword coverage adjustment
```

The exact implementation should be treated as the current heuristic rather than a universal optimal weighting.

---

# 26. Failure handling

The mapper is designed not to stop the entire pipeline when an LLM call fails.

If the LLM call or JSON parsing fails:

1. The best retrieved candidate is selected.
2. A small candidate range is produced heuristically.
3. The output note records that the result was a heuristic match and includes the failure reason.

This means the CSV can still be generated, but those rows should be reviewed before being treated as high-confidence mappings.

---

# 27. Important accuracy considerations

This system is a **page-mapping assistant**, not a proof system.

A result such as:

```text
primary, pages 64–68
```

means the retrieval and adjudication stages judged those pages to be the best available coverage among the candidate pages.

It does not guarantee that:

- every page in the range is necessary
- no earlier/later page is relevant
- the printed page number exactly matches the PDF page number
- the book edition perfectly matches the syllabus citation
- the LLM's interpretation is always correct

For important academic use, review the generated mappings.

---

# 28. Known limitations

## 28.1 OCR quality

Scanned PDFs depend on OCR quality.

Poor scans, unusual fonts, mathematical notation, diagrams and tables can reduce retrieval accuracy.

## 28.2 Page-number offsets

Physical PDF pages and printed book pages may differ.

Use:

```text
--printed-page-offset
```

when the difference is consistent.

## 28.3 Citation parsing

Book citation extraction is heuristic and may not perfectly parse every publisher's citation style.

## 28.4 Topic splitting

The parser is tuned for the observed CBCS-style syllabus structure. A significantly different college syllabus format may require regex or splitting-rule changes.

## 28.5 Candidate retrieval

If the relevant page is not among the retrieved candidates, the LLM cannot recover it because it is explicitly restricted to the candidate page list.

## 28.6 LLM dependency

Cloud backends require the relevant API access. Ollama requires a local model. OmniRoute requires a working configured gateway/provider.

---

# 29. Debugging workflow

If a subject is missing:

```text
Check subject code
        ↓
Check syllabus_parser output
        ↓
Check book_files.json
```

If a book is skipped:

```text
[!] Book file not found
```

Check the path in `book_files.json`.

If no topics are found:

```text
Run syllabus_parser.py directly
```

Example:

```bash
python syllabus_parser.py AI_DS.pdf AD4351
```

If a book is not being indexed correctly:

```bash
python book_indexer.py "books/your_book.pdf"
```

The indexer prints:

```text
Indexed N pages
X text pages
Y OCR pages
```

If mappings look poor:

1. inspect the generated CSV
2. inspect the relevant `.index.json`
3. increase `--top-k`
4. verify the textbook edition
5. verify the printed-page offset
6. try another backend/model
7. test the topic against a single known textbook

---

# 30. Suggested validation process

Before trusting a large run, validate representative topics:

### Easy topic

Choose a topic whose wording clearly appears in the book.

Expected:

```text
primary
```

with a sensible chapter/page range.

### Indirect topic

Choose a topic whose textbook wording differs from the syllabus wording.

This tests fuzzy retrieval.

### Missing topic

Choose a topic not covered by the selected book.

Expected:

```text
not found
```

### Scanned page

Choose a topic located in an image-only section.

This tests OCR.

### Page offset

Compare the reported physical page with the printed page.

This tests:

```text
--printed-page-offset
```

---

# 31. Sample output interpretation

The supplied `sample_1book.csv` demonstrates examples such as:

```text
Data Science → Benefits and uses
```

mapped to a primary page range, and:

```text
structured arrays
```

reported as:

```text
not found
```

It also demonstrates `supplementary` and `brief mention` classifications.

This distinction is useful because a textbook can mention a syllabus concept without providing a complete treatment.

---

# 32. Example end-to-end workflow

## Step 1 — Put books in the books directory

```text
books/
├── data_science_book.pdf
├── statistics_book.pdf
└── ...
```

## Step 2 — Add the mappings

```json
{
  "AD4351": [
    {
      "file": "books/data_science_book.pdf",
      "title": "Introducing Data Science",
      "author": "Davy Cielen et al.",
      "edition": "1st",
      "publisher": "Manning Publications",
      "year": "2016",
      "book_type": "reference"
    }
  ]
}
```

## Step 3 — Configure the LLM

For Gemini:

```bash
export GEMINI_API_KEY="..."
```

or configure OmniRoute:

```bash
export OMNIROUTE_BASE_URL="http://localhost:20128/v1"
export OMNIROUTE_API_KEY="..."
```

## Step 4 — Run a small test

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --max-books-per-subject 1 \
  --max-topics-per-module 2 \
  --out test.csv
```

## Step 5 — Review

Open:

```text
test.csv
```

Check:

- topic
- sub-topic
- book
- chapter
- page_start
- page_end
- coverage
- notes

## Step 6 — Run the complete subject

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --out AD4351_mapping.csv
```

## Step 7 — Run multiple subjects

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 AD4501 AD4301 \
  --out selected_subjects.csv
```

---

# 33. Design principles

The project currently follows these principles:

### 1. Parse deterministically where possible

The syllabus structure is handled with regexes and deterministic rules instead of spending an LLM call on parsing.

### 2. Search before using an LLM

The LLM sees only retrieved candidate pages.

### 3. Support real-world PDFs

Both text PDFs and scanned PDFs are supported.

### 4. Cache expensive work

Book indexing is cached so OCR does not have to be repeated unnecessarily.

### 5. Preserve uncertainty

The CSV distinguishes:

```text
primary
supplementary
brief mention
not found
```

rather than pretending every match is equally strong.

### 6. Keep the book mapping explicit

`book_files.json` makes the relationship between syllabus subjects and local PDFs deterministic.

### 7. Keep the pipeline backend-independent

The topic-mapping layer supports Gemini, Ollama, OpenAI-compatible endpoints and OmniRoute.

---

# 34. Future improvements

Potential improvements that fit the current architecture include:

- chapter-aware candidate retrieval
- embedding/vector retrieval in addition to fuzzy matching
- semantic reranking
- confidence scores
- automatic printed-page-offset detection
- automatic duplicate-book detection
- book edition validation
- parallel topic/book processing
- retry and rate-limit handling
- persistent LLM result caching
- SQLite/PostgreSQL output instead of CSV only
- HTML/web dashboard for browsing mappings
- manual correction workflow
- mapping confidence review UI
- side-by-side syllabus/book page verification
- support for multiple page ranges for one topic
- improved mathematical OCR
- table-aware OCR
- incremental processing when only one book changes

---

# 35. Security and API-key handling

Never put real credentials inside:

```text
book_files.json
README.md
CSV output
source code
```

Use environment variables or `.env`.

Add `.env` to `.gitignore`:

```gitignore
.env
```

If an API key is accidentally committed, revoke/rotate it immediately.

---

# 36. Quick reference

### Parse syllabus

```bash
python syllabus_parser.py AI_DS.pdf
```

### Inspect one subject

```bash
python syllabus_parser.py AI_DS.pdf AD4351
```

### Index one book

```bash
python book_indexer.py "books/book.pdf"
```

### Test one subject + one book

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --max-books-per-subject 1 \
  --max-topics-per-module 2 \
  --out test.csv
```

### Full subject

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --subjects AD4351 \
  --out mapped_topics.csv
```

### Full configured collection

```bash
python main.py \
  --syllabus AI_DS.pdf \
  --book-files book_files.json \
  --out mapped_topics.csv
```

---

# 37. Current project status

Based on the supplied source files:

```text
Syllabus parsing       ✓ Implemented
Semester detection     ✓ Implemented
Topic extraction       ✓ Implemented
Sub-topic extraction   ✓ Implemented
Book citation parsing  ✓ Implemented
Text PDF indexing      ✓ Implemented
Scanned PDF OCR        ✓ Implemented
Index caching          ✓ Implemented
Fuzzy candidate search ✓ Implemented
LLM adjudication       ✓ Implemented
Gemini backend         ✓ Implemented
Ollama backend         ✓ Implemented
OpenAI-compatible      ✓ Implemented
OmniRoute backend      ✓ Implemented
CSV export             ✓ Implemented
Failure fallback       ✓ Implemented
```

The supplied syllabus was successfully parsed during documentation into **58 subjects, 273 modules and 1,232 topics**.

The supplied `book_files.json` currently contains **15 subject mappings, 38 book entries and 36 unique book paths**.

---

# 38. License / source material note

No license information was supplied with the uploaded project files, so this README does not assign a license.

The syllabus and textbook PDFs may be subject to their respective copyright and institutional distribution rules. Use the system only with materials you are authorized to access and process.

---

## Summary

This project turns:

```text
College syllabus
+
Local textbook collection
+
Optional LLM
```

into:

```text
Topic → Book → Chapter → Page range → Coverage → Notes
```

The architecture intentionally separates deterministic document parsing, local PDF indexing/OCR, candidate retrieval and LLM reasoning. This makes the system easier to debug and allows the LLM backend to be changed without redesigning the PDF-processing pipeline.
