from django.contrib import admin
from .models import Quiz, Question


class QuestionInline(admin.TabularInline):
    """Inline admin for questions within a quiz."""

    model = Question
    extra = 0
    fields = ['question_title', 'question_options', 'answer']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(Quiz)
class QuizAdmin(admin.ModelAdmin):
    """Admin interface for Quiz model."""

    list_display = ['id', 'title', 'user', 'created_at', 'updated_at']
    list_filter = ['created_at', 'updated_at', 'user']
    search_fields = ['title', 'description', 'user__username']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [QuestionInline]
    
    fieldsets = (
        ('Quiz Information', {
            'fields': ('user', 'title', 'description', 'video_url')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    """Admin interface for Question model."""

    list_display = ['id', 'quiz_link', 'question_title_short', 'answer', 'created_at']
    list_filter = ['created_at', 'quiz']
    search_fields = ['question_title', 'answer', 'quiz__title']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Question Details', {
            'fields': ('quiz', 'question_title', 'question_options', 'answer')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def quiz_link(self, obj):
        """Display quiz title with ID as link."""
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse('admin:quiz_app_quiz_change', args=[obj.quiz.id])
        return format_html('<a href="{}">{} ({})</a>', url, obj.quiz.title, obj.quiz.id)
    
    quiz_link.short_description = 'Quiz'
    quiz_link.admin_order_field = 'quiz'
    
    def question_title_short(self, obj):
        """Display shortened question title."""
        return obj.question_title[:50] + '...' if len(obj.question_title) > 50 else obj.question_title
    
    question_title_short.short_description = 'Question'
