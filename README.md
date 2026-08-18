Issue: Real-world Indian university syllabi (e.g., Anna University, Sairam, VTU, JNTU) use inconsistent topic delimiters. Many syllabi use en-dashes (–), em-dashes (—), or spaced hyphens (-) to separate individual topics within a module rather than standard commas (,) or semicolons (;).

​Root Cause: The initial syllabus_parser.py implementation strictly split topics using regex matching on , and ;. When encountering en-dashes, the parser failed to split distinct topics, lumping long paragraphs into a single mega-topic.

​Complication: Naively splitting on standard hyphens (-) over-splits legitimate compound technical terms (e.g., breadth-first, non-linear, rule-based, trade-offs, set-up).

​Required Fix: Update split_topics() in syllabus_parser.py to target en-dashes (–), em-dashes (—), and spaced hyphens (-) while shielding compound-word hyphens (\b\w+-\w+\b).
