from rest_framework.permissions import BasePermission

from accounts.rbac import user_has_permission
from api.rbac_routes import resolve_permission


class RbacPermission(BasePermission):
    """Enforce ModMe-style RBAC based on request path and HTTP method."""

    message = 'You do not have permission to perform this action.'

    def has_permission(self, request, view) -> bool:
        if not request.user or not request.user.is_authenticated:
            return True

        permission = resolve_permission(request.method, request.path)
        return user_has_permission(request.user, permission)
