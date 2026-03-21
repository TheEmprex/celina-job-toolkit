"""
Core generation engine — all 8 generators + NLP-lite keyword extraction.
No API keys required for template-based generation.
"""

import re
import random
import urllib.parse
from typing import Optional

# ---------------------------------------------------------------------------
# Skill & keyword dictionaries
# ---------------------------------------------------------------------------

TECH_SKILLS = [
    "python", "java", "javascript", "typescript", "c\\+\\+", "c#", "go", "golang", "rust",
    "ruby", "php", "swift", "kotlin", "scala", "r\\b", "matlab", "perl",
    "react", "angular", "vue", "next\\.?js", "node\\.?js", "express", "django", "flask",
    "spring", "rails", "laravel", "fastapi", ".net", "asp\\.net",
    "aws", "azure", "gcp", "google cloud", "cloud", "terraform", "ansible",
    "docker", "kubernetes", "k8s", "ci/cd", "jenkins", "github actions", "gitlab",
    "sql", "nosql", "postgresql", "postgres", "mysql", "mongodb", "redis",
    "elasticsearch", "dynamodb", "cassandra", "kafka", "rabbitmq",
    "machine learning", "deep learning", "nlp", "computer vision", "ai",
    "tensorflow", "pytorch", "scikit-learn", "pandas", "numpy",
    "html", "css", "sass", "tailwind", "bootstrap",
    "git", "linux", "unix", "bash", "shell",
    "rest", "graphql", "grpc", "microservices", "api",
    "agile", "scrum", "jira", "confluence",
    "figma", "sketch", "adobe", "photoshop",
    "tableau", "power bi", "looker", "data visualization",
    "spark", "hadoop", "airflow", "dbt", "snowflake", "bigquery", "redshift",
    "excel", "powerpoint", "salesforce", "hubspot", "sap",
    "blockchain", "web3", "solidity",
    "cybersecurity", "security", "oauth", "sso", "encryption",
    "ios", "android", "react native", "flutter", "mobile",
    "testing", "unit test", "integration test", "selenium", "cypress", "jest",
    "devops", "sre", "infrastructure", "monitoring", "observability",
    "grafana", "prometheus", "datadog", "splunk", "new relic",
]

SOFT_SKILLS = [
    "leadership", "communication", "collaboration", "teamwork", "problem.solving",
    "analytical", "critical thinking", "creativity", "innovation", "adaptability",
    "time management", "project management", "stakeholder", "mentoring", "coaching",
    "presentation", "negotiation", "decision.making", "strategic thinking",
    "attention to detail", "customer.focused", "cross.functional", "self.starter",
    "proactive", "autonomous", "fast.paced", "deadline",
]

ACTION_VERBS = [
    "build", "design", "develop", "implement", "create", "lead", "manage",
    "drive", "own", "architect", "deliver", "optimize", "scale", "maintain",
    "collaborate", "partner", "mentor", "define", "establish", "improve",
    "analyze", "evaluate", "research", "investigate", "solve", "troubleshoot",
    "deploy", "automate", "integrate", "monitor", "support", "coordinate",
    "write", "document", "review", "test", "ship", "launch", "iterate",
]

DEPARTMENT_MAP = {
    r"software|engineer|developer|sre|devops|backend|frontend|fullstack|full.stack|platform": "Engineering",
    r"product\s*manager|product\s*owner|product\s*lead": "Product",
    r"design|ux|ui|user experience|user interface|graphic": "Design",
    r"data\s*scientist|data\s*engineer|data\s*analyst|machine\s*learning|ml\b|ai\b|analytics": "Data & Analytics",
    r"marketing|growth|seo|content|brand|social media|digital marketing": "Marketing",
    r"sales|account\s*executive|business\s*development|bdr|sdr|revenue": "Sales",
    r"finance|accounting|controller|treasury|fp&a": "Finance",
    r"human\s*resources|hr\b|people\s*ops|talent|recruiter|recruiting": "People / HR",
    r"operations|supply chain|logistics|procurement": "Operations",
    r"legal|compliance|regulatory|counsel": "Legal",
    r"customer\s*success|customer\s*support|account\s*manager|client": "Customer Success",
    r"security|infosec|cybersec|penetration|threat": "Security",
    r"project\s*manager|program\s*manager|pmo|scrum\s*master": "Project Management",
    r"consultant|advisory|strategy": "Consulting",
    r"research|scientist|r&d": "Research",
    r"qa|quality|test\s*engineer|sdet": "Quality Assurance",
}

SENIORITY_SIGNALS = {
    "senior": ["senior", "sr\\.?", "lead", "principal", "staff", "iii", "iv", "3", "4", "5+"],
    "mid": ["mid", "ii", "2", "intermediate"],
    "junior": ["junior", "jr\\.?", "entry", "associate", "intern", "i\\b", "1", "graduate", "new grad"],
    "executive": ["director", "vp", "vice president", "head of", "chief", "cto", "cfo", "ceo", "coo", "svp", "evp"],
}

# ---------------------------------------------------------------------------
# NLP-lite extraction
# ---------------------------------------------------------------------------

def extract_skills(description: str) -> dict:
    """Extract skills, responsibilities, seniority, department from a job description."""
    text = description.lower()
    text = re.sub(r"<[^>]+>", " ", text)  # strip HTML
    text = re.sub(r"&\w+;", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Extract tech skills
    found_tech = []
    for skill in TECH_SKILLS:
        pattern = r"\b" + skill + r"\b"
        try:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                clean = re.sub(r"\\", "", skill).replace("\\b", "").replace("\\.?", "").replace("\\.",".")
                found_tech.append((clean, len(matches)))
        except re.error:
            continue

    found_tech.sort(key=lambda x: x[1], reverse=True)
    tech_skills = [s[0] for s in found_tech[:15]]

    # Extract soft skills
    found_soft = []
    for skill in SOFT_SKILLS:
        pattern = r"\b" + skill + r"\b"
        try:
            if re.search(pattern, text, re.IGNORECASE):
                clean = skill.replace(".", " ").replace("\\b", "")
                found_soft.append(clean)
        except re.error:
            continue

    # Extract responsibilities (sentences starting with action verbs)
    sentences = re.split(r"[.\n•\-\*]", description)
    responsibilities = []
    for sentence in sentences:
        s = sentence.strip()
        if len(s) < 10:
            continue
        first_word = s.split()[0].lower() if s.split() else ""
        if first_word in ACTION_VERBS:
            responsibilities.append(s)
    responsibilities = responsibilities[:8]

    # Detect seniority
    seniority = "mid"
    for level, signals in SENIORITY_SIGNALS.items():
        for signal in signals:
            if re.search(r"\b" + signal + r"\b", text, re.IGNORECASE):
                seniority = level
                break

    # Detect department
    department = "General"
    for pattern, dept in DEPARTMENT_MAP.items():
        if re.search(pattern, text, re.IGNORECASE):
            department = dept
            break

    return {
        "tech_skills": tech_skills,
        "soft_skills": found_soft[:8],
        "responsibilities": responsibilities,
        "seniority": seniority,
        "department": department,
    }


def detect_department_from_title(title: str) -> str:
    """Detect department from job title alone."""
    for pattern, dept in DEPARTMENT_MAP.items():
        if re.search(pattern, title, re.IGNORECASE):
            return dept
    return "General"


def simplify_title(title: str) -> str:
    """Simplify a job title for use in messages."""
    title = re.sub(r"\b(senior|sr\.?|junior|jr\.?|lead|principal|staff|ii|iii|iv)\b", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+", " ", title).strip(" -,/")
    return title or "professional"


def guess_domain(company: str) -> str:
    """Guess the company's email domain."""
    # Common known mappings
    known = {
        "google": "google.com", "alphabet": "google.com",
        "meta": "meta.com", "facebook": "meta.com",
        "amazon": "amazon.com", "aws": "amazon.com",
        "apple": "apple.com", "microsoft": "microsoft.com",
        "netflix": "netflix.com", "spotify": "spotify.com",
        "uber": "uber.com", "airbnb": "airbnb.com",
        "salesforce": "salesforce.com", "stripe": "stripe.com",
        "twitter": "x.com", "x": "x.com",
        "linkedin": "linkedin.com", "snap": "snap.com",
        "snapchat": "snap.com", "tesla": "tesla.com",
        "nvidia": "nvidia.com", "intel": "intel.com",
        "ibm": "ibm.com", "oracle": "oracle.com",
        "adobe": "adobe.com", "shopify": "shopify.com",
        "datadog": "datadoghq.com", "twilio": "twilio.com",
        "square": "squareup.com", "block": "block.xyz",
        "palantir": "palantir.com", "snowflake": "snowflake.com",
        "databricks": "databricks.com", "confluent": "confluent.io",
    }
    clean = re.sub(r"[^a-z0-9\s]", "", company.lower()).strip()
    if clean in known:
        return known[clean]
    slug = re.sub(r"\s+", "", clean)
    return f"{slug}.com"


def company_slug(company: str) -> str:
    """URL-friendly company slug."""
    return re.sub(r"[^a-z0-9]", "-", company.lower()).strip("-")


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------

def generate_cover_letter(title: str, company: str, description: str, extracted: dict) -> str:
    """Generate a tailored cover letter from templates."""
    skills = extracted["tech_skills"][:5]
    soft = extracted["soft_skills"][:3]
    responsibilities = extracted["responsibilities"][:3]
    seniority = extracted["seniority"]
    department = extracted["department"]

    skills_str = ", ".join(skills) if skills else "the core technologies in your stack"
    soft_str = " and ".join(soft) if soft else "strong communication and collaboration"
    simplified = simplify_title(title)

    # Tone adjustments
    if seniority == "senior" or seniority == "executive":
        experience_line = "With extensive experience in the field"
        impact_line = "I have a proven track record of driving impact at scale"
    elif seniority == "junior":
        experience_line = "As an enthusiastic and fast-learning professional"
        impact_line = "I am eager to contribute and grow within a dynamic team"
    else:
        experience_line = "With solid hands-on experience"
        impact_line = "I have consistently delivered results in fast-paced environments"

    # Build responsibility highlights
    if responsibilities:
        resp_bullets = "\n".join(f"  - {r}" for r in responsibilities[:3])
        resp_section = f"\nI am particularly excited about the responsibilities outlined in this role:\n{resp_bullets}\n\nThese align closely with my experience and what I am passionate about."
    else:
        resp_section = f"\nI am particularly excited about the opportunity to contribute to {company}'s {department.lower()} team and the impact this role can have."

    templates = [
        f"""Dear Hiring Team at {company},

I am writing to express my strong interest in the {title} position at {company}. {experience_line}, I am confident that my background in {skills_str} makes me a strong fit for this role.

{impact_line}, with a particular focus on {soft_str}. {resp_section}

What draws me to {company} is the opportunity to work alongside talented professionals and contribute to meaningful projects. I thrive in environments that value innovation and collaboration, and I am excited about the impact I can make in this role.

I would welcome the opportunity to discuss how my skills and experience can contribute to your team's success. Thank you for considering my application, and I look forward to the possibility of speaking with you.

Best regards,
Celina""",

        f"""Dear {company} Recruiting Team,

I am excited to apply for the {title} role at {company}. {experience_line} in {skills_str}, I believe I bring the right combination of technical expertise and {soft_str} that this position demands.

{impact_line}. Throughout my career, I have developed a deep understanding of {department.lower()} best practices and have consistently sought to go beyond expectations. {resp_section}

I am drawn to {company} because of its reputation for excellence and innovation. I am eager to bring my skills and energy to your team and contribute to the exciting work ahead.

I would love the chance to discuss this role further. Thank you for your time and consideration.

Warm regards,
Celina""",

        f"""Dear Hiring Manager,

The {title} opportunity at {company} immediately caught my attention, and I am thrilled to submit my application. {experience_line} across {skills_str}, I am well-prepared to hit the ground running in this role.

{impact_line}, always with a focus on {soft_str}. I take pride in being someone who not only delivers technically but also elevates the people and processes around me. {resp_section}

{company} stands out to me as a company that values both innovation and its people. I am excited about the prospect of contributing to a team that shares my passion for excellence in {department.lower()}.

I am looking forward to the opportunity to discuss how I can contribute to {company}'s continued success. Thank you for considering my application.

Best,
Celina""",
    ]

    return random.choice(templates)


def generate_linkedin_search_links(company: str, title: str, department: str) -> list[dict]:
    """Generate LinkedIn People search URLs."""
    base = "https://www.linkedin.com/search/results/people/"
    queries = [
        (f'"{company}" recruiter', f"Recruiters at {company}"),
        (f'"{company}" talent acquisition', f"Talent Acquisition at {company}"),
        (f'"{company}" hiring manager', f"Hiring Managers at {company}"),
        (f'"{company}" "{department}" lead', f"{department} Leads at {company}"),
        (f'"{company}" "{department}" manager', f"{department} Managers at {company}"),
        (f'"{company}" "{department}"', f"{department} Team Members at {company}"),
        (f'"{company}" HR', f"HR Team at {company}"),
        (f'"{company}" head of {department.lower()}', f"Head of {department} at {company}"),
    ]

    links = []
    for query, label in queries:
        encoded = urllib.parse.urlencode({"keywords": query, "origin": "GLOBAL_SEARCH_HEADER"})
        links.append({
            "label": label,
            "url": f"{base}?{encoded}",
            "query": query,
        })

    # Add company page search
    slug = company_slug(company)
    links.append({
        "label": f"{company} LinkedIn Company Page",
        "url": f"https://www.linkedin.com/company/{slug}/people/",
        "query": f"{company} company page",
    })

    return links


def generate_connection_messages(title: str, company: str, department: str) -> list[dict]:
    """Generate LinkedIn connection request messages (under 300 chars)."""
    simplified = simplify_title(title)

    messages = [
        {
            "target": "Recruiter",
            "message": f"Hi! I recently applied for the {title} role at {company} and would love to connect. I'd appreciate any insights you might have about the team and role. Looking forward to connecting!",
        },
        {
            "target": "Hiring Manager",
            "message": f"Hi! I'm very interested in the {title} position at {company}. As someone passionate about {department.lower()}, I'd love to learn more about your team's work. Would you be open to a brief chat?",
        },
        {
            "target": "Team Member",
            "message": f"Hi! I'm exploring the {title} role at {company} and would love to hear about your experience on the {department.lower()} team. I'd really appreciate any insights. Looking forward to connecting!",
        },
        {
            "target": "General / Alumni",
            "message": f"Hi! I'm currently exploring opportunities at {company}, specifically the {title} role. I'd love to connect and learn more about the company culture and team. Thanks in advance!",
        },
    ]

    # Trim to 300 chars
    for m in messages:
        if len(m["message"]) > 300:
            m["message"] = m["message"][:297] + "..."
        m["char_count"] = len(m["message"])

    return messages


def generate_followup_templates(title: str, company: str, department: str) -> list[dict]:
    """Generate follow-up / InMail message templates."""
    return [
        {
            "title": "After Applying (Send to Recruiter/HR)",
            "message": f"""Hi [Name],

I hope this message finds you well! I recently submitted my application for the {title} position at {company} and wanted to reach out personally.

I'm genuinely excited about this opportunity — the role aligns perfectly with my background in {department.lower()}, and I've been following {company}'s work with great interest.

I would love the chance to discuss how my experience could contribute to your team. Would you have a few minutes for a quick chat this week or next?

Thank you for your time, and I look forward to hearing from you!

Best regards,
Celina""",
        },
        {
            "title": "After Connecting (Send to Hiring Manager)",
            "message": f"""Hi [Name],

Thank you so much for accepting my connection request! I've been exploring the {title} role at {company} and I'm really impressed by the team's work in {department.lower()}.

I'd love to learn more about the team's current priorities and what you're looking for in this role. Your perspective would be incredibly valuable as I prepare my application.

Would you be open to a 15-minute call at your convenience? I'm happy to work around your schedule.

Thanks again for connecting!

Best,
Celina""",
        },
        {
            "title": "Cold InMail (Send to Team Lead / Manager)",
            "message": f"""Hi [Name],

I hope you don't mind me reaching out — I came across {company}'s {title} opening and was immediately drawn to the role. Your team's work in {department.lower()} really resonates with my professional interests and experience.

I'd love to learn more about the challenges your team is tackling and how I might be able to contribute. I believe my background in {department.lower()} could be a great fit.

If you have a few minutes, I'd truly appreciate the opportunity to chat. No pressure at all — I understand you're busy!

Warm regards,
Celina""",
        },
        {
            "title": "Follow-Up After No Response (1 week later)",
            "message": f"""Hi [Name],

I wanted to follow up on my previous message regarding the {title} position at {company}. I completely understand how busy things can get!

I remain very enthusiastic about this opportunity and would love to connect briefly at your convenience. Even a quick pointer in the right direction would be greatly appreciated.

Thank you for your time, and I hope to hear from you soon!

Best regards,
Celina""",
        },
    ]


def guess_email_patterns(company: str) -> dict:
    """Generate email pattern guesses for a company."""
    domain = guess_domain(company)

    patterns = [
        {"pattern": "first.last", "example": f"celina.lastname@{domain}"},
        {"pattern": "firstlast", "example": f"celinalastname@{domain}"},
        {"pattern": "first", "example": f"celina@{domain}"},
        {"pattern": "flast", "example": f"clasname@{domain}"},
        {"pattern": "first_last", "example": f"celina_lastname@{domain}"},
        {"pattern": "firstl", "example": f"celinal@{domain}"},
        {"pattern": "first-last", "example": f"celina-lastname@{domain}"},
        {"pattern": "last.first", "example": f"lastname.celina@{domain}"},
    ]

    return {
        "domain": domain,
        "patterns": patterns,
        "note": f"The most common corporate pattern is first.last@{domain}. Verify with Hunter.io or email verification tools before sending.",
    }


def generate_google_dorks(company: str, title: str, department: str) -> list[dict]:
    """Generate Google search queries to find employees and emails."""
    domain = guess_domain(company)

    dorks = [
        {
            "label": f"Find {company} employees on LinkedIn",
            "query": f'site:linkedin.com/in "{company}" "{title}"',
        },
        {
            "label": f"Find {company} recruiters on LinkedIn",
            "query": f'site:linkedin.com/in "{company}" recruiter',
        },
        {
            "label": f"Find {company} {department} team on LinkedIn",
            "query": f'site:linkedin.com/in "{company}" "{department}"',
        },
        {
            "label": f"Find {company} email addresses",
            "query": f'"{company}" "@{domain}" email',
        },
        {
            "label": f"Find {company} on GitHub",
            "query": f'site:github.com "{company}"',
        },
        {
            "label": f"Find {company} hiring discussions",
            "query": f'"{company}" "hiring" "{title}" -site:linkedin.com',
        },
        {
            "label": f"Find {company} employee reviews",
            "query": f'"{company}" site:glassdoor.com reviews',
        },
        {
            "label": f"Find {company} team blog / engineering blog",
            "query": f'"{company}" engineering blog OR tech blog OR team blog',
        },
    ]

    for d in dorks:
        encoded = urllib.parse.urlencode({"q": d["query"]})
        d["url"] = f"https://www.google.com/search?{encoded}"

    return dorks


def generate_tool_links(company: str) -> list[dict]:
    """Generate links to useful job search / people-finding tools."""
    domain = guess_domain(company)
    slug = company_slug(company)
    encoded_company = urllib.parse.quote(company)

    return [
        {
            "name": "Hunter.io",
            "description": "Find email addresses and patterns for any company",
            "url": f"https://hunter.io/search/{domain}",
            "icon": "mail",
        },
        {
            "name": "RocketReach",
            "description": "Find emails, phone numbers, and social media profiles",
            "url": f"https://rocketreach.co/company-search?company={encoded_company}",
            "icon": "rocket",
        },
        {
            "name": "Apollo.io",
            "description": "Free B2B contact database with email finder",
            "url": f"https://app.apollo.io/#/people?organizationName={encoded_company}",
            "icon": "users",
        },
        {
            "name": "LinkedIn Company Page",
            "description": "Browse employees, jobs, and company updates",
            "url": f"https://www.linkedin.com/company/{slug}/people/",
            "icon": "linkedin",
        },
        {
            "name": "Glassdoor",
            "description": "Company reviews, salaries, and interview questions",
            "url": f"https://www.glassdoor.com/Search/results.htm?keyword={encoded_company}",
            "icon": "star",
        },
        {
            "name": "Crunchbase",
            "description": "Company funding, investors, and key people",
            "url": f"https://www.crunchbase.com/textsearch?q={encoded_company}",
            "icon": "trending-up",
        },
        {
            "name": "SignalHire",
            "description": "Find personal and work emails, phone numbers",
            "url": f"https://www.signalhire.com/companies/{slug}",
            "icon": "search",
        },
        {
            "name": "Wellfound (AngelList)",
            "description": "Startup jobs, company info, and team pages",
            "url": f"https://wellfound.com/company/{slug}",
            "icon": "briefcase",
        },
    ]


def generate_interview_prep(title: str, company: str, description: str, extracted: dict) -> dict:
    """Generate interview preparation material."""
    skills = extracted["tech_skills"]
    soft = extracted["soft_skills"]
    responsibilities = extracted["responsibilities"]
    seniority = extracted["seniority"]
    department = extracted["department"]

    # Likely technical/role-specific questions
    tech_questions = []
    for skill in skills[:6]:
        tech_questions.append(f"Can you describe your experience with {skill}?")
        tech_questions.append(f"How have you used {skill} to solve a real-world problem?")

    if department == "Engineering":
        tech_questions.extend([
            "Walk me through how you would design a system for [X]. What trade-offs would you consider?",
            "Tell me about a time you had to debug a complex production issue. How did you approach it?",
            "How do you ensure code quality in your projects?",
            "Describe your experience with CI/CD pipelines and deployment strategies.",
        ])
    elif department == "Data & Analytics":
        tech_questions.extend([
            "How do you approach building a data pipeline from scratch?",
            "Tell me about a time your analysis led to a significant business decision.",
            "How do you handle data quality issues?",
        ])
    elif department == "Product":
        tech_questions.extend([
            "How do you prioritize features when resources are limited?",
            "Walk me through how you would launch a new product from 0 to 1.",
            "Tell me about a time you had to say no to a stakeholder. How did you handle it?",
        ])
    elif department == "Marketing":
        tech_questions.extend([
            "How do you measure the success of a marketing campaign?",
            "Tell me about a campaign you ran that exceeded expectations.",
            "How do you stay on top of changing digital marketing trends?",
        ])
    else:
        tech_questions.extend([
            f"What interests you most about the {department.lower()} field?",
            f"How do you stay current with trends in {department.lower()}?",
        ])

    # Behavioral questions
    behavioral = [
        "Tell me about a time you faced a challenging situation at work. How did you handle it?",
        "Describe a time you had to work with someone difficult. What was your approach?",
        "Give an example of a project where you took initiative beyond your assigned responsibilities.",
        "Tell me about a time you failed. What did you learn from it?",
        "How do you handle competing priorities and tight deadlines?",
        "Describe a time you received constructive feedback. How did you respond?",
        "Tell me about your most impactful project. What made it successful?",
    ]

    # STAR prompts
    star_prompts = []
    for skill in skills[:4]:
        star_prompts.append(f"Prepare a STAR story about a time you used {skill} to deliver meaningful results.")
    for soft_skill in soft[:3]:
        star_prompts.append(f"Prepare a STAR story demonstrating your {soft_skill} skills.")
    if responsibilities:
        star_prompts.append(f"Prepare a STAR story about when you had to '{responsibilities[0].lower().strip()}'.")

    # Questions to ask them
    questions_to_ask = [
        f"What does success look like for the {title} role in the first 6 months?",
        f"Can you tell me about the team I would be working with?",
        f"What are the biggest challenges the {department.lower()} team is currently facing?",
        f"How would you describe the culture at {company}?",
        f"What is the growth trajectory for someone in this role?",
        f"How does {company} support professional development and learning?",
        f"What is the team's current tech stack and are there plans to evolve it?",
        f"What does the typical day-to-day look like for this position?",
    ]

    # Research checklist
    research_checklist = [
        f"Visit {company}'s website and understand their products/services",
        f"Read {company}'s 'About Us' and 'Careers' pages",
        f"Check {company}'s recent news and press releases",
        f"Look at {company}'s LinkedIn page for recent updates and culture posts",
        f"Read Glassdoor reviews for {company} (focus on recent ones)",
        f"Research {company}'s competitors and market position",
        f"Look up the interviewer(s) on LinkedIn if known",
        f"Prepare 2-3 specific examples of how your experience matches the job description",
        f"Review common {department} interview questions and practice answers",
        f"Prepare your elevator pitch (30-second self-introduction)",
    ]

    return {
        "key_skills": skills[:10],
        "soft_skills": soft[:6],
        "department": department,
        "seniority": seniority,
        "tech_questions": tech_questions[:10],
        "behavioral_questions": behavioral,
        "star_prompts": star_prompts[:6],
        "questions_to_ask": questions_to_ask,
        "research_checklist": research_checklist,
    }


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def generate_all(title: str, company: str, description: str, openai_key: Optional[str] = None) -> dict:
    """Generate all content for a job application."""
    extracted = extract_skills(description)
    department = detect_department_from_title(title)
    if department == "General" and extracted["department"] != "General":
        department = extracted["department"]

    result = {
        "job": {
            "title": title,
            "company": company,
            "department": department,
            "seniority": extracted["seniority"],
            "key_skills": extracted["tech_skills"][:10],
            "soft_skills": extracted["soft_skills"][:6],
        },
        "cover_letter": generate_cover_letter(title, company, description, extracted),
        "linkedin_search": generate_linkedin_search_links(company, title, department),
        "connection_messages": generate_connection_messages(title, company, department),
        "followup_templates": generate_followup_templates(title, company, department),
        "email_patterns": guess_email_patterns(company),
        "google_dorks": generate_google_dorks(company, title, department),
        "tool_links": generate_tool_links(company),
        "interview_prep": generate_interview_prep(title, company, description, extracted),
    }

    # Optional: AI-powered generation with OpenAI
    if openai_key:
        try:
            result = _enhance_with_ai(result, title, company, description, extracted, department, openai_key)
        except Exception as e:
            result["ai_note"] = f"AI enhancement failed ({str(e)[:100]}). Using template-based generation."

    return result


def _enhance_with_ai(result: dict, title: str, company: str, description: str,
                     extracted: dict, department: str, api_key: str) -> dict:
    """Enhance generation with OpenAI API."""
    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    skills_str = ", ".join(extracted["tech_skills"][:8])
    soft_str = ", ".join(extracted["soft_skills"][:5])

    # AI Cover Letter
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a professional career coach helping a job seeker named Celina write compelling cover letters. Write in first person as Celina. Be confident but not arrogant. Keep it to 3-4 paragraphs. Do not use buzzwords excessively."},
                {"role": "user", "content": f"""Write a tailored cover letter for:
- Role: {title}
- Company: {company}
- Department: {department}
- Key skills required: {skills_str}
- Soft skills: {soft_str}
- Seniority: {extracted['seniority']}

Job description:
{description[:2000]}"""},
            ],
            max_tokens=800,
            temperature=0.7,
        )
        result["cover_letter"] = resp.choices[0].message.content
        result["ai_generated"] = True
    except Exception:
        pass

    # AI Connection Messages
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Generate 4 short LinkedIn connection request messages for a job seeker named Celina. Each must be UNDER 300 characters. Make them natural and personalized. Return them in this exact format:\nRECRUITER: message\nHIRING MANAGER: message\nTEAM MEMBER: message\nGENERAL: message"},
                {"role": "user", "content": f"Role: {title} at {company}, {department} department."},
            ],
            max_tokens=400,
            temperature=0.8,
        )
        text = resp.choices[0].message.content
        targets = {"RECRUITER": "Recruiter", "HIRING MANAGER": "Hiring Manager", "TEAM MEMBER": "Team Member", "GENERAL": "General / Alumni"}
        messages = []
        for line in text.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            for key, target in targets.items():
                if line.upper().startswith(key):
                    msg = line.split(":", 1)[1].strip() if ":" in line else line
                    if len(msg) > 300:
                        msg = msg[:297] + "..."
                    messages.append({"target": target, "message": msg, "char_count": len(msg)})
                    break
        if messages:
            result["connection_messages"] = messages
    except Exception:
        pass

    return result
