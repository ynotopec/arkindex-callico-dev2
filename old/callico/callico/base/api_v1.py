from django.urls import path

from callico.projects.api import AuthorityValueList, ElementRetrieve, ProjectList

urlpatterns = [
    path("projects/", ProjectList.as_view(), name="list-projects"),
    path("element/<uuid:pk>/", ElementRetrieve.as_view(), name="retrieve-element"),
    path("authority/<uuid:pk>/values/", AuthorityValueList.as_view(), name="list-authority-values"),
]
