from django.urls import path

from tests.testapp import views

urlpatterns = [
    path("things/", views.ThingList.as_view()),
    path("things/new/", views.ThingCreate.as_view()),
    path("things/<uuid:pk>/", views.ThingDetail.as_view()),
    path("things/<uuid:pk>/status/", views.ThingStatus.as_view()),
    path("things/<uuid:pk>/recording/", views.ThingRecording.as_view()),
    path("retry-policy/", views.RetryPolicyWrite.as_view()),
]
# Not part of urlpatterns: used by the lint tests and the ObjectScoped backstop test.
unscoped_patterns = [path("unscoped/<uuid:pk>/", views.UnscopedDetail.as_view())]
