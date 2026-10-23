from rest_framework.throttling import UserRateThrottle


class ApiUserThrottle(UserRateThrottle):
    scope = "api-user"
