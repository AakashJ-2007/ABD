import os
import logging
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Import Scout Agent
try:
    from agents.scout_agent import run_scout
except ImportError:
    try:
        from agents.scout_agent import run_scout
    except ImportError:
        def run_scout(role, location):
            return {"LinkedIn": [], "Devpost": [], "Unstop": []}

# Fallback imports for Strategist and Recruiter-Match agents
try:
    from agents.strategist_agent import run_strategist_agent
except ImportError:
    def run_strategist_agent(title, company, location, link):
        return {
            "job_description": f"Role focusing on {title} at {company}.",
            "hard_skills": ["Python", "REST APIs", "SQL", "Git", "Docker"],
            "soft_skills": ["Problem Solving", "Collaboration", "Communication"],
            "skill_gap_roadmap": ["Master API endpoint patterns.", "Review deployment strategies."],
            "interview_prep_questions": [f"How do you design scalable APIs for {title}?"]
        }

try:
    from dissection.recruiter_match_agent import run_recruiter_match_agent
except ImportError:
    def run_recruiter_match_agent(job, strategist_analysis, student_profile):
        return {"match_score": 85, "feedback": "Good match based on core Python skill sets."}

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")
if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app)

# Only LinkedIn, Devpost, and Unstop horizontally
KNOWN_PORTALS = ["LinkedIn", "Devpost", "Unstop"]


@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/search", methods=["POST"])
def search():
    body = request.get_json(force=True, silent=True) or {}
    role = (body.get("role") or "Python Developer").strip()
    location = (body.get("location") or "Remote").strip()

    try:
        result = run_scout(role, location)
    except Exception as e:
        app.logger.error(f"Scout Agent error: {e}")
        return jsonify({"error": f"Scout Agent failed: {e}"}), 500

    # Initialize response dict with only LinkedIn, Devpost, Unstop
    sources = {portal: [] for portal in KNOWN_PORTALS}

    if isinstance(result, dict):
        # Support old format {"jobs": [...], "hackathons": [...]}
        if "jobs" in result or "hackathons" in result:
            all_items = result.get("jobs", []) + result.get("hackathons", [])
            for item in all_items:
                portal = item.get("source")
                if portal in sources:
                    sources[portal].append(item)
        # Support new platform format {"LinkedIn": [...], "Devpost": [...], "Unstop": [...]}
        else:
            for portal in KNOWN_PORTALS:
                if portal in result and isinstance(result[portal], list):
                    sources[portal] = result[portal]

    return jsonify({"sources": sources})


@app.route("/api/analyze", methods=["POST"])
def analyze():
    body = request.get_json(force=True, silent=True) or {}
    title = body.get("title", "")
    company = body.get("company", "")
    location = body.get("location", "Remote")
    link = body.get("link", "")

    if not title or not company:
        return jsonify({"error": "title and company are required"}), 400

    try:
        analysis = run_strategist_agent(title, company, location, link)
    except Exception as e:
        return jsonify({"error": f"Strategist Agent failed: {e}"}), 500

    return jsonify({"analysis": analysis})


@app.route("/api/match", methods=["POST"])
def match():
    body = request.get_json(force=True, silent=True) or {}
    job = body.get("job", {})
    strategist_analysis = body.get("strategist_analysis", {})
    student_profile = body.get("student_profile", {})

    try:
        result = run_recruiter_match_agent(job, strategist_analysis, student_profile)
    except Exception as e:
        return jsonify({"error": f"Recruiter-Match Agent failed: {e}"}), 500

    return jsonify({"match": result})


if __name__ == "__main__":
    app.run(debug=True, port=5000)