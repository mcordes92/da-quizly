"""Models for quiz application."""

from django.db import models
from django.contrib.auth.models import User

class Quiz(models.Model):
    """Model representing a quiz generated from a video."""

    user = models.ForeignKey(User, related_name="quizzes", on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    video_url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Quiz"
        verbose_name_plural = "Quizzes"
        ordering = ['-created_at']

    def __str__(self):
        return self.title

class Question(models.Model):
    """Model representing a quiz question with multiple choice options."""

    quiz = models.ForeignKey(Quiz, related_name="questions", on_delete=models.CASCADE)
    question_title = models.TextField()
    question_options = models.JSONField()
    answer = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Question"
        verbose_name_plural = "Questions"
        ordering = ['id']

    def __str__(self):
        return f"{self.question_title[:50]}..." if len(self.question_title) > 50 else self.question_title