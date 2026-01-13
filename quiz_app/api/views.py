"""API views for quiz creation, listing, and management using AI-powered content generation."""

import json, os, re, tempfile, subprocess, whisper

from django.db import transaction
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from rest_framework import status, views, permissions, response

from yt_dlp import YoutubeDL
from google import genai

from quiz_app.models import Quiz, Question
from .serializers import CreateQuizSerializer, QuizSerializer, QuizUpdateSerializer

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

class CreateQuizView(views.APIView):
    """Handle quiz creation from YouTube video URLs using AI-generated content."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Create a new quiz from a YouTube video URL.

        Extract transcript from video, generate quiz questions using AI,
        and save the quiz with questions to the database.
        """
        serializer = CreateQuizSerializer(data=request.data)

        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        raw_url = serializer.validated_data["url"]
        normalized_url = self._normalize_youtube_url(raw_url)

        if not normalized_url:
            return response.Response({"error": "Invalid YouTube URL."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            transcript = self._get_transcript_with_ytdlp_and_whisper(normalized_url)
            if not transcript or len(transcript.strip()) < 50:
                return response.Response({"detail": "No Transcript Found."}, status=status.HTTP_400_BAD_REQUEST)

            quiz_json = self._generate_quiz_with_gemini(transcript)
            self._validate_quiz_json(quiz_json)

            with transaction.atomic():
                quiz = Quiz.objects.create(
                    user=request.user,
                    title=quiz_json["title"],
                    description=quiz_json["description"],
                    video_url=normalized_url,
                )

                for q in quiz_json["questions"]:
                    Question.objects.create(
                        quiz=quiz,
                        question_title=q["question_title"],
                        question_options=q["question_options"],
                        answer=q["answer"],
                    )

            return response.Response(QuizSerializer(quiz).data, status=status.HTTP_201_CREATED)

        except ValueError as e:
            return response.Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return response.Response({"detail": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
    def _normalize_youtube_url(self, url: str):
        """Normalize YouTube URL to standard watch format.

        Extracts video ID from various YouTube URL formats and returns
        a standardized URL.
        """
        m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
        if not m:
            return None
        vid = m.group(1)
        return f"https://www.youtube.com/watch?v={vid}"
    
    def _get_transcript_with_ytdlp_and_whisper(self, url: str):
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

            subprocess.run(["ffmpeg", "-y", "-i", downloaded, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_path], 
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True               
            )

            model = whisper.load_model("base")
            result = model.transcribe(wav_path)

            text = (result.get("text") or "").strip()

            return text if len(text) >= 50 else None


    def _vtt_to_text(self, vtt_content: str):
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

    def _generate_quiz_with_gemini(self, transcript: str):
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

        raw = self._strip_json_fences(raw)

        try:
            return json.loads(raw)
        except Exception as e:
            raise ValueError(f"AI has failed the Job: {str(e)}")

    def _strip_json_fences(self, text: str):
        """Remove markdown code fences from JSON response.

        Strips triple backticks and language identifiers from AI responses.
        """
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
            t = re.sub(r"\s*```$", "", t)
            t = t.strip()
        return t

    def _validate_quiz_json(self, data: dict):
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
            
class QuizListView(views.APIView):
    """Handle listing all quizzes for the authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Retrieve all quizzes owned by the authenticated user."""
        quizzes = Quiz.objects.filter(user=request.user).prefetch_related("questions").order_by("-created_at")
        return response.Response(QuizSerializer(quizzes, many=True).data, status=status.HTTP_200_OK)

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

class QuizDetailView(views.APIView):
    """Handle retrieval, updating, and deletion of individual quizzes."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        """Retrieve a specific quiz with all questions.

        Returns 403 if quiz doesn't belong to authenticated user.
        """
        quiz = get_object_or_404(Quiz, id=id)
        if quiz.user_id != request.user.id:
            return response.Response({"detail": "Access denied - Quiz does not belong to the user."}, status=status.HTTP_403_FORBIDDEN)
        return response.Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        """Update quiz title or description.

        Returns 403 if quiz doesn't belong to authenticated user.
        """
        quiz = get_object_or_404(Quiz, id=id)
        if quiz.user_id != request.user.id:
            return response.Response({"detail": "Access denied - Quiz does not belong to the user."}, status=status.HTTP_403_FORBIDDEN)

        serializer = QuizUpdateSerializer(quiz, data=request.data, partial=True)
        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return response.Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        """Delete a quiz and all associated questions.

        Returns 403 if quiz doesn't belong to authenticated user.
        """
        quiz = get_object_or_404(Quiz, id=id)
        if quiz.user_id != request.user.id:
            return response.Response({"detail": "Access denied - Quiz does not belong to the user."}, status=status.HTTP_403_FORBIDDEN)

        quiz.delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)