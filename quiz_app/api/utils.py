"""Utility functions for quiz generation from YouTube videos."""

import json
import os
import re
import tempfile
import subprocess

import whisper
from yt_dlp import YoutubeDL
from google import genai

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


def normalize_youtube_url(url: str):
    """Normalize YouTube URL to standard watch format.

    Extracts video ID from various YouTube URL formats and returns
    a standardized URL.
    """
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    if not m:
        return None
    vid = m.group(1)
    return f"https://www.youtube.com/watch?v={vid}"


def get_transcript_with_ytdlp_and_whisper(url: str):
    """Download video audio and transcribe it using Whisper.

    Downloads audio from YouTube video, converts to WAV format,
    and uses OpenAI Whisper for speech-to-text transcription.
    """
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "%(id)s.%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": out,
            "quiet": True,
            "noplaylist": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id")

        if not video_id:
            return None

        downloaded = None

        for f in os.listdir(tmp):
            if f.startswith(video_id + "."):
                downloaded = os.path.join(tmp, f)
                break

        if not downloaded or not os.path.isfile(downloaded):
            return None

        wav_path = os.path.join(tmp, f"{video_id}.wav")

        subprocess.run(
            ["ffmpeg", "-y", "-i", downloaded, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )

        model = whisper.load_model("base")
        result = model.transcribe(wav_path)

        text = (result.get("text") or "").strip()

        return text if len(text) >= 50 else None


def vtt_to_text(vtt_content: str):
    """Convert VTT subtitle content to plain text.

    Removes VTT formatting, timestamps, and tags, returning clean text.
    """
    lines = []
    for line in vtt_content.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("WEBVTT"):
            continue
        if "-->" in line:
            continue
        if re.match(r"^\d+$", line):
            continue
        line = re.sub(r"<[^>]+>", "", line)
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            lines.append(line)
    text = " ".join(lines)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_quiz_with_gemini(transcript: str):
    """Generate quiz questions from transcript using Google Gemini AI.

    Sends transcript to Gemini API with structured prompt and
    returns parsed JSON with quiz data.
    """
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set.")

    client = genai.Client(api_key=GEMINI_API_KEY, http_options={"api_version": "v1"})
    prompt = build_gemini_quiz_prompt(transcript)

    result = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    raw = (getattr(result, "text", None) or "").strip()

    if not raw:
        raise ValueError("AI has failed the Job: Empty response from model.")

    raw = strip_json_fences(raw)

    try:
        return json.loads(raw)
    except Exception as e:
        raise ValueError(f"AI has failed the Job: {str(e)}")


def strip_json_fences(text: str):
    """Remove markdown code fences from JSON response.

    Strips triple backticks and language identifiers from AI responses.
    """
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
        t = t.strip()
    return t


def validate_quiz_json(data: dict):
    """Validate quiz JSON structure and content.

    Ensures quiz has required fields and exactly 10 valid questions
    with 4 unique options each.
    """
    if not isinstance(data, dict):
        raise ValueError("Invalid quiz format.")

    if "title" not in data or "description" not in data or "questions" not in data:
        raise ValueError("Missing required quiz fields.")

    questions = data["questions"]

    if not isinstance(questions, list) or len(questions) != 10:
        raise ValueError("Quiz must contain exactly 10 questions.")

    for q in questions:
        if not isinstance(q, dict):
            raise ValueError("Invalid question format.")

        for k in ["question_title", "question_options", "answer"]:
            if k not in q:
                raise ValueError("Question is missing.")

        opts = q["question_options"]
        ans = q["answer"]

        if not isinstance(opts, list) or len(opts) != 4:
            raise ValueError("Every question must have exactly 4 options.")
        if len(set(opts)) != 4:
            raise ValueError("Options must be unique.")
        if ans not in opts:
            raise ValueError("Answer must be one of the question_options.")


def build_gemini_quiz_prompt(transcript: str):
    """Build a structured prompt for Gemini AI to generate quiz questions.

    Creates a detailed prompt with JSON schema, requirements, and the
    video transcript for quiz generation.
    """
    return f"""Based on the following transcript, generate a quiz in valid JSON format.

The quiz must follow this exact structure:

{{
  "title": "Create a concise quiz title based on the topic of the transcript.",
  "description": "Summarize the transcript in no more than 150 characters. Do not include any quiz questions or answers.",
  "questions": [
    {{
      "question_title": "The question goes here.",
      "question_options": ["Option A", "Option B", "Option C", "Option D"],
      "answer": "The correct answer from the above options"
    }}
  ]
}}

Requirements:
- Exactly 10 questions.
- Each question must have exactly 4 distinct answer options.
- Only one correct answer is allowed per question, and it must be present in 'question_options'.
- The output must be valid JSON and parsable as-is.
- Do not include explanations, comments, or any text outside the JSON.

Transcript:
{transcript}
"""
