from rest_framework.permissions import BasePermission

ADMIN, MANAGER, SALES = "Admin", "Campaign Manager", "Sales/Follow-up"


def user_roles(user):
    return set(user.groups.values_list("name", flat=True))


class RolePermission(BasePermission):
    # Views declare roles = {"GET": {"Admin"}}; an undeclared method is denied
    def has_permission(self, request, view):
        allowed = getattr(view, "roles", {}).get(request.method)
        return bool(allowed) and request.user.groups.filter(name__in=allowed).exists()
