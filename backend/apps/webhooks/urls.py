from django.urls import path

from .views import DograhRunWebhook

urlpatterns = [path("dograh/run-completed", DograhRunWebhook.as_view())]
