from django.contrib.auth.models import User
from rest_framework import status, views, permissions, response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken

from .serializers import RegistrationSerializer, CookieTokenObtainPairSerializer


class RegistrationView(views.APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return response.Response({"detail": "User created successfully!"}, status=status.HTTP_201_CREATED)
        return response.Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(TokenObtainPairView):
    permission_classes = [permissions.AllowAny]
    serializer_class = CookieTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
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
    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
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
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
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
