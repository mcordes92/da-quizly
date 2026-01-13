"""API views for quiz creation, listing, and management using AI-powered content generation."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status, views, permissions, response

from quiz_app.models import Quiz, Question
from .serializers import CreateQuizSerializer, QuizSerializer, QuizUpdateSerializer
from .utils import (
    normalize_youtube_url,
    get_transcript_with_ytdlp_and_whisper,
    generate_quiz_with_gemini,
    validate_quiz_json,
)

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
        normalized_url = normalize_youtube_url(raw_url)

        if not normalized_url:
            return response.Response({"error": "Invalid YouTube URL."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            transcript = get_transcript_with_ytdlp_and_whisper(normalized_url)
            if not transcript or len(transcript.strip()) < 50:
                return response.Response({"detail": "No Transcript Found."}, status=status.HTTP_400_BAD_REQUEST)

            quiz_json = generate_quiz_with_gemini(transcript)
            validate_quiz_json(quiz_json)

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

class QuizListView(views.APIView):
    """Handle listing all quizzes for the authenticated user."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Retrieve all quizzes owned by the authenticated user."""
        quizzes = Quiz.objects.filter(user=request.user).prefetch_related("questions").order_by("-created_at")
        return response.Response(QuizSerializer(quizzes, many=True).data, status=status.HTTP_200_OK)


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