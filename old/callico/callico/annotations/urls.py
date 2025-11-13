from django.urls import path

from callico.annotations.views import TaskDiscussion
from callico.annotations.views.classification import (
    ClassificationTaskUserAnnotate,
    ClassificationTaskUserDetails,
    ClassificationTaskUserModerate,
)
from callico.annotations.views.element_group import (
    ElementGroupTaskUserAnnotate,
    ElementGroupTaskUserDetails,
    ElementGroupTaskUserModerate,
)
from callico.annotations.views.elements import (
    ElementsTaskUserAnnotate,
    ElementsTaskUserDetails,
    ElementsTaskUserModerate,
)
from callico.annotations.views.entity import EntityTaskUserAnnotate, EntityTaskUserDetails, EntityTaskUserModerate
from callico.annotations.views.entity_form import (
    EntityFormTaskUserAnnotate,
    EntityFormTaskUserDetails,
    EntityFormTaskUserModerate,
)
from callico.annotations.views.transcription import (
    TranscriptionTaskUserAnnotate,
    TranscriptionTaskUserDetails,
    TranscriptionTaskUserModerate,
)

urlpatterns = [
    # TaskUserDetails URLs
    path("<uuid:pk>/transcription/", TranscriptionTaskUserDetails.as_view(), name="user-task-details-transcription"),
    path("<uuid:pk>/entity/", EntityTaskUserDetails.as_view(), name="user-task-details-entity"),
    path("<uuid:pk>/entity-form/", EntityFormTaskUserDetails.as_view(), name="user-task-details-entity-form"),
    path("<uuid:pk>/classification/", ClassificationTaskUserDetails.as_view(), name="user-task-details-classification"),
    path("<uuid:pk>/elements/", ElementsTaskUserDetails.as_view(), name="user-task-details-elements"),
    path("<uuid:pk>/element-group/", ElementGroupTaskUserDetails.as_view(), name="user-task-details-element-group"),
    # Annotate URLs
    path("<uuid:pk>/annotate/transcription/", TranscriptionTaskUserAnnotate.as_view(), name="annotate-transcription"),
    path("<uuid:pk>/annotate/entity/", EntityTaskUserAnnotate.as_view(), name="annotate-entity"),
    path("<uuid:pk>/annotate/entity-form/", EntityFormTaskUserAnnotate.as_view(), name="annotate-entity-form"),
    path(
        "<uuid:pk>/annotate/classification/", ClassificationTaskUserAnnotate.as_view(), name="annotate-classification"
    ),
    path("<uuid:pk>/annotate/elements/", ElementsTaskUserAnnotate.as_view(), name="annotate-elements"),
    path("<uuid:pk>/annotate/element-group/", ElementGroupTaskUserAnnotate.as_view(), name="annotate-element-group"),
    # Moderate URLs
    path("<uuid:pk>/moderate/transcription/", TranscriptionTaskUserModerate.as_view(), name="moderate-transcription"),
    path("<uuid:pk>/moderate/entity/", EntityTaskUserModerate.as_view(), name="moderate-entity"),
    path("<uuid:pk>/moderate/entity-form/", EntityFormTaskUserModerate.as_view(), name="moderate-entity-form"),
    path(
        "<uuid:pk>/moderate/classification/", ClassificationTaskUserModerate.as_view(), name="moderate-classification"
    ),
    path("<uuid:pk>/moderate/elements/", ElementsTaskUserModerate.as_view(), name="moderate-elements"),
    path("<uuid:pk>/moderate/element-group/", ElementGroupTaskUserModerate.as_view(), name="moderate-element-group"),
    # Discussion URL
    path("<uuid:pk>/discussion/", TaskDiscussion.as_view(), name="task-discussion"),
]
