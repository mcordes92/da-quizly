"""API views for user authentication including registration, login, token refresh, and logout."""

from django.contrib.auth.models import User
from rest_framework import status, views, permissions, response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegistrationSerializer, CookieTokenObtainPairSerializer


class RegistrationView(views.APIView):
    """Handle user registration."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """Create a new user account."""
        serializer = RegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response({"detail": "User created successfully!"}, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(TokenObtainPairView):
    """Handle user login and set authentication cookies."""

    permission_classes = [permissions.AllowAny]
    serializer_class = CookieTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        """Authenticate user and set access and refresh tokens as HTTP-only cookies."""
        res = super().post(request, *args, **kwargs)
        if res.status_code != 200:
            return res

        access = res.data.get("access")
        refresh = res.data.get("refresh")

        if access and refresh:
            res.set_cookie("access_token", access, httponly=True, secure=True, samesite="Lax", path="/")
            res.set_cookie("refresh_token", refresh, httponly=True, secure=True, samesite="Lax", path="/api/token/refresh/")

        user = res.data.get("user")

        res.data = {
            "detail": "Login successfully!",
            "user": user
        }

        return res


class CookieTokenRefreshView(TokenRefreshView):
    """Handle token refresh using cookie-stored refresh token."""

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        """Refresh access token using the refresh token from cookies."""
        refresh = request.COOKIES.get("refresh_token")
        if not refresh:
            return response.Response({"detail": "Refresh token invalid or missing."}, status=status.HTTP_401_UNAUTHORIZED)

        request.data["refresh"] = refresh
        res = super().post(request, *args, **kwargs)
        if res.status_code != 200:
            return res

        access = res.data.get("access")
        if access:
            res.set_cookie("access_token", access, httponly=True, secure=True, samesite="Lax", path="/")

        res.data = {
            "detail": "Token refreshed",
            "access": access
        }

        return res


class LogoutView(views.APIView):
    """Handle user logout and token invalidation."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Blacklist refresh token and delete authentication cookies."""
        refresh = request.COOKIES.get("refresh_token")
        if refresh:
            token = RefreshToken(refresh)
            token.blacklist()

        res = response.Response({
            "detail": "Log-Out successfully! All Tokens will be deleted. Refresh token is now invalid."
        })

        res.delete_cookie("access_token", path="/")
        res.delete_cookie("refresh_token", path="/api/token/refresh/")

        return res
