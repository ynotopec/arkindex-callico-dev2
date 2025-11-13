from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import IsAdminUser, IsAuthenticated

from callico.projects.models import Authority, Element, Project
from callico.projects.permissions import IsAdminOrElementReadOnly
from callico.projects.serializers import AuthorityValueSerializer, ElementSerializer, ProjectSerializer


class ProjectList(ListAPIView):
    permission_classes = [IsAdminUser]
    serializer_class = ProjectSerializer

    def get_queryset(self):
        return Project.objects.select_related("provider").order_by("name")


class ElementRetrieve(RetrieveAPIView):
    permission_classes = [IsAuthenticated, IsAdminOrElementReadOnly]
    serializer_class = ElementSerializer
    queryset = Element.objects.all()


class AuthorityValueList(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AuthorityValueSerializer

    def get_queryset(self):
        authority = get_object_or_404(Authority, id=self.kwargs["pk"])
        qs = authority.values.all()

        if search := self.request.query_params.get("search"):
            qs = qs.filter(Q(value__icontains=search) | Q(authority_value_id__icontains=search))

        return qs.order_by("value", "authority_value_id")[:50]
