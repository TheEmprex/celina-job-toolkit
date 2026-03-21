"""
Celina's Job Application Toolkit — Flask Application (v3: Fully Autonomous)
SSE streaming, smart input, one-click everything.
Run: python app.py
"""

import json
import uuid
import re
import threading
import queue
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from generator import generate_all, detect_department_from_title, extract_skills, generate_cover_letter, generate_interview_prep
from scraper import scrape_job_posting
from finder import find_people_stream, research_company, verify_mx, guess_domain, guess_emails_for_person

app = Flask(__name__)

# In-memory job queues for SSE streaming
jobs: dict[str, queue.Queue] = {}
jobs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Smart input parser
# ---------------------------------------------------------------------------

def parse_smart_input(raw: str) -> dict:
    """
    Auto-detect input type:
    - URL → scrape it
    - "Title at Company" → split
    - Just text → treat as company name
    """
    raw = raw.strip()

    # Check if it's a URL
    if re.match(r"^https?://", raw, re.IGNORECASE) or any(
        domain in raw.lower() for domain in [
            "greenhouse.io", "lever.co", "linkedin.com", "indeed.com",
            "workday.com", "jobs.", "careers.", "boards.",
        ]
    ):
        url = raw if raw.startswith("http") else f"https://{raw}"
        # Try to extract company from URL as fallback
        company_from_url = extract_company_from_url(url)
        return {"type": "url", "url": url, "title": "", "company": company_from_url, "description": ""}

    # Check for "Title at Company" or "Title @ Company"
    m = re.match(r"^(.+?)\s+(?:at|@|chez|bei|à)\s+(.+)$", raw, re.IGNORECASE)
    if m:
        return {"type": "title_company", "title": m.group(1).strip(), "company": m.group(2).strip(), "description": "", "url": ""}

    # Fallback: treat as company name
    return {"type": "company_only", "title": "", "company": raw, "description": "", "url": ""}


def extract_company_from_url(url: str) -> str:
    """Extract company name from job board URL patterns."""
    url_lower = url.lower()

    # greenhouse.io/company/... or boards.greenhouse.io/company/...  or job-boards.greenhouse.io/company/...
    m = re.search(r"greenhouse\.io/(\w[\w-]+?)(?:/|$)", url_lower)
    if m and m.group(1) not in ("jobs", "embed"):
        return m.group(1).replace("-", " ").title()

    # jobs.lever.co/company/...
    m = re.search(r"lever\.co/(\w[\w-]+?)(?:/|$)", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # linkedin.com/company/name
    m = re.search(r"linkedin\.com/company/([\w-]+)", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # workday: company.wd5.myworkdayjobs.com or company.myworkdayjobs.com
    m = re.search(r"([\w-]+?)\.(?:wd\d+\.)?myworkdayjobs\.com", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # ashbyhq.com/company or jobs.ashby.io/company
    m = re.search(r"ashby(?:hq)?\.(?:com|io)/([\w-]+)", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # workable.com/company
    m = re.search(r"workable\.com/([\w-]+?)(?:/|$)", url_lower)
    if m and m.group(1) not in ("o", "j"):
        return m.group(1).replace("-", " ").title()
    # apply.workable.com/company
    m = re.search(r"apply\.workable\.com/([\w-]+?)(?:/|$)", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # smartrecruiters: jobs.smartrecruiters.com/Company/
    m = re.search(r"smartrecruiters\.com/([\w-]+?)(?:/|$)", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # companyname.careers.com or jobs.companyname.com or careers.companyname.com
    m = re.search(r"(?:jobs|careers|apply)\.([\w-]+?)\.", url_lower)
    if m:
        name = m.group(1)
        if name not in ("com", "co", "io", "org", "net", "workable"):
            return name.replace("-", " ").title()

    # metacareers.com → Meta
    m = re.search(r"([\w-]+?)careers\.com", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # Generic: try the main domain name
    m = re.search(r"https?://(?:www\.)?([\w-]+)\.", url_lower)
    if m:
        name = m.group(1)
        skip = {"boards", "jobs", "careers", "apply", "greenhouse", "lever",
                "linkedin", "indeed", "glassdoor", "workday", "myworkdayjobs",
                "ashbyhq", "ashby", "workable", "smartrecruiters", "job"}
        if name not in skip:
            return name.replace("-", " ").title()

    return ""


# ---------------------------------------------------------------------------
# Message personalization
# ---------------------------------------------------------------------------

def personalize_messages(person: dict, title: str, company: str, department: str) -> dict:
    name = person["name"]
    first = name.split()[0] if name.split() else "there"
    cat = person["category"]
    their_title = person.get("job_title", "")

    # Connection request (under 300 chars)
    if cat == "recruiter":
        conn = f"Hi {first}! I applied for the {title} role at {company} and saw you're on the recruiting team. I'd love to connect and learn more about the opportunity!"
    elif cat in ("hiring_manager", "leadership"):
        conn = f"Hi {first}! I'm very interested in the {title} role at {company}. I'd love to connect and hear about your team's work. I believe my background could be a great fit!"
    elif cat == "hr":
        conn = f"Hi {first}! I recently applied for the {title} position at {company}. I'd love to connect and learn more about the team and culture!"
    else:
        conn = f"Hi {first}! I'm exploring the {title} role at {company} and would love to hear about your experience on the team. Any insights would be appreciated!"
    if len(conn) > 300:
        conn = conn[:297] + "..."

    # Follow-up
    if cat == "recruiter":
        followup = f"Hi {first},\n\nI recently applied for the {title} position at {company} and wanted to reach out personally. I'm genuinely excited about this opportunity and believe my experience aligns well with what the team is looking for.\n\nWould you have a few minutes for a quick chat? I'd love to learn more about the role and share how I could contribute.\n\nBest regards,\nCelina"
    elif cat in ("hiring_manager", "leadership"):
        followup = f"Hi {first},\n\nI saw the {title} opening at {company} and was immediately drawn to the role. {f'As someone in a {their_title} position, your' if their_title else 'Your'} perspective on the team really interests me.\n\nWould you be open to a brief 15-minute chat? I'd love to learn about the challenges your team is tackling.\n\nWarm regards,\nCelina"
    else:
        followup = f"Hi {first},\n\nThanks for connecting! I'm exploring the {title} role at {company} and would really value your perspective. What's it like working there? Any insight would help me a lot.\n\nBest,\nCelina"

    # Email
    email_subj = f"Inquiry About the {title} Position at {company}"
    email_body = f"Hi {first},\n\nMy name is Celina, and I recently came across the {title} position at {company}. I'm very excited about this opportunity and wanted to reach out directly.\n\nI've done extensive research on {company} and I'm impressed by the team's work. I believe my skills would be a strong fit for this role.\n\nWould you be available for a brief call in the coming days?\n\nBest regards,\nCelina"

    return {
        "connection_request": {"text": conn, "char_count": len(conn)},
        "followup_message": followup,
        "email_subject": email_subj,
        "email_body": email_body,
    }


# ---------------------------------------------------------------------------
# Pipeline (runs in background thread, pushes SSE events to queue)
# ---------------------------------------------------------------------------

def run_pipeline(job_id: str, raw_input: str, q: queue.Queue, openai_key=None, hunter_key=None):
    """Main pipeline: parse → scrape → find people → research → generate."""
    try:
        # Step 1: Parse input
        emit(q, "status", {"step": "parsing", "message": "Analyzing your input..."})
        parsed = parse_smart_input(raw_input)

        # Step 2: Scrape if URL
        if parsed["type"] == "url":
            emit(q, "status", {"step": "scraping", "message": "Fetching job posting..."})
            try:
                scraped = scrape_job_posting(parsed["url"])
                if scraped.get("success"):
                    parsed["title"] = scraped.get("title", "") or parsed["title"]
                    parsed["company"] = scraped.get("company", "") or parsed["company"]
                    parsed["description"] = scraped.get("description", "") or parsed["description"]
                    emit(q, "status", {"step": "scraping", "message": f"Got it: {parsed['title'] or 'job'} at {parsed['company'] or 'company'}"})
                else:
                    emit(q, "status", {"step": "scraping", "message": f"Could not scrape page. Using company from URL: {parsed['company'] or 'unknown'}..."})
            except Exception as e:
                emit(q, "status", {"step": "scraping", "message": f"Scrape failed. Using company from URL: {parsed['company'] or 'unknown'}..."})

        title = parsed["title"] or "General Role"
        company = parsed["company"]
        description = parsed["description"] or f"{title} at {company}"

        if not company:
            emit(q, "app_error", {"message": "Could not determine the company name from this URL. Try typing it as: \"Job Title at Company Name\" instead."})
            q.put(None)
            return

        # Step 3: Analyze job
        emit(q, "status", {"step": "analyzing", "message": "Analyzing job requirements..."})
        extracted = extract_skills(description)
        department = detect_department_from_title(title)
        if department == "General" and extracted["department"] != "General":
            department = extracted["department"]

        job_info = {
            "title": title,
            "company": company,
            "department": department,
            "seniority": extracted["seniority"],
            "key_skills": extracted["tech_skills"][:10],
            "soft_skills": extracted["soft_skills"][:6],
        }
        emit(q, "job_info", job_info)

        # Step 4: Verify email domain
        domain = guess_domain(company)
        mx_result = verify_mx(domain)
        emit(q, "email_verification", mx_result)

        # Step 5: Stream people
        emit(q, "status", {"step": "searching", "message": f"Searching for people at {company}..."})
        people_count = 0
        for person in find_people_stream(company, title, department, hunter_key):
            person["personalized_messages"] = personalize_messages(person, title, company, department)
            emit(q, "person", person)
            people_count += 1
            if people_count % 5 == 0:
                emit(q, "status", {"step": "searching", "message": f"Found {people_count} people so far..."})

        emit(q, "status", {"step": "searching", "message": f"Found {people_count} people total."})

        # Step 6: Company research
        emit(q, "status", {"step": "researching", "message": f"Researching {company}..."})
        research = research_company(company)
        emit(q, "company_research", research)

        # Step 7: Cover letter
        emit(q, "status", {"step": "generating", "message": "Writing cover letter..."})
        result = generate_all(title, company, description, openai_key)
        emit(q, "cover_letter", {"text": result["cover_letter"]})

        # Step 8: Interview prep
        emit(q, "status", {"step": "generating", "message": "Preparing interview questions..."})
        emit(q, "interview_prep", result["interview_prep"])

        # Step 9: Email patterns
        emit(q, "email_patterns", result["email_patterns"])

        # Done
        emit(q, "done", {"total_people": people_count, "title": title, "company": company, "department": department})

    except Exception as e:
        emit(q, "app_error", {"message": str(e)[:500]})
    finally:
        q.put(None)  # sentinel
        # Cleanup after 5 minutes
        threading.Timer(300, lambda: cleanup_job(job_id)).start()


def emit(q: queue.Queue, event_type: str, data: dict):
    q.put({"type": event_type, "data": data})


def cleanup_job(job_id: str):
    with jobs_lock:
        jobs.pop(job_id, None)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/start", methods=["POST"])
def start():
    """Start a new pipeline. Returns a job_id for SSE streaming."""
    data = request.get_json()
    raw_input = (data.get("input") or "").strip()

    if not raw_input:
        return jsonify({"error": "Please enter something."}), 400

    openai_key = (data.get("openai_key") or "").strip() or None
    hunter_key = (data.get("hunter_key") or "").strip() or None

    job_id = str(uuid.uuid4())
    q = queue.Queue()

    with jobs_lock:
        jobs[job_id] = q

    t = threading.Thread(target=run_pipeline, args=(job_id, raw_input, q, openai_key, hunter_key), daemon=True)
    t.start()

    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    """SSE endpoint: stream pipeline events to the client."""
    with jobs_lock:
        q = jobs.get(job_id)

    if not q:
        return Response("event: error\ndata: {\"message\": \"Job not found\"}\n\n", mimetype="text/event-stream")

    def generate():
        while True:
            try:
                event = q.get(timeout=120)
                if event is None:
                    yield f"event: done_stream\ndata: {{}}\n\n"
                    break
                yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
            except queue.Empty:
                yield f"event: keepalive\ndata: {{}}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# Keep old scrape endpoint for manual URL fetch
@app.route("/scrape", methods=["POST"])
def scrape():
    data = request.get_json()
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not url.startswith("http"):
        url = "https://" + url
    return jsonify(scrape_job_posting(url))


if __name__ == "__main__":
    print("\n✨ Celina's Job Toolkit is running!")
    print("👉 Open http://localhost:3000 in your browser\n")
    app.run(host="127.0.0.1", port=3000, threaded=True)
