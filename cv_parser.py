"""
CV / Resume parser for Celina's Job Application Toolkit.

Parses raw CV text (or PDF bytes) and returns a dict that matches the profile
schema defined in profile.py.  Uses regex + heuristics — no ML models needed.

Blueprint ``cv_bp`` exposes three POST endpoints:
    /cv/parse-text     — accepts {"text": "..."}
    /cv/parse-pdf      — accepts multipart file upload (field name "file")
    /cv/auto-setup     — parses CV text AND saves the result as the profile
"""

from __future__ import annotations

import io
import re
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from profile import load_profile, save_profile

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Section headers we look for (case-insensitive).  Order matters for matching
# priority when two headers appear on the same line.
_SECTION_HEADERS: list[str] = [
    # Experience
    "work experience",
    "professional experience",
    "employment history",
    "employment",
    "work history",
    "experience",
    # Education
    "education",
    "academic background",
    "qualifications",
    # Skills
    "technical skills",
    "core competencies",
    "key skills",
    "competencies",
    "skills",
    # Languages
    "languages",
    "language skills",
    # Summary / profile
    "professional summary",
    "executive summary",
    "career objective",
    "objective",
    "summary",
    "profile",
    "about me",
    "about",
    # Certifications (not mapped to a profile key but parsed to avoid polluting others)
    "certifications",
    "certificates",
    "licenses",
    "awards",
    "honours",
    "honors",
    "publications",
    "projects",
    "volunteer",
    "interests",
    "hobbies",
    "references",
]

# Map section header keywords to the profile key they correspond to.
_HEADER_TO_KEY: dict[str, str] = {
    "work experience": "experience",
    "professional experience": "experience",
    "employment history": "experience",
    "employment": "experience",
    "work history": "experience",
    "experience": "experience",
    "education": "education",
    "academic background": "education",
    "qualifications": "education",
    "technical skills": "skills",
    "core competencies": "skills",
    "key skills": "skills",
    "competencies": "skills",
    "skills": "skills",
    "languages": "languages",
    "language skills": "languages",
    "professional summary": "summary",
    "executive summary": "summary",
    "career objective": "summary",
    "objective": "summary",
    "summary": "summary",
    "profile": "summary",
    "about me": "summary",
    "about": "summary",
}

# Regex helpers
_EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
)
_PHONE_RE = re.compile(
    r"(?<!\d)"                          # no digit before
    r"(?:\+?\d{1,4}[\s.\-]?)?"         # optional country code
    r"(?:\(?\d{1,5}\)?[\s.\-]?)?"      # optional area code
    r"\d[\d\s.\-]{5,14}\d"             # core number
    r"(?!\d)",                          # no digit after
)
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[a-zA-Z0-9\-_%]+/?",
    re.IGNORECASE,
)
_LOCATION_RE = re.compile(
    r"(?:based\s+in|located\s+in|location\s*[:\-]?|address\s*[:\-]?)\s*"
    r"([A-Z][A-Za-z\s\-'.]+(?:,\s*[A-Z][A-Za-z\s\-'.]+)*)",
    re.IGNORECASE,
)
# Fallback: "City, Country" pattern on a line by itself or after a pipe/bullet
_LOCATION_FALLBACK_RE = re.compile(
    r"^[\s|•\-*]*([A-Z][A-Za-z\-'.]+(?:\s[A-Z][A-Za-z\-'.]+)*"
    r",\s*[A-Z][A-Za-z\-'.]+(?:\s[A-Za-z\-'.]+)*)[\s|•\-*]*$",
    re.MULTILINE,
)

# Date range patterns: "Jan 2020 - Present", "2019-2022", "03/2021 - 12/2023"
_MONTH = r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
_DATE = r"(?:" + _MONTH + r"[\s./\-]*\d{2,4}|\d{1,2}[/.\-]\d{2,4}|\d{4})"
_END = r"(?:" + _MONTH + r"[\s./\-]*\d{2,4}|\d{1,2}[/.\-]\d{2,4}|\d{4}|[Pp]resent|[Cc]urrent|[Nn]ow|[Oo]ngoing)"
_DATE_RANGE_RE = re.compile(
    r"(" + _DATE + r")" + r"\s*[-\u2013\u2014]+\s*" + r"(" + _END + r")",
    re.IGNORECASE,
)

# Bullet / list-item prefix
_BULLET_RE = re.compile(r"^\s*[\-\*\u2022\u25E6\u25AA\u2023\u2043>]\s*")

# Section header line detector — a line that is *just* a header (possibly with
# decoration like dashes, colons, or ALL-CAPS).
def _build_section_re() -> re.Pattern:
    headers_alt = "|".join(re.escape(h) for h in _SECTION_HEADERS)
    return re.compile(
        r"^\s*[\-=_*#]*\s*(?:" + headers_alt + r")\s*[\-=_*#:]*\s*$",
        re.IGNORECASE | re.MULTILINE,
    )

_SECTION_LINE_RE = _build_section_re()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _clean(text: str) -> str:
    """Normalise whitespace but preserve line breaks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # collapse runs of blank lines into at most two
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_bullet(line: str) -> str:
    return _BULLET_RE.sub("", line).strip()


def _is_header_line(line: str) -> Optional[str]:
    """If *line* is a section header, return the normalised header name."""
    stripped = line.strip().strip("-=_*#:").strip()
    low = stripped.lower()
    for h in _SECTION_HEADERS:
        if low == h:
            return h
    return None


def _split_sections(text: str) -> dict[str, str]:
    """Split the CV text into {header_name: body_text}."""
    lines = text.split("\n")
    sections: dict[str, list[str]] = {}
    current_header: Optional[str] = None
    preamble_lines: list[str] = []

    for line in lines:
        header = _is_header_line(line)
        if header is not None:
            current_header = header
            sections.setdefault(current_header, [])
        elif current_header is not None:
            sections[current_header].append(line)
        else:
            preamble_lines.append(line)

    result: dict[str, str] = {"_preamble": "\n".join(preamble_lines).strip()}
    for h, body_lines in sections.items():
        result[h] = "\n".join(body_lines).strip()
    return result


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_email(text: str) -> str:
    m = _EMAIL_RE.search(text)
    return m.group(0) if m else ""


def _extract_phone(text: str) -> str:
    """Return the first plausible phone number found."""
    for m in _PHONE_RE.finditer(text):
        candidate = m.group(0).strip()
        # Filter out things that are clearly years or IDs (4-digit numbers)
        digits_only = re.sub(r"\D", "", candidate)
        if len(digits_only) >= 7:
            return candidate
    return ""


def _extract_linkedin(text: str) -> str:
    m = _LINKEDIN_RE.search(text)
    if m:
        url = m.group(0)
        if not url.startswith("http"):
            url = "https://" + url
        return url.rstrip("/")
    return ""


def _extract_location(text: str) -> str:
    m = _LOCATION_RE.search(text)
    if m:
        return m.group(1).strip().strip(",")
    m = _LOCATION_FALLBACK_RE.search(text)
    if m:
        return m.group(1).strip()
    return ""


def _extract_name(preamble: str) -> tuple[str, str]:
    """Best-effort extraction of name from the CV preamble.

    Strategy: take the first non-empty line that does not look like contact
    info (no '@', no 'linkedin', no digits-heavy content).
    """
    for line in preamble.split("\n"):
        line = line.strip().strip("-=_*#:").strip()
        if not line:
            continue
        # Skip contact-info lines
        if "@" in line or "linkedin" in line.lower():
            continue
        if re.search(r"\d{4,}", line):
            continue
        # Skip lines that look like section headers
        if _is_header_line(line):
            continue
        # Assume this is the name
        parts = line.split()
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], " ".join(parts[1:])
    return "", ""


def _extract_summary(section_text: str) -> str:
    """Clean up a summary/profile/about section."""
    lines = [l.strip() for l in section_text.strip().split("\n") if l.strip()]
    return " ".join(lines)


def _extract_summary_from_preamble(preamble: str, email: str, phone: str, linkedin: str) -> str:
    """If no Summary section header was found, try to pull a paragraph from
    the preamble (skip contact-info lines and the name line)."""
    lines = preamble.split("\n")
    paragraph_lines: list[str] = []
    skipped_name = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if paragraph_lines:
                break  # end of the first paragraph
            continue

        # Skip the name line (first substantive line)
        if not skipped_name and not re.search(r"\d{4,}", stripped) and "@" not in stripped:
            skipped_name = True
            continue

        # Skip contact lines
        if email and email in stripped:
            continue
        if phone and phone in stripped:
            continue
        if linkedin and "linkedin" in stripped.lower():
            continue
        if re.match(r"^[\d\s\+\(\)\-./]+$", stripped):
            continue

        paragraph_lines.append(stripped)

    return " ".join(paragraph_lines).strip()


def _extract_skills(section_text: str) -> list[str]:
    """Extract individual skills from a skills section.

    Handles:
    - Comma-separated lists: "Python, JavaScript, Docker"
    - Bullet lists
    - Category headers:  "Programming: Python, Java, C++"
    """
    skills: list[str] = []
    for line in section_text.split("\n"):
        line = _strip_bullet(line)
        if not line:
            continue
        # Strip optional category header ("Programming Languages: ...")
        if ":" in line:
            _, _, after_colon = line.partition(":")
            line = after_colon.strip() if after_colon.strip() else line

        # Try comma / semicolon / pipe split
        if re.search(r"[,;|]", line):
            for chunk in re.split(r"[,;|]", line):
                s = chunk.strip().strip("-•*").strip()
                if s:
                    skills.append(s)
        else:
            # Single skill per line
            s = line.strip()
            if s and len(s) < 80:
                skills.append(s)

    # Deduplicate preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for s in skills:
        low = s.lower()
        if low not in seen:
            seen.add(low)
            unique.append(s)
    return unique


def _extract_experience(section_text: str) -> list[dict[str, Any]]:
    """Parse an experience section into a list of role dicts.

    Each dict: {title, company, duration, highlights: [str]}

    Heuristic: a new role starts when we see a date range on a line.  The
    non-date portion of that line (and possibly the preceding line) gives
    the title/company.
    """
    entries: list[dict[str, Any]] = []
    lines = section_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue

        # Check for a date range on this line
        dm = _DATE_RANGE_RE.search(line)
        if dm:
            duration = dm.group(0).strip()
            # Remove the date range from the line to get title/company info
            role_line = (line[: dm.start()] + " " + line[dm.end() :]).strip()
            role_line = role_line.strip("|-–—,").strip()

            title = ""
            company = ""

            if role_line:
                # Try splitting on common separators: " at ", " - ", " | ", ","
                for sep in [" at ", " @ "]:
                    if sep in role_line.lower():
                        idx = role_line.lower().index(sep)
                        title = role_line[:idx].strip()
                        company = role_line[idx + len(sep) :].strip()
                        break
                else:
                    # Try pipe, dash, comma
                    parts = re.split(r"\s*[|,]\s*|\s+[\-\u2013\u2014]\s+", role_line, maxsplit=1)
                    if len(parts) == 2:
                        title = parts[0].strip()
                        company = parts[1].strip()
                    else:
                        title = role_line

            # If the previous line has no date and is non-empty, it might be
            # the title or company that was on its own line.
            if (not title or not company) and i > 0:
                prev = lines[i - 1].strip()
                if prev and not _DATE_RANGE_RE.search(prev) and not _BULLET_RE.match(prev):
                    prev_clean = _strip_bullet(prev)
                    if not title:
                        title = prev_clean
                    elif not company:
                        company = prev_clean

            # Collect highlights (bullet lines following the role header)
            highlights: list[str] = []
            i += 1
            while i < len(lines):
                hl = lines[i].strip()
                if not hl:
                    i += 1
                    # A blank line after bullets may still be followed by more
                    # bullets for the same role, but if the *next* non-blank
                    # line has a date range it's a new role.
                    continue
                # If it looks like a new role (has a date range and is NOT a bullet)
                if _DATE_RANGE_RE.search(hl) and not _BULLET_RE.match(hl):
                    break
                # If it's a section header, stop
                if _is_header_line(hl):
                    break
                highlights.append(_strip_bullet(hl))
                i += 1

            entries.append({
                "title": title,
                "company": company,
                "duration": duration,
                "highlights": "\n".join(highlights),
            })
        else:
            i += 1

    return entries


def _extract_education(section_text: str) -> list[dict[str, str]]:
    """Parse an education section.

    Returns list of {degree, school, year}.
    """
    entries: list[dict[str, str]] = []
    lines = [l.strip() for l in section_text.split("\n") if l.strip()]

    # Strategy: group consecutive non-empty lines into blocks separated by
    # blank lines.  Each block is one education entry.
    blocks: list[list[str]] = []
    current_block: list[str] = []
    for line in lines:
        if not line:
            if current_block:
                blocks.append(current_block)
                current_block = []
        else:
            current_block.append(line)
    if current_block:
        blocks.append(current_block)

    # If we only got one block, try to split by date ranges
    if len(blocks) == 1 and len(blocks[0]) > 2:
        new_blocks: list[list[str]] = []
        buf: list[str] = []
        for line in blocks[0]:
            if _DATE_RANGE_RE.search(line) and buf:
                # The date range line belongs to the current entry
                buf.append(line)
                new_blocks.append(buf)
                buf = []
            else:
                buf.append(line)
        if buf:
            new_blocks.append(buf)
        if len(new_blocks) > 1:
            blocks = new_blocks

    for block in blocks:
        combined = " | ".join(block)
        degree = ""
        school = ""
        year = ""

        # Try to find a year or date range
        year_m = re.search(r"\b((?:19|20)\d{2})\b", combined)
        range_m = _DATE_RANGE_RE.search(combined)
        if range_m:
            year = range_m.group(0).strip()
        elif year_m:
            year = year_m.group(1)

        # Look for degree keywords
        degree_kw = re.compile(
            r"((?:Bachelor|Master|Ph\.?D|MBA|B\.?S\.?c?|M\.?S\.?c?|B\.?A\.?|M\.?A\.?|"
            r"B\.?Eng|M\.?Eng|Associate|Diploma|Certificate|Licence|Licencia|"
            r"Doctor(?:ate)?|DUT|BTS|Ing[eé]nieur|Baccalaur[eé]at)"
            r"[^,\n|]*)",
            re.IGNORECASE,
        )
        dm = degree_kw.search(combined)
        if dm:
            degree = dm.group(1).strip().strip("|-–—,").strip()

        # The school is typically the line or portion that is NOT the degree
        # and NOT just a year.
        for line in block:
            line_clean = _strip_bullet(line)
            if not line_clean:
                continue
            if degree and degree.lower() in line_clean.lower():
                continue
            if year and line_clean.strip() == year.strip():
                continue
            if re.match(r"^[\d\s\-/–—]+$", line_clean):
                continue
            if not school:
                # Remove date portion if present
                school_candidate = _DATE_RANGE_RE.sub("", line_clean).strip()
                school_candidate = re.sub(r"\b(?:19|20)\d{2}\b", "", school_candidate).strip()
                school_candidate = school_candidate.strip("|-–—,").strip()
                if school_candidate:
                    school = school_candidate

        # Fallback: if we couldn't isolate degree vs school, just store the
        # combined text.
        if not degree and not school:
            full = " ".join(block).strip()
            degree = full

        entries.append({
            "degree": degree,
            "school": school,
            "year": year,
        })

    return entries


def _extract_languages(section_text: str) -> list[str]:
    """Extract language names from a Languages section."""
    langs: list[str] = []
    for line in section_text.split("\n"):
        line = _strip_bullet(line)
        if not line:
            continue
        # "French (native)", "English - Fluent", "German: B2"
        # Split on commas first, then process each chunk
        chunks = re.split(r"[,;]", line) if re.search(r"[,;]", line) else [line]
        for chunk in chunks:
            chunk = chunk.strip()
            if not chunk:
                continue
            # Take just the language name (strip proficiency)
            lang_name = re.split(r"[\(\[\-–—:/]", chunk)[0].strip()
            if lang_name and len(lang_name) < 40:
                langs.append(chunk.strip())  # keep proficiency info
    return langs


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_cv_text(text: str) -> dict:
    """Parse raw CV/resume text and return a dict matching the profile schema.

    Never raises — returns empty strings / lists on failure.
    """
    try:
        return _parse_cv_text_inner(text)
    except Exception:
        # Absolute safety net — never crash.
        return {
            "name": "",
            "last_name": "",
            "email": "",
            "phone": "",
            "linkedin_url": "",
            "summary": "",
            "skills": [],
            "experience": [],
            "education": [],
            "languages": [],
            "location": "",
            "target_roles": [],
            "tone": "professional",
        }


def _parse_cv_text_inner(text: str) -> dict:
    text = _clean(text)
    if not text:
        return parse_cv_text("")  # triggers the except branch → empty profile

    sections = _split_sections(text)
    preamble = sections.get("_preamble", "")

    # --- Contact info (search entire text) ---
    email = _extract_email(text)
    phone = _extract_phone(text)
    linkedin_url = _extract_linkedin(text)
    location = _extract_location(text)

    # If location not found via explicit patterns, search preamble for
    # "City, Country"-style line within first ~10 lines
    if not location:
        top = "\n".join(text.split("\n")[:12])
        location = _extract_location(top)
        if not location:
            m = _LOCATION_FALLBACK_RE.search(top)
            if m:
                loc_candidate = m.group(1)
                # Filter out things that are clearly names (name already extracted)
                if "," in loc_candidate:
                    location = loc_candidate

    # --- Name ---
    first_name, last_name = _extract_name(preamble)

    # --- Summary ---
    summary = ""
    for h in ("professional summary", "executive summary", "summary", "profile",
              "about me", "about", "career objective", "objective"):
        if h in sections:
            summary = _extract_summary(sections[h])
            break
    if not summary:
        summary = _extract_summary_from_preamble(preamble, email, phone, linkedin_url)

    # --- Skills ---
    skills: list[str] = []
    for h in ("technical skills", "core competencies", "key skills", "competencies", "skills"):
        if h in sections:
            skills = _extract_skills(sections[h])
            break

    # --- Experience ---
    experience: list[dict] = []
    for h in ("work experience", "professional experience", "employment history",
              "employment", "work history", "experience"):
        if h in sections:
            experience = _extract_experience(sections[h])
            break

    # --- Education ---
    education: list[dict] = []
    for h in ("education", "academic background", "qualifications"):
        if h in sections:
            education = _extract_education(sections[h])
            break

    # --- Languages ---
    languages: list[str] = []
    for h in ("languages", "language skills"):
        if h in sections:
            languages = _extract_languages(sections[h])
            break

    return {
        "name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "linkedin_url": linkedin_url,
        "summary": summary,
        "skills": skills,
        "experience": experience,
        "education": education,
        "languages": languages,
        "location": location,
        "target_roles": [],
        "tone": "professional",
    }


def parse_cv_pdf(pdf_bytes: bytes) -> dict:
    """Extract text from a PDF resume and parse it.

    Uses *pdfplumber* for high-quality text extraction.  Falls back to
    PyPDF2 if pdfplumber is unavailable.  Returns the same dict as
    ``parse_cv_text``.
    """
    text = ""

    # --- Try pdfplumber first ---
    try:
        import pdfplumber  # type: ignore[import-untyped]

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages_text: list[str] = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            text = "\n\n".join(pages_text)
    except ImportError:
        pass
    except Exception:
        pass  # fall through to PyPDF2

    # --- Fallback: PyPDF2 ---
    if not text:
        try:
            from PyPDF2 import PdfReader  # type: ignore[import-untyped]

            reader = PdfReader(io.BytesIO(pdf_bytes))
            pages_text = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    pages_text.append(page_text)
            text = "\n\n".join(pages_text)
        except ImportError:
            return parse_cv_text("")  # no PDF library available
        except Exception:
            return parse_cv_text("")  # corrupted / unreadable PDF

    return parse_cv_text(text)


# ---------------------------------------------------------------------------
# Flask Blueprint
# ---------------------------------------------------------------------------

cv_bp = Blueprint("cv", __name__, url_prefix="/cv")


@cv_bp.route("/parse-text", methods=["POST"])
def route_parse_text():
    """Accept ``{"text": "..."}`` and return the parsed profile dict."""
    body = request.get_json(silent=True) or {}
    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Missing or empty 'text' field"}), 400
    parsed = parse_cv_text(text)
    return jsonify(parsed)


@cv_bp.route("/parse-pdf", methods=["POST"])
def route_parse_pdf():
    """Accept a multipart file upload (field ``file``) and return parsed profile."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use form field 'file'."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400
    pdf_bytes = file.read()
    if not pdf_bytes:
        return jsonify({"error": "Uploaded file is empty"}), 400
    parsed = parse_cv_pdf(pdf_bytes)
    return jsonify(parsed)


@cv_bp.route("/auto-setup", methods=["POST"])
def route_auto_setup():
    """Parse CV text AND save the result as the user's profile.

    Accepts ``{"text": "..."}``.  Merges the parsed data into the existing
    profile (so that fields the parser cannot detect are preserved).
    """
    body = request.get_json(silent=True) or {}
    text = body.get("text", "")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Missing or empty 'text' field"}), 400

    parsed = parse_cv_text(text)

    # Merge: keep existing profile values for fields the parser left empty.
    existing = load_profile()
    for key, value in parsed.items():
        if value:  # only overwrite if the parser found something
            existing[key] = value

    save_profile(existing)
    return jsonify({"success": True, "profile": existing})
