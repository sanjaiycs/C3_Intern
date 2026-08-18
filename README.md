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

## Syllabus Topic Parsing — Delimiter Handling

### Problem
Real-world Indian university syllabi, including syllabi from universities such as Anna University, Sairam, VTU, and JNTU, use inconsistent delimiters when listing topics within a module.
Topics may be separated using:

- Commas (",")
- Semicolons (";")
- En-dashes ("–")
- Em-dashes ("—")
- Spaced hyphens ("-")

For example:

Searching – Sorting – Hashing – Graph Traversal
or:
Searching - Sorting - Hashing - Graph Traversal

### Root Cause
The initial implementation of "syllabus_parser.py" used a regular expression that only split topics on commas and semicolons.
As a result, syllabi using en-dashes, em-dashes, or spaced hyphens were not parsed correctly.
'the parser could incorrectly treat the entire sequence as one large topic:
Searching – Sorting – Hashing – Graph Traversal'
to produce mega-topics, reducing the accuracy of downstream textbook page-range retrieval and LLM adjudication.

### Required Fix
Update the "split_topics()" function in "syllabus_parser.py" to recognize:
en-dashes: "–"
em-dashes: "—"
and spaced hyphens: " - " while avoiding unnecessary splitting of legitimate compound technical terms.
dCompound-word protection:
the parser should distinguish between:
graph traversal - breadth-first search - sorting 
and:
breadth-first 
the first should produce separate topics, while the second must remain a single term.
a suitable regular-expression strategy is to target en-dashes, em-dashes, and hyphens surrounded by whitespace,
rather than splitting indiscriminately on every " - ".

### Expected Behavior
Input:
s Searching – Sorting – Hashing – Graph Traversal Output:
s ["Searching", "Sorting", "Hashing", "Graph Traversal"]
e Input:
graph traversal - Breadth-first Search - Depth-first Search Output:
g ["Graph Traversal", "Breadth-First Search", "Depth-Fir...