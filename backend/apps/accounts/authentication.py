from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication

ACCESS_COOKIE = "access_token"
REFRESH_COOKIE = "refresh_token"


class CookieJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        raw = request.COOKIES.get(ACCESS_COOKIE)
        if raw is None:
            return None
        token = self.get_validated_token(raw)
        SessionAuthentication().enforce_csrf(request)  # cookie auth must be CSRF-checked
        return self.get_user(token), token
