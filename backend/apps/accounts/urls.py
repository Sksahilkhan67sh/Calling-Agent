from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("token", views.LoginView.as_view(), name="auth-token"),
    path("token/refresh", views.RefreshView.as_view(), name="auth-token-refresh"),
    path("logout", views.LogoutView.as_view(), name="auth-logout"),
    path("csrf", views.CsrfView.as_view(), name="auth-csrf"),
    path("mfa/enroll", views.MfaEnrollView.as_view(), name="auth-mfa-enroll"),
    path("mfa/confirm", views.MfaConfirmView.as_view(), name="auth-mfa-confirm"),
]
