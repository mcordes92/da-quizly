"""Utility helper functions for quiz application."""

import re


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
