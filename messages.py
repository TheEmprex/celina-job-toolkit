"""
Sophisticated message generation engine for job application outreach.

Generates multiple variants of connection requests, follow-ups, emails,
plus networking strategy and follow-up sequences.
"""

import random


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_name(person: dict) -> str:
    """Extract first name from person dict."""
    name = person.get("name", "")
    return name.split()[0] if name.split() else "there"


def _clip(text: str, limit: int = 300) -> str:
    """Ensure text stays under character limit."""
    if len(text) <= limit:
        return text
    # Cut at last space before limit, add ellipsis
    truncated = text[: limit - 3]
    last_space = truncated.rfind(" ")
    if last_space > limit // 2:
        truncated = truncated[:last_space]
    return truncated + "..."


def _skills_phrase(skills: list, max_items: int = 3) -> str:
    """Turn a skills list into a readable phrase like 'Python, React, and AWS'."""
    if not skills:
        return ""
    chosen = skills[:max_items]
    if len(chosen) == 1:
        return chosen[0]
    if len(chosen) == 2:
        return f"{chosen[0]} and {chosen[1]}"
    return ", ".join(chosen[:-1]) + f", and {chosen[-1]}"


def _seniority_adjective(seniority: str) -> str:
    """Map seniority to a descriptor for message tone."""
    mapping = {
        "senior": "seasoned",
        "mid": "solid",
        "junior": "early-career",
        "lead": "experienced",
        "executive": "executive-level",
    }
    return mapping.get((seniority or "").lower(), "")


def _department_angle(department: str) -> str:
    """Return a department-relevant conversation hook."""
    angles = {
        "Engineering": "the technical challenges your team is solving",
        "Product": "how your team shapes the product roadmap",
        "Design": "the design culture and creative process at the company",
        "Data & Analytics": "the data-driven initiatives your team is working on",
        "Marketing": "the marketing strategy and brand direction",
        "Sales": "how the sales team is driving growth",
        "Finance": "the financial strategy and growth trajectory",
        "People / HR": "the company culture and what makes the team special",
        "Operations": "how the team keeps operations running smoothly",
        "Legal": "the legal landscape and compliance challenges you navigate",
        "Customer Success": "how your team delivers value to customers",
        "Security": "the security challenges and initiatives you are tackling",
        "Project Management": "how projects are managed and delivered",
        "Consulting": "the strategic projects you are working on",
        "Research": "the cutting-edge research your team is pursuing",
        "Quality Assurance": "how quality is woven into the development process",
    }
    return angles.get(department, "the exciting work happening at the company")


# ---------------------------------------------------------------------------
# Connection request generators (all must stay under 300 chars)
# ---------------------------------------------------------------------------

def _connection_requests_recruiter(first: str, title: str, company: str, department: str, seniority: str, skills: list) -> list:
    skill_note = f" My background in {_skills_phrase(skills)} aligns well." if skills else ""

    professional = _clip(
        f"Hi {first}, I applied for the {title} role at {company} and noticed you handle recruiting for the team. "
        f"I would love to connect and discuss how my experience could be a great fit.{skill_note}"
    )
    friendly = _clip(
        f"Hey {first}! I came across the {title} opening at {company} and saw you are part of the talent team. "
        f"Would be great to connect and chat about the role!"
    )
    direct = _clip(
        f"Hi {first}, I am actively pursuing the {title} position at {company}. "
        f"As the recruiter for this role, could we connect? I would welcome the chance to share why I am a strong candidate."
    )
    return [
        {"style": "professional", "text": professional, "char_count": len(professional)},
        {"style": "friendly", "text": friendly, "char_count": len(friendly)},
        {"style": "direct", "text": direct, "char_count": len(direct)},
    ]


def _connection_requests_hiring_manager(first: str, title: str, company: str, department: str, seniority: str, skills: list) -> list:
    skill_note = f" with expertise in {_skills_phrase(skills)}" if skills else ""

    professional = _clip(
        f"Hi {first}, I am very interested in the {title} role at {company}. "
        f"As someone leading the team, your perspective would be invaluable. "
        f"I would love to connect and learn about your vision for the role."
    )
    friendly = _clip(
        f"Hey {first}! The {title} position at {company} really caught my eye. "
        f"I am a {department} professional{skill_note} and would love to hear about your team's work!"
    )
    direct = _clip(
        f"Hi {first}, I am applying for the {title} role on your team at {company}. "
        f"I bring strong {department} experience and would appreciate connecting to discuss the opportunity."
    )
    return [
        {"style": "professional", "text": professional, "char_count": len(professional)},
        {"style": "friendly", "text": friendly, "char_count": len(friendly)},
        {"style": "direct", "text": direct, "char_count": len(direct)},
    ]


def _connection_requests_leadership(first: str, title: str, company: str, department: str, seniority: str, skills: list) -> list:
    professional = _clip(
        f"Hi {first}, I am pursuing the {title} role at {company} and admire the direction you have taken the {department} team. "
        f"I would love to connect and learn more about the team's trajectory."
    )
    friendly = _clip(
        f"Hey {first}! I have been following {company}'s growth and the {title} opening excites me. "
        f"Would love to connect and hear your perspective on the team!"
    )
    direct = _clip(
        f"Hi {first}, as a {department} leader at {company}, your insight on the {title} role would mean a lot. "
        f"Could we connect? I am eager to discuss how I can contribute."
    )
    return [
        {"style": "professional", "text": professional, "char_count": len(professional)},
        {"style": "friendly", "text": friendly, "char_count": len(friendly)},
        {"style": "direct", "text": direct, "char_count": len(direct)},
    ]


def _connection_requests_hr(first: str, title: str, company: str, department: str, seniority: str, skills: list) -> list:
    professional = _clip(
        f"Hi {first}, I recently applied for the {title} position at {company}. "
        f"I would love to connect and learn more about the team culture and what makes {company} a great place to work."
    )
    friendly = _clip(
        f"Hey {first}! I am exploring the {title} role at {company} and would love to learn about the culture and team. "
        f"Always great to connect with people who shape the employee experience!"
    )
    direct = _clip(
        f"Hi {first}, I have applied for the {title} role at {company} and wanted to connect with someone on the People team. "
        f"I would appreciate any guidance on the hiring process."
    )
    return [
        {"style": "professional", "text": professional, "char_count": len(professional)},
        {"style": "friendly", "text": friendly, "char_count": len(friendly)},
        {"style": "direct", "text": direct, "char_count": len(direct)},
    ]


def _connection_requests_team_member(first: str, title: str, company: str, department: str, seniority: str, skills: list) -> list:
    skill_note = f" (I also work with {_skills_phrase(skills)})" if skills else ""

    professional = _clip(
        f"Hi {first}, I am applying for the {title} role at {company} and would love an insider perspective on the team. "
        f"Would you be open to connecting?"
    )
    friendly = _clip(
        f"Hey {first}! I am excited about the {title} opening at {company} and noticed we are in the same field. "
        f"Would love to connect and hear about your experience there{skill_note}!"
    )
    direct = _clip(
        f"Hi {first}, I am interested in joining {company} as a {title}. "
        f"As someone on the team, your insight would be really helpful. Happy to connect!"
    )
    return [
        {"style": "professional", "text": professional, "char_count": len(professional)},
        {"style": "friendly", "text": friendly, "char_count": len(friendly)},
        {"style": "direct", "text": direct, "char_count": len(direct)},
    ]


# ---------------------------------------------------------------------------
# Follow-up generators
# ---------------------------------------------------------------------------

def _followups_recruiter(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)
    skills_sentence = f" My background spans {skills_str}, which I believe aligns well with what the team needs." if skills_str else ""

    formal = (
        f"Dear {first},\n\n"
        f"Thank you for connecting. I recently applied for the {title} position at {company} and wanted to "
        f"reach out directly to express my strong interest.{skills_sentence}\n\n"
        f"I would welcome the opportunity to discuss how my qualifications match this role. Would you have 15 minutes "
        f"for a brief call this week or next?\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\nCelina"
    )
    conversational = (
        f"Hi {first}!\n\n"
        f"Thanks so much for accepting my request! I am really excited about the {title} role at {company} "
        f"and wanted to put a face to my application.\n\n"
        f"I have been working in {department} and this opportunity feels like a perfect next step for me. "
        f"Is there anything you think I should highlight in the process?{' I have solid experience with ' + skills_str + '.' if skills_str else ''}\n\n"
        f"Would love to chat whenever works for you!\n\n"
        f"Cheers,\nCelina"
    )
    value_focused = (
        f"Hi {first},\n\n"
        f"Thanks for connecting. I applied for the {title} role and after reviewing the requirements, "
        f"I am confident I can make an immediate impact on the {department} team at {company}.\n\n"
        f"{'Specifically, my work with ' + skills_str + ' has prepared me to hit the ground running. ' if skills_str else ''}"
        f"I would love to walk you through a couple of specific examples of relevant work I have done.\n\n"
        f"Could we find 15 minutes to chat?\n\n"
        f"Best,\nCelina"
    )
    return [
        {"style": "formal", "text": formal},
        {"style": "conversational", "text": conversational},
        {"style": "value_focused", "text": value_focused},
    ]


def _followups_hiring_manager(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)
    title_ref = f"As {their_title}, you" if their_title else "You"

    formal = (
        f"Dear {first},\n\n"
        f"Thank you for connecting. I am writing to express my strong interest in the {title} position at {company}. "
        f"{title_ref} have a unique perspective on what success looks like in this role, and I would value the chance to learn more.\n\n"
        f"{'My experience with ' + skills_str + ' aligns closely with the role requirements. ' if skills_str else ''}"
        f"Would you be open to a brief conversation? I would be grateful for any insight into the team's current priorities.\n\n"
        f"Warm regards,\nCelina"
    )
    conversational = (
        f"Hi {first}!\n\n"
        f"Really appreciate you connecting! I have been diving into everything I can find about {company}'s "
        f"{department} team and the work is genuinely exciting to me.\n\n"
        f"The {title} role feels like a great fit for where I want to take my career. "
        f"I would love to hear about {_department_angle(department)} and what you are looking for in your next hire.\n\n"
        f"Any chance you have 15 minutes this week for a quick chat?\n\n"
        f"Thanks so much,\nCelina"
    )
    value_focused = (
        f"Hi {first},\n\n"
        f"Thanks for connecting. I wanted to share why the {title} role at {company} resonated with me so strongly.\n\n"
        f"{'I bring hands-on experience with ' + skills_str + ', and ' if skills_str else ''}"
        f"I have been working on similar challenges in {department} and have developed approaches that I think "
        f"could bring real value to your team. I would love to share specific examples.\n\n"
        f"Would a brief call work for you?\n\n"
        f"Best,\nCelina"
    )
    return [
        {"style": "formal", "text": formal},
        {"style": "conversational", "text": conversational},
        {"style": "value_focused", "text": value_focused},
    ]


def _followups_leadership(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)

    formal = (
        f"Dear {first},\n\n"
        f"Thank you for connecting. I am reaching out regarding the {title} opening at {company}. "
        f"Your leadership of the {department} function is impressive, and I am drawn to the direction you have set for the team.\n\n"
        f"{'With my background in ' + skills_str + ', I' if skills_str else 'I'} believe I could contribute meaningfully. "
        f"Would you have a few minutes to share your vision for this role?\n\n"
        f"Respectfully,\nCelina"
    )
    conversational = (
        f"Hi {first}!\n\n"
        f"Thanks for accepting my connection. I have been following {company}'s journey and really admire "
        f"what the {department} team has accomplished under your direction.\n\n"
        f"The {title} role is exactly the kind of challenge I am looking for. "
        f"Would love to hear your thoughts on where the team is headed.\n\n"
        f"Thanks,\nCelina"
    )
    value_focused = (
        f"Hi {first},\n\n"
        f"Appreciate the connection. The {title} position at {company} stands out to me because of the team's trajectory.\n\n"
        f"{'My experience with ' + skills_str + ' has given me a strong foundation, and ' if skills_str else ''}"
        f"I have tackled similar {department} challenges and delivered measurable results. "
        f"I would welcome the chance to discuss how I could support your team's goals.\n\n"
        f"Best regards,\nCelina"
    )
    return [
        {"style": "formal", "text": formal},
        {"style": "conversational", "text": conversational},
        {"style": "value_focused", "text": value_focused},
    ]


def _followups_hr(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    formal = (
        f"Dear {first},\n\n"
        f"Thank you for connecting. I recently applied for the {title} role at {company} and wanted to learn more "
        f"about the team and culture from someone who helps shape it every day.\n\n"
        f"I am very enthusiastic about this opportunity and would love any guidance you might offer about "
        f"the hiring timeline or process. I want to make sure I present my best self.\n\n"
        f"Thank you so much,\nCelina"
    )
    conversational = (
        f"Hi {first}!\n\n"
        f"Thanks for connecting! I applied for the {title} position and I am genuinely excited about {company}. "
        f"The culture seems really special and that matters a lot to me.\n\n"
        f"Do you have any tips for standing out in the process? I want to make sure my application truly reflects "
        f"how much I would love to be part of the team.\n\n"
        f"Thanks so much,\nCelina"
    )
    value_focused = (
        f"Hi {first},\n\n"
        f"Thanks for the connection. I applied for the {title} role and after researching {company}'s values "
        f"and culture, I am even more excited about the opportunity.\n\n"
        f"I pride myself on being a collaborative, low-ego team player who adds positive energy to any workplace. "
        f"I think that aligns well with what {company} looks for.\n\n"
        f"Could you share any insight into the next steps?\n\n"
        f"Best,\nCelina"
    )
    return [
        {"style": "formal", "text": formal},
        {"style": "conversational", "text": conversational},
        {"style": "value_focused", "text": value_focused},
    ]


def _followups_team_member(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)

    formal = (
        f"Dear {first},\n\n"
        f"Thank you for connecting. I am exploring the {title} opportunity at {company} and would greatly appreciate "
        f"an insider's perspective on the team and day-to-day work.\n\n"
        f"{'We seem to share a background in ' + skills_str + '. ' if skills_str else ''}"
        f"What has your experience been like at {company}? Any insight would help me a lot.\n\n"
        f"Thanks in advance,\nCelina"
    )
    conversational = (
        f"Hi {first}!\n\n"
        f"Thanks for connecting! I am looking at the {title} role at {company} and figured who better to ask "
        f"than someone already on the team.\n\n"
        f"How do you like working there? What is the team dynamic like? "
        f"{'I noticed we both work with ' + skills_str + ' so I think we speak the same language! ' if skills_str else ''}"
        f"Any honest insight would be really helpful.\n\n"
        f"Cheers,\nCelina"
    )
    value_focused = (
        f"Hi {first},\n\n"
        f"Appreciate the connection! I am interested in the {title} position and I am trying to understand "
        f"what the biggest challenges are for the {department} team at {company} right now.\n\n"
        f"{'I have been working with ' + skills_str + ' and would love to know how those skills play into the daily work. ' if skills_str else ''}"
        f"Would you be open to sharing your thoughts?\n\n"
        f"Thanks,\nCelina"
    )
    return [
        {"style": "formal", "text": formal},
        {"style": "conversational", "text": conversational},
        {"style": "value_focused", "text": value_focused},
    ]


# ---------------------------------------------------------------------------
# Email generators
# ---------------------------------------------------------------------------

def _emails_recruiter(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)

    professional = {
        "style": "professional",
        "subject": f"Application for {title} at {company} - Eager to Connect",
        "body": (
            f"Hi {first},\n\n"
            f"My name is Celina, and I recently applied for the {title} position at {company}. "
            f"I am reaching out because I am genuinely passionate about this opportunity and wanted to introduce myself directly.\n\n"
            f"{'My background includes strong experience with ' + skills_str + ', which I believe aligns well with the role requirements. ' if skills_str else ''}"
            f"I have been working in {department} and this position represents exactly the kind of challenge I thrive on.\n\n"
            f"I would love the chance to discuss my qualifications in more detail. "
            f"Would you have 15-20 minutes for a call this week or next?\n\n"
            f"Thank you for your time and I look forward to hearing from you.\n\n"
            f"Best regards,\nCelina"
        ),
    }
    warm = {
        "style": "warm",
        "subject": f"Excited About the {title} Opportunity at {company}!",
        "body": (
            f"Hi {first},\n\n"
            f"I hope this message finds you well! I am Celina and I just submitted my application for the "
            f"{title} role at {company}. I could not resist reaching out personally because this opportunity "
            f"genuinely excites me.\n\n"
            f"I have been following {company}'s work and really admire what the team is building. "
            f"{'On the technical side, I bring experience with ' + skills_str + ' that I think would translate well. ' if skills_str else ''}"
            f"Beyond the skills, what draws me most is the chance to be part of something meaningful.\n\n"
            f"I would love to chat whenever you have a moment. No pressure at all, just happy to connect!\n\n"
            f"Warmly,\nCelina"
        ),
    }
    direct = {
        "style": "direct",
        "subject": f"{title} Role at {company} - Strong Candidate Reaching Out",
        "body": (
            f"Hi {first},\n\n"
            f"I will keep this brief. I applied for the {title} position at {company} and believe I am a strong fit. "
            f"{'I bring hands-on experience with ' + skills_str + ' and a track record of delivering results in ' + department + '. ' if skills_str else f'I have a solid track record in {department}. '}\n\n"
            f"Three reasons I stand out:\n"
            f"1. Relevant {department} experience with measurable impact\n"
            f"2. {'Technical depth in ' + skills_str if skills_str else 'Strong technical and domain expertise'}\n"
            f"3. Genuine enthusiasm for {company}'s mission and growth\n\n"
            f"I would appreciate 15 minutes of your time. When works best for you?\n\n"
            f"Best,\nCelina"
        ),
    }
    return [professional, warm, direct]


def _emails_hiring_manager(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)
    title_mention = f"As {their_title} at {company}" if their_title else f"As a leader at {company}"

    professional = {
        "style": "professional",
        "subject": f"Interest in the {title} Role on Your Team at {company}",
        "body": (
            f"Hi {first},\n\n"
            f"My name is Celina, and I am writing to express my strong interest in the {title} position at {company}. "
            f"{title_mention}, you have a firsthand understanding of what the role demands, and I wanted to reach out directly.\n\n"
            f"{'My experience spans ' + skills_str + ', and I have applied these skills in ' + department + ' contexts that mirror the challenges your team faces. ' if skills_str else f'I have relevant {department} experience that I believe would translate well to your team. '}"
            f"I am particularly drawn to {_department_angle(department)}.\n\n"
            f"I have submitted my formal application and would welcome the chance to discuss how I could contribute to your team.\n\n"
            f"Thank you for your consideration.\n\n"
            f"Best regards,\nCelina"
        ),
    }
    warm = {
        "style": "warm",
        "subject": f"Would Love to Join Your {department} Team at {company}",
        "body": (
            f"Hi {first},\n\n"
            f"I came across the {title} opening at {company} and it immediately sparked my interest. "
            f"After learning about the work your {department} team is doing, I knew I had to reach out.\n\n"
            f"What excites me most is {_department_angle(department)}. "
            f"{'I have been honing my skills in ' + skills_str + ' and I am eager to bring that experience to a team like yours. ' if skills_str else 'I am eager to bring my experience to a team like yours. '}\n\n"
            f"I would love to hear about what you are looking for in your next hire and share how my background fits.\n\n"
            f"Looking forward to connecting,\nCelina"
        ),
    }
    direct = {
        "style": "direct",
        "subject": f"{title} at {company} - Why I Am the Right Fit",
        "body": (
            f"Hi {first},\n\n"
            f"I applied for the {title} role and want to share directly why I believe I am a strong candidate for your team.\n\n"
            f"{'I bring production-level experience with ' + skills_str + '. ' if skills_str else ''}"
            f"I have worked on similar {department} challenges and consistently delivered results. "
            f"I am not just looking for any role; the work {company} is doing in {department} is what I want to dedicate my energy to.\n\n"
            f"I would be happy to walk through specific examples. Could we find 20 minutes to connect?\n\n"
            f"Best,\nCelina"
        ),
    }
    return [professional, warm, direct]


def _emails_leadership(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)

    professional = {
        "style": "professional",
        "subject": f"Regarding the {title} Opportunity at {company}",
        "body": (
            f"Dear {first},\n\n"
            f"I am writing to introduce myself in connection with the {title} position at {company}. "
            f"Your leadership of the {department} organization is impressive, and I would be honored to contribute to the team's continued success.\n\n"
            f"{'My professional background includes deep experience with ' + skills_str + '. ' if skills_str else ''}"
            f"I am drawn to {company}'s vision and believe my experience would allow me to make a meaningful contribution from day one.\n\n"
            f"If your schedule permits, I would greatly appreciate a brief conversation to learn more about the team's direction.\n\n"
            f"Respectfully,\nCelina"
        ),
    }
    warm = {
        "style": "warm",
        "subject": f"Inspired by {company}'s Work - Interested in the {title} Role",
        "body": (
            f"Hi {first},\n\n"
            f"I have been following {company}'s growth with genuine admiration, and when I saw the {title} opening, "
            f"I felt compelled to reach out to you directly.\n\n"
            f"The trajectory of your {department} team is exciting, and it is the kind of environment where I do my best work. "
            f"{'My experience with ' + skills_str + ' gives me a solid foundation to contribute right away. ' if skills_str else ''}"
            f"But more than the technical fit, I am drawn to the vision you are building toward.\n\n"
            f"I would love the chance to learn more about where you see the team heading.\n\n"
            f"With appreciation,\nCelina"
        ),
    }
    direct = {
        "style": "direct",
        "subject": f"{title} at {company} - Introduction from a Strong Candidate",
        "body": (
            f"Hi {first},\n\n"
            f"I will be direct: I am very interested in the {title} position at {company} and I believe I can deliver significant value.\n\n"
            f"{'My technical strengths include ' + skills_str + '. ' if skills_str else ''}"
            f"I have a track record of driving results in {department} and I am ready to do the same for your team. "
            f"What sets me apart is my ability to combine execution with strategic thinking.\n\n"
            f"I would welcome 15 minutes to make my case. When would work for you?\n\n"
            f"Best regards,\nCelina"
        ),
    }
    return [professional, warm, direct]


def _emails_hr(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    professional = {
        "style": "professional",
        "subject": f"Following Up on My {title} Application at {company}",
        "body": (
            f"Hi {first},\n\n"
            f"My name is Celina, and I recently submitted my application for the {title} position at {company}. "
            f"I wanted to reach out to you on the People team to express how excited I am about this opportunity.\n\n"
            f"I have been researching {company}'s culture and values, and they resonate strongly with how I approach my work. "
            f"I am someone who thrives in collaborative environments and truly cares about the impact I make.\n\n"
            f"Could you share any insight into the hiring timeline? I want to ensure I am prepared for every step.\n\n"
            f"Thank you for your time,\nCelina"
        ),
    }
    warm = {
        "style": "warm",
        "subject": f"So Excited About the {title} Role at {company}!",
        "body": (
            f"Hi {first},\n\n"
            f"I just applied for the {title} position and I am genuinely thrilled about the possibility of joining {company}. "
            f"Everything I have read about the culture and team tells me this could be an amazing fit.\n\n"
            f"I love that {company} clearly invests in its people, and that is something I value deeply. "
            f"I would love to learn more about what makes the team tick from your perspective.\n\n"
            f"Looking forward to hopefully being part of the journey!\n\n"
            f"Warmly,\nCelina"
        ),
    }
    direct = {
        "style": "direct",
        "subject": f"{title} Application at {company} - Quick Introduction",
        "body": (
            f"Hi {first},\n\n"
            f"I applied for the {title} role at {company} and wanted to briefly introduce myself. "
            f"I am a {department} professional who cares deeply about both the work and the team environment.\n\n"
            f"Two things I want to highlight:\n"
            f"1. I have relevant experience and am ready to contribute from day one\n"
            f"2. Culture fit matters to me as much as the role itself, and {company}'s values align with mine\n\n"
            f"What is the best way to stay in touch about the process?\n\n"
            f"Best,\nCelina"
        ),
    }
    return [professional, warm, direct]


def _emails_team_member(first: str, title: str, company: str, their_title: str, department: str, skills: list) -> list:
    skills_str = _skills_phrase(skills)

    professional = {
        "style": "professional",
        "subject": f"Fellow {department} Professional - Question About {company}",
        "body": (
            f"Hi {first},\n\n"
            f"My name is Celina, and I am a {department} professional currently exploring the {title} opportunity at {company}. "
            f"I found your profile and thought you might have a great perspective on what it is like to be part of the team.\n\n"
            f"{'We seem to share a background in ' + skills_str + ', which makes me even more curious about the technical environment. ' if skills_str else ''}"
            f"I would really value hearing about your day-to-day experience and what you enjoy most about working at {company}.\n\n"
            f"No pressure at all, but if you have a few minutes, I would be very grateful.\n\n"
            f"Best regards,\nCelina"
        ),
    }
    warm = {
        "style": "warm",
        "subject": f"Hi from a Potential Future Teammate at {company}!",
        "body": (
            f"Hi {first}!\n\n"
            f"I am Celina and I am currently interviewing for the {title} role at {company}. "
            f"I have to say, everything I have learned so far has me really excited about the possibility of joining the team.\n\n"
            f"{'I noticed you work with ' + skills_str + ' too, which is awesome! ' if skills_str else ''}"
            f"I would love to hear what your experience has been like. What is the team culture like? "
            f"What would you tell someone considering joining?\n\n"
            f"Thanks for any insight you can share!\n\n"
            f"Cheers,\nCelina"
        ),
    }
    direct = {
        "style": "direct",
        "subject": f"Quick Question About the {department} Team at {company}",
        "body": (
            f"Hi {first},\n\n"
            f"I am applying for the {title} role at {company} and wanted to get a real perspective from someone on the team.\n\n"
            f"A few things I would love to know:\n"
            f"- What is the biggest challenge the {department} team is tackling right now?\n"
            f"- {'How does the team use ' + skills_str + ' in practice?' if skills_str else 'What does the tech stack look like day-to-day?'}\n"
            f"- What would make someone really successful in this role?\n\n"
            f"Any insight would be hugely helpful. Thanks for your time!\n\n"
            f"Best,\nCelina"
        ),
    }
    return [professional, warm, direct]


# ---------------------------------------------------------------------------
# Dispatch maps
# ---------------------------------------------------------------------------

_CONNECTION_DISPATCH = {
    "recruiter": _connection_requests_recruiter,
    "hiring_manager": _connection_requests_hiring_manager,
    "leadership": _connection_requests_leadership,
    "hr": _connection_requests_hr,
    "team_member": _connection_requests_team_member,
}

_FOLLOWUP_DISPATCH = {
    "recruiter": _followups_recruiter,
    "hiring_manager": _followups_hiring_manager,
    "leadership": _followups_leadership,
    "hr": _followups_hr,
    "team_member": _followups_team_member,
}

_EMAIL_DISPATCH = {
    "recruiter": _emails_recruiter,
    "hiring_manager": _emails_hiring_manager,
    "leadership": _emails_leadership,
    "hr": _emails_hr,
    "team_member": _emails_team_member,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_message_variants(person: dict, title: str, company: str,
                              department: str, seniority: str, skills: list) -> dict:
    """
    Generate 3 variants of each message type for a given person.

    Args:
        person: dict with at least "name", "category", and optionally "job_title"
        title: the job title being applied for
        company: the company name
        department: detected department (e.g., "Engineering", "Product")
        seniority: detected seniority level (e.g., "senior", "mid", "junior")
        skills: list of key technical skills extracted from the job posting

    Returns:
        dict with keys "connection_requests", "followups", "emails"
    """
    first = _first_name(person)
    category = person.get("category", "team_member")
    their_title = person.get("job_title", "")
    skills = skills or []

    # Connection requests
    conn_fn = _CONNECTION_DISPATCH.get(category, _connection_requests_team_member)
    connection_requests = conn_fn(first, title, company, department, seniority, skills)

    # Safety: enforce 300 char limit on all connection requests
    for cr in connection_requests:
        if cr["char_count"] > 300:
            cr["text"] = _clip(cr["text"], 300)
            cr["char_count"] = len(cr["text"])

    # Follow-ups
    followup_fn = _FOLLOWUP_DISPATCH.get(category, _followups_team_member)
    followups = followup_fn(first, title, company, their_title, department, skills)

    # Emails
    email_fn = _EMAIL_DISPATCH.get(category, _emails_team_member)
    emails = email_fn(first, title, company, their_title, department, skills)

    return {
        "connection_requests": connection_requests,
        "followups": followups,
        "emails": emails,
    }


def generate_networking_strategy(people: list, title: str, company: str) -> dict:
    """
    Generate a comprehensive networking strategy for reaching out to a list of people.

    Args:
        people: list of person dicts (each with "name", "category", etc.)
        title: the job title being applied for
        company: the company name

    Returns:
        dict with priority_order, timing, two_week_plan, and dos_and_donts
    """

    # --- Priority ordering ---
    category_priority = {
        "recruiter": 1,
        "hiring_manager": 2,
        "hr": 3,
        "leadership": 4,
        "team_member": 5,
    }
    category_reasons = {
        "recruiter": "Recruiters are your fastest path to getting your application noticed and moved forward",
        "hiring_manager": "The hiring manager makes the final call; building rapport here is critical",
        "hr": "HR can provide process guidance and ensure your application is in the right pipeline",
        "leadership": "Leaders can champion your candidacy and provide strategic context about the role",
        "team_member": "Team members give authentic insights and can refer you internally, which carries significant weight",
    }

    sorted_people = sorted(
        people,
        key=lambda p: category_priority.get(p.get("category", "team_member"), 5),
    )

    priority_order = []
    for i, person in enumerate(sorted_people):
        cat = person.get("category", "team_member")
        priority_order.append({
            "name": person.get("name", "Unknown"),
            "reason": category_reasons.get(cat, "Could provide valuable perspective on the role and team"),
            "priority": i + 1,
            "category": cat,
        })

    # --- Timing recommendations ---
    timing = {
        "best_days": ["Tuesday", "Wednesday", "Thursday"],
        "best_times": "8:00-10:00 AM or 1:00-3:00 PM in the recipient's local time zone",
        "avoid": (
            "Mondays (inbox overload from the weekend), Fridays after 2 PM (people are winding down), "
            "weekends (messages get buried), holidays, and the last week of a quarter (everyone is heads-down on deliverables)"
        ),
        "pro_tips": [
            f"Space out your {company} outreach so multiple people do not receive messages on the same day",
            "Send connection requests in the morning; follow up with messages in the early afternoon",
            "If someone views your profile but does not respond, wait 5 days before a gentle nudge",
        ],
    }

    # --- Two-week plan ---
    recruiters = [p["name"] for p in sorted_people if p.get("category") == "recruiter"]
    hiring_managers = [p["name"] for p in sorted_people if p.get("category") == "hiring_manager"]
    hr_people = [p["name"] for p in sorted_people if p.get("category") == "hr"]
    leaders = [p["name"] for p in sorted_people if p.get("category") == "leadership"]
    team_members = [p["name"] for p in sorted_people if p.get("category") == "team_member"]

    two_week_plan = []

    # Day 1: Submit application + connect with recruiters
    day1_targets = recruiters[:2] if recruiters else hr_people[:1]
    two_week_plan.append({
        "day": 1,
        "action": f"Submit your application for {title} at {company}. Send connection requests to recruiters with a personalized note mentioning the role.",
        "targets": day1_targets,
    })

    # Day 2: Connect with hiring manager
    day2_targets = hiring_managers[:2] if hiring_managers else leaders[:1]
    two_week_plan.append({
        "day": 2,
        "action": "Send connection requests to hiring managers. Use the professional variant to show respect for their time.",
        "targets": day2_targets,
    })

    # Day 3: Connect with team members
    day3_targets = team_members[:3]
    two_week_plan.append({
        "day": 3,
        "action": "Connect with team members to get insider perspectives. Use the friendly variant to build genuine rapport.",
        "targets": day3_targets,
    })

    # Day 4: Follow up with recruiters who accepted
    two_week_plan.append({
        "day": 4,
        "action": "Send follow-up messages to any recruiters or HR contacts who accepted your connection request. Share your enthusiasm and ask about the timeline.",
        "targets": recruiters[:2] + hr_people[:1],
    })

    # Day 5: HR outreach
    day5_targets = hr_people[:2] if hr_people else []
    if day5_targets:
        two_week_plan.append({
            "day": 5,
            "action": "Reach out to HR and People team contacts if you have not already. Ask about the hiring process and culture.",
            "targets": day5_targets,
        })

    # Day 6: Follow up with hiring managers
    two_week_plan.append({
        "day": 6,
        "action": "Send a follow-up message to hiring managers who accepted your request. Focus on value: share what you can bring to the team.",
        "targets": hiring_managers[:2],
    })

    # Day 7: Engage with company content
    two_week_plan.append({
        "day": 7,
        "action": f"Like and thoughtfully comment on recent posts from {company}'s page and your new connections. This keeps you visible without being pushy.",
        "targets": [],
    })

    # Day 8: Connect with more team members
    remaining_team = team_members[3:6]
    if remaining_team:
        two_week_plan.append({
            "day": 8,
            "action": "Expand your network within the team. Connect with additional team members and ask about their experience.",
            "targets": remaining_team,
        })

    # Day 9: Leadership outreach
    if leaders:
        two_week_plan.append({
            "day": 9,
            "action": "Send connection requests to leadership contacts. Use a respectful, professional tone and reference the team's accomplishments.",
            "targets": leaders[:2],
        })

    # Day 10: Follow up with team members
    two_week_plan.append({
        "day": 10,
        "action": "Follow up with team members who connected. Ask specific questions about the team's challenges and culture.",
        "targets": team_members[:3],
    })

    # Day 11: Send emails to key contacts
    email_targets = (recruiters[:1] + hiring_managers[:1]) or hr_people[:1]
    two_week_plan.append({
        "day": 11,
        "action": "If you have email addresses, send a polished email to your top 1-2 contacts. Use the professional email variant.",
        "targets": email_targets,
    })

    # Day 12: Engage again
    two_week_plan.append({
        "day": 12,
        "action": f"Continue engaging with {company} content on LinkedIn. Share a relevant article or insight to demonstrate your expertise.",
        "targets": [],
    })

    # Day 13: Gentle follow-up with non-responders
    two_week_plan.append({
        "day": 13,
        "action": "Send a brief, gracious follow-up to anyone who accepted your connection but has not responded to messages. Keep it light and low-pressure.",
        "targets": recruiters[:1] + hiring_managers[:1],
    })

    # Day 14: Status check and next steps
    two_week_plan.append({
        "day": 14,
        "action": f"Review your progress. If you have not heard back on your application, send one final polite check-in to your primary recruiter contact at {company}.",
        "targets": recruiters[:1] if recruiters else hr_people[:1],
    })

    # --- Do's and Don'ts ---
    dos_and_donts = {
        "recruiters": {
            "do": [
                "Mention the specific role you applied for by name",
                "Be concise and respectful of their time; they handle dozens of candidates daily",
                "Express genuine enthusiasm without sounding desperate",
                "Ask about the hiring timeline so you can follow up appropriately",
                "Thank them regardless of the outcome",
            ],
            "dont": [
                "Send a generic message that could apply to any company",
                "Follow up more than twice without a response",
                "Ask them to fast-track your application or skip steps",
                "Complain about the application process or timeline",
                "Message them outside of business hours repeatedly",
            ],
        },
        "hiring_managers": {
            "do": [
                "Show you have researched the team's work and challenges",
                "Lead with what you can contribute, not what you want",
                "Reference specific skills or projects that are relevant to their team",
                "Ask thoughtful questions about the role's priorities",
                "Keep messages shorter than you think they should be",
            ],
            "dont": [
                "Be overly casual or assume familiarity too quickly",
                "Oversell yourself with exaggerated claims",
                "Ask about salary, benefits, or perks in initial outreach",
                "Send multiple messages if they do not respond; one follow-up is enough",
                "Criticize their current team or products, even constructively",
            ],
        },
        "hr": {
            "do": [
                "Ask about company culture and values sincerely",
                "Show that you have done your homework on the company",
                "Be polite and patient about process questions",
                "Express interest in the company broadly, not just the role",
                "Thank them for any guidance they provide",
            ],
            "dont": [
                "Try to bypass the formal application process",
                "Ask them to share confidential information about other candidates",
                "Be impatient about response times",
                "Focus only on compensation and benefits",
                "Treat them as a stepping stone rather than a valued contact",
            ],
        },
        "leadership": {
            "do": [
                "Be concise and show you respect their executive-level time",
                "Reference the company's strategic direction or recent milestones",
                "Demonstrate that you think about the big picture, not just your role",
                "Be confident but humble in your approach",
                "Make it easy for them to say yes to a brief conversation",
            ],
            "dont": [
                "Write long, rambling messages",
                "Ask them to intervene in the hiring process on your behalf",
                "Be overly familiar or casual",
                "Name-drop or overstate your connections",
                "Follow up aggressively; leaders are busy and one follow-up is the maximum",
            ],
        },
        "team_members": {
            "do": [
                "Be genuine and curious about their day-to-day experience",
                "Find common ground through shared skills or interests",
                "Ask open-ended questions that invite conversation",
                "Offer to reciprocate by sharing your own insights or network",
                "Be transparent that you are exploring the role",
            ],
            "dont": [
                "Pump them for confidential interview questions or insider tips",
                "Make them feel like they are being used for a referral",
                "Ignore them once you have gotten what you need",
                "Ask them to put in a word before you have built rapport",
                "Be dismissive if they do not have direct hiring influence",
            ],
        },
    }

    return {
        "priority_order": priority_order,
        "timing": timing,
        "two_week_plan": two_week_plan,
        "dos_and_donts": dos_and_donts,
    }


def generate_followup_sequence(person: dict, title: str, company: str) -> dict:
    """
    Generate a multi-step follow-up sequence for a specific person.

    Args:
        person: dict with at least "name" and "category"
        title: the job title being applied for
        company: the company name

    Returns:
        dict with "sequence" key containing a list of timed actions
    """
    first = _first_name(person)
    category = person.get("category", "team_member")
    their_title = person.get("job_title", "")

    # --- Day 0: Connection request ---
    if category == "recruiter":
        day0_message = (
            f"Hi {first}, I applied for the {title} role at {company} and noticed "
            f"you are part of the recruiting team. I would love to connect and learn more about the opportunity!"
        )
    elif category == "hiring_manager":
        day0_message = (
            f"Hi {first}, I am very interested in the {title} role at {company}. "
            f"I would love to connect and hear about your team's priorities. I think my background could be a great fit!"
        )
    elif category == "leadership":
        day0_message = (
            f"Hi {first}, I am pursuing the {title} opportunity at {company} and admire the direction of the team. "
            f"I would love to connect and learn more about the vision."
        )
    elif category == "hr":
        day0_message = (
            f"Hi {first}, I recently applied for the {title} position at {company}. "
            f"I would love to connect and learn more about the culture and team!"
        )
    else:
        day0_message = (
            f"Hi {first}, I am exploring the {title} role at {company} and would love to hear about your experience. "
            f"Would be great to connect!"
        )
    day0_message = _clip(day0_message, 300)

    # --- Day 3: Thank-you after acceptance ---
    if category == "recruiter":
        day3_message = (
            f"Hi {first},\n\n"
            f"Thanks so much for connecting! I am really excited about the {title} opportunity at {company}. "
            f"I submitted my application and wanted to reach out personally to express my genuine interest.\n\n"
            f"Would you have a few minutes to chat about the role and where things stand in the process? "
            f"I would love to share a bit about my background and hear what the team is looking for.\n\n"
            f"Looking forward to it!\n\n"
            f"Best,\nCelina"
        )
    elif category == "hiring_manager":
        day3_message = (
            f"Hi {first},\n\n"
            f"Really appreciate you accepting my request! I have been researching {company}'s work "
            f"and the {title} role is genuinely exciting to me.\n\n"
            f"I would love to learn more about the challenges your team is focused on right now. "
            f"Would you be open to a quick 15-minute chat sometime this week?\n\n"
            f"Thanks again,\nCelina"
        )
    elif category == "leadership":
        day3_message = (
            f"Hi {first},\n\n"
            f"Thank you for connecting. I have great respect for what you and the team have built at {company}. "
            f"The {title} role caught my attention because of the team's trajectory.\n\n"
            f"If you ever have a few spare minutes, I would love to hear your perspective on what makes someone successful "
            f"in this kind of role at {company}.\n\n"
            f"Best regards,\nCelina"
        )
    elif category == "hr":
        day3_message = (
            f"Hi {first},\n\n"
            f"Thanks for connecting! I am really enthusiastic about the {title} role at {company}. "
            f"The culture seems wonderful and it matters a lot to me to join a team where I can thrive.\n\n"
            f"Would you be able to share any tips about the hiring process or what the team values most?\n\n"
            f"Thank you,\nCelina"
        )
    else:
        day3_message = (
            f"Hi {first},\n\n"
            f"Thanks for accepting! I am looking into the {title} opportunity at {company} and really value getting "
            f"a real perspective from someone on the team.\n\n"
            f"What has your experience been like? What do you enjoy most about working at {company}?\n\n"
            f"Cheers,\nCelina"
        )

    # --- Day 7: Follow up if no response ---
    if category == "recruiter":
        day7_message = (
            f"Hi {first},\n\n"
            f"I hope you are having a good week! I wanted to follow up on my earlier message about the {title} role "
            f"at {company}. I completely understand how busy things can get on the recruiting side.\n\n"
            f"I remain very interested and would love to connect whenever your schedule allows. "
            f"Even a brief 10-minute call would be great.\n\n"
            f"Thanks for your time,\nCelina"
        )
    elif category == "hiring_manager":
        day7_message = (
            f"Hi {first},\n\n"
            f"Just wanted to circle back on the {title} role. I have continued learning about {company}'s work "
            f"and my excitement has only grown.\n\n"
            f"I know your time is valuable, so even a quick async exchange would be wonderful. "
            f"Is there a particular challenge the team is focused on that I could share relevant experience about?\n\n"
            f"Best,\nCelina"
        )
    elif category == "leadership":
        day7_message = (
            f"Hi {first},\n\n"
            f"I wanted to briefly follow up on my earlier note about the {title} position. "
            f"I have been diving deeper into {company}'s recent work and I am even more convinced this is the right fit.\n\n"
            f"No pressure at all. If you have a moment, I would love to hear any thoughts. "
            f"Either way, I appreciate the connection.\n\n"
            f"Warm regards,\nCelina"
        )
    elif category == "hr":
        day7_message = (
            f"Hi {first},\n\n"
            f"Just checking in! I wanted to see if you had any updates on the {title} hiring process at {company}. "
            f"I am still very excited about the opportunity and want to make sure I am doing everything I can on my end.\n\n"
            f"Thanks so much for any guidance,\nCelina"
        )
    else:
        day7_message = (
            f"Hi {first},\n\n"
            f"Hope things are going well! I messaged earlier about the {title} role at {company} and totally understand "
            f"if you have been busy.\n\n"
            f"If you ever have a free moment to share your thoughts on the team, I would love to hear them. "
            f"No worries at all if not!\n\n"
            f"Thanks,\nCelina"
        )

    # --- Day 14: Final gentle follow-up ---
    if category in ("recruiter", "hr"):
        day14_message = (
            f"Hi {first},\n\n"
            f"I wanted to send one last note about the {title} position at {company}. "
            f"I have tremendous respect for how busy the hiring process can be and I do not want to be a bother.\n\n"
            f"I remain very interested and enthusiastic about this opportunity. "
            f"If anything changes or if there is a better way for me to follow up, please do not hesitate to let me know.\n\n"
            f"Wishing you a great rest of the week,\nCelina"
        )
    elif category in ("hiring_manager", "leadership"):
        day14_message = (
            f"Hi {first},\n\n"
            f"I hope all is well. I wanted to send a final note to reiterate my genuine interest in the {title} role "
            f"at {company}. I understand priorities shift and schedules fill up.\n\n"
            f"If the timing ever works out for a conversation, I would be glad to connect. "
            f"In the meantime, I truly appreciate you accepting my request and wish you and the team all the best.\n\n"
            f"Kind regards,\nCelina"
        )
    else:
        day14_message = (
            f"Hi {first},\n\n"
            f"Just a quick note to say thanks again for connecting. I have really enjoyed learning about {company} "
            f"through my research and conversations.\n\n"
            f"If you ever think of anything that might help me in the process for the {title} role, I would love to hear it. "
            f"And regardless of how things go, I hope we stay in touch.\n\n"
            f"All the best,\nCelina"
        )

    # --- Day 21: Optional long-term nurture (bonus) ---
    if category == "team_member":
        day21_message = (
            f"Hi {first},\n\n"
            f"I wanted to share an article I came across that reminded me of the work at {company}. "
            f"Thought you might find it interesting.\n\n"
            f"Hope things are going well on the team. It was great connecting with you.\n\n"
            f"Best,\nCelina"
        )
    elif category == "recruiter":
        day21_message = (
            f"Hi {first},\n\n"
            f"I know it has been a few weeks since we last connected. I wanted to let you know I am still very "
            f"interested in opportunities at {company}, even if the timing was not right for the {title} role.\n\n"
            f"If anything else opens up that could be a fit, I would love to be considered. "
            f"Thanks for keeping me in mind!\n\n"
            f"Best,\nCelina"
        )
    else:
        day21_message = (
            f"Hi {first},\n\n"
            f"Hope you are doing well! I wanted to stay connected and continue following {company}'s journey. "
            f"I remain very interested in contributing to the team whenever the right opportunity arises.\n\n"
            f"Wishing you all the best,\nCelina"
        )

    sequence = [
        {
            "day": 0,
            "action": "Send connection request with personalized note",
            "message": day0_message,
            "tips": "Send on a Tuesday or Wednesday morning for best acceptance rates.",
        },
        {
            "day": 3,
            "action": "Send thank-you message after connection is accepted",
            "message": day3_message,
            "tips": "If they have not accepted yet, wait. Do not send a second request.",
        },
        {
            "day": 7,
            "action": "Follow up if no response to initial message",
            "message": day7_message,
            "tips": "Keep it light. Reference something new you learned about the company to show ongoing interest.",
        },
        {
            "day": 14,
            "action": "Final gentle follow-up",
            "message": day14_message,
            "tips": "This is your last direct outreach. Be graceful and leave the door open.",
        },
        {
            "day": 21,
            "action": "Long-term relationship nurture (optional)",
            "message": day21_message,
            "tips": "Shift from asking to giving. Share value, stay visible, and maintain the connection for future opportunities.",
        },
    ]

    return {"sequence": sequence}
