"""
People finder — searches the web for real employees at a company,
extracts LinkedIn profiles, guesses emails, categorizes them.
Streaming version: yields people one by one as they're found.
Also: company research and MX verification.
"""

import re
import sys
import time
import random
import urllib.parse
from datetime import datetime
import requests
import dns.resolver
from bs4 import BeautifulSoup
from typing import Optional, Generator


# ---------------------------------------------------------------------------
# Search engines
# ---------------------------------------------------------------------------

def search_ddgs(query: str, max_results: int = 15) -> list[dict]:
    """Search using the ddgs library."""
    try:
        from ddgs import DDGS
        raw = list(DDGS().text(query, max_results=max_results))
        return [{"title": r.get("title", ""), "url": r.get("href", ""), "snippet": r.get("body", "")} for r in raw]
    except Exception as e:
        print(f"[ddgs] {e}")
        return []


def search_startpage(query: str, max_results: int = 15) -> list[dict]:
    """Search Startpage as fallback."""
    results = []
    try:
        resp = requests.post(
            "https://www.startpage.com/sp/search",
            data={"query": query, "cat": "web"},
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"},
            timeout=15,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href*='linkedin.com/in']"):
            href = a.get("href", "")
            parent = a.find_parent(class_=re.compile(r"result|w-gl"))
            snippet = ""
            if parent:
                p = parent.select_one("p")
                if p:
                    snippet = p.get_text(strip=True)
            results.append({"title": a.get_text(strip=True) or href, "url": href, "snippet": snippet})
            if len(results) >= max_results:
                break
    except Exception as e:
        print(f"[Startpage] {e}")
    return results


def web_search(query: str, max_results: int = 15) -> list[dict]:
    """Search using multiple engines with dedup."""
    all_results = []
    seen = set()

    for engine in [search_ddgs, search_startpage]:
        try:
            results = engine(query, max_results)
            for r in results:
                if r["url"] not in seen:
                    seen.add(r["url"])
                    all_results.append(r)
            if len(all_results) >= max_results:
                break
            if len(all_results) < 3:
                time.sleep(random.uniform(0.5, 1.5))
        except Exception:
            continue

    return all_results[:max_results]


# ---------------------------------------------------------------------------
# Name cleaning & validation helpers
# ---------------------------------------------------------------------------

# Words that indicate job titles, not person names
_TITLE_WORDS = frozenset({
    "recruiter", "recruiting", "manager", "engineer", "director", "coordinator",
    "specialist", "analyst", "consultant", "lead", "head", "chief", "officer",
    "president", "associate", "intern", "senior", "junior", "principal", "staff",
    "vp", "gtm", "hr", "talent", "founder", "ceo", "cto", "cfo", "coo", "svp",
    "evp", "partner", "advisor", "architect", "developer", "designer",
    "marketing", "sales", "operations", "finance", "accounting", "legal",
    "program", "product", "project", "executive", "administrator", "supervisor",
    "digital", "revenue", "strategy", "strategic", "global", "regional",
    "commercial", "technical", "clinical", "creative", "communications",
})

# Emoji / special-character pattern (broad Unicode ranges for emoji)
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002700-\U000027BF"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero-width joiner
    "\U00002600-\U000026FF"  # misc symbols
    "\U0000200B-\U0000200F"  # zero-width spaces
    "\U0000202A-\U0000202E"  # bidi controls
    "\U00002060-\U00002064"  # invisible chars
    "\U0000FEFF"             # BOM
    "\U000E0020-\U000E007F"  # tags
    "\U0001F900-\U0001F9FF"  # supplemental symbols
    "\U0001FA00-\U0001FA6F"  # chess symbols
    "\U0001FA70-\U0001FAFF"  # symbols extended
    "]+",
    flags=re.UNICODE,
)


def _clean_name(raw_name: str) -> str:
    """Aggressively clean a name extracted from a LinkedIn search result title."""
    name = raw_name

    # Strip non-ASCII control characters (U+0000-U+001F, U+007F-U+009F)
    name = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", name)

    # Strip emoji and special Unicode characters
    name = _EMOJI_RE.sub(" ", name)

    # Strip parenthetical suffixes: (Ex-Google), (She/Her), (MBA), (he/him), etc.
    name = re.sub(r"\s*\(.*?\)\s*", " ", name)

    # Strip leading numbering like "1." or "12."
    name = re.sub(r"^\d+\.\s*", "", name)

    # Strip trailing " at <Company>" patterns (e.g. "John Smith at UNICEF")
    name = re.sub(r"\s+at\s+\S.*$", "", name, flags=re.IGNORECASE)

    # Strip trailing credential/degree abbreviations after comma: ", MPA", ", MBA", ", PhD", ", PHR", ", CDR"
    name = re.sub(r",\s*[A-Z]{2,5}(?:\s*,\s*[A-Z]{2,5})*\s*$", "", name)

    # Strip trailing punctuation: commas, periods, colons, semicolons, pipes
    name = re.sub(r"[,.\:;|]+\s*$", "", name)

    # Strip leading/trailing quotes, whitespace, dashes, and en-dashes
    name = name.strip(" \t\n\r\"'`\u2013\u2014-")

    # Collapse multiple consecutive spaces
    name = re.sub(r"\s+", " ", name).strip()

    return name


def _is_valid_name(name: str) -> bool:
    """Validate that a cleaned string looks like a real person's name."""
    if not name or len(name) < 3:
        return False

    words = name.split()

    # Must have at least 2 words
    if len(words) < 2:
        return False

    # Each word must be at least 2 characters
    for w in words:
        if len(w) < 2:
            return False

    # No word should be ALL CAPS if 2+ chars (catches acronyms like "HR",
    # "UN", "USA", "NETI", "EMEA" that leaked into the name)
    for w in words:
        stripped = w.strip(",.:;")
        if stripped.isupper() and len(stripped) >= 2:
            return False

    # Reject if any word is an organisational-unit keyword
    _ORG_UNIT_WORDS = frozenset({
        "programme", "program", "team", "unit", "division", "department",
        "office", "center", "centre", "committee", "council", "board",
        "group", "network", "initiative", "service", "services", "academy",
        "institute", "foundation", "organisation", "organization",
        "association",
    })
    lowered_words = [w.lower().strip(",.:;") for w in words]
    if any(w in _ORG_UNIT_WORDS for w in lowered_words):
        return False

    # Reject if EVERY word is a title word (e.g. "Senior Manager")
    if all(w in _TITLE_WORDS for w in lowered_words):
        return False

    # Reject if >60% of words are title/functional words (catches "Digital Marketing and Revenue")
    _FILLER = {"and", "or", "the", "of", "for", "in", "at", "to", "with", "a", "an"}
    functional_count = sum(1 for w in lowered_words if w in _TITLE_WORDS or w in _FILLER)
    if len(lowered_words) >= 3 and functional_count / len(lowered_words) > 0.6:
        return False

    # Reject names ending with "at <Company>" (in case _clean_name didn't
    # fully strip it)
    if re.search(r"\bat\s+\S+$", name, re.IGNORECASE):
        return False

    # Reject the whole name if it exactly matches a known non-name
    skip_exact = {
        "linkedin", "recruiter", "manager", "engineer", "company", "jobs",
        "principal", "search", "director", "head", "profile", "people",
    }
    if name.lower().strip() in skip_exact:
        return False

    return True


def _try_extract_name_from_title(first_part: str, job_title_part: str) -> str:
    """
    If the first 'name' word looks like a title word (e.g. the search result
    title was 'Recruiter, GTM - Sarah Johnson - Company'), try to recover
    the real name from later parts.
    """
    words = first_part.split()
    if not words:
        return first_part

    first_word_lower = words[0].lower().strip(",.:;")
    if first_word_lower in _TITLE_WORDS:
        # The 'name' part is probably actually a job title; try the job_title part
        # as a potential name instead
        candidate = _clean_name(job_title_part)
        if _is_valid_name(candidate):
            return candidate

    return first_part


# ---------------------------------------------------------------------------
# LinkedIn extraction
# ---------------------------------------------------------------------------

def extract_linkedin_person(result: dict, company: str = "") -> Optional[dict]:
    """
    Extract person info from a LinkedIn search result.
    Returns None if the result is not a valid person profile.
    If company is provided, validates the person is associated with that company.
    """
    url = result.get("url", "")
    title = result.get("title", "")
    snippet = result.get("snippet", "")

    m = re.search(r"linkedin\.com/in/([a-zA-Z0-9\-]+)", url)
    if not m:
        return None

    slug = m.group(1)
    profile_url = f"https://www.linkedin.com/in/{slug}"

    # ----- Parse name and job title from the search result title -----

    # Strip LinkedIn suffixes: "| LinkedIn", "- LinkedIn", "on LinkedIn", etc.
    title_clean = re.sub(r"\s*[\|]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    title_clean = re.sub(r"\s*[\-\u2013\u2014]\s*LinkedIn.*$", "", title_clean, flags=re.IGNORECASE)
    title_clean = re.sub(r"\s+on\s+LinkedIn.*$", "", title_clean, flags=re.IGNORECASE)
    title_clean = re.sub(r"\s+LinkedIn$", "", title_clean, flags=re.IGNORECASE)
    title_clean = title_clean.strip()

    # Split into name / job_title / rest on dash or en-dash
    parts = re.split(r"\s*[\-\u2013\u2014]\s*", title_clean, maxsplit=2)

    raw_name = parts[0].strip() if parts else ""
    job_title = parts[1].strip() if len(parts) >= 2 else ""

    # Clean the name
    name = _clean_name(raw_name)

    # If the extracted name looks like a title, try swapping with job_title
    if not _is_valid_name(name) and job_title:
        name = _try_extract_name_from_title(name, job_title)
        name = _clean_name(name)

    # If name still starts with a title-like word but has a real name after it,
    # try dropping the leading title words.
    # e.g. "Recruiter, GTM Sarah Johnson" -> "Sarah Johnson"
    if name:
        words = name.split()
        # Find the first word that isn't a title word
        start_idx = 0
        for i, w in enumerate(words):
            if w.lower().strip(",.:;") not in _TITLE_WORDS:
                start_idx = i
                break
        else:
            start_idx = len(words)  # all words are title words

        if start_idx > 0 and start_idx < len(words):
            candidate = " ".join(words[start_idx:])
            candidate = _clean_name(candidate)
            if _is_valid_name(candidate):
                name = candidate

    # Final validation
    if not _is_valid_name(name):
        return None

    # ----- Company validation -----
    company_verified = True
    is_former = False
    if company:
        company_lower = company.lower()
        combined_text = f"{title} {job_title} {snippet}".lower()

        # 1) Word-boundary phrase match (handles "UNICEF France" matching "UNICEF")
        #    Use \b to prevent "Stripe" matching "Pinstripe"
        phrase_pattern = r'\b' + re.escape(company_lower) + r'\b'
        if re.search(phrase_pattern, combined_text):
            company_verified = True
        else:
            # Multi-word company: ALL significant words must appear with word boundaries
            company_words = [w for w in company_lower.split() if len(w) > 2]
            if company_words:
                company_verified = all(
                    re.search(r'\b' + re.escape(cw) + r'\b', combined_text)
                    for cw in company_words
                )
            else:
                # Short words only (e.g. "HP", "3M") — exact boundary match on full name
                company_verified = bool(re.search(phrase_pattern, combined_text))

        # 2) Ex-employee detection
        if company_verified:
            _FORMER_PREFIXES = re.compile(
                r'(?:^|[\s,;|(])'
                r'(?:ex[\-\s]|former\s+|formerly\s+|previously\s+(?:at\s+)?|past\s+|left\s+)'
                + re.escape(company_lower),
                re.IGNORECASE,
            )
            _FORMER_TITLE = re.compile(
                r'(?:^|[\s,;|(])'
                r'(?:ex[\-\s]|former\s+|formerly\s+|previously\s+|past\s+)',
                re.IGNORECASE,
            )
            if _FORMER_PREFIXES.search(combined_text):
                company_verified = False
                is_former = True
            elif _FORMER_TITLE.search(job_title.lower()):
                company_verified = False
                is_former = True

    # ----- Categorize -----
    combined_for_cat = f"{job_title} {snippet}".lower()
    category = categorize_role(combined_for_cat, job_title)

    person = {
        "name": name,
        "job_title": job_title,
        "profile_url": profile_url,
        "slug": slug,
        "snippet": snippet[:200],
        "category": category,
        "company_verified": company_verified,
        "is_former": is_former,
    }

    return person


def categorize_role(text: str, job_title: str = "") -> str:
    """
    Categorize a person's role based on their combined text (job_title + snippet).
    If job_title is empty, examines the text more thoroughly.
    """
    text = text.lower()

    # Recruiter / talent
    if any(kw in text for kw in [
        "recruit", "talent acquisition", "talent partner", "sourcer",
        "staffing", "talent team",
    ]):
        return "recruiter"

    # Leadership
    if any(kw in text for kw in [
        "head of", "director", "vp ", "vice president", "chief",
        "cto", "cfo", "coo", "svp", "evp", "managing director",
        "general manager", "country manager",
    ]):
        return "leadership"

    # Hiring manager
    if any(kw in text for kw in [
        "engineering manager", "team lead", "tech lead", "hiring manager",
        "group manager", "department manager", "program manager",
        "development manager",
    ]):
        return "hiring_manager"

    # HR / People
    if any(kw in text for kw in [
        "hr ", "human resources", "people ops", "people operations",
        "people partner", "people team", "hrbp", "people & culture",
        "employee experience",
    ]):
        return "hr"

    # If job_title is empty, default to team_member rather than guessing wrong
    if not job_title.strip():
        return "team_member"

    return "team_member"


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

KNOWN_DOMAINS = {
    "google": "google.com", "alphabet": "google.com", "meta": "meta.com",
    "facebook": "meta.com", "amazon": "amazon.com", "aws": "amazon.com",
    "apple": "apple.com", "microsoft": "microsoft.com", "netflix": "netflix.com",
    "spotify": "spotify.com", "uber": "uber.com", "airbnb": "airbnb.com",
    "salesforce": "salesforce.com", "stripe": "stripe.com", "linkedin": "linkedin.com",
    "tesla": "tesla.com", "nvidia": "nvidia.com", "intel": "intel.com",
    "ibm": "ibm.com", "oracle": "oracle.com", "adobe": "adobe.com",
    "shopify": "shopify.com", "datadog": "datadoghq.com", "twilio": "twilio.com",
    "square": "squareup.com", "block": "block.xyz", "palantir": "palantir.com",
    "snowflake": "snowflake.com", "databricks": "databricks.com",
    "confluent": "confluent.io", "snap": "snap.com",
    "bytedance": "bytedance.com", "tiktok": "bytedance.com",
    "doordash": "doordash.com", "instacart": "instacart.com",
    "pinterest": "pinterest.com", "reddit": "reddit.com",
    "dropbox": "dropbox.com", "slack": "slack.com", "figma": "figma.com",
    "notion": "makenotion.com", "discord": "discord.com",
    "cloudflare": "cloudflare.com", "elastic": "elastic.co",
    "mongodb": "mongodb.com", "hashicorp": "hashicorp.com",
    "gitlab": "gitlab.com", "github": "github.com",
    "atlassian": "atlassian.com", "lyft": "lyft.com",
    "robinhood": "robinhood.com", "coinbase": "coinbase.com", "plaid": "plaid.com",
}


def guess_domain(company: str) -> str:
    clean = re.sub(r"[^a-z0-9\s]", "", company.lower()).strip()
    if clean in KNOWN_DOMAINS:
        return KNOWN_DOMAINS[clean]
    return re.sub(r"\s+", "", clean) + ".com"


def guess_emails_for_person(name: str, company: str) -> list[str]:
    domain = guess_domain(company)
    parts = name.lower().strip().split()
    if len(parts) < 2:
        return [f"{parts[0]}@{domain}"] if parts else []
    first = re.sub(r"[^a-z]", "", parts[0])
    last = re.sub(r"[^a-z]", "", parts[-1])
    if not first or not last:
        return []
    return [
        f"{first}.{last}@{domain}",
        f"{first}{last}@{domain}",
        f"{first}@{domain}",
        f"{first[0]}{last}@{domain}",
        f"{first}_{last}@{domain}",
    ]


def verify_mx(domain: str) -> dict:
    """Check if domain has valid MX records."""
    try:
        answers = dns.resolver.resolve(domain, "MX")
        records = sorted([(r.preference, str(r.exchange).rstrip(".")) for r in answers])
        return {"domain": domain, "mx_valid": True, "mx_records": [r[1] for r in records[:5]]}
    except Exception:
        return {"domain": domain, "mx_valid": False, "mx_records": []}


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------

def research_company(company: str) -> dict:
    """Search for recent news, funding, culture about a company."""
    result = {"news": [], "funding": [], "culture": []}
    current_year = datetime.now().year

    try:
        news = web_search(f'"{company}" news {current_year} {current_year - 1}', max_results=5)
        result["news"] = [{"title": r["title"], "url": r["url"], "snippet": r["snippet"]} for r in news if r["title"]]
    except Exception:
        pass

    time.sleep(random.uniform(0.5, 1.5))

    try:
        culture = web_search(f'"{company}" culture OR "what it\'s like to work" OR glassdoor review', max_results=5)
        result["culture"] = [{"title": r["title"], "url": r["url"], "snippet": r["snippet"]} for r in culture if r["title"]]
    except Exception:
        pass

    return result


# ---------------------------------------------------------------------------
# Streaming people finder
# ---------------------------------------------------------------------------

def find_people_stream(company: str, title: str, department: str, hunter_key: Optional[str] = None) -> Generator[dict, None, None]:
    """
    Generator that yields people one by one as they're found.
    Each yielded dict has name, job_title, profile_url, emails, category, etc.
    Finds up to 25 people across varied search queries.
    """
    seen_slugs: set[str] = set()
    max_people = 25

    # Build a diverse set of search queries
    searches: list[tuple[str, str]] = [
        # Recruiters / talent
        (f'"{company}" recruiter site:linkedin.com/in', "recruiter"),
        (f'"{company}" talent acquisition site:linkedin.com/in', "recruiter"),
        # Hiring managers
        (f'"{company}" hiring manager {department} site:linkedin.com/in', "hiring_manager"),
        (f'"{company}" {department} manager site:linkedin.com/in', "hiring_manager"),
        (f'"{company}" {department} lead site:linkedin.com/in', "hiring_manager"),
        # Team members
        (f'"{company}" {department} site:linkedin.com/in', "team_member"),
        (f'"{company}" {department} engineer site:linkedin.com/in', "team_member"),
        # HR / people
        (f'"{company}" HR people site:linkedin.com/in', "hr"),
        (f'"{company}" people team site:linkedin.com/in', "hr"),
        # Leadership
        (f'"{company}" head of {department} site:linkedin.com/in', "leadership"),
        (f'"{company}" program director site:linkedin.com/in', "leadership"),
        # Generic / non-site-restricted queries (sometimes yield more results)
        (f'"{company}" {department} team linkedin.com/in', "team_member"),
        (f'"{company}" hiring {department} linkedin.com/in', "hiring_manager"),
        (f'"{company}" team linkedin.com/in', "team_member"),
    ]

    total_found = 0
    for i, (query, expected_category) in enumerate(searches):
        if total_found >= max_people:
            return

        try:
            results = web_search(query, max_results=10)
        except Exception as e:
            print(f"[Search error] query={query!r}: {e}", file=sys.stderr)
            continue

        for r in results:
            if total_found >= max_people:
                return

            try:
                person = extract_linkedin_person(r, company=company)
            except Exception as e:
                print(f"[Extract error] {e}", file=sys.stderr)
                continue

            if not person:
                continue
            if person["slug"] in seen_slugs:
                continue
            # Skip people who don't work at the company or are ex-employees
            if not person.get("company_verified", True):
                continue
            if person.get("is_former", False):
                continue

            seen_slugs.add(person["slug"])

            # If our categorization returned generic "team_member" but the
            # search query was targeted, prefer the expected category
            if person["category"] == "team_member" and expected_category != "team_member":
                person["category"] = expected_category

            # Generate email guesses
            person["emails"] = guess_emails_for_person(person["name"], company)

            yield person
            total_found += 1

        # Polite delay between queries
        if i < len(searches) - 1 and total_found < max_people:
            time.sleep(random.uniform(1.0, 2.5))
