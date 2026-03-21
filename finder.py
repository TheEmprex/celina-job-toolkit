"""
People finder — searches the web for real employees at a company,
extracts LinkedIn profiles, guesses emails, categorizes them.
Streaming version: yields people one by one as they're found.
Also: company research and MX verification.
"""

import re
import time
import random
import urllib.parse
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
# LinkedIn extraction
# ---------------------------------------------------------------------------

def extract_linkedin_person(result: dict) -> Optional[dict]:
    """Extract person info from a LinkedIn search result."""
    url = result.get("url", "")
    title = result.get("title", "")
    snippet = result.get("snippet", "")

    m = re.search(r"linkedin\.com/in/([a-zA-Z0-9\-]+)", url)
    if not m:
        return None

    slug = m.group(1)
    profile_url = f"https://www.linkedin.com/in/{slug}"

    # Parse name and title from search result title
    title_clean = re.sub(r"\s*[\|–\-]\s*LinkedIn.*$", "", title, flags=re.IGNORECASE)
    title_clean = re.sub(r"\s*on LinkedIn.*$", "", title_clean, flags=re.IGNORECASE)
    parts = re.split(r"\s*[\-–]\s*", title_clean, maxsplit=2)

    name = parts[0].strip() if parts else ""
    job_title = parts[1].strip() if len(parts) >= 2 else ""

    name = re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"^\d+\.\s*", "", name)

    if not name or len(name) < 3 or len(name.split()) < 2:
        return None

    # Skip non-person names (job titles, generic words, etc.)
    skip_exact = {"linkedin", "recruiter", "manager", "engineer", "company", "jobs", "principal", "search", "director", "head"}
    if name.lower().strip() in skip_exact:
        return None
    # Skip if any word in name is a job-title word (e.g. "Recruiter, GTM" or "Senior Engineer")
    title_words = {"recruiter", "recruiting", "manager", "engineer", "director", "coordinator",
                   "specialist", "analyst", "consultant", "lead", "head", "chief", "officer",
                   "president", "associate", "intern", "senior", "junior", "principal", "staff",
                   "vp", "gtm", "hr", "talent"}
    name_words = {w.lower().strip(",.:") for w in name.split()}
    if name_words & title_words:
        return None

    combined = f"{job_title} {snippet}".lower()
    category = categorize_role(combined)

    return {
        "name": name,
        "job_title": job_title,
        "profile_url": profile_url,
        "slug": slug,
        "snippet": snippet[:200],
        "category": category,
    }


def categorize_role(text: str) -> str:
    text = text.lower()
    if any(kw in text for kw in ["recruit", "talent acquisition", "talent partner", "sourcer", "staffing"]):
        return "recruiter"
    elif any(kw in text for kw in ["head of", "director", "vp ", "vice president", "chief", "cto", "cfo", "coo", "svp"]):
        return "leadership"
    elif any(kw in text for kw in ["engineering manager", "team lead", "tech lead", "hiring manager"]):
        return "hiring_manager"
    elif any(kw in text for kw in ["hr ", "human resources", "people ops", "people operations", "people partner"]):
        return "hr"
    else:
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

    try:
        news = web_search(f'"{company}" news 2026 2025', max_results=5)
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
    """
    seen_slugs = set()

    searches = [
        (f'"{company}" recruiter site:linkedin.com/in', "recruiter"),
        (f'"{company}" talent acquisition site:linkedin.com/in', "recruiter"),
        (f'"{company}" hiring manager {department} site:linkedin.com/in', "hiring_manager"),
        (f'"{company}" {department} manager site:linkedin.com/in', "hiring_manager"),
        (f'"{company}" {department} lead site:linkedin.com/in', "hiring_manager"),
        (f'"{company}" {department} site:linkedin.com/in', "team_member"),
        (f'"{company}" HR people site:linkedin.com/in', "hr"),
        (f'"{company}" head of {department} site:linkedin.com/in', "leadership"),
    ]

    total_found = 0
    for i, (query, expected_category) in enumerate(searches):
        try:
            results = web_search(query, max_results=10)
            for r in results:
                person = extract_linkedin_person(r)
                if person and person["slug"] not in seen_slugs:
                    seen_slugs.add(person["slug"])
                    if person["category"] == "team_member" and expected_category != "team_member":
                        person["category"] = expected_category
                    person["emails"] = guess_emails_for_person(person["name"], company)
                    yield person
                    total_found += 1
                    if total_found >= 20:
                        return

            if i < len(searches) - 1:
                time.sleep(random.uniform(1.0, 2.5))
        except Exception as e:
            print(f"[Search error] {e}")
            continue
