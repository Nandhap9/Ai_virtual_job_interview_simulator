import asyncio
from asyncio import WindowsSelectorEventLoopPolicy
from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import google.generativeai as genai
import PyPDF2
import os
import json
import re
import random
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import timedelta

# Set the event loop policy for Windows (if applicable)
asyncio.set_event_loop_policy(WindowsSelectorEventLoopPolicy())

# Configure Google Gemini API
genai.configure(api_key="AIzaSyA4SNvB-yq0LXTipy2qUboVBYgJU6ctL_4")  # Your API key
gemini_model = genai.GenerativeModel("gemini-1.5-flash")  # Changed to free model

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change to a secure random key in production
app.permanent_session_lifetime = timedelta(days=1)  # Session lasts 1 day

# Path to JSON database
USERS_DB = "users.json"

@app.route('/check-auth')
def check_auth():
    if 'username' in session:
        return jsonify({
            'authenticated': True,
            'username': session['username']
        })
    return jsonify({
        'authenticated': False
    })

# Initialize users.json if it doesn't exist
if not os.path.exists(USERS_DB):
    with open(USERS_DB, "w") as f:
        json.dump({}, f)

# Store resume content and interview state
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
    """Load users from JSON file."""
    with open(USERS_DB, "r") as f:
        return json.load(f)

def save_users(users):
    """Save users to JSON file."""
    with open(USERS_DB, "w") as f:
        json.dump(users, f, indent=4)

def extract_text_from_pdf(file):
    """Extract text from a PDF file."""
    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        return f"Error extracting text from PDF: {e}"

def analyze_resume(document_content):
    global resume_content, interview_state
    resume_content = document_content
    interview_state["stage"] = "analysis"

    try:
        prompt = (
            "You are an AI Job Interview Simulator. Analyze the resume and return your answer strictly in JSON format. "
            "Your output must be a valid JSON object with the following keys: "
            "`acknowledgment` (a string message acknowledging the resume upload), "
            "`key_skills` (an array of the top 5 skills), and "
            "`prompt` (a string message to prompt the interview). "
            "Do not include any extra text or markdown formatting.\n\n"
            f"Analyze this resume:\n\n{document_content}"
        )

        # Use Gemini model
        response = gemini_model.generate_content(prompt)

        # Extract text response
        response_text = response.text

        # Ensure response is valid JSON
        json_match = re.search(r"\{.*\}", response_text, re.DOTALL)
        if not json_match:
            return "Error: The AI response did not contain valid JSON. Please try again or adjust your prompt."

        json_str = json_match.group()
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as json_err:
            return f"Error parsing JSON: {json_err}"

        skills = data.get("key_skills", [])
        interview_state["skills"] = skills[:5] if skills else []
        interview_state["questions_per_skill"] = {skill: 0 for skill in interview_state["skills"]}

        formatted_skills = "\n".join([f"- {skill}" for skill in interview_state["skills"]])
        final_response = (
            f"{data.get('acknowledgment', 'Thank you for uploading your resume.')}\n\n"
            f"**Key Skills**:\n{formatted_skills}\n\n"
            f"{data.get('prompt', 'Please type \"start\" to begin the interview.')}"
        )
        return final_response.strip() if final_response else "Sorry, I couldn't process the resume."
    except Exception as e:
        return f"Error: {e}"

def generate_interview_question():
    global interview_state
    if not interview_state["skills"]:
        return "No skills were identified from your resume. Please upload a more detailed resume to continue the interview."

    total_questions_possible = len(interview_state["skills"]) * 1  # 2 questions per skill
    if interview_state["total_questions_asked"] >= total_questions_possible:
        return generate_feedback()

    for skill in interview_state["skills"]:
        if interview_state["questions_per_skill"][skill] < 1:
            try:
                prompt = (
                    "You are an AI Job Interview Simulator conducting a real-time interview. "
                    "Generate one thoughtful, job-relevant question based on the skill provided. "
                    "Keep it concise, professional, and conversational.\n\n"
                    f"Generate a question for the skill: {skill}"
                )

                # Use Gemini model
                response = gemini_model.generate_content(prompt)
                response_text = response.text.strip()

                interview_state["questions_per_skill"][skill] += 1
                interview_state["total_questions_asked"] += 1

                # Update video metrics randomly to simulate analysis
                interview_state["video_metrics"] = {
                    "eye_contact": random.randint(30, 90),
                    "sentiment": random.choice(["positive", "neutral", "negative"]),
                    "facial_expression": random.choice(["neutral", "smiling", "confused", "engaged"]),
                    "speech_clarity": random.choice(["clear", "moderate", "muffled"]),
                    "confidence_level": random.choice(["low", "moderate", "high"])
                }

                return response_text if response_text else f"Tell me about your experience with {skill}."
            except Exception as e:
                return f"Error generating question: {e}"
    return "Unexpected error in question generation."

def generate_feedback():
    global interview_state
    try:
        prompt = (
            "You are an AI Job Interview Simulator. Based on the user's responses to interview questions, "
            "provide feedback in a structured format: "
            "- Start with a positive acknowledgment of their participation. "
            "- **Strengths**: Highlight what they did well (e.g., clarity, confidence). "
            "- **Weaknesses**: Note areas for improvement (e.g., detail, specificity). "
            "- **Areas for Improvement**: Suggest specific ways to enhance their responses. "
            "Use the responses provided and keep the tone constructive and encouraging.\n\n"
            f"Responses:\n\n{chr(10).join(interview_state['responses'])}"
        )

        # Use Gemini model
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip()

        interview_state["stage"] = "completed"
        return response_text if response_text else "Feedback could not be generated."
    except Exception as e:
        return f"Error: {e}"

def generate_tips():
    """Generate random interview tips based on current performance metrics."""
    tips = []
    metrics = interview_state["video_metrics"]

    # Eye contact tips
    if metrics["eye_contact"] < 50:
        tips.append("Try to maintain eye contact with the camera for better engagement.")
    elif metrics["eye_contact"] > 70:
        tips.append("Great job maintaining eye contact! Keep it up.")

    # Sentiment tips
    if metrics["sentiment"] == "negative":
        tips.append("Try to maintain a more positive tone in your responses.")

    # Facial expression tips
    if metrics["facial_expression"] == "neutral":
        tips.append("Consider smiling more naturally to appear approachable.")
    elif metrics["facial_expression"] == "confused":
        tips.append("Try to relax your facial expressions to appear more confident.")

    # Speech clarity tips
    if metrics["speech_clarity"] == "muffled":
        tips.append("Speak a bit more clearly and at a moderate pace.")

    # Confidence tips
    if metrics["confidence_level"] == "low":
        tips.append("Practice power poses before interviews to boost confidence.")

    # Add some general tips if we don't have enough
    general_tips = [
        "Structure your answers using the STAR method (Situation, Task, Action, Result).",
        "Pause briefly before answering to collect your thoughts.",
        "Prepare stories from your experience that highlight your skills.",
        "Avoid filler words like 'um' and 'ah' for more polished responses."
    ]

    while len(tips) < 2 and general_tips:
        tips.append(general_tips.pop(random.randint(0, len(general_tips)-1)))

    return tips

def handle_user_response(user_input):
    global interview_state
    if interview_state["stage"] == "initial":
        return {
            "response": "Please upload your resume to begin the interview simulation!",
            "metrics": None,
            "tips": None
        }
    elif interview_state["stage"] == "analysis":
        if user_input.lower().strip() in ["start", "begin", "yes"]:
            interview_state["stage"] = "interview"
            question = generate_interview_question()
            return {
                "response": question,
                "metrics": interview_state["video_metrics"],
                "tips": generate_tips()
            }
        return {
            "response": "Please confirm to start the interview (e.g., 'start' or 'yes').",
            "metrics": None,
            "tips": None
        }
    elif interview_state["stage"] == "interview":
        interview_state["responses"].append(user_input)
        question = generate_interview_question()
        return {
            "response": question,
            "metrics": interview_state["video_metrics"],
            "tips": generate_tips()
        }
    elif interview_state["stage"] == "completed":
        return {
            "response": "The interview is complete! You can upload a new resume to start again.",
            "metrics": None,
            "tips": None
        }
    return {
        "response": "Something went wrong. Please try again.",
        "metrics": None,
        "tips": None
    }

@app.route("/")
def landing():
    return render_template("landing.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if not username or not password:
            flash("Username and password are required!", "error")
            return redirect(url_for("register"))

        users = load_users()
        if username in users:
            flash("Username already exists!", "error")
            return redirect(url_for("register"))

        users[username] = {"password": generate_password_hash(password)}
        save_users(users)
        flash("Registration successful! Please log in.", "success")
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
            flash("Logged in successfully!", "success")
            return redirect(url_for("index"))
        else:
            flash("Invalid username or password!", "error")
            return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out successfully!", "success")
    return redirect(url_for("landing"))

@app.route("/interview")
def index():
    if "username" not in session:
        flash("Please log in to access the interview simulator.", "error")
        return redirect(url_for("login"))
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    if "username" not in session:
        return jsonify({
            "response": "Please log in to continue.",
            "metrics": None,
            "tips": None
        }), 401

    data = request.get_json()
    user_input = data.get("message", "")
    result = handle_user_response(user_input)
    return jsonify(result)

@app.route("/upload", methods=["POST"])
def upload():
    if "username" not in session:
        return jsonify({
            "response": "Please log in to upload a resume.",
            "metrics": None,
            "tips": None
        }), 401

    global interview_state
    if "file" not in request.files:
        return jsonify({
            "response": "No file uploaded.",
            "metrics": None,
            "tips": None
        }), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({
            "response": "No file selected.",
            "metrics": None,
            "tips": None
        }), 400

    if file.filename.endswith(".pdf"):
        document_content = extract_text_from_pdf(file)
    elif file.filename.endswith(".txt"):
        document_content = file.read().decode("utf-8")
    else:
        return jsonify({
            "response": "Unsupported file format. Please upload a PDF or text file.",
            "metrics": None,
            "tips": None
        }), 400

    if "Error" in document_content:
        return jsonify({
            "response": document_content,
            "metrics": None,
            "tips": None
        }), 500

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
    return jsonify({
        "response": response,
        "metrics": None,
        "tips": None
    })

@app.route("/build_resume", methods=["POST"])
def build_resume():
    if "username" not in session:
        return jsonify({
            "response": "Please log in to build a resume.",
            "metrics": None,
            "tips": None
        }), 401

    data = request.get_json()
    user_input = data.get("input", "")

    if not user_input:
        return jsonify({
            "response": "No input provided for resume generation.",
            "metrics": None,
            "tips": None
        }), 400

    try:
        prompt = (
            "You are an AI Resume Builder. Generate a professional resume based on the following information:\n\n"
            f"{user_input}\n\n"
            "Ensure the resume includes sections for contact information, summary, skills, work experience, education, and certifications. "
            "Format the resume in a clean and professional manner."
        )

        # Use Gemini model
        response = gemini_model.generate_content(prompt)
        response_text = response.text.strip()

        return jsonify({
            "response": response_text if response_text else "Sorry, I couldn't generate the resume."
        })
    except Exception as e:
        return jsonify({
            "response": f"Error generating resume: {e}"
        }), 500

if __name__ == "__main__":
    app.run(debug=True)
