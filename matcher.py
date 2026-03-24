"""
Profile-vs-job matching engine for Celina's Job Application Toolkit.

Compares a user's profile against a parsed job description and produces:
  - A weighted match score (0-100)
  - Lists of matched / missing skills and keywords
  - Actionable tips to improve the match
  - One-sentence "why this person" explanations for networking contacts
"""

import re
from collections import Counter

from generator import SENIORITY_SIGNALS, DEPARTMENT_MAP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize(text: str) -> str:
    """Lowercase, strip extra whitespace, remove punctuation except hyphens."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s\-/+#.]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def _tokenize(text: str) -> set[str]:
    """Break text into a set of lowercase tokens."""
    return set(re.findall(r"[\w+#./-]+", text.lower()))


def _skill_match(skill: str, token_pool: set[str], raw_text: str) -> bool:
    """Check whether a skill appears in a token pool or the raw text.

    Handles multi-word skills (e.g. 'machine learning') by falling back
    to a substring search in the raw lowercased text.
    """
    normalized_skill = skill.lower().strip()
    # Single-token skill: direct set membership
    if " " not in normalized_skill:
        if normalized_skill in token_pool:
            return True
    # Multi-word or fallback: substring in raw text
    if normalized_skill in raw_text:
        return True
    return False


def _count_keyword_in_text(keyword: str, text: str) -> int:
    """Count occurrences of a keyword (case-insensitive) in text."""
    try:
        return len(re.findall(r"\b" + re.escape(keyword.lower()) + r"\b", text.lower()))
    except re.error:
        return text.lower().count(keyword.lower())


def _profile_text_blob(profile: dict) -> str:
    """Concatenate all meaningful text fields from the profile into one blob."""
    parts = []
    parts.append(profile.get("summary", ""))
    for exp in profile.get("experience", []):
        parts.append(exp.get("title", ""))
        parts.append(exp.get("company", ""))
        parts.append(exp.get("duration", ""))
        for h in exp.get("highlights", []):
            parts.append(h)
    for edu in profile.get("education", []):
        parts.append(edu.get("degree", ""))
        parts.append(edu.get("school", ""))
    parts.extend(profile.get("skills", []))
    parts.extend(profile.get("target_roles", []))
    return " ".join(p for p in parts if p)


def _estimate_experience_years(profile: dict) -> float:
    """Estimate total years of experience from the profile's experience list.

    Parses the 'duration' field looking for patterns like:
        '2 years', '3 yrs', '6 months', '2019 - 2023', 'Jan 2020 - Present'
    Returns a float (e.g. 4.5 years). Defaults to 0 if nothing is parseable.
    """
    total_years = 0.0
    for exp in profile.get("experience", []):
        duration = exp.get("duration", "")
        if not duration:
            continue

        # Try "X year(s)" pattern
        year_match = re.search(r"(\d+)\s*(?:year|yr)s?", duration, re.IGNORECASE)
        month_match = re.search(r"(\d+)\s*(?:month|mo)s?", duration, re.IGNORECASE)

        if year_match or month_match:
            years = int(year_match.group(1)) if year_match else 0
            months = int(month_match.group(1)) if month_match else 0
            total_years += years + months / 12.0
            continue

        # Try "YYYY - YYYY" or "YYYY - Present" pattern
        range_match = re.search(
            r"(\d{4})\s*[-\u2013\u2014]\s*(\d{4}|present|current|now)",
            duration, re.IGNORECASE,
        )
        if range_match:
            start = int(range_match.group(1))
            end_str = range_match.group(2).lower()
            if end_str in ("present", "current", "now"):
                import datetime
                end = datetime.date.today().year
            else:
                end = int(end_str)
            total_years += max(end - start, 0)
            continue

    return total_years


def _seniority_from_years(years: float) -> str:
    """Map experience years to a rough seniority band."""
    if years >= 10:
        return "executive"
    if years >= 5:
        return "senior"
    if years >= 2:
        return "mid"
    return "junior"


def _detect_department_from_roles(target_roles: list[str]) -> set[str]:
    """Return a set of departments that match the user's target roles."""
    departments = set()
    for role in target_roles:
        for pattern, dept in DEPARTMENT_MAP.items():
            if re.search(pattern, role, re.IGNORECASE):
                departments.add(dept)
    return departments


def _score_label(score: int) -> str:
    """Map a 0-100 score to a human-readable label."""
    if score >= 90:
        return "Perfect Match"
    if score >= 70:
        return "Strong Match"
    if score >= 50:
        return "Good Match"
    if score >= 30:
        return "Partial Match"
    return "Low Match"


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def calculate_match_score(profile: dict, extracted: dict, description: str) -> dict:
    """Compare a profile against a parsed job description and return a match result.

    Parameters
    ----------
    profile : dict
        From ``load_profile()`` -- keys: skills, experience, education,
        target_roles, summary (and others).
    extracted : dict
        From ``extract_skills()`` -- keys: tech_skills, soft_skills,
        responsibilities, seniority, department.
    description : str
        The raw job description text.

    Returns
    -------
    dict  with keys: score, label, matched_skills, missing_skills,
          matched_keywords, missing_keywords, tips.
    """

    # ---- Guard: empty / missing profile ---------------------------------
    if not profile or not any(profile.get(k) for k in ("skills", "experience", "summary", "target_roles")):
        return {
            "score": 0,
            "label": "Set up your profile for a match score",
            "matched_skills": [],
            "missing_skills": extracted.get("tech_skills", []),
            "matched_keywords": [],
            "missing_keywords": extracted.get("soft_skills", []),
            "tips": [
                "Fill in your profile with your skills, experience, and target roles to get a personalised match score."
            ],
        }

    # ---- Build lookup structures ----------------------------------------
    profile_blob = _normalize(_profile_text_blob(profile))
    profile_tokens = _tokenize(profile_blob)
    profile_skills_lower = {s.lower().strip() for s in profile.get("skills", [])}

    jd_tech: list[str] = extracted.get("tech_skills", [])
    jd_soft: list[str] = extracted.get("soft_skills", [])
    jd_seniority: str = extracted.get("seniority", "mid")
    jd_department: str = extracted.get("department", "General")

    # ---- 1. Tech skill overlap  (40 %) ----------------------------------
    matched_skills: list[str] = []
    missing_skills: list[str] = []

    for skill in jd_tech:
        skill_lower = skill.lower().strip()
        # Check explicit skills list first, then broader profile text
        if skill_lower in profile_skills_lower or _skill_match(skill, profile_tokens, profile_blob):
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    tech_total = len(jd_tech)
    tech_ratio = len(matched_skills) / tech_total if tech_total else 1.0
    tech_score = tech_ratio * 40  # out of 40

    # ---- 2. Soft skill overlap (20 %) -----------------------------------
    matched_keywords: list[str] = []
    missing_keywords: list[str] = []

    for kw in jd_soft:
        kw_clean = kw.replace(".", " ").strip().lower()
        if _skill_match(kw_clean, profile_tokens, profile_blob):
            matched_keywords.append(kw_clean)
        else:
            missing_keywords.append(kw_clean)

    soft_total = len(jd_soft)
    soft_ratio = len(matched_keywords) / soft_total if soft_total else 1.0
    soft_score = soft_ratio * 20  # out of 20

    # ---- 3. Seniority alignment (15 %) ----------------------------------
    experience_years = _estimate_experience_years(profile)
    profile_seniority = _seniority_from_years(experience_years)

    seniority_order = {"junior": 0, "mid": 1, "senior": 2, "executive": 3}
    profile_level = seniority_order.get(profile_seniority, 1)
    jd_level = seniority_order.get(jd_seniority, 1)
    level_gap = abs(profile_level - jd_level)

    if level_gap == 0:
        seniority_score = 15.0
    elif level_gap == 1:
        seniority_score = 10.0
    elif level_gap == 2:
        seniority_score = 4.0
    else:
        seniority_score = 0.0

    # ---- 4. Department / role alignment (15 %) --------------------------
    target_roles = profile.get("target_roles", [])
    profile_departments = _detect_department_from_roles(target_roles)

    # Also check if any target role text overlaps with the JD title area
    target_tokens = set()
    for role in target_roles:
        target_tokens |= _tokenize(role)

    jd_title_tokens = _tokenize(description.split("\n")[0]) if description else set()

    dept_match = jd_department in profile_departments
    role_word_overlap = bool(target_tokens & jd_title_tokens)

    if dept_match and role_word_overlap:
        dept_score = 15.0
    elif dept_match or role_word_overlap:
        dept_score = 10.0
    elif target_roles:
        # They have targets but none match
        dept_score = 3.0
    else:
        # No target roles specified; neutral
        dept_score = 7.5

    # ---- 5. Keyword density (10 %) --------------------------------------
    # Count how many JD keywords appear in the profile's summary + experience
    jd_keywords: set[str] = set()
    for skill in jd_tech:
        jd_keywords.add(skill.lower())
    for kw in jd_soft:
        jd_keywords.add(kw.replace(".", " ").strip().lower())
    for resp in extracted.get("responsibilities", []):
        for word in _tokenize(resp):
            if len(word) > 3:
                jd_keywords.add(word)

    if jd_keywords:
        hits = sum(1 for kw in jd_keywords if kw in profile_blob)
        density_ratio = min(hits / len(jd_keywords), 1.0)
    else:
        density_ratio = 0.5  # neutral when nothing to compare

    density_score = density_ratio * 10  # out of 10

    # ---- Aggregate -------------------------------------------------------
    raw_score = tech_score + soft_score + seniority_score + dept_score + density_score
    score = max(0, min(100, round(raw_score)))
    label = _score_label(score)

    # ---- Generate tips ---------------------------------------------------
    tips = _build_tips(
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        matched_keywords=matched_keywords,
        missing_keywords=missing_keywords,
        profile=profile,
        extracted=extracted,
        description=description,
        profile_seniority=profile_seniority,
        jd_seniority=jd_seniority,
        jd_department=jd_department,
        dept_match=dept_match,
    )

    return {
        "score": score,
        "label": label,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matched_keywords": matched_keywords,
        "missing_keywords": missing_keywords,
        "tips": tips,
    }


# ---------------------------------------------------------------------------
# Tip generation
# ---------------------------------------------------------------------------

def _build_tips(
    *,
    matched_skills: list[str],
    missing_skills: list[str],
    matched_keywords: list[str],
    missing_keywords: list[str],
    profile: dict,
    extracted: dict,
    description: str,
    profile_seniority: str,
    jd_seniority: str,
    jd_department: str,
    dept_match: bool,
) -> list[str]:
    """Produce 2-4 actionable, personalised tips."""
    tips: list[str] = []

    # Tip: missing high-frequency tech skills
    if missing_skills:
        # Count how many times each missing skill appears in the JD
        skill_freq: list[tuple[str, int]] = []
        for skill in missing_skills:
            count = _count_keyword_in_text(skill, description)
            skill_freq.append((skill, max(count, 1)))
        skill_freq.sort(key=lambda x: x[1], reverse=True)

        top = skill_freq[0]
        if top[1] >= 2:
            tips.append(
                f"Add {top[0].title()} to your profile -- it's mentioned "
                f"{top[1]} time{'s' if top[1] > 1 else ''} in the job description."
            )
        elif len(missing_skills) <= 3:
            names = ", ".join(s.title() for s in missing_skills)
            tips.append(
                f"The JD asks for {names} -- consider adding "
                f"{'them' if len(missing_skills) > 1 else 'it'} to your skills if you have any exposure."
            )
        else:
            top_three = ", ".join(s.title() for s in missing_skills[:3])
            tips.append(
                f"You're missing {len(missing_skills)} required tech skills. "
                f"Prioritise {top_three} -- they feature most prominently."
            )

    # Tip: missing soft skills / keywords
    if missing_keywords and len(tips) < 4:
        kws = ", ".join(k.title() for k in missing_keywords[:3])
        tips.append(
            f"Weave keywords like {kws} into your summary or experience highlights "
            f"to better match this JD."
        )

    # Tip: relevant experience callout
    if matched_skills and profile.get("experience") and len(tips) < 4:
        # Find an experience entry whose highlights or title mention a matched skill
        for exp in profile["experience"]:
            highlights = exp.get("highlights", [])
            if isinstance(highlights, str):
                highlights = [highlights]
            exp_text = " ".join(
                [exp.get("title", ""), exp.get("company", "")] + highlights
            ).lower()
            for skill in matched_skills:
                if skill.lower() in exp_text:
                    company_name = exp.get("company", "your previous company")
                    tips.append(
                        f"Your experience at {company_name} is very relevant to this role "
                        f"-- make sure to highlight your {skill.title()} work in your cover letter."
                    )
                    break
            if len(tips) >= 3:
                break

    # Tip: seniority mismatch
    if profile_seniority != jd_seniority and len(tips) < 4:
        seniority_labels = {
            "junior": "entry-level",
            "mid": "mid-level",
            "senior": "senior",
            "executive": "executive/director-level",
        }
        jd_label = seniority_labels.get(jd_seniority, jd_seniority)
        profile_label = seniority_labels.get(profile_seniority, profile_seniority)
        tips.append(
            f"This role is {jd_label} but your profile reads as {profile_label}. "
            f"Adjust how you frame your experience to match the expected seniority."
        )

    # Tip: department mismatch
    if not dept_match and profile.get("target_roles") and len(tips) < 4:
        tips.append(
            f"This role sits in {jd_department}, which isn't listed among your target roles. "
            f"If you're genuinely interested, add a relevant target role to strengthen the match."
        )

    # Tip: empty profile sections
    if not profile.get("summary") and len(tips) < 4:
        tips.append(
            "Write a profile summary -- it gives the matcher more text to compare "
            "against the JD and boosts your keyword density score."
        )

    if not profile.get("experience") and len(tips) < 4:
        tips.append(
            "Add your work experience to your profile. Even a single entry with "
            "highlights will substantially improve your match score."
        )

    # Ensure we have at least 2 tips
    if len(tips) < 2:
        if matched_skills:
            pct = round(len(matched_skills) / (len(matched_skills) + len(missing_skills)) * 100)
            tips.append(
                f"You match {pct}% of the required tech skills -- that's a solid foundation. "
                f"Focus on filling the gaps to push your score higher."
            )
        else:
            tips.append(
                "Try tailoring your profile's skills list to mirror the exact terms "
                "used in the job description -- even small wording changes help."
            )

    return tips[:4]


# ---------------------------------------------------------------------------
# "Why this person" one-liner
# ---------------------------------------------------------------------------

_CATEGORY_TEMPLATES = {
    "recruiter": (
        "{name} is a recruiter at {company} -- "
        "they can fast-track your application to the hiring manager."
    ),
    "hiring manager": (
        "{name} leads the {department} team -- "
        "impressing them is key to getting hired."
    ),
    "leadership": (
        "{name} is {job_title} at {company} -- "
        "a connection here signals serious interest."
    ),
    "hr": (
        "{name} handles people ops at {company} -- "
        "they can give you insider info on the hiring process."
    ),
    "team member": (
        "{name} is on the {department} team at {company} -- "
        "they can tell you what the day-to-day is really like "
        "and may refer you internally."
    ),
}


def generate_why_this_person(person: dict, title: str, company: str) -> str:
    """Return a 1-sentence explanation of why this contact is valuable.

    Parameters
    ----------
    person : dict
        Must contain *category* (str), *job_title* (str), *name* (str).
    title : str
        The job title being applied for (used to infer department).
    company : str
        The company name.

    Returns
    -------
    str  -- A single, specific sentence.
    """
    name = person.get("name", "This person") or "This person"
    category = (person.get("category", "") or "").lower().strip()
    job_title = person.get("job_title", "") or ""

    # Detect department from the job title being applied for
    department = "the team"
    for pattern, dept in DEPARTMENT_MAP.items():
        if re.search(pattern, title, re.IGNORECASE):
            department = dept.lower()
            break

    # Pick the right template
    template = _CATEGORY_TEMPLATES.get(category)
    if template is None:
        # Fallback: try partial matching on the category string
        for key, tmpl in _CATEGORY_TEMPLATES.items():
            if key in category:
                template = tmpl
                break

    if template is None:
        # Ultimate fallback
        return (
            f"{name} works at {company} -- connecting with them "
            f"could provide valuable insight into the {department} team."
        )

    return template.format(
        name=name,
        company=company,
        department=department,
        job_title=job_title,
    )
