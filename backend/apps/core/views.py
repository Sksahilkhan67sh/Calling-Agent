from django.db import OperationalError, connection
from django.http import JsonResponse


def health(request):
    try:
        connection.ensure_connection()
    except OperationalError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
