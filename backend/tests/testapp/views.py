from rest_framework import serializers
from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveAPIView, UpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.authentication import EnrollmentTokenAuthentication
from apps.accounts.permissions import HasCapability, IsEnrollmentCredential, ObjectScoped
from apps.accounts.querysets import ScopedViewMixin
from tests.testapp.models import ScopedThing


class ThingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScopedThing
        fields = ["id", "title", "status"]
        read_only_fields = ["id"]


class ThingList(ScopedViewMixin, ListAPIView):
    queryset = ScopedThing.objects.all()
    serializer_class = ThingSerializer
    permission_classes = [HasCapability("campaigns.view_own", "campaigns.view_all")]


class ThingDetail(ScopedViewMixin, RetrieveAPIView):
    queryset = ScopedThing.objects.all()
    serializer_class = ThingSerializer
    permission_classes = [HasCapability("campaigns.view_own", "campaigns.view_all")]


class ThingCreate(CreateAPIView):
    serializer_class = ThingSerializer
    permission_classes = [HasCapability("campaigns.create")]

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ThingStatus(ScopedViewMixin, UpdateAPIView):
    queryset = ScopedThing.objects.all()
    serializer_class = ThingSerializer
    permission_classes = [HasCapability("campaigns.update_status")]
    http_method_names = ["patch"]


class ThingRecording(APIView):
    permission_classes = [HasCapability("recordings.listen")]

    def get(self, request, pk):
        return Response({"recording": "signed-url-placeholder"})


class RetryPolicyWrite(APIView):
    permission_classes = [HasCapability("retry_policy.write")]

    def put(self, request):
        return Response({"updated": True})


class UnscopedDetail(RetrieveAPIView):
    """Deliberately bypasses ScopedViewMixin to prove the ObjectScoped backstop (and the lint) work."""

    queryset = ScopedThing.objects.all()
    serializer_class = ThingSerializer
    permission_classes = [HasCapability("campaigns.view_own"), ObjectScoped]


class EnrollProbe(APIView):
    """Stands in for the enrolment endpoints (P2-09): only the restricted credential may pass."""

    authentication_classes = [EnrollmentTokenAuthentication]
    permission_classes = [IsEnrollmentCredential]

    def post(self, request):
        return Response({"user": str(request.user.pk)})


class EnrollCapabilityProbe(APIView):
    """A misconfigured view: lists the enrolment authenticator AND a capability permission."""

    authentication_classes = [EnrollmentTokenAuthentication]
    permission_classes = [HasCapability("campaigns.view_own")]

    def get(self, request):
        return Response({"leaked": True})
