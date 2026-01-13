# DA-Quizly

A Django REST Framework application that automatically generates interactive quizzes from YouTube videos using AI-powered content analysis. The application extracts audio from YouTube videos, transcribes it using OpenAI Whisper, and generates quiz questions using Google's Gemini AI.

## Features

- **AI-Powered Quiz Generation**: Automatically creates 10 multiple-choice questions from any YouTube video
- **Smart Transcription**: Uses yt-dlp for video download and OpenAI Whisper for speech-to-text conversion
- **JWT Authentication**: Secure authentication with HTTP-only cookies for enhanced security
- **User Management**: Complete registration, login, logout, and token refresh functionality
- **Quiz Management**: Create, read, update, and delete quizzes with full CRUD operations
- **User-Specific Content**: Each user has access only to their own quizzes
- **CORS Support**: Configured for cross-origin requests from local development environments

## Getting Started

### Prerequisites

- Python 3.10 or higher
- FFmpeg (required for audio processing)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd da-quizly
   ```

2. **Create and activate a virtual environment**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # macOS/Linux
   python -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**
   
   Create a `.env` file in the project root:
   ```env
   DJANGO_SECRET_KEY=your-secret-key-here
   GEMINI_API_KEY=your-gemini-api-key-here
   GEMINI_MODEL=gemini-2.5-flash
   ```

5. **Run database migrations**
   ```bash
   python manage.py migrate
   ```

6. **Create a superuser (optional)**
   ```bash
   python manage.py createsuperuser
   ```

7. **Start the development server**
   ```bash
   python manage.py runserver
   ```

   The API will be available at `http://127.0.0.1:8000/`

## Usage Examples

### User Registration

Register a new user account:

```bash
curl -X POST http://127.0.0.1:8000/api/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "username": "testuser",
    "email": "test@example.com",
    "password": "securepassword123",
    "confirmed_password": "securepassword123"
  }'
```

### User Login

Login and receive authentication cookies:

```bash
curl -X POST http://127.0.0.1:8000/api/login/ \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{
    "username": "testuser",
    "password": "securepassword123"
  }'
```

### Create a Quiz

Generate a quiz from a YouTube video (requires authentication):

```bash
curl -X POST http://127.0.0.1:8000/api/createQuiz/ \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
  }'
```

**Note**: Quiz generation may take 1-3 minutes depending on video length.

### List All Quizzes

Retrieve all quizzes for the authenticated user:

```bash
curl -X GET http://127.0.0.1:8000/api/quizzes/ \
  -b cookies.txt
```

### Get Quiz Details

Retrieve a specific quiz with all questions:

```bash
curl -X GET http://127.0.0.1:8000/api/quizzes/1/ \
  -b cookies.txt
```

### Update Quiz

Update quiz title or description:

```bash
curl -X PATCH http://127.0.0.1:8000/api/quizzes/1/ \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -d '{
    "title": "Updated Quiz Title",
    "description": "Updated description"
  }'
```

### Delete Quiz

Delete a quiz and all associated questions:

```bash
curl -X DELETE http://127.0.0.1:8000/api/quizzes/1/ \
  -b cookies.txt
```

### Token Refresh

Refresh the access token using the refresh token cookie:

```bash
curl -X POST http://127.0.0.1:8000/api/token/refresh/ \
  -b cookies.txt
```

### Logout

Logout and invalidate tokens:

```bash
curl -X POST http://127.0.0.1:8000/api/logout/ \
  -b cookies.txt
```

## API Reference

### Authentication Endpoints

| Endpoint | Method | Authentication | Description |
|----------|--------|----------------|-------------|
| `/api/register/` | POST | None | Register a new user account |
| `/api/login/` | POST | None | Login and receive authentication cookies |
| `/api/token/refresh/` | POST | None (uses cookie) | Refresh access token |
| `/api/logout/` | POST | Required | Logout and invalidate refresh token |

### Quiz Endpoints

| Endpoint | Method | Authentication | Description |
|----------|--------|----------------|-------------|
| `/api/createQuiz/` | POST | Required | Create a quiz from a YouTube video URL |
| `/api/quizzes/` | GET | Required | List all quizzes for authenticated user |
| `/api/quizzes/<id>/` | GET | Required | Retrieve a specific quiz with questions |
| `/api/quizzes/<id>/` | PATCH | Required | Update quiz title or description |
| `/api/quizzes/<id>/` | DELETE | Required | Delete a quiz |

### Request/Response Examples

**Registration Request:**
```json
{
  "username": "testuser",
  "email": "test@example.com",
  "password": "securepassword123",
  "confirmed_password": "securepassword123"
}
```

**Quiz Creation Request:**
```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
}
```

**Quiz Response:**
```json
{
  "id": 1,
  "title": "Introduction to Python Programming",
  "description": "Learn the basics of Python including variables, functions, and control structures.",
  "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "created_at": "2026-01-13T10:30:00Z",
  "updated_at": "2026-01-13T10:30:00Z",
  "questions": [
    {
      "id": 1,
      "question_title": "What is a variable in Python?",
      "question_options": [
        "A container for storing data",
        "A type of loop",
        "A function",
        "A class"
      ],
      "answer": "A container for storing data",
      "created_at": "2026-01-13T10:30:00Z",
      "updated_at": "2026-01-13T10:30:00Z"
    }
  ]
}
```

## Project Structure

```
da-quizly/
├── auth_app/              # User authentication app
│   ├── api/
│   │   ├── serializers.py # User & token serializers
│   │   ├── views.py       # Auth API views
│   │   └── urls.py        # Auth URL routing
│   ├── authentication.py  # Custom JWT cookie authentication
│   └── models.py
├── quiz_app/              # Quiz management app
│   ├── api/
│   │   ├── serializers.py # Quiz & question serializers
│   │   ├── views.py       # Quiz API views
│   │   └── urls.py        # Quiz URL routing
│   └── models.py          # Quiz & Question models
├── core/                  # Project settings
│   ├── settings.py        # Django configuration
│   └── urls.py            # Main URL routing
├── requirements.txt       # Python dependencies
└── manage.py             # Django management script
```

## Key Technologies

- **Django 6.0.1**: Web framework
- **Django REST Framework 3.16.1**: API framework
- **djangorestframework-simplejwt 5.5.1**: JWT authentication
- **OpenAI Whisper**: Speech-to-text transcription
- **Google Gemini AI**: Quiz question generation
- **yt-dlp**: YouTube video download
- **FFmpeg**: Audio processing
- **SQLite**: Database (development)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DJANGO_SECRET_KEY` | Django secret key for security | Yes |
| `GEMINI_API_KEY` | Google Gemini API key for quiz generation | Yes |
| `GEMINI_MODEL` | Gemini model to use (default: gemini-2.5-flash) | No |

## Support

For issues, questions, or feature requests, please open an issue in the project repository.

## Contributing

Contributions are welcome! Please ensure your code follows the project's coding standards and includes appropriate tests.

## License

This project's license information should be added to a `LICENSE` file in the repository root.