"""
Deep researcher — salary estimation, company intel, and interview prep.
Uses web_search from finder.py to gather data from multiple queries,
then extracts structured insights via regex and heuristics.
"""

from finder import web_search
import re, time, random


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sleep():
    """Polite delay between searches."""
    time.sleep(random.uniform(1.0, 2.0))


def _safe_search(query: str, max_results: int = 15) -> list[dict]:
    """Run web_search wrapped in try/except so we never crash."""
    try:
        return web_search(query, max_results=max_results)
    except Exception as e:
        print(f"[researcher] search failed: {e}")
        return []


def _source(result: dict) -> dict:
    """Normalise a search result into a source dict."""
    return {
        "title": result.get("title", ""),
        "url": result.get("url", ""),
        "snippet": result.get("snippet", ""),
    }


# ---------------------------------------------------------------------------
# Salary extraction
# ---------------------------------------------------------------------------

def _extract_salary_numbers(text: str) -> list[int]:
    """
    Pull every dollar-amount we can find out of *text* and return them
    as a sorted list of annual integers.

    Handles:
      $120k  $120K  $120,000  $1,200,000
      $120k-$180k  $120K - $180K  $120,000-$180,000
      $120k to $180k
      120k-180k  (no dollar sign but has 'k')
      $55 to $85 per hour  /  $55/hr  /  $55 per hour
      $120,000 per year  /  $120,000/year  /  $120,000/yr
      $120,000 - $180,000 a year
      $120k/year  $120k per year
    """
    numbers: list[int] = []

    # ---- Pattern 1: $XXXk or XXXk (with or without dollar sign) ----------
    # Matches: $120k, $120K, 120k, $85.5k
    for m in re.finditer(
        r"\$?\s*(\d{2,4}(?:\.\d{1,2})?)\s*[kK]", text
    ):
        val = float(m.group(1))
        # Sanity: if the number is below 10 it's probably not a salary
        if val >= 10:
            numbers.append(int(val * 1000))

    # ---- Pattern 2: $XXX,XXX (comma-separated full amounts) -------------
    # Matches: $120,000  $1,200,000  $85,500
    for m in re.finditer(
        r"\$\s*(\d{1,3}(?:,\d{3})+)", text
    ):
        raw = m.group(1).replace(",", "")
        val = int(raw)
        if val >= 10_000:
            numbers.append(val)

    # ---- Pattern 3: $XXX (plain integer, no comma, no k) ----------------
    # Only treat as salary if followed by per year / /year / per annum / annually
    for m in re.finditer(
        r"\$\s*(\d{3,9})\s*(?:per\s+year|/year|/yr|per\s+annum|annually|a\s+year)",
        text, re.IGNORECASE,
    ):
        val = int(m.group(1))
        if val >= 10_000:
            numbers.append(val)

    # ---- Pattern 4: hourly → annual ($XX to $XX per hour, $XX/hr) -------
    hourly_pattern = (
        r"\$\s*(\d{2,4}(?:\.\d{1,2})?)"        # first amount
        r"(?:\s*(?:to|-|–|—)\s*"                 # optional range separator
        r"\$?\s*(\d{2,4}(?:\.\d{1,2})?))?"      # optional second amount
        r"\s*(?:per\s+hour|/hr|/hour|an\s+hour)" # hourly indicator
    )
    for m in re.finditer(hourly_pattern, text, re.IGNORECASE):
        for g in [m.group(1), m.group(2)]:
            if g:
                hourly = float(g)
                if 10 <= hourly <= 500:
                    numbers.append(int(hourly * 2080))  # 40h * 52w

    # Deduplicate and sort
    numbers = sorted(set(numbers))

    # Final sanity filter: keep only plausible annual salaries
    numbers = [n for n in numbers if 15_000 <= n <= 5_000_000]

    return numbers


def _format_range(numbers: list[int]) -> str:
    """Turn a sorted list of salary ints into a readable range string."""
    if not numbers:
        return "Not found"
    low = numbers[0]
    high = numbers[-1]
    def _fmt(n: int) -> str:
        if n % 1000 == 0:
            return f"${n // 1000}k"
        return f"${n:,}"
    if low == high:
        return _fmt(low)
    return f"{_fmt(low)}-{_fmt(high)}"


# ---------------------------------------------------------------------------
# 1. Salary research
# ---------------------------------------------------------------------------

def research_salary(title: str, company: str, location: str = None) -> dict:
    """
    Estimate the salary range for a role by running multiple searches
    and extracting dollar amounts from the results.

    Returns:
        {
            "estimated_range": "$120k-$180k" or "Not found",
            "sources": [{"title", "url", "snippet"}, ...],
            "numbers": [sorted list of ints],
        }
    """
    all_sources: list[dict] = []
    all_numbers: list[int] = []
    seen_urls: set[str] = set()

    loc_suffix = f" {location}" if location else ""

    queries = [
        f'"{company}" "{title}" salary{loc_suffix}',
        f'"{title}" salary range 2025 2026{loc_suffix}',
        f'glassdoor "{company}" "{title}" salary{loc_suffix}',
    ]

    for i, q in enumerate(queries):
        results = _safe_search(q, max_results=15)
        for r in results:
            snippet = r.get("snippet", "")
            title_text = r.get("title", "")
            url = r.get("url", "")

            # Extract numbers from both title and snippet
            nums = _extract_salary_numbers(f"{title_text} {snippet}")
            all_numbers.extend(nums)

            # Collect source (deduplicated)
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_sources.append(_source(r))

        if i < len(queries) - 1:
            _sleep()

    all_numbers = sorted(set(all_numbers))

    return {
        "estimated_range": _format_range(all_numbers),
        "sources": all_sources,
        "numbers": all_numbers,
    }


# ---------------------------------------------------------------------------
# 2. Deep company research
# ---------------------------------------------------------------------------

def research_company_deep(company: str) -> dict:
    """
    Build a deep profile of a company by running ~5 themed searches.

    Returns:
        {
            "size": str,
            "funding": str,
            "tech_stack": [str],
            "news": [{"title", "url", "snippet"}],
            "rating": str,
            "culture": [{"title", "url", "snippet"}],
            "competitors": [str],
        }
    """
    result: dict = {
        "size": "Unknown",
        "funding": "Unknown",
        "tech_stack": [],
        "news": [],
        "rating": "Unknown",
        "culture": [],
        "competitors": [],
    }

    seen_urls: set[str] = set()

    def _add_unique(target_list: list, items: list[dict]):
        for r in items:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                target_list.append(_source(r))

    # --- Search 1: size / headcount ---
    try:
        hits = _safe_search(f'"{company}" employees OR headcount OR "company size"', max_results=10)
        for r in hits:
            text = f"{r.get('title', '')} {r.get('snippet', '')}"
            # Look for patterns like "10,000 employees", "500+ employees", "50-100 employees"
            m = re.search(
                r"(\d[\d,]*(?:\+)?(?:\s*(?:to|-|–)\s*\d[\d,]*)?)\s*employees",
                text, re.IGNORECASE,
            )
            if m and result["size"] == "Unknown":
                result["size"] = m.group(0).strip()
                break
    except Exception:
        pass

    _sleep()

    # --- Search 2: funding / valuation ---
    try:
        hits = _safe_search(f'"{company}" funding OR valuation OR "series" OR IPO OR revenue', max_results=10)
        for r in hits:
            text = f"{r.get('title', '')} {r.get('snippet', '')}"
            # Look for funding rounds or valuation mentions
            m = re.search(
                r"(\$[\d,.]+\s*(?:billion|million|B|M)\s*(?:valuation|funding|raised|round|series\s*\w)?)",
                text, re.IGNORECASE,
            )
            if m and result["funding"] == "Unknown":
                result["funding"] = m.group(0).strip()
                break
    except Exception:
        pass

    _sleep()

    # --- Search 3: tech stack / engineering blog ---
    try:
        hits = _safe_search(
            f'"{company}" tech stack OR engineering blog OR "built with" OR architecture',
            max_results=10,
        )
        tech_keywords = [
            "python", "java", "javascript", "typescript", "go", "golang", "rust",
            "c++", "c#", "ruby", "scala", "kotlin", "swift", "php", "elixir",
            "react", "angular", "vue", "next.js", "nuxt", "svelte",
            "node.js", "django", "flask", "fastapi", "spring", "rails",
            "aws", "gcp", "azure", "kubernetes", "docker", "terraform",
            "kafka", "rabbitmq", "redis", "postgresql", "postgres", "mysql",
            "mongodb", "dynamodb", "elasticsearch", "cassandra", "snowflake",
            "spark", "airflow", "flink", "dbt",
            "graphql", "grpc", "rest",
            "datadog", "splunk", "grafana", "prometheus",
            "github", "gitlab", "jenkins", "circleci",
            "machine learning", "pytorch", "tensorflow",
        ]
        found_tech: set[str] = set()
        for r in hits:
            text = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
            for kw in tech_keywords:
                if kw in text:
                    # Capitalise nicely
                    found_tech.add(kw.title() if len(kw) > 3 else kw.upper())
        result["tech_stack"] = sorted(found_tech)
    except Exception:
        pass

    _sleep()

    # --- Search 4: recent news ---
    try:
        hits = _safe_search(f'"{company}" news 2025 2026', max_results=10)
        _add_unique(result["news"], hits)
    except Exception:
        pass

    _sleep()

    # --- Search 5: Glassdoor rating + culture + competitors ---
    try:
        hits = _safe_search(
            f'glassdoor "{company}" rating OR review OR culture', max_results=10
        )
        for r in hits:
            text = f"{r.get('title', '')} {r.get('snippet', '')}"
            # Try to extract a rating like "3.8" or "4.2/5"
            m = re.search(r"(\d\.\d)\s*(?:/\s*5|out of 5|stars?|rating)?", text)
            if m and result["rating"] == "Unknown":
                result["rating"] = f"{m.group(1)}/5"
        _add_unique(result["culture"], hits)
    except Exception:
        pass

    # --- Competitors: try to extract from snippets already collected ---
    try:
        comp_hits = _safe_search(
            f'"{company}" competitors OR "similar companies" OR "alternatives to"',
            max_results=10,
        )
        competitor_names: list[str] = []
        for r in comp_hits:
            text = f"{r.get('title', '')} {r.get('snippet', '')}"
            # Look for comma-separated lists near "competitors" or "alternatives"
            m = re.search(
                r"(?:competitors?|alternatives?|similar\s+(?:companies|to))[\s:]+([^.]{10,120})",
                text, re.IGNORECASE,
            )
            if m:
                chunk = m.group(1)
                # Split on commas and "and"
                parts = re.split(r",\s*|\s+and\s+", chunk)
                for p in parts:
                    name = p.strip().strip(".")
                    # Filter: skip very short/long or generic words
                    if 2 < len(name) < 40 and name.lower() != company.lower():
                        competitor_names.append(name)
        # Deduplicate preserving order
        seen_comp: set[str] = set()
        for c in competitor_names:
            cl = c.lower()
            if cl not in seen_comp:
                seen_comp.add(cl)
                result["competitors"].append(c)
            if len(result["competitors"]) >= 10:
                break
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# 3. Interview research
# ---------------------------------------------------------------------------

def research_interview(company: str, title: str) -> dict:
    """
    Gather real interview questions, process descriptions, and tips
    for a specific role at a specific company.

    Returns:
        {
            "questions": [str],
            "process": str,
            "tips": [str],
            "sources": [{"title", "url", "snippet"}],
        }
    """
    result: dict = {
        "questions": [],
        "process": "Unknown",
        "tips": [],
        "sources": [],
    }

    seen_urls: set[str] = set()
    all_snippets: list[str] = []

    def _collect(hits: list[dict]):
        for r in hits:
            url = r.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                result["sources"].append(_source(r))
            snippet = r.get("snippet", "")
            title_text = r.get("title", "")
            if snippet:
                all_snippets.append(f"{title_text}. {snippet}")

    queries = [
        f'"{company}" "{title}" interview questions',
        f'glassdoor "{company}" interview process "{title}"',
        f'"{company}" interview tips OR "how to prepare" "{title}"',
        f'"{company}" "{title}" interview experience 2025 2026',
    ]

    for i, q in enumerate(queries):
        hits = _safe_search(q, max_results=10)
        _collect(hits)
        if i < len(queries) - 1:
            _sleep()

    # --- Extract interview questions from snippets ---
    question_set: set[str] = set()
    for text in all_snippets:
        # Sentences ending with "?"
        for m in re.finditer(r"([A-Z][^.!?]{10,200}\?)", text):
            q = m.group(1).strip()
            # Skip meta questions like "Looking for..." or "Want to know..."
            if not re.match(r"^(Looking|Want|Need|Ready|Are you|Do you want)", q, re.IGNORECASE):
                ql = q.lower()
                if ql not in question_set:
                    question_set.add(ql)
                    result["questions"].append(q)

        # Numbered questions: "1. Tell me about...", "2) Describe..."
        for m in re.finditer(r"\d+[\.\)]\s*([A-Z][^.!?]{10,200}[.?])", text):
            q = m.group(1).strip()
            ql = q.lower()
            if ql not in question_set:
                question_set.add(ql)
                result["questions"].append(q)

    # Cap to 20 most relevant questions
    result["questions"] = result["questions"][:20]

    # --- Extract process description ---
    process_keywords = [
        "phone screen", "technical interview", "onsite", "on-site",
        "coding challenge", "take-home", "behavioral", "system design",
        "hiring manager", "recruiter call", "panel", "final round",
        "offer", "background check", "stages", "rounds", "steps",
        "whiteboard", "live coding", "pair programming",
    ]
    process_sentences: list[str] = []
    for text in all_snippets:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for s in sentences:
            sl = s.lower()
            if any(kw in sl for kw in process_keywords):
                clean = s.strip()
                if len(clean) > 20 and clean not in process_sentences:
                    process_sentences.append(clean)

    if process_sentences:
        result["process"] = " ".join(process_sentences[:5])

    # --- Extract tips ---
    tip_patterns = [
        r"(?:tip|advice|recommend|suggest|prepare|make sure|focus on|practice|brush up on|be ready)[:\s]+([^.!?]{15,200}[.!])",
        r"([A-Z][^.!?]{15,200}(?:important|crucial|key|essential|helpful|recommended)[^.!?]*[.!])",
    ]
    tip_set: set[str] = set()
    for text in all_snippets:
        for pat in tip_patterns:
            for m in re.finditer(pat, text, re.IGNORECASE):
                tip = m.group(1).strip() if m.lastindex else m.group(0).strip()
                tl = tip.lower()
                if tl not in tip_set and len(tip) > 15:
                    tip_set.add(tl)
                    result["tips"].append(tip)

    # Also grab sentences that contain actionable advice
    advice_verbs = ["prepare", "study", "review", "practice", "learn", "research", "know", "understand", "expect"]
    for text in all_snippets:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for s in sentences:
            sl = s.lower()
            if any(v in sl for v in advice_verbs) and ("interview" in sl or "coding" in sl or "question" in sl):
                clean = s.strip()
                cl = clean.lower()
                if cl not in tip_set and 20 < len(clean) < 300:
                    tip_set.add(cl)
                    result["tips"].append(clean)

    # Cap tips
    result["tips"] = result["tips"][:15]

    return result
