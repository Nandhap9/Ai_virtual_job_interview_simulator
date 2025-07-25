import asyncio
import sys

# Set Windows-specific event loop policy only if running on Windows
if sys.platform.startswith("win"):
    from asyncio import WindowsSelectorEventLoopPolicy
    asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import google.generativeai as genai
import PyPDF2
import os
import json
import re
import random
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

# Configure Google Gemini API
genai.configure(api_key="AIzaSyA4SNvB-yq0LXTipy2qUboVBYgJU6ctL_4")  # Replace with secure method in production
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Replace with secure random key in production
app.permanent_session_lifetime = timedelta(days=1)

USERS_DB = "users.json"

@app.route('/check-auth')
def check_auth():
    if 'username' in session:
        return jsonify({
            'authenticated': True,
            'username': session['username']
        })
    return jsonify({'authenticated': False})

if not os.path.exists(USERS_DB):
    with open(USERS_DB, "w") as f:
        json.dump({}, f)

resume_content = ""
interview_state = {
    "stage": "initial",
    "skills": [],
    "questions_per_skill": {},
    "total_questions_asked": 0,
    "responses": [],
    "video_metrics": {
        "eye_contact": 0,
        "sentiment": "neutral",
        "facial_expression": "neutral",
        "speech_clarity": "moderate",
        "confidence_level": "moderate"
    }
}

def load_users():
    with open(USERS_DB, "r") as f:
        return json.load(f)

def save_users(users):
    with open(USERS_DB, "w") as f:
        json.dump(users, f, indent=4)

def extract_text_from_pdf(file):
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        return "".join(page.extract_text() or "" for page in pdf_reader.pages)
    except Exception as e:
        return f"Error extracting text from PDF: {e}"

def analyze_resume(document_content):
    global resume_content, interview_state
    resume_content = document_content
    interview_state["stage"] = "analysis"

    try:
        prompt = (
            "You are an AI Job Interview Simulator. Analyze the resume and return your answer strictly in JSON format. "
            "Include `acknowledgment`, `key_skills`, and `prompt`. Resume content:\n\n"
            f"{document_content}"
        )
        response = gemini_model.generate_content(prompt)
        response_text = response.text
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            return "Error: The AI response did not contain valid JSON."
        data = json.loads(json_match.group())
        skills = data.get("key_skills", [])
        interview_state["skills"] = skills[:5]
        interview_state["questions_per_skill"] = {skill: 0 for skill in interview_state["skills"]}
        formatted_skills = "\n".join([f"- {skill}" for skill in interview_state["skills"]])
        return (
            f"{data.get('acknowledgment', 'Resume received.')}\n\n"
            f"**Key Skills**:\n{formatted_skills}\n\n"
            f"{data.get('prompt', 'Please type \"start\" to begin.')}"
        ).strip()
    except Exception as e:
        return f"Error: {e}"

def generate_interview_question():
    global interview_state
    if not interview_state["skills"]:
        return "No skills identified. Please upload a detailed resume."
    if interview_state["total_questions_asked"] >= len(interview_state["skills"]) * 1:
        return generate_feedback()
    for skill in interview_state["skills"]:
        if interview_state["questions_per_skill"][skill] < 1:
            try:
                prompt = (
                    f"You are an AI Interviewer. Ask one question about this skill: {skill}."
                )
                response = gemini_model.generate_content(prompt)
                interview_state["questions_per_skill"][skill] += 1
                interview_state["total_questions_asked"] += 1
                interview_state["video_metrics"] = {
                    "eye_contact": random.randint(30, 90),
                    "sentiment": random.choice(["positive", "neutral", "negative"]),
                    "facial_expression": random.choice(["neutral", "smiling", "confused", "engaged"]),
                    "speech_clarity": random.choice(["clear", "moderate", "muffled"]),
                    "confidence_level": random.choice(["low", "moderate", "high"])
                }
                return response.text.strip() or f"Tell me about your experience with {skill}."
            except Exception as e:
                return f"Error generating question: {e}"
    return "Unexpected error."

def generate_feedback():
    global interview_state
    try:
        prompt = (
            "You are an AI Interview Feedback Coach. Provide feedback based on the following responses:\n\n"
            f"{chr(10).join(interview_state['responses'])}"
        )
        response = gemini_model.generate_content(prompt)
        interview_state["stage"] = "completed"
        return response.text.strip() or "Feedback could not be generated."
    except Exception as e:
        return f"Error: {e}"

def generate_tips():
    metrics = interview_state["video_metrics"]
    tips = []
    if metrics["eye_contact"] < 50:
        tips.append("Try to maintain eye contact with the camera.")
    if metrics["sentiment"] == "negative":
        tips.append("Maintain a positive tone during answers.")
    if metrics["facial_expression"] == "neutral":
        tips.append("Try smiling to look more engaged.")
    if metrics["speech_clarity"] == "muffled":
        tips.append("Speak more clearly and confidently.")
    if metrics["confidence_level"] == "low":
        tips.append("Practice mock interviews to boost confidence.")
    if len(tips) < 2:
        tips.append("Use the STAR method in your answers.")
    return tips

def handle_user_response(user_input):
    global interview_state
    stage = interview_state["stage"]
    if stage == "initial":
        return {"response": "Upload your resume to begin.", "metrics": None, "tips": None}
    elif stage == "analysis":
        if user_input.lower().strip() in ["start", "begin", "yes"]:
            interview_state["stage"] = "interview"
            question = generate_interview_question()
            return {"response": question, "metrics": interview_state["video_metrics"], "tips": generate_tips()}
        return {"response": "Please type 'start' to begin the interview.", "metrics": None, "tips": None}
    elif stage == "interview":
        interview_state["responses"].append(user_input)
        question = generate_interview_question()
        return {"response": question, "metrics": interview_state["video_metrics"], "tips": generate_tips()}
    elif stage == "completed":
        return {"response": "Interview is complete. Upload a new resume to start again.", "metrics": None, "tips": None}
    return {"response": "Something went wrong.", "metrics": None, "tips": None}

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Username and password required.", "error")
            return redirect(url_for("register"))
        users = load_users()
        if username in users:
            flash("Username already exists.", "error")
            return redirect(url_for("register"))
        users[username] = {"password": generate_password_hash(password)}
        save_users(users)
        flash("Registered successfully. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        users = load_users()
        if username in users and check_password_hash(users[username]["password"], password):
            session.permanent = True
            session["username"] = username
            flash("Logged in.", "success")
            return redirect(url_for("index"))
        flash("Invalid credentials.", "error")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out.", "success")
    return redirect(url_for("landing"))

@app.route("/interview")
def index():
    if "username" not in session:
        flash("Login to access the interview simulator.", "error")
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if "username" not in session:
        return jsonify({"response": "Please log in.", "metrics": None, "tips": None}), 401
    data = request.get_json()
    user_input = data.get("message", "")
    return jsonify(handle_user_response(user_input))

@app.route("/upload", methods=["POST"])
def upload():
    if "username" not in session:
        return jsonify({"response": "Login to upload resume.", "metrics": None, "tips": None}), 401
    global interview_state
    if "file" not in request.files:
        return jsonify({"response": "No file uploaded."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"response": "No file selected."}), 400
    if file.filename.endswith(".pdf"):
        document_content = extract_text_from_pdf(file)
    elif file.filename.endswith(".txt"):
        document_content = file.read().decode("utf-8")
    else:
        return jsonify({"response": "Only PDF or text files are supported."}), 400
    if "Error" in document_content:
        return jsonify({"response": document_content}), 500
    interview_state = {
        "stage": "initial",
        "skills": [],
        "questions_per_skill": {},
        "total_questions_asked": 0,
        "responses": [],
        "video_metrics": {
            "eye_contact": 0,
            "sentiment": "neutral",
            "facial_expression": "neutral",
            "speech_clarity": "moderate",
            "confidence_level": "moderate"
        }
    }
    response = analyze_resume(document_content)
    return jsonify({"response": response})

@app.route("/build_resume", methods=["POST"])
def build_resume():
    if "username" not in session:
        return jsonify({"response": "Login to build resume."}), 401
    data = request.get_json()
    user_input = data.get("input", "")
    if not user_input:
        return jsonify({"response": "No input provided."}), 400
    try:
        prompt = (
            "You are an AI Resume Builder. Create a professional resume based on:\n\n"
            f"{user_input}\n\nInclude contact info, summary, skills, experience, education, and certifications."
        )
        response = gemini_model.generate_content(prompt)
        return jsonify({"response": response.text.strip()})
    except Exception as e:
        return jsonify({"response": f"Error: {e}"}), 500

if __name__ == "__main__":
    app.run(debug=True)
