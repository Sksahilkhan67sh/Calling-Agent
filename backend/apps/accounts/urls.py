from django.urls import path

from . import views

urlpatterns = [
    path("token", views.LoginView.as_view()),
    path("token/refresh", views.RefreshView.as_view()),
    path("logout", views.LogoutView.as_view()),
]
