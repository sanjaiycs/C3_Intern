"""
syllabus_parser.py
-------------------
Parses a college curriculum/syllabus PDF (CBCS-style, e.g. Anna University /
Sairam Engineering College format) into a structured list of:

    Subject -> Module/Unit -> Topics -> Sub-topics

and the associated Text Book / Reference Book citations for that subject.

This is regex-based (no LLM needed for this step) because syllabus PDFs of
this kind follow a very predictable layout:

    <CODE> <SUBJECT NAME> ... L T P C
    (optional "Common to ..." line)
    <L> <T> <P> <C>
    OBJECTIVES
    ...
    UNIT I <UNIT TITLE> <hours>
    <topic paragraph, semicolons/commas separated, may contain CO tags>
    UNIT II <UNIT TITLE> <hours>
    ...
    TOTAL: NN PERIODS
    TEXT BOOKS
    1. Author, "Title", edition, Publisher, year.
    ...
    REFERENCE BOOKS
    1. ...
    COURSE OUTCOMES
    ...

Works on any PDF with a similar structure -- tweak the regexes below if your
college's format differs slightly.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #

@dataclass
class BookRef:
    raw: str
    author: str = ""
    title: str = ""
    edition: str = ""
    publisher: str = ""
    year: str = ""
    book_type: str = "textbook"  # "textbook" or "reference"


@dataclass
class TopicItem:
    topic: str
    subtopics: List[str] = field(default_factory=list)


@dataclass
class Module:
    module_no: int
    module_title: str
    hours: Optional[str]
    raw_text: str
    topics: List[TopicItem] = field(default_factory=list)  # topic -> [subtopics]


@dataclass
class Subject:
    subject_code: str
    subject_name: str
    semester: Optional[str]
    modules: List[Module] = field(default_factory=list)
    text_books: List[BookRef] = field(default_factory=list)
    reference_books: List[BookRef] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# PDF text extraction
# --------------------------------------------------------------------------- #

def get_pdf_text_per_page(pdf_path: str) -> List[str]:
    """Returns a list of page texts. Uses PyMuPDF if available (fast/accurate),
    else falls back to pdfplumber."""
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        return [page.get_text() for page in doc]
    except ImportError:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            return [p.extract_text() or "" for p in pdf.pages]


# --------------------------------------------------------------------------- #
# Regexes
# --------------------------------------------------------------------------- #

SEMESTER_RE = re.compile(r'^SEMESTER\s+([IVX]+)', re.MULTILINE)

# e.g. "GE4105 PROBLEM SOLVING AND PYTHON PROGRAMMING L T P C"
SUBJECT_HEADER_RE = re.compile(
    r'(?P<code>[A-Z]{2,4}\d{3,5})\s+(?P<name>[A-Z][A-Z0-9 &/(),.\-]{4,100}?)\s+L\s*T\s*P\s*C',
)

# e.g. "UNIT I ALGORITHMIC PROBLEM SOLVING 9"  or "UNIT III ... 7+12"
UNIT_RE = re.compile(
    r'UNIT\s+([IVX]+)\s+([A-Z][A-Z0-9 &/(),.\-\']{3,100}?)\s+(\d+(?:\+\d+)?)\s*\n',
)

TEXTBOOKS_HDR_RE = re.compile(r'^\s*TEXT\s*BOOKS?\s*$', re.MULTILINE)
REFBOOKS_HDR_RE = re.compile(r'^\s*REFERENCE\s*BOOKS?\s*$', re.MULTILINE)
COURSE_OUTCOMES_HDR_RE = re.compile(r'^\s*COURSE\s+OUTCOMES\s*$', re.MULTILINE)
MAPPING_HDR_RE = re.compile(r'^\s*MAPPING\s+OF\s+COs', re.MULTILINE)

# Numbered citation entries: "1. Author..., "Title", Publisher, Year."
CITATION_ITEM_RE = re.compile(r'\n\s*(\d{1,2})\.\s+', re.MULTILINE)

ROMAN_MAP = {'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5, 'VI': 6, 'VII': 7, 'VIII': 8}


# --------------------------------------------------------------------------- #
# Citation parsing (best-effort -- publisher catalogs vary a lot in format)
# --------------------------------------------------------------------------- #

YEAR_RE = re.compile(r'(19|20)\d{2}')
EDITION_RE = re.compile(r'(\d+(?:st|nd|rd|th)\s*Ed(?:ition|\.)?)', re.IGNORECASE)


def parse_citation(raw: str, book_type: str) -> BookRef:
    raw_clean = re.sub(r'\s+', ' ', raw).strip()

    year_m = YEAR_RE.search(raw_clean)
    year = year_m.group(0) if year_m else ""

    edition_m = EDITION_RE.search(raw_clean)
    edition = edition_m.group(1) if edition_m else ""

    # Title heuristic: text within the first pair of quotes (curly or straight)
    title_m = re.search(r'[\u201c"\'\u2018]([^\u201d"\'\u2019]{4,150})[\u201d"\'\u2019]', raw_clean)
    title = title_m.group(1).strip() if title_m else ""

    # Author heuristic: text before the title/quote, else before first comma
    if title_m:
        author = raw_clean[:title_m.start()].strip(' ,.\u2013-')
    else:
        author = raw_clean.split(',')[0].strip()

    # Publisher heuristic: segment right after title/edition, before year,
    # excluding pure place names is hard -- keep it as the trailing chunk
    # minus the year.
    tail = raw_clean
    if title_m:
        tail = raw_clean[title_m.end():]
    tail = re.sub(EDITION_RE, '', tail)
    if year_m:
        tail = tail[:tail.find(year_m.group(0))]
    publisher = tail.strip(' ,.\u2013-')

    return BookRef(
        raw=raw_clean,
        author=author,
        title=title,
        edition=edition,
        publisher=publisher,
        year=year,
        book_type=book_type,
    )


def split_citations(block_text: str, book_type: str) -> List[BookRef]:
    """Split a TEXT BOOKS / REFERENCE BOOKS block into individual citations."""
    if not block_text.strip():
        return []
    parts = CITATION_ITEM_RE.split('\n' + block_text)
    # parts alternates [prefix, num, entry, num, entry, ...]; drop numbers
    entries = [p for p in parts[2::2]] if len(parts) > 2 else [block_text]
    return [parse_citation(e, book_type) for e in entries if e.strip()]


# --------------------------------------------------------------------------- #
# Topic / sub-topic splitting
# --------------------------------------------------------------------------- #

def split_topics(unit_body: str) -> List[TopicItem]:
    """Split a unit's descriptive paragraph into a Topic -> [Sub-topics]
    hierarchy.

    Heuristic (tune this to your college's phrasing style):
      - Strip inline CO tags (CO1..CO9) and a trailing "TOTAL: NN PERIODS".
      - Split on ';' first -- each semicolon-separated segment becomes one
        TOPIC (these usually mark a shift to a new sub-theme within the unit).
      - Within a topic segment, split on ',' -- each comma-separated phrase
        becomes one SUB-TOPIC under that topic.
      - If a topic segment has only one comma-phrase (i.e. no meaningful
        sub-split), it's kept as a topic with no sub-topics -- the topic
        phrase itself is what gets mapped to pages in that case.
    """
    text = re.sub(r'\bCO\d+\b', '', unit_body)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r'TOTAL:\s*\d+\s*PERIODS.*$', '', text, flags=re.IGNORECASE)

    major_chunks = [c.strip(' .') for c in text.split(';') if c.strip(' .')]
    items: List[TopicItem] = []
    for chunk in major_chunks:
        subs = [s.strip(' .-') for s in chunk.split(',') if len(s.strip(' .-')) >= 3]
        if not subs:
            continue
        if len(subs) == 1:
            items.append(TopicItem(topic=subs[0], subtopics=[]))
        elif len(chunk) <= 90:
            # Short segment: use the whole thing as the topic label, and
            # each comma-phrase as a sub-topic under it.
            items.append(TopicItem(topic=chunk, subtopics=subs))
        else:
            # Long segment: use the first phrase as the topic label, and
            # the REST of the comma-phrases as its sub-topics (avoids
            # duplicating the topic label as its own first sub-topic).
            items.append(TopicItem(topic=subs[0], subtopics=subs[1:]))

    if not items and text:
        items = [TopicItem(topic=text, subtopics=[])]
    return items


# --------------------------------------------------------------------------- #
# Main parse routine
# --------------------------------------------------------------------------- #

def parse_syllabus(pdf_path: str) -> List[Subject]:
    pages = get_pdf_text_per_page(pdf_path)
    full_text = "\n".join(pages)

    # Track current semester as we scan subject headers in document order
    header_matches = list(SUBJECT_HEADER_RE.finditer(full_text))
    semester_matches = list(SEMESTER_RE.finditer(full_text))

    def semester_for_pos(pos: int) -> Optional[str]:
        current = None
        for m in semester_matches:
            if m.start() <= pos:
                current = m.group(1)
            else:
                break
        return current

    subjects: List[Subject] = []

    for idx, hm in enumerate(header_matches):
        start = hm.end()
        end = header_matches[idx + 1].start() if idx + 1 < len(header_matches) else len(full_text)
        block = full_text[start:end]

        code = hm.group('code').strip()
        name = re.sub(r'\s+', ' ', hm.group('name')).strip()
        semester = semester_for_pos(hm.start())

        subject = Subject(subject_code=code, subject_name=name, semester=semester)

        # --- split off TEXT BOOKS / REFERENCE BOOKS / COURSE OUTCOMES tail ---
        tb_m = TEXTBOOKS_HDR_RE.search(block)
        rb_m = REFBOOKS_HDR_RE.search(block)
        co_m = COURSE_OUTCOMES_HDR_RE.search(block)
        map_m = MAPPING_HDR_RE.search(block)

        units_end = min([m.start() for m in [tb_m, rb_m, co_m, map_m] if m] or [len(block)])
        units_block = block[:units_end]

        if tb_m:
            tb_end = rb_m.start() if rb_m else (co_m.start() if co_m else (map_m.start() if map_m else len(block)))
            subject.text_books = split_citations(block[tb_m.end():tb_end], "textbook")
        if rb_m:
            rb_end = co_m.start() if co_m else (map_m.start() if map_m else len(block))
            subject.reference_books = split_citations(block[rb_m.end():rb_end], "reference")

        # --- parse units/modules ---
        unit_matches = list(UNIT_RE.finditer(units_block))
        for uidx, um in enumerate(unit_matches):
            roman, title, hours = um.group(1), um.group(2).strip(), um.group(3)
            body_start = um.end()
            body_end = unit_matches[uidx + 1].start() if uidx + 1 < len(unit_matches) else len(units_block)
            body = units_block[body_start:body_end]

            module = Module(
                module_no=ROMAN_MAP.get(roman, uidx + 1),
                module_title=re.sub(r'\s+', ' ', title),
                hours=hours,
                raw_text=re.sub(r'\s+', ' ', body).strip(),
            )
            module.topics = split_topics(body)
            subject.modules.append(module)

        if subject.modules:  # only keep subjects where we actually found units
            subjects.append(subject)

    return subjects


# --------------------------------------------------------------------------- #
# CLI / quick test
# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys
    import json

    path = sys.argv[1] if len(sys.argv) > 1 else "AI_DS.pdf"
    subs = parse_syllabus(path)
    print(f"Parsed {len(subs)} subjects")
    for s in subs[:2]:
        print(f"\n{s.subject_code} - {s.subject_name} (Sem {s.semester})")
        for m in s.modules:
            print(f"  Module {m.module_no}: {m.module_title} ({m.hours} hrs)")
            for t in m.topics[:5]:
                print(f"    Topic: {t.topic[:70]}")
                for sub in t.subtopics[:5]:
                    print(f"       - {sub}")
        for b in s.text_books:
            print(f"  [Textbook] {b.author} | {b.title} | {b.edition} | {b.publisher} | {b.year}")
