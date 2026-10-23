from rest_framework.permissions import BasePermission


class RolePermission(BasePermission):
    # Views declare roles = {"GET": {"Admin"}}; an undeclared method is denied
    def has_permission(self, request, view):
        allowed = getattr(view, "roles", {}).get(request.method)
        return bool(allowed) and request.user.groups.filter(name__in=allowed).exists()
