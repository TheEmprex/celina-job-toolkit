"""
Celina's Job Application Toolkit — Flask Application (v4: Full Suite)
SSE streaming, smart input, profile, tracker, exports, salary research, message variants.
Run: python app.py
"""

import json
import uuid
import re
import threading
import queue
import traceback
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from generator import generate_all, detect_department_from_title, extract_skills
from scraper import scrape_job_posting
from finder import find_people_stream, research_company, verify_mx, guess_domain

app = Flask(__name__)

# In-memory job queues for SSE streaming
jobs: dict[str, queue.Queue] = {}
jobs_lock = threading.Lock()

# ---------------------------------------------------------------------------
# Register blueprints (graceful — app works even if modules aren't ready yet)
# ---------------------------------------------------------------------------

try:
    from profile import profile_bp
    app.register_blueprint(profile_bp)
    print("[+] Profile module loaded")
except Exception as e:
    print(f"[-] Profile module not available: {e}")

try:
    from cv_parser import cv_bp
    app.register_blueprint(cv_bp)
    print("[+] CV parser loaded")
except Exception as e:
    print(f"[-] CV parser not available: {e}")

try:
    from tracker import tracker_bp
    app.register_blueprint(tracker_bp)
    print("[+] Tracker module loaded")
except Exception as e:
    print(f"[-] Tracker module not available: {e}")

try:
    from goals import goals_bp
    app.register_blueprint(goals_bp)
    print("[+] Goals module loaded")
except Exception as e:
    print(f"[-] Goals module not available: {e}")

try:
    from job_scanner import scanner_bp
    app.register_blueprint(scanner_bp)
    print("[+] Job scanner loaded")
except Exception as e:
    print(f"[-] Job scanner not available: {e}")

try:
    from exporter import exporter_bp
    app.register_blueprint(exporter_bp)
    print("[+] Exporter module loaded")
except Exception as e:
    print(f"[-] Exporter module not available: {e}")

# Optional modules (imported inside pipeline for flexibility)
def try_import_messages():
    try:
        from messages import generate_message_variants, generate_networking_strategy, generate_followup_sequence
        return generate_message_variants, generate_networking_strategy, generate_followup_sequence
    except Exception:
        return None, None, None

def try_import_researcher():
    try:
        from researcher import research_salary, research_company_deep, research_interview
        return research_salary, research_company_deep, research_interview
    except Exception:
        return None, None, None

def try_import_exporter_cache():
    try:
        from exporter import save_result
        return save_result
    except Exception:
        return None

def try_import_matcher():
    try:
        from matcher import calculate_match_score, generate_why_this_person
        return calculate_match_score, generate_why_this_person
    except Exception:
        return None, None

def try_load_profile():
    try:
        from profile import load_profile, has_profile
        if has_profile():
            return load_profile()
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Smart input parser
# ---------------------------------------------------------------------------

def parse_smart_input(raw: str) -> dict:
    raw = raw.strip()

    if re.match(r"^https?://", raw, re.IGNORECASE) or any(
        domain in raw.lower() for domain in [
            "greenhouse.io", "lever.co", "linkedin.com", "indeed.com",
            "workday.com", "jobs.", "careers.", "boards.",
        ]
    ):
        url = raw if raw.startswith("http") else f"https://{raw}"
        company_from_url = extract_company_from_url(url)
        return {"type": "url", "url": url, "title": "", "company": company_from_url, "description": ""}

    m = re.match(r"^(.+?)\s+(?:at|@|chez|bei|à)\s+(.+)$", raw, re.IGNORECASE)
    if m:
        return {"type": "title_company", "title": m.group(1).strip(), "company": m.group(2).strip(), "description": "", "url": ""}

    return {"type": "company_only", "title": "", "company": raw, "description": "", "url": ""}


def extract_company_from_url(url: str) -> str:
    url_lower = url.lower()

    patterns = [
        (r"greenhouse\.io/(\w[\w-]+?)(?:/|$)", lambda m: m.group(1) not in ("jobs", "embed")),
        (r"lever\.co/(\w[\w-]+?)(?:/|$)", None),
        (r"linkedin\.com/company/([\w-]+)", None),
        (r"([\w-]+?)\.(?:wd\d+\.)?myworkdayjobs\.com", None),
        (r"ashby(?:hq)?\.(?:com|io)/([\w-]+)", None),
        (r"apply\.workable\.com/([\w-]+?)(?:/|$)", None),
        (r"smartrecruiters\.com/([\w-]+?)(?:/|$)", None),
    ]
    for pat, extra_check in patterns:
        m = re.search(pat, url_lower)
        if m:
            if extra_check and not extra_check(m):
                continue
            return m.group(1).replace("-", " ").title()

    # jobs.company.com or careers.company.com
    m = re.search(r"(?:jobs|careers|apply)\.([\w-]+?)\.", url_lower)
    if m and m.group(1) not in ("com", "co", "io", "org", "net", "workable"):
        return m.group(1).replace("-", " ").title()

    # metacareers.com → Meta
    m = re.search(r"([\w-]+?)careers\.com", url_lower)
    if m:
        return m.group(1).replace("-", " ").title()

    # Generic domain
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
# Message personalization (basic fallback, enhanced by messages.py if available)
# ---------------------------------------------------------------------------

def personalize_messages(person: dict, title: str, company: str, department: str,
                         seniority: str = "mid", skills: list = None, profile: dict = None) -> dict:
    """
    Generate messages in a UNIFIED format the frontend can always rely on.
    Returns: {
        connection_requests: [{style, text, char_count}, ...],  # 1-3 variants
        followups: [{style, text}, ...],
        emails: [{style, subject, body}, ...],
    }
    """
    gen_variants, _, gen_sequence = try_import_messages()

    # Try the full variant system first
    if gen_variants:
        try:
            result = gen_variants(person, title, company, department, seniority, skills or [])
            # Validate shape — make sure it has the expected keys
            if "connection_requests" in result and isinstance(result["connection_requests"], list):
                # Also attach follow-up sequence if available
                if gen_sequence:
                    try:
                        result["followup_sequence"] = gen_sequence(person, title, company).get("sequence", [])
                    except Exception:
                        pass
                return result
        except Exception:
            pass

    # Fallback: generate single messages wrapped in the same list format
    name = person["name"]
    first = name.split()[0] if name.split() else "there"
    cat = person["category"]
    sender = "Celina"
    if profile:
        sender = profile.get("name") or sender
        sender_last = profile.get("last_name", "")
        if sender_last:
            sender = f"{sender} {sender_last}"

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

    if cat == "recruiter":
        followup = f"Hi {first},\n\nI recently applied for the {title} position at {company} and wanted to reach out personally. I'm genuinely excited about this opportunity.\n\nWould you have a few minutes for a quick chat?\n\nBest regards,\n{sender}"
    elif cat in ("hiring_manager", "leadership"):
        followup = f"Hi {first},\n\nI saw the {title} opening at {company} and was immediately drawn to the role. Would you be open to a brief 15-minute chat?\n\nWarm regards,\n{sender}"
    else:
        followup = f"Hi {first},\n\nThanks for connecting! I'm exploring the {title} role at {company} and would really value your perspective.\n\nBest,\n{sender}"

    return {
        "connection_requests": [
            {"style": "professional", "text": conn, "char_count": len(conn)},
        ],
        "followups": [
            {"style": "professional", "text": followup},
        ],
        "emails": [
            {"style": "professional", "subject": f"Inquiry About the {title} Position at {company}",
             "body": f"Hi {first},\n\nMy name is {sender}, and I recently came across the {title} position at {company}. I believe my skills would be a strong fit.\n\nWould you be available for a brief call?\n\nBest regards,\n{sender}"},
        ],
        "followup_sequence": [],
    }


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_pipeline(job_id: str, raw_input: str, q: queue.Queue,
                 openai_key=None, hunter_key=None, extra_description="", lang="en"):
    try:
        profile = try_load_profile()
        save_result = try_import_exporter_cache()
        research_salary, research_company_deep, research_interview = try_import_researcher()
        calc_match, gen_why = try_import_matcher()

        _, gen_strategy, gen_sequence = try_import_messages()

        all_people = []
        pipeline_data = {"lang": lang}

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
            except Exception:
                emit(q, "status", {"step": "scraping", "message": f"Scrape failed. Using: {parsed['company'] or 'unknown'}..."})

        title = parsed["title"] or "General Role"
        company = parsed["company"]
        description = parsed["description"] or ""
        # Merge in the extra description pasted by the user
        if extra_description:
            description = (description + "\n\n" + extra_description).strip()
        if not description:
            description = f"{title} at {company}"

        if not company:
            emit(q, "app_error", {"message": "Could not determine the company name. Try: \"Job Title at Company Name\""})
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
        pipeline_data["job"] = job_info
        pipeline_data["title"] = title
        pipeline_data["company"] = company
        pipeline_data["department"] = department
        pipeline_data["url"] = parsed.get("url", "")

        # Step 3b: Match score (if profile exists)
        if calc_match and profile:
            try:
                match = calc_match(profile, extracted, description)
                emit(q, "match_score", match)
                pipeline_data["match_score"] = match
            except Exception:
                pass

        # Step 4: Verify email domain
        domain = guess_domain(company)
        mx_result = verify_mx(domain)
        emit(q, "email_verification", mx_result)

        # Step 5: Stream people
        emit(q, "status", {"step": "searching", "message": f"Searching for people at {company}..."})
        people_count = 0
        for person in find_people_stream(company, title, department, hunter_key):
            person["personalized_messages"] = personalize_messages(
                person, title, company, department,
                extracted["seniority"], extracted["tech_skills"], profile
            )
            # Add "why this person" reasoning
            if gen_why:
                try:
                    person["why"] = gen_why(person, title, company)
                except Exception:
                    pass
            emit(q, "person", person)
            all_people.append(person)
            people_count += 1
            if people_count % 5 == 0:
                emit(q, "status", {"step": "searching", "message": f"Found {people_count} people so far..."})

        emit(q, "status", {"step": "searching", "message": f"Found {people_count} people total."})

        # Step 5b: Networking strategy (if messages.py available)
        if gen_strategy and all_people:
            try:
                strategy = gen_strategy(all_people, title, company)
                emit(q, "networking_strategy", strategy)
                pipeline_data["networking_strategy"] = strategy
            except Exception:
                pass

        # Step 6: Company research (basic)
        emit(q, "status", {"step": "researching", "message": f"Researching {company}..."})
        research = research_company(company)
        emit(q, "company_research", research)
        pipeline_data["company_research"] = research

        # Step 6b: Deep research (salary, interview intel)
        if research_salary:
            try:
                emit(q, "status", {"step": "researching", "message": f"Looking up salary data..."})
                salary = research_salary(title, company)
                emit(q, "salary_data", salary)
                pipeline_data["salary"] = salary
            except Exception:
                pass

        if research_interview:
            try:
                emit(q, "status", {"step": "researching", "message": f"Finding interview questions..."})
                interview_intel = research_interview(company, title)
                emit(q, "interview_intel", interview_intel)
                pipeline_data["interview_intel"] = interview_intel
            except Exception:
                pass

        # Step 7: Cover letter (profile-enhanced)
        emit(q, "status", {"step": "generating", "message": "Writing cover letter..."})
        result = generate_all(title, company, description, openai_key)
        cover_text = result["cover_letter"]

        # Enhance cover letter with profile data
        if profile:
            sender_name = profile.get("name", "Celina")
            sender_last = profile.get("last_name", "")
            full_name = f"{sender_name} {sender_last}".strip() if sender_last else sender_name

            # Replace the placeholder name "Celina" in sign-off lines.
            # Use specific closings to avoid replacing "Celina" if it appears
            # mid-sentence (e.g. in AI-generated text about the user).
            for closing in ("Best regards,", "Warm regards,", "Best,", "Sincerely,", "Kind regards,"):
                cover_text = cover_text.replace(f"{closing}\nCelina", f"{closing}\n{full_name}")

            # If profile has a summary, weave it after the first *body* paragraph
            # (index 0 = greeting, index 1 = first body paragraph, so insert at 2)
            if profile.get("summary"):
                summary = profile["summary"]
                paragraphs = cover_text.split("\n\n")
                if len(paragraphs) > 2:
                    paragraphs.insert(2, summary)
                    cover_text = "\n\n".join(paragraphs)

            # Add contact info footer if available (must come last)
            contact_lines = []
            if profile.get("email"):
                contact_lines.append(profile["email"])
            if profile.get("phone"):
                contact_lines.append(profile["phone"])
            if profile.get("linkedin_url"):
                contact_lines.append(profile["linkedin_url"])
            if contact_lines:
                cover_text += "\n\n" + " | ".join(contact_lines)

        emit(q, "cover_letter", {"text": cover_text})
        pipeline_data["cover_letter"] = cover_text

        # Step 8: Interview prep
        emit(q, "status", {"step": "generating", "message": "Preparing interview questions..."})
        emit(q, "interview_prep", result["interview_prep"])
        pipeline_data["interview_prep"] = result["interview_prep"]

        # Step 9: Email patterns
        emit(q, "email_patterns", result["email_patterns"])
        pipeline_data["email_patterns"] = result["email_patterns"]
        pipeline_data["people"] = all_people

        # Save result to cache for exports
        if save_result:
            try:
                save_result(job_id, pipeline_data)
            except Exception:
                pass

        # Save to tracker
        try:
            from tracker import save_pipeline_result
            save_pipeline_result(pipeline_data)
        except Exception:
            pass

        # Log activity for weekly goals
        try:
            from goals import log_activity
            log_activity("searched", company=company, details=f"Searched for {title} at {company}")
            log_activity("applied", company=company, details=f"Found {people_count} contacts for {title}")
        except Exception:
            pass

        # Done
        emit(q, "done", {
            "total_people": people_count,
            "title": title,
            "company": company,
            "department": department,
            "job_id": job_id,
        })

    except Exception as e:
        traceback.print_exc()
        emit(q, "app_error", {"message": str(e)[:500]})
    finally:
        q.put(None)
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


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/start", methods=["POST"])
def start():
    data = request.get_json()
    raw_input = (data.get("input") or "").strip()
    if not raw_input:
        return jsonify({"error": "Please enter something."}), 400

    openai_key = (data.get("openai_key") or "").strip() or None
    hunter_key = (data.get("hunter_key") or "").strip() or None
    extra_description = (data.get("description") or "").strip()
    lang = (data.get("lang") or "en").strip()

    job_id = str(uuid.uuid4())
    q = queue.Queue()
    with jobs_lock:
        jobs[job_id] = q

    t = threading.Thread(
        target=run_pipeline,
        args=(job_id, raw_input, q, openai_key, hunter_key, extra_description, lang),
        daemon=True,
    )
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/stream/<job_id>")
def stream(job_id):
    with jobs_lock:
        q = jobs.get(job_id)
    if not q:
        return Response("event: app_error\ndata: {\"message\": \"Job not found\"}\n\nevent: done_stream\ndata: {}\n\n", mimetype="text/event-stream")

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
    import os
    port = int(os.environ.get("PORT", 3000))
    print(f"\n✨ Celina's Job Toolkit is running!")
    print(f"👉 Open http://localhost:{port} in your browser\n")
    app.run(host="0.0.0.0", port=port, threaded=True)
