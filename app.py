import os
import logging
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("career_os_backend")

# --- 1. FLEXIBLE AGENT IMPORTS ---

# Scout Agent
try:
    from scout_agent import run_scout
except ImportError:
    try:
        from agents.scout_agent import run_scout
    except ImportError:
        logger.warning("scout_agent module not found. Using fallback function.")
        def run_scout(role, location):
            return {"LinkedIn": [], "Devpost": [], "Unstop": []}

# Strategist Agent
try:
    from strategist_agent import run_strategist_agent
except ImportError:
    try:
        from agents.strategist_agent import run_strategist_agent
    except ImportError:
        logger.warning("strategist_agent module not found. Using fallback function.")
        def run_strategist_agent(title, company, location, link):
            return {
                "job_description": f"Role focusing on {title} responsibilities at {company}.",
                "hard_skills": ["Python", "REST APIs", "SQL", "Git", "Docker"],
                "soft_skills": ["Problem Solving", "Team Collaboration", "Communication"],
                "skill_gap_roadmap": ["Master API endpoint patterns.", "Review deployment workflows."],
                "interview_prep_questions": [f"How do you design scalable APIs for {title}?"]
            }

# Recruiter Match Agent
try:
    from recruiter_match_agent import run_recruiter_match_agent
except ImportError:
    try:
        from dissection.recruiter_match_agent import run_recruiter_match_agent
    except ImportError:
        logger.warning("recruiter_match_agent module not found. Using fallback function.")
        def run_recruiter_match_agent(job, strategist_analysis, student_profile):
            return {
                "match_score": 85,
                "matched_skills": ["Python", "REST APIs", "Git"],
                "missing_skills": ["Docker", "Kubernetes"],
                "feedback": "Good match based on core Python skill sets."
            }

# --- 2. FLASK SETUP & PATH RESOLUTION ---

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(BASE_DIR, "templates")

if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
if not os.path.exists(FRONTEND_DIR):
    FRONTEND_DIR = BASE_DIR

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
CORS(app, resources={r"/api/*": {"origins": "*"}})

KNOWN_PORTALS = ["LinkedIn", "Devpost", "Unstop"]


# --- 3. ROUTES & API ENDPOINTS ---

@app.route("/")
def index():
    if os.path.exists(os.path.join(FRONTEND_DIR, "index.html")):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify({"status": "active", "message": "CareerOS Backend API is running."}), 200


@app.route("/api/search", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def search():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    body = request.get_json(force=True, silent=True) or {}
    role = (body.get("role") or "Python Developer").strip()
    location = (body.get("location") or "Remote").strip()

    try:
        result = run_scout(role, location)
    except Exception as e:
        app.logger.error(f"Scout Agent error: {e}")
        return jsonify({"error": f"Scout Agent failed: {e}"}), 500

    # Ensure format maps to LinkedIn, Devpost, Unstop
    sources = {portal: [] for portal in KNOWN_PORTALS}

    if isinstance(result, dict):
        if "jobs" in result or "hackathons" in result:
            all_items = result.get("jobs", []) + result.get("hackathons", [])
            for item in all_items:
                portal = item.get("source")
                if portal in sources:
                    sources[portal].append(item)
        else:
            for portal in KNOWN_PORTALS:
                if portal in result and isinstance(result[portal], list):
                    sources[portal] = result[portal]

    return jsonify({"sources": sources}), 200


@app.route("/api/analyze", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def analyze():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    body = request.get_json(force=True, silent=True) or {}
    title = body.get("title", "")
    company = body.get("company", "")
    location = body.get("location", "Remote")
    link = body.get("link", "")

    if not title and not company:
        return jsonify({"error": "title and company are required"}), 400

    try:
        analysis = run_strategist_agent(title, company, location, link)
        return jsonify({"analysis": analysis}), 200
    except Exception as e:
        app.logger.error(f"Strategist Agent error: {e}")
        return jsonify({"error": f"Strategist Agent failed: {e}"}), 500


@app.route("/api/match", methods=["GET", "POST", "OPTIONS"], strict_slashes=False)
def match():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    body = request.get_json(force=True, silent=True) or {}
    job = body.get("job", {})
    strategist_analysis = body.get("strategist_analysis")
    student_profile = body.get("student_profile", {})
    resume_text = body.get("resume_text") or student_profile.get("resume_text", "")

    title = job.get("title", "Developer")
    company = job.get("company", "Target Company")
    location = job.get("location", "Remote")
    link = job.get("link", "")

    # Auto-run Strategist Agent if job requirements dissection wasn't passed in body
    if not strategist_analysis:
        try:
            strategist_analysis = run_strategist_agent(title, company, location, link)
        except Exception as e:
            strategist_analysis = {}

    try:
        # Handle string or dict parameters for recruiter match agent
        try:
            result = run_recruiter_match_agent(job, strategist_analysis, resume_text)
        except TypeError:
            result = run_recruiter_match_agent(job, strategist_analysis, {"resume_text": resume_text})

        return jsonify({"match": result}), 200

    except Exception as e:
        app.logger.error(f"Recruiter-Match Agent error: {e}")
        return jsonify({"error": f"Recruiter-Match Agent failed: {e}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
