import json, os, re, tempfile

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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateQuizSerializer(data=request.data)

        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        raw_url = serializer.validated_data["url"]
        normalized_url = self._normalize_youtube_url(raw_url)

        if not normalized_url:
            return response.Response({"error": "Invalid YouTube URL."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            transcript = self._get_transcript_with_ytdlp(normalized_url)
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
        m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
        if not m:
            return None
        vid = m.group(1)
        return f"https://www.youtube.com/watch?v={vid}"
    
    def _get_transcript_with_ytdlp(self, url: str):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "%(id)s.%(ext)s")

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": out,
                "quiet": False,  # Ändere zu False für besseres Debugging
                "noplaylist": True,
                "skip_download": True,
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitlesformat": "vtt",
                
                # WICHTIG: Anti-Rate-Limiting
                "extractor_retries": 5,
                "retries": 10,
                "sleep_interval": 2,
                "max_sleep_interval": 8,
                
            }

            with YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                video_id = info.get("id")
                if not video_id:
                    return None
                ydl.download([url])

            vtt_files = [f for f in os.listdir(tmp) if f.startswith(video_id) and f.endswith(".vtt")]
            if not vtt_files:
                return None
            
            vtt_path = os.path.join(tmp, vtt_files[0])
            with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
                vtt_content = f.read()
            
            return self._vtt_to_text(vtt_content)

    def _vtt_to_text(self, vtt_content: str):
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
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z]*\s*", "", t)
            t = re.sub(r"\s*```$", "", t)
            t = t.strip()
        return t

    def _validate_quiz_json(self, data: dict):
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
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        quizzes = Quiz.objects.filter(user=request.user).prefetch_related("questions").order_by("-created_at")
        return response.Response(QuizSerializer(quizzes, many=True).data, status=status.HTTP_200_OK)

def build_gemini_quiz_prompt(transcript: str):
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
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id):
        quiz = get_object_or_404(Quiz, id=id)
        if quiz.user_id != request.user.id:
            return response.Response({"detail": "Access denied - Quiz does not belong to the user."}, status=status.HTTP_403_FORBIDDEN)
        return response.Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)

    def patch(self, request, id):
        quiz = get_object_or_404(Quiz, id=id)
        if quiz.user_id != request.user.id:
            return response.Response({"detail": "Access denied - Quiz does not belong to the user."}, status=status.HTTP_403_FORBIDDEN)

        serializer = QuizUpdateSerializer(quiz, data=request.data, partial=True)
        if not serializer.is_valid():
            return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        serializer.save()
        return response.Response(QuizSerializer(quiz).data, status=status.HTTP_200_OK)

    def delete(self, request, id):
        quiz = get_object_or_404(Quiz, id=id)
        if quiz.user_id != request.user.id:
            return response.Response({"detail": "Access denied - Quiz does not belong to the user."}, status=status.HTTP_403_FORBIDDEN)

        quiz.delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)