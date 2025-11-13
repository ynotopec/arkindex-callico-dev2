from rest_framework.permissions import BasePermission

from callico.projects.mixins import ProjectACLMixin


class IsAdminOrElementReadOnly(BasePermission, ProjectACLMixin):
    def has_object_permission(self, request, view, obj):
        # Add request to attributes for the ACL mixin to work with self.user
        self.request = request

        return self.user.is_admin or self.has_read_access(obj.project)
