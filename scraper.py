"""
Best-effort job posting scraper.
Handles common job boards: LinkedIn, Greenhouse, Lever, Indeed, Workday.
Falls back to generic HTML extraction.
"""

import re
import requests
from bs4 import BeautifulSoup
from typing import Optional


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
}


def scrape_job_posting(url: str) -> dict:
    """
    Scrape a job posting URL and return title, company, description.
    Returns dict with keys: title, company, description, success, error
    """
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Remove script and style elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()

        # Try platform-specific extraction first
        result = None

        if "greenhouse.io" in url or "boards.greenhouse" in url:
            result = _extract_greenhouse(soup)
        elif "lever.co" in url or "jobs.lever" in url:
            result = _extract_lever(soup)
        elif "linkedin.com" in url:
            result = _extract_linkedin(soup)
        elif "indeed.com" in url:
            result = _extract_indeed(soup)
        elif "myworkdayjobs.com" in url or "workday.com" in url:
            result = _extract_workday(soup)

        # Fallback to generic extraction
        if not result or not result.get("description"):
            result = _extract_generic(soup, url)

        result["success"] = True
        result["url"] = url
        return result

    except requests.RequestException as e:
        return {
            "success": False,
            "error": f"Failed to fetch URL: {str(e)[:200]}",
            "title": "",
            "company": "",
            "description": "",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to parse page: {str(e)[:200]}",
            "title": "",
            "company": "",
            "description": "",
        }


def _extract_greenhouse(soup: BeautifulSoup) -> dict:
    """Extract from Greenhouse job boards."""
    title = ""
    company = ""
    description = ""

    # Title
    h1 = soup.find("h1", class_="app-title") or soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # Company
    company_el = soup.find("span", class_="company-name") or soup.find(class_="company")
    if company_el:
        company = company_el.get_text(strip=True)

    # Description
    content = soup.find("div", id="content") or soup.find("div", class_="content")
    if content:
        description = content.get_text(separator="\n", strip=True)

    return {"title": title, "company": company, "description": description}


def _extract_lever(soup: BeautifulSoup) -> dict:
    """Extract from Lever job pages."""
    title = ""
    company = ""
    description = ""

    h2 = soup.find("h2", class_="posting-headline")
    if h2:
        title = h2.get_text(strip=True)

    # Lever usually has company in the page title
    page_title = soup.find("title")
    if page_title:
        parts = page_title.get_text().split(" - ")
        if len(parts) >= 2:
            company = parts[-1].strip()

    content = soup.find("div", class_="content") or soup.find("div", {"class": re.compile("posting")})
    if content:
        description = content.get_text(separator="\n", strip=True)

    return {"title": title, "company": company, "description": description}


def _extract_linkedin(soup: BeautifulSoup) -> dict:
    """Extract from LinkedIn job postings (limited — often requires auth)."""
    title = ""
    company = ""
    description = ""

    # LinkedIn job pages
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    company_el = soup.find("a", class_="topcard__org-name-link") or soup.find(class_=re.compile("company"))
    if company_el:
        company = company_el.get_text(strip=True)

    desc_el = soup.find("div", class_="description__text") or soup.find(class_=re.compile("description"))
    if desc_el:
        description = desc_el.get_text(separator="\n", strip=True)

    # Fallback to meta tags
    if not title:
        og_title = soup.find("meta", property="og:title")
        if og_title:
            title = og_title.get("content", "")
    if not description:
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            description = og_desc.get("content", "")

    return {"title": title, "company": company, "description": description}


def _extract_indeed(soup: BeautifulSoup) -> dict:
    """Extract from Indeed job postings."""
    title = ""
    company = ""
    description = ""

    h1 = soup.find("h1", class_=re.compile("jobTitle|title"))
    if h1:
        title = h1.get_text(strip=True)

    comp = soup.find(attrs={"data-company-name": True}) or soup.find(class_=re.compile("companyName"))
    if comp:
        company = comp.get_text(strip=True)

    desc = soup.find("div", id="jobDescriptionText") or soup.find(class_=re.compile("jobDescription"))
    if desc:
        description = desc.get_text(separator="\n", strip=True)

    return {"title": title, "company": company, "description": description}


def _extract_workday(soup: BeautifulSoup) -> dict:
    """Extract from Workday job postings."""
    title = ""
    company = ""
    description = ""

    h2 = soup.find("h2", attrs={"data-automation-id": "jobPostingHeader"})
    if h2:
        title = h2.get_text(strip=True)
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    # Workday often has company in URL or breadcrumb
    breadcrumb = soup.find(attrs={"data-automation-id": "breadcrumbs"})
    if breadcrumb:
        company = breadcrumb.get_text(strip=True).split("/")[0].strip()

    desc = soup.find(attrs={"data-automation-id": "jobPostingDescription"})
    if desc:
        description = desc.get_text(separator="\n", strip=True)

    return {"title": title, "company": company, "description": description}


def _extract_generic(soup: BeautifulSoup, url: str) -> dict:
    """Generic extraction fallback."""
    title = ""
    company = ""
    description = ""

    # Title: try h1 first, then page title
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)
    else:
        page_title = soup.find("title")
        if page_title:
            title = page_title.get_text(strip=True)

    # Company: try meta tags, structured data
    for meta in soup.find_all("meta"):
        content = meta.get("content", "")
        name = meta.get("name", "").lower() + meta.get("property", "").lower()
        if "company" in name or "employer" in name or "organization" in name:
            company = content
            break

    # Try JSON-LD structured data
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            import json
            data = json.loads(script.string)
            if isinstance(data, dict):
                if data.get("@type") == "JobPosting":
                    title = title or data.get("title", "")
                    description = description or data.get("description", "")
                    org = data.get("hiringOrganization", {})
                    if isinstance(org, dict):
                        company = company or org.get("name", "")
        except (json.JSONDecodeError, TypeError):
            continue

    # Description: try common selectors
    desc_selectors = [
        {"class_": re.compile(r"job.?description|description|content|posting", re.I)},
        {"id": re.compile(r"job.?description|description|content", re.I)},
        {"role": "main"},
    ]
    for selector in desc_selectors:
        el = soup.find("div", **selector) or soup.find("section", **selector)
        if el:
            text = el.get_text(separator="\n", strip=True)
            if len(text) > 100:
                description = text
                break

    # Last resort: get the largest text block
    if not description:
        all_text = soup.get_text(separator="\n", strip=True)
        if len(all_text) > 200:
            description = all_text[:5000]

    return {"title": title, "company": company, "description": description}
