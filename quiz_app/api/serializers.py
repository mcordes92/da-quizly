"""Serializers for quiz API."""

from rest_framework import serializers
from quiz_app.models import Quiz, Question

class QuestionSerializer(serializers.ModelSerializer):
    """Serializer for quiz questions."""

    class Meta:
        model = Question
        fields = ["id", "question_title", "question_options", "answer", "created_at", "updated_at"]

class QuizSerializer(serializers.ModelSerializer):
    """Serializer for quizzes with nested questions."""

    questions = QuestionSerializer(many=True, read_only=True)

    class Meta:
        model = Quiz
        fields = ["id", "title", "description", "created_at", "updated_at", "video_url", "questions"]

class QuizUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating quiz title and description."""

    class Meta:
        model = Quiz
        fields = ["title", "description"]
        extra_kwargs = {
            "title": {"required": False, "allow_blank": False},
            "description": {"required": False, "allow_blank": True},
        }

class CreateQuizSerializer(serializers.Serializer):
    """Serializer for creating a quiz from a video URL."""

    url = serializers.URLField()
