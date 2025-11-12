from django.contrib import messages
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils.translation import gettext as _

from callico.annotations.forms import ClassificationAnnotateForm
from callico.annotations.views import (
    BaseTaskUserAnnotate,
    BaseTaskUserDetails,
    BaseTaskUserManage,
    BaseTaskUserModerate,
    ManagerRedirectionRequired,
)


class ClassificationTaskUserDetails(BaseTaskUserDetails):
    def preprocess_answers(self):
        # Retrieve all classes in a single query to display their names
        class_ids = [annotation.value["classification"] for annotation in self.object.annotations.all()]
        self.classes = {str(cls.id): str(cls) for cls in self.task.campaign.project.classes.filter(id__in=class_ids)}

    def get_formatted_annotation(self, annotation):
        class_id = annotation.value["classification"]

        formatted_annotation = super().get_formatted_annotation(annotation)
        formatted_annotation["answers"] = (
            [
                {
                    "label": _("Class"),
                    "value": self.classes[class_id].capitalize(),
                }
            ]
            if class_id in self.classes
            else []
        )
        return formatted_annotation


class ClassificationTaskUserManage(BaseTaskUserManage):
    form_class = ClassificationAnnotateForm
    template_name = "user_task_manage_classification.html"

    def get_value(self, form):
        return {"classification": form.cleaned_data.get("annotation")}

    def post(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
        except ManagerRedirectionRequired as e:
            element = e.element
            url, kwargs = (
                ("element-details", {"pk": element.id})
                if not element.type.folder
                else ("project-browse", {"project_id": element.project_id, "element_id": element.id})
            )
            return HttpResponseRedirect(reverse(url, kwargs=kwargs))

        form = self.get_form()

        if self.post_parameter_is_valid():
            return self.form_valid(form)

        choices = [key for key, value in form.fields["annotation"].choices]
        selected_class = next((key for key in self.request.POST if key in choices), None)
        form.data = {"annotation": selected_class}

        if form.is_valid():
            return self.form_valid(form)

        for error in dict(form.errors)["annotation"]:
            messages.add_message(self.request, messages.ERROR, error)
        return self.form_invalid(form)


class ClassificationTaskUserAnnotate(ClassificationTaskUserManage, BaseTaskUserAnnotate):
    pass


class ClassificationTaskUserModerate(ClassificationTaskUserManage, BaseTaskUserModerate):
    pass
