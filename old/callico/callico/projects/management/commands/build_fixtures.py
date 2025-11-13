# -*- coding: utf-8 -*-
import json
import logging
import random
from pathlib import Path

from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand
from django.utils.functional import cached_property

from callico.annotations.models import Task, TaskState, TaskUser
from callico.projects.models import (
    Campaign,
    CampaignMode,
    CampaignState,
    Class,
    Element,
    Image,
    Membership,
    Project,
    Provider,
    Role,
    Type,
)
from callico.users.models import User

logger = logging.getLogger(__name__)

FIXTURES = Path(__file__).parent / "fixtures"

PASSWORD = make_password("Teklia12345")
MEMBERS = {
    # Three contributors
    "contributor@teklia.com": Role.Contributor,
    "contributor2@teklia.com": Role.Contributor,
    "contributor3@teklia.com": Role.Contributor,
    # One moderator
    "moderator@teklia.com": Role.Moderator,
    # One manager
    "manager@teklia.com": Role.Manager,
}
USERS = {
    # Admin
    "admin@teklia.com": {"display_name": "Admin account", "is_admin": True, "is_staff": True},
    # A user associated with no project
    "public@teklia.com": {"display_name": "Public account", "is_admin": False, "is_staff": False},
    # At least one non-admin user of each role
    **{
        email: {"display_name": f"{email.split('@')[0].capitalize()} account", "is_admin": False, "is_staff": False}
        for email in MEMBERS
    },
}

PROVIDER_NAME = "Arkindex for fixtures building"
PROVIDER_API_URL = "https://arkindex.teklia.com/api/v1"
# If you want to be able to import data from Arkindex, or publish annotations to Arkindex,
# you will need to update this api_token field with a real Arkindex API token.
PROVIDER_API_TOKEN = "placeholder_token"


class Command(BaseCommand):
    @cached_property
    def provider(self):
        provider, _created = Provider.objects.get_or_create(
            api_url=PROVIDER_API_URL, defaults={"name": PROVIDER_NAME, "api_token": PROVIDER_API_TOKEN}
        )
        return provider

    def create_users(self):
        User.objects.bulk_create(
            [User(email=email, password=PASSWORD, **values) for email, values in USERS.items()],
            ignore_conflicts=True,
        )

    def create_project(self, data):
        users = {email: user_id for user_id, email in User.objects.values_list("id", "email")}
        project, created = Project.objects.get_or_create(
            name=data["name"],
            defaults={
                "public": data.get("public", False),
                "provider": self.provider,
                "provider_object_id": data.get("arkindex_project_id"),
            },
        )

        # Add members
        if data.get("users", False):
            logger.info(f"Adding users to project {project.name}…")
            project.memberships.bulk_create(
                [Membership(user_id=users[email], role=role, project_id=project.id) for email, role in MEMBERS.items()],
                ignore_conflicts=True,
            )

        return project, created

    def create_ml_classes(self, project, data):
        project.classes.bulk_create(
            [
                Class(name=item["name"], project_id=project.id, provider=self.provider, provider_object_id=item["id"])
                for item in data
            ],
            ignore_conflicts=True,
        )

    def create_element_types(self, project, data):
        project.types.bulk_create(
            [
                Type(
                    name=item["name"],
                    folder=bool(item["name"] == "folder"),
                    project_id=project.id,
                    provider=self.provider,
                    provider_object_id=item["id"],
                )
                for item in data
            ],
            ignore_conflicts=True,
        )

    def build_element(self, project, parent, order, data, get_or_create_image=False):
        element_dict = {
            "project_id": project.id,
            "type": Type.objects.get(project_id=project.id, name=data["type"]),
            "name": data["name"],
            "provider_id": self.provider.id,
            "provider_object_id": data["id"],
        }

        if get_or_create_image:
            image, _created = Image.objects.get_or_create(
                iiif_url=data["image"]["iiif_url"],
                width=data["image"]["width"],
                height=data["image"]["height"],
            )
        else:
            image = parent.image if parent else None

        if image:
            element_dict["image"] = image
            element_dict["polygon"] = data["polygon"]

        if parent:
            element_dict["parent"] = parent
            element_dict["order"] = order

        if "transcription" in data:
            element_dict["transcription"] = data["transcription"]

        return Element(**element_dict)

    def create_elements(self, project, data):
        for folder_element in data:
            # Create folder
            created_folder = self.build_element(project, None, None, folder_element)
            created_folder.save()

            # Create page elements
            for i, page in enumerate(folder_element["pages"]):
                created_page = self.build_element(project, created_folder, i, page, get_or_create_image=True)
                created_page.save()

                # Bulk create page children if there are no tables (table elements have row children elements)
                if not (any(item["type"] == "table") for item in page.get("children", [])):
                    Element.objects.bulk_create(
                        [self.build_element(project, created_page, i, item) for i, item in enumerate(page["children"])]
                    )
                    continue

                # Create children elements one by one if there are table elements
                for i, item in enumerate(page.get("children", [])):
                    created_element = self.build_element(project, created_page, i, item)
                    created_element.save()

                    # Create row sub-elements, if there are any
                    if len(item.get("children", [])):
                        Element.objects.bulk_create(
                            [
                                self.build_element(project, created_element, i, child)
                                for i, child in enumerate(item["children"])
                            ]
                        )

    def create_campaigns(self, project):
        manager_user = User.objects.get(email="manager@teklia.com")

        if Element.objects.filter(project_id=project.id, type__name="text_line").exists():
            Campaign.objects.create(
                name="Transcription campaign",
                mode=CampaignMode.Transcription,
                project_id=project.id,
                creator=manager_user,
                configuration={
                    "children_types": [str(Type.objects.get(project=project, name="text_line").id)],
                    "display_grouped_inputs": True,
                },
            )

        if Element.objects.filter(project_id=project.id, transcription__text__isnull=False).exists():
            Campaign.objects.create(
                name="Entity campaign",
                mode=CampaignMode.Entity,
                max_user_tasks=2,
                project_id=project.id,
                creator=manager_user,
                configuration={
                    "types": [
                        {"entity_type": "First name", "entity_color": "#e34d69"},
                        {"entity_type": "Last name", "entity_color": "#e34dcf"},
                        {"entity_type": "Occupation", "entity_color": "#914de3"},
                        {"entity_type": "Date of birth", "entity_color": "#4d4de3"},
                        {"entity_type": "Place of birth", "entity_color": "#4d8ce3"},
                        {"entity_type": "Address", "entity_color": "#4de1e3"},
                    ],
                    "transcription_display": "next_to_image",
                    "context_type": "",
                },
            )
            Campaign.objects.create(
                name="Entity form campaign",
                mode=CampaignMode.EntityForm,
                project_id=project.id,
                creator=manager_user,
                configuration={
                    "fields": [
                        {
                            "help_text": "Fill in the subject's first name which is in the third column from the left",
                            "entity_type": "First name",
                            "instruction": "Subject's first name",
                        },
                        {
                            "help_text": "Fill in the subject's last name which is in the fourth column from the left",
                            "entity_type": "Last name",
                            "instruction": "Subject's last name",
                        },
                    ],
                    "context_type": str(Type.objects.get(project=project, name="table").id),
                },
            )

        if project.name == "HORAE with users":
            Campaign.objects.create(
                name="Element group campaign",
                mode=CampaignMode.ElementGroup,
                project_id=project.id,
                creator=manager_user,
                configuration={
                    "group_type": str(Type.objects.get(project=project, name="paragraph").id),
                    "carousel_type": str(Type.objects.get(project=project, name="page").id),
                },
            )

        if Class.objects.filter(project=project).exists():
            Campaign.objects.create(
                name="Classification campaign",
                mode=CampaignMode.Classification,
                project_id=project.id,
                max_user_tasks=2,
                creator=manager_user,
                configuration={
                    "classes": [str(item.id) for item in Class.objects.filter(project=project).all()],
                    "context_type": "",
                },
            )

        Campaign.objects.create(
            name="Elements campaign",
            mode=CampaignMode.Elements,
            project_id=project.id,
            creator=manager_user,
            configuration={
                "element_types": [
                    str(Type.objects.get(project=project, name="text_zone").id),
                    str(Type.objects.get(project=project, name="text_line").id),
                ]
            },
        )

    def create_tasks(self, project):
        for campaign in project.campaigns.all():
            element_type = "page"

            if campaign.mode in [CampaignMode.Entity, CampaignMode.EntityForm] or (
                campaign.mode == CampaignMode.Classification and project.types.filter(name="row").exists()
            ):
                element_type = "row"
            elif campaign.mode == CampaignMode.ElementGroup:
                element_type = "folder"

            Task.objects.bulk_create(
                [
                    Task(campaign=campaign, element=elem)
                    for elem in Element.objects.filter(
                        project=project, type=Type.objects.get(name=element_type, project=project)
                    )
                ]
            )

    def assign_tasks(self, project):
        # Create preview tasks
        for campaign in Campaign.objects.filter(tasks__isnull=False, project=project).distinct():
            TaskUser.objects.create(
                user=User.objects.get(email="manager@teklia.com"),
                is_preview=True,
                task=random.choice(list(campaign.tasks.all())),
                state=TaskState.Pending,
            )

        # Assign tasks to contributors
        contributors = User.objects.filter(email__icontains="contributor").all()
        TaskUser.objects.bulk_create(
            [
                TaskUser(
                    user=random.choice(contributors),
                    task=one_task,
                )
                for one_task in Task.objects.filter(campaign__project=project)
            ]
        )

        # Publish half the tasks
        draft_user_tasks = TaskUser.objects.filter(state=TaskState.Draft, task__campaign__project=project).distinct()
        to_publish = random.sample(
            list(draft_user_tasks),
            int(draft_user_tasks.count() / 2),
        )
        for item in to_publish:
            item.state = TaskState.Pending

        TaskUser.objects.bulk_update(to_publish, ["state"])

        # Mark the campaigns as Running
        Campaign.objects.filter(project=project).update(state=CampaignState.Running)

    def handle(self, *args, **options):
        logger.info("Creating users…")
        self.create_users()

        logger.info("Creating project Private project no users…")
        private_project_no_users, created = Project.objects.get_or_create(name="Private project no users", public=False)
        if not created:
            logger.warning(f"Project {private_project_no_users.name} already exists.")

        # The JSON files used are generated from Arkindex by this code https://gitlab.teklia.com/callico/callico/-/snippets/37
        for filename in FIXTURES.glob("*.json"):
            project_data = json.load(open(filename, "r"))

            logger.info(f"Creating project {project_data['name']}…")
            callico_project, created = self.create_project(project_data)
            if not created:
                logger.warning(f"Project {callico_project.name} already exists. Skipping…")
                continue

            logger.info(f"Creating element types for project {callico_project.name}…")
            self.create_element_types(callico_project, project_data["element_types"])

            logger.info(f"Creating classes for project {callico_project.name}…")
            self.create_ml_classes(callico_project, project_data["ml_classes"])

            logger.info(f"Creating elements for project {callico_project.name}…")
            self.create_elements(callico_project, project_data["folders"])

            logger.info(f"Creating annotation campaigns for project {callico_project.name}…")
            self.create_campaigns(callico_project)

            logger.info(f"Creating tasks for project {callico_project.name}…")
            self.create_tasks(callico_project)

            if "with users" in callico_project.name:
                logger.info(f"Assigning tasks to users in project {callico_project.name}…")
                self.assign_tasks(callico_project)
