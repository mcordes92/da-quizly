"""Service layer for quiz creation"""

import os
import tempfile
import subprocess
import json

import whisper
from yt_dlp import YoutubeDL
from google import genai
from django.db import transaction

from quiz_app.models import Quiz, Question
from .utils import normalize_youtube_url, strip_json_fences, build_gemini_quiz_prompt


GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")


class QuizService:
    """Service class for handling quiz-related business logic."""

    @staticmethod
    def create_quiz_from_youtube(user, url: str) -> Quiz:
        """Create a complete quiz from a YouTube video URL.
        
        Orchestrates the entire quiz creation process:
        1. Normalizes and validates the YouTube URL
        2. Extracts video transcript
        3. Generates quiz content with AI
        4. Validates the generated content
        5. Saves quiz and questions to database
        
        Args:
            user: The authenticated user creating the quiz
            url: Raw YouTube video URL
            
        Returns:
            Quiz: The created quiz instance with all questions
            
        Raises:
            ValueError: If URL is invalid, transcript unavailable, or AI generation fails
        """
        normalized_url = normalize_youtube_url(url)
        
        if not normalized_url:
            raise ValueError("Invalid YouTube URL.")
        
        transcript = QuizService.extract_video_transcript(normalized_url)
        
        if not transcript or len(transcript.strip()) < 50:
            raise ValueError("No Transcript Found.")
        
        quiz_json = QuizService.generate_quiz_content(transcript)
        QuizService.validate_quiz_data(quiz_json)
        
        return QuizService.save_quiz_to_database(user, quiz_json, normalized_url)

    @staticmethod
    def extract_video_transcript(url: str) -> str:
        """Download video audio and transcribe it using Whisper.

        Downloads audio from YouTube video, converts to WAV format,
        and uses OpenAI Whisper for speech-to-text transcription.
        
        Args:
            url: Normalized YouTube video URL
            
        Returns:
            str: Transcribed text from the video
            
        Raises:
            Exception: If download or transcription fails
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
                raise ValueError("Could not extract video ID.")

            downloaded = None

            for f in os.listdir(tmp):
                if f.startswith(video_id + "."):
                    downloaded = os.path.join(tmp, f)
                    break

            if not downloaded or not os.path.isfile(downloaded):
                raise ValueError("Failed to download video audio.")

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

    @staticmethod
    def generate_quiz_content(transcript: str) -> dict:
        """Generate quiz questions from transcript using Google Gemini AI.

        Sends transcript to Gemini API with structured prompt and
        returns parsed JSON with quiz data.
        
        Args:
            transcript: Video transcript text
            
        Returns:
            dict: Quiz data containing title, description, and questions
            
        Raises:
            ValueError: If API key missing or AI response invalid
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

    @staticmethod
    def validate_quiz_data(data: dict):
        """Validate quiz JSON structure and content.

        Ensures quiz has required fields and exactly 10 valid questions
        with 4 unique options each.
        
        Args:
            data: Quiz data dictionary to validate
            
        Raises:
            ValueError: If validation fails
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

    @staticmethod
    def save_quiz_to_database(user, quiz_data: dict, video_url: str) -> Quiz:
        """Save quiz and all questions to database in a transaction.
        
        Args:
            user: The user creating the quiz
            quiz_data: Validated quiz data with title, description, questions
            video_url: YouTube video URL
            
        Returns:
            Quiz: The created quiz instance with all questions
        """
        with transaction.atomic():
            quiz = Quiz.objects.create(
                user=user,
                title=quiz_data["title"],
                description=quiz_data["description"],
                video_url=video_url,
            )

            for q in quiz_data["questions"]:
                Question.objects.create(
                    quiz=quiz,
                    question_title=q["question_title"],
                    question_options=q["question_options"],
                    answer=q["answer"],
                )

        return quiz
