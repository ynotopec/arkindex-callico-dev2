from django.db.models import Q
from django.http.response import Http404
from django.utils.translation import gettext as _

from callico.projects.models import ADMIN_ROLES, Project, Role


class ACLMixin:
    _user = None

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._user = user

    @property
    def user(self):
        return self._user or self.request.user


class ProjectACLMixin(ACLMixin):
    @property
    def readable_projects(self):
        return Project.objects.filter(Q(public=True) | Q(memberships__user=self.user)).distinct()

    def get_project(self):
        try:
            project = Project.objects.get(id=self.kwargs["project_id"])
        except Project.DoesNotExist:
            raise Http404(_("No project matching this ID exists"))

        return project

    def has_read_access(self, project):
        return project.public or (not self.user.is_anonymous and project.memberships.filter(user=self.user).exists())

    def has_admin_access(self, project):
        # Manager or Moderator role on the project
        return project.memberships.filter(user=self.user, role__in=ADMIN_ROLES).exists()

    def has_manager_access(self, project):
        return project.memberships.filter(user=self.user, role=Role.Manager).exists()

    def has_moderator_access(self, project):
        return project.memberships.filter(user=self.user, role=Role.Moderator).exists()

    def has_contributor_access(self, project):
        return project.memberships.filter(user=self.user, role=Role.Contributor).exists()
