# -*- coding: utf-8 -*-
import json
import logging
from collections import Counter, defaultdict
from typing import List

from apistar.exceptions import ErrorResponse
from django.db.models import Exists, OuterRef, Prefetch

from callico.annotations.models import Annotation, Task, TaskState, TaskUser
from callico.annotations.views.entity import random_color
from callico.process.arkindex.imports import ArkindexProcessBase
from callico.process.models import Process
from callico.projects.models import Campaign, CampaignMode, Element, TextOrientation, Type

CHUNK_SIZE = 5000
# This character is used to force the publication of empty transcriptions to Arkindex:
# - for Transcription annotations, each empty transcription will be replaced by this character
# - for EntityForm annotations, transcriptions are forged by concatenating their entities,
#   if the resulting forged transcription is empty, it will be replaced by this character.
EMPTY_SET_CHARACTER = "∅"


class ArkindexExport(ArkindexProcessBase):
    def __init__(
        self,
        arkindex_provider: str,
        process: Process,
        campaign_id: str,
        corpus_id: str,
        worker_run_id: str,
        exported_states: List[TaskState],
        force_republication: bool,
        use_raw_publication: bool,
        entities_order: List[List[str]],
        concat_parent_type_id: str,
    ):
        self.corpus_id = corpus_id
        self.worker_run_id = worker_run_id
        self.exported_states = exported_states
        self.force_republication = force_republication
        self.use_raw_publication = use_raw_publication
        self.entities_order = entities_order
        self.concat_parent_type = Type.objects.get(id=concat_parent_type_id) if concat_parent_type_id else None
        self.campaign = Campaign.objects.get(id=campaign_id)
        process.add_log(f'Using campaign "{self.campaign}"', logging.INFO)

        super().__init__(process=process, arkindex_provider=arkindex_provider)

    @staticmethod
    def from_configuration(process, config):
        return ArkindexExport(
            process=process,
            arkindex_provider=config["arkindex_provider"],
            campaign_id=config["campaign"],
            corpus_id=config["corpus"],
            worker_run_id=config["worker_run"],
            exported_states=config["exported_states"],
            force_republication=config.get("force_republication", False),
            use_raw_publication=config.get("use_raw_publication", False),
            entities_order=config.get("entities_order", []),
            concat_parent_type_id=config.get("concatenation_parent_type"),
        )

    def publish_transcriptions(self, task, annotations):
        all_transcriptions = [annotation.value.get("transcription") for annotation in annotations]
        if not all(isinstance(transcriptions, dict) and transcriptions for transcriptions in all_transcriptions):
            self.process.add_log(
                f"Skipping the task {task.id} as at least one of its last transcription annotations holds an invalid value",
                logging.ERROR,
            )
            return False

        # Retrieving elements for the annotations on this task
        elements = Element.objects.filter(
            id__in=[id for transcriptions in all_transcriptions for id in transcriptions],
            provider=self.arkindex_provider,
        ).order_by("created")
        elements_ids = [str(id) for id in elements.values_list("id", flat=True)]

        # Grouping transcriptions for each element to compute the confidence later on
        # Structure:
        # grouped_transcriptions = {
        #     "element1_id": {"tr_1": count = 2, "tr_2": count = 1},
        #     "element2_id": {"tr_1": count = 3},
        #     ...
        # }
        # On Arkindex, for element1_id, we'll have 66% confidence for tr_1 and 33% for tr_2
        # and for element2_id, we'll have 100% confidence for tr_1
        grouped_transcriptions = defaultdict(Counter)
        nb_replaced, nb_skipped = 0, 0
        for transcriptions, annotation in zip(all_transcriptions, annotations):
            for id, transcription in transcriptions.items():
                # Handling skipped transcription
                if id not in elements_ids:
                    nb_skipped += 1
                    self.process.add_log(
                        f'Skipping the transcription for the element {id} on annotation {annotation.id} as it is not an element from the Arkindex provider "{self.arkindex_provider}"',
                        logging.WARNING,
                    )
                    continue

                if not transcription.get("text"):
                    nb_replaced += 1
                    self.process.add_log(
                        f"The transcription for the element {id} on annotation {annotation.id} is empty, publishing {EMPTY_SET_CHARACTER} instead",
                        logging.WARNING,
                    )
                    transcription["text"] = EMPTY_SET_CHARACTER

                # Transcription isn't skipped and should be published
                grouped_transcriptions[id].update([transcription["text"]])

                # If the transcription was marked as uncertain, we need to decrease its confidence
                if transcription.get("uncertain"):
                    grouped_transcriptions[id + "_uncertain_trs"].update([transcription["text"]])

        to_publish = []
        for element in elements:
            transcriptions = grouped_transcriptions.get(str(element.id), {})
            uncertain_transcriptions = grouped_transcriptions.get(str(element.id) + "_uncertain_trs", {})

            if len(transcriptions) > 1:
                self.process.add_log(
                    f"Differing transcriptions for the element {element.id} were found on the task {task.id}",
                    logging.WARNING,
                )

            total = sum(transcriptions.values())
            for transcription, count in transcriptions.items():
                uncertain_count = uncertain_transcriptions.get(transcription, 0)
                certain_count = count - uncertain_count
                final_count = uncertain_count * 0.5 + certain_count

                common_payload = {
                    "element_id": element.provider_object_id,
                    "text": transcription,
                    "orientation": "horizontal-rl"
                    if element.text_orientation == TextOrientation.RightToLeft
                    else "horizontal-lr",
                }
                nb_publications, confidence = (
                    (1, final_count / total) if not self.use_raw_publication else (certain_count, 1)
                )
                to_publish += [
                    {
                        **common_payload,
                        "confidence": confidence,
                    }
                ] * nb_publications
                if self.use_raw_publication:
                    to_publish += [
                        {
                            **common_payload,
                            "confidence": 0.5,
                        }
                    ] * uncertain_count

        if to_publish:
            try:
                self.arkindex_client.request(
                    "CreateTranscriptions",
                    body={"transcriptions": to_publish, "worker_run_id": str(self.worker_run_id)},
                )
            except ErrorResponse as e:
                self.process.add_log(
                    f"Failed to publish {len(to_publish)} transcriptions retrieved from the annotations on the task {task.id}: {e.status_code} - {e.content}",
                    logging.ERROR,
                )
                return False

            self.process.add_log(
                f"Successfully published {len(to_publish)} transcriptions with their confidence for task {task.id}",
                logging.INFO,
            )

        if nb_replaced:
            self.process.add_log(
                f"Replaced {nb_replaced} empty transcriptions on the task {task.id} by {EMPTY_SET_CHARACTER}",
                logging.INFO,
            )

        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} transcriptions on the task {task.id} that were on elements from another Arkindex provider",
                logging.INFO,
            )
        return True

    def get_allowed_element_types(self, project):
        try:
            corpus = self.arkindex_client.request("RetrieveCorpus", id=self.corpus_id)
        except ErrorResponse as e:
            self.process.add_log(
                f"Failed to retrieve available types on the Arkindex corpus {self.corpus_id}: {e.status_code} - {e.content}",
                logging.ERROR,
            )
            return {}

        external_slugs = [element_type["slug"] for element_type in corpus["types"]]
        return {
            str(internal_id): external_slug
            for internal_id, external_slug in project.types.filter(
                provider=self.arkindex_provider, provider_object_id__in=external_slugs
            ).values_list("id", "provider_object_id")
        }

    def publish_elements(self, task, annotations):
        all_elements = [annotation.value.get("elements") for annotation in annotations]
        if not all(isinstance(element, list) for element in all_elements):
            self.process.add_log(
                f"Skipping the task {task.id} as at least one of its last element annotations holds an invalid value",
                logging.ERROR,
            )
            return False

        elements = [element for elements in all_elements for element in elements]
        filtered_elements = [element for element in elements if element["element_type"] in self.allowed_element_types]
        # Keys in the Counter are dicts dumped into strings, Counter can't count dicts
        grouped_elements = Counter([json.dumps(element) for element in filtered_elements])
        types = Counter()

        to_publish = []
        for element_str, count in grouped_elements.items():
            # The dict was stored as a string in the Counter, we need to reload it
            element = json.loads(element_str)

            element_type = self.allowed_element_types[element["element_type"]]

            nb_publications, confidence = (1, count / len(all_elements)) if not self.use_raw_publication else (count, 1)
            to_publish += [
                {
                    "type": element_type,
                    "polygon": element["polygon"],
                    "name": str(types[element_type] + 1 + i),
                    "confidence": confidence,
                }
                for i in range(nb_publications)
            ]

            types.update([element_type] * nb_publications)

        if to_publish:
            try:
                self.arkindex_client.request(
                    "CreateElements",
                    id=task.element.provider_object_id,
                    body={
                        "worker_run_id": str(self.worker_run_id),
                        "elements": to_publish,
                    },
                )
            except ErrorResponse as e:
                self.process.add_log(
                    f"Failed to publish elements retrieved from the annotations on the task {task.id}: {e.status_code} - {e.content}",
                    logging.ERROR,
                )
                return False

            self.process.add_log(
                f"Successfully published {len(to_publish)} elements with their confidence for task {task.id}",
                logging.INFO,
            )

        nb_skipped = len(elements) - len(filtered_elements)
        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} element annotations for task {task.id} because no type matches them in the Arkindex corpus",
                logging.INFO,
            )

        return True

    def publish_and_link_element_group(self, task, index, elements, confidence=1):
        try:
            published_group = self.arkindex_client.request(
                "CreateElement",
                body={
                    "name": str(index),
                    "confidence": confidence,
                    "type": self.configured_element_group_type,
                    "corpus": self.corpus_id,
                    "parent": task.element.provider_object_id,
                    "worker_run_id": str(self.worker_run_id),
                },
            )
        except ErrorResponse as e:
            self.process.add_log(
                f"Failed to publish a group of elements from the annotations on the task {task.id}: {e.status_code} - {e.content}",
                logging.ERROR,
            )
            return False

        nb_failed = 0
        for element_id in elements:
            try:
                self.arkindex_client.request(
                    "CreateElementParent",
                    parent=published_group["id"],
                    child=element_id,
                )
            except ErrorResponse as e:
                self.process.add_log(
                    f"Failed to link an element to the group {index} from the annotations on the task {task.id}: {e.status_code} - {e.content}",
                    logging.ERROR,
                )
                nb_failed += 1

        if nb_failed:
            # At least one element wasn't properly linked to the parent group
            return False

        self.process.add_log(
            f"Successfully published the group {index} and linked {len(elements)} elements to it from the annotations on the task {task.id}",
            logging.INFO,
        )
        return True

    def publish_element_groups(self, task, annotations):
        all_groups = [annotation.value.get("groups") for annotation in annotations]
        if not all(isinstance(groups, list) for groups in all_groups):
            self.process.add_log(
                f"Skipping the task {task.id} as at least one of its last element group annotations holds an invalid value",
                logging.ERROR,
            )
            return False

        callico_elements = {
            str(element.id): element.provider_object_id
            for element in Element.objects.filter(
                id__in=[
                    element_id for groups in all_groups for group in groups for element_id in group.get("elements", [])
                ],
                provider=self.arkindex_provider,
            )
        }

        nb_skipped = 0
        grouped_groups = Counter()
        for groups in all_groups:
            for group in groups:
                elements = [
                    callico_elements[element_id]
                    for element_id in group.get("elements", [])
                    if element_id in callico_elements
                ]

                if not elements:
                    # Empty groups should not be published
                    nb_skipped += 1
                    continue

                # Searching if we already found an equal set of elements
                key = next(
                    (key for key in grouped_groups.keys() if json.loads(key) == elements),
                    json.dumps(elements),
                )
                # Keys in the Counter are dicts dumped into strings, Counter can't count dicts
                grouped_groups.update([key])

        nb_failed, next_index = 0, 1
        for group_str, count in grouped_groups.items():
            # The list was stored as a string in the Counter, we need to reload it
            elements = json.loads(group_str)

            # Publishing the groups
            nb_publications, confidence = (1, count / len(all_groups)) if not self.use_raw_publication else (count, 1)
            published = [
                self.publish_and_link_element_group(
                    task,
                    next_index + i,
                    elements,
                    confidence=confidence,
                )
                for i in range(nb_publications)
            ]
            nb_failed += nb_publications - sum(published)
            next_index += nb_publications

        if nb_failed:
            # At least one group publication failed completely (parent creation) or partially (children linking)
            return False

        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} groups of elements from the annotations on the task {task.id} that were either empty or only containing elements from another Arkindex provider",
                logging.INFO,
            )

        return True

    def get_or_create_entity_type(self, log_hint, entity):
        if entity["entity_type"] not in self.entity_types:
            try:
                created_type = self.arkindex_client.request(
                    "CreateEntityType",
                    body={
                        "name": entity["entity_type"],
                        "color": entity.get("entity_color", random_color()).replace("#", ""),
                        "corpus": str(self.corpus_id),
                    },
                )
                # Add the newly created entity type to the list of existing types
                self.entity_types[entity["entity_type"]] = created_type["id"]
            except ErrorResponse as e:
                entity_value = f"entity {entity['value']}" if entity.get("value") else "entity"
                self.process.add_log(
                    f"Failed to publish {entity_value} of type {entity['entity_type']} {log_hint}; an error "
                    f"occurred while creating the entity type {entity['entity_type']} in the corpus {str(self.corpus_id)}: {e.status_code} - {e.content}",
                    logging.ERROR,
                )
                return None

        return self.entity_types[entity["entity_type"]]

    def create_transcription_entities(self, log_hint, entities, transcription_id):
        try:
            self.arkindex_client.request(
                "CreateTranscriptionEntities",
                id=transcription_id,
                body={"worker_run_id": str(self.worker_run_id), "transcription_entities": entities},
            )
        except ErrorResponse as e:
            self.process.add_log(
                f"Failed to publish and link {len(entities)} entities with the transcription {log_hint}: {e.status_code} - {e.content}",
                logging.ERROR,
            )
            return False

        self.process.add_log(
            f"Successfully published and linked {len(entities)} entities with the transcription {log_hint}",
            logging.INFO,
        )
        return True

    def publish_entities(self, task, annotations):
        if not task.element.transcription.get("id"):
            self.process.add_log(f"Skipping the task {task.id} as there is no transcription ID", logging.WARNING)
            return False

        all_entities = [annotation.value.get("entities") for annotation in annotations]
        if not all(isinstance(entities, list) for entities in all_entities):
            self.process.add_log(
                f"Skipping the task {task.id} as at least one of its last entity annotations holds an invalid value",
                logging.ERROR,
            )
            return False

        # Keys in the Counter are dicts dumped into strings, Counter can't count dicts
        grouped_entities = Counter([json.dumps(entity) for entities in all_entities for entity in entities])

        nb_failed, nb_skipped = 0, 0
        entities_to_publish = []
        for entity_str, count in grouped_entities.items():
            # The dict was stored as a string in the Counter, we need to reload it
            entity = json.loads(entity_str)

            # Handling skipped entities
            if entity["length"] == 0:
                nb_skipped += 1 if not self.use_raw_publication else count
                self.process.add_log(
                    f"Skipping the entity of type {entity['entity_type']} from the annotations on the task {task.id} as it is empty",
                    logging.WARNING,
                )
                continue

            # Retrieving or creating the entity type
            entity_type_id = self.get_or_create_entity_type(f"from the annotations on the task {task.id}", entity)
            if not entity_type_id:
                nb_failed += 1 if not self.use_raw_publication else count
                continue

            # Building entities_to_publish
            nb_publications, confidence = (1, count / len(all_entities)) if not self.use_raw_publication else (count, 1)
            entities_to_publish.extend(
                [
                    {
                        "offset": entity["offset"],
                        "length": entity["length"],
                        "type_id": entity_type_id,
                        "confidence": confidence,
                    }
                ]
                * nb_publications
            )

        if len(entities_to_publish):
            # Create the transcription entities on Arkindex using the bulk endpoint
            published_entities = self.create_transcription_entities(
                f"from the annotations on the task {task.id}",
                entities_to_publish,
                task.element.transcription["id"],
            )
            if not published_entities:
                nb_failed += len(entities_to_publish)

        if nb_failed:
            # At least one entity publication failed
            return False

        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} empty entities from the annotations on the task {task.id}", logging.INFO
            )

        return True

    def publish_transcription(self, transcription_id, text, confidence, log_hint):
        try:
            return self.arkindex_client.request(
                "CreateTranscription",
                id=transcription_id,
                body={
                    "text": text,
                    "worker_run_id": str(self.worker_run_id),
                    "confidence": confidence,
                },
            )
        except ErrorResponse as e:
            self.process.add_log(
                f"Failed to publish {log_hint}: {e.status_code} - {e.content}",
                logging.ERROR,
            )

    def sort_entities(self, entities):
        """
        This part of the code is slightly complex, as we have to think about sorting not only
        the entities that are still configured, but also those that are no longer.

        Indeed, the campaign configuration can be updated at any time, so we can delete, modify
        or add entities to be annotated, while existing annotations will remain unchanged.

        - For example, on Tuesday, the entities configured are ("first_name" and "last_name")
        and users annotate tasks.
        - If the configuration changes on Wednesday to become ("first_name" and "age"), we don't
        clean up the existing annotations, which will remain as they are, and users will be able
        to annotate new tasks with the updated configuration.
        - Then, during publication, we'll find tasks with configured entities ("first_name" and
        "age") and others with unconfigured entities ("last_name").

        We therefore need to sort the configured entities according to the order provided by the
        user (identical to the one configured or not) and then add, any unconfigured entities that
        may remain, at the end of this list (in alphabetical order).
        """
        orderable_from_config = []
        alphabetically_sortable = []
        for entity in entities:
            if [entity["entity_type"], entity["instruction"]] in self.entities_order:
                orderable_from_config.append(entity)
            else:
                alphabetically_sortable.append(entity)

        # Sort entities which are still configured
        sorted_left = sorted(
            orderable_from_config,
            key=lambda entity: self.entities_order.index([entity["entity_type"], entity["instruction"]]),
        )

        # Sort entities which aren't configured anymore but were annotated before the configuration changed
        sorted_right = sorted(
            alphabetically_sortable, key=lambda entity: (entity["entity_type"], entity["instruction"])
        )

        # Concatenate the two sorted lists
        return sorted_left + sorted_right

    def create_transcription_and_transcription_entities(self, task, entities, confidence=1):
        # Forging the transcription with the valid entities and publishing it
        values = [entity["value"] for entity in entities if entity.get("value")]
        transcription_text = " ".join(values)
        log_hint = f"the transcription forged with {len(values)} valid entities"

        # If no valid entities were found at all (they are all empty) then we publish an "empty" transcription
        if not values:
            transcription_text = EMPTY_SET_CHARACTER
            log_hint = f"the empty transcription using the {EMPTY_SET_CHARACTER} character"
            self.process.add_log(
                f"All {len(entities)} entities from the annotations on the task {task.id} are empty, publishing a {EMPTY_SET_CHARACTER} transcription in replacement",
                logging.WARNING,
            )

        transcription = self.publish_transcription(
            task.element.provider_object_id,
            transcription_text,
            confidence,
            f"{log_hint} from the annotations on the task {task.id}",
        )
        if not transcription:
            # No need to continue if the transcription wasn't published at all
            return False

        self.process.add_log(
            f"Successfully published {log_hint} from the annotations on the task {task.id}",
            logging.INFO,
        )

        # If no valid entities were found at all (they are all empty), we don't need to process entities
        if not values:
            return True

        entities_to_publish = []
        nb_failed = 0
        offset = 0
        for entity in entities:
            # Handling skipped entities
            if not entity["value"]:
                self.process.add_log(
                    f"Skipping the entity of type {entity['entity_type']} from the annotations on the task {task.id} as it is empty",
                    logging.WARNING,
                )
                continue

            # Building entities_to_publish
            entity_type_id = self.get_or_create_entity_type(f"from the annotations on the task {task.id}", entity)
            if entity_type_id:
                entities_to_publish.append(
                    {
                        "offset": offset,
                        "length": len(entity["value"]),
                        "type_id": entity_type_id,
                        "confidence": 0.5 if entity.get("uncertain") else 1,
                    }
                )
            else:
                nb_failed += 1

            # Incrementing the offset (even if there was a failure during the entity type creation)
            offset += len(entity["value"]) + 1

        if len(entities_to_publish):
            # Create the transcription entities on Arkindex using the bulk endpoint
            published = self.create_transcription_entities(
                f"from the annotations on the task {task.id}", entities_to_publish, transcription["id"]
            )
            if not published:
                nb_failed += len(entities_to_publish)

        if nb_failed:
            # At least one entity wasn't properly created and linked to the transcription
            return False

        return True

    def publish_transcription_entities(self, task, annotations):
        all_entities = [annotation.value.get("values") for annotation in annotations]
        if not all(isinstance(entities, list) and entities for entities in all_entities):
            self.process.add_log(
                f"Skipping the task {task.id} as at least one of its last entity form annotations holds an invalid value",
                logging.ERROR,
            )
            return False

        grouped_entities = Counter()
        all_entities_with_uncertainty = {}
        for entities in all_entities:
            # Creating a copy of the list and removing the uncertainty values to obtain correct counts
            entities_copy = [entity.copy() for entity in entities]
            [entity.pop("uncertain") for entity in entities if "uncertain" in entity]
            # Sorting the entities to test equality
            sorted_entities = self.sort_entities(entities)
            # Searching if we already found an equal set of entities
            key = next(
                (key for key in grouped_entities.keys() if self.sort_entities(json.loads(key)) == sorted_entities),
                json.dumps(entities),
            )
            # Keys in the Counter are dicts dumped into strings, Counter can't count dicts
            grouped_entities.update([key])
            # Storing the list with complete values (uncertainty included) in a "cache"
            all_entities_with_uncertainty[key] = entities_copy

        if len(grouped_entities) > 1:
            self.process.add_log(
                f"Differing sets of entities were found on annotations from task {task.id}", logging.WARNING
            )

        nb_failed, nb_skipped = 0, 0
        for entities_str, count in grouped_entities.items():
            # Retrieving the list of complete values (with uncertainty) from the "cache"
            entities = self.sort_entities(all_entities_with_uncertainty[entities_str])

            # Publishing the entities
            nb_publications, confidence = (1, count / len(all_entities)) if not self.use_raw_publication else (count, 1)
            published = [
                self.create_transcription_and_transcription_entities(
                    task,
                    entities,
                    confidence=confidence,
                )
                for _i in range(nb_publications)
            ]

            nb_failed += nb_publications - sum(published)
            nb_empty_entities = sum([not entity.get("value") for entity in entities])
            # Truly skipped entities are the one coming from incomplete answers (some entities are empty) not from blank ones (all entities are empty)
            if nb_empty_entities != len(entities):
                nb_skipped += nb_empty_entities * nb_publications

        if nb_failed:
            # At least one transcription publication failed completely (transcription creation) or partially (entities creation/linking)
            return False

        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} empty entities from the annotations on the task {task.id}",
                logging.INFO,
            )

        return True

    def get_allowed_classes(self, project):
        try:
            ml_classes = list(self.arkindex_client.paginate("ListCorpusMLClasses", id=self.corpus_id))
        except ErrorResponse as e:
            self.process.add_log(
                f"Failed to retrieve available classes on the Arkindex corpus {self.corpus_id}: {e.status_code} - {e.content}",
                logging.ERROR,
            )
            return {}

        external_ids = [ml_class["id"] for ml_class in ml_classes]
        return {
            str(internal_id): external_id
            for internal_id, external_id in project.classes.filter(
                provider=self.arkindex_provider, provider_object_id__in=external_ids
            ).values_list("id", "provider_object_id")
        }

    def get_corpus_entity_types(self):
        try:
            entity_types = list(self.arkindex_client.paginate("ListCorpusEntityTypes", id=self.corpus_id))
        except ErrorResponse as e:
            self.process.add_log(
                f"Failed to retrieve existing entity types on the Arkindex corpus {self.corpus_id}: {e.status_code} - {e.content}",
                logging.ERROR,
            )
            return {}

        return {item["name"]: item["id"] for item in entity_types}

    def publish_classifications(self, task, annotations):
        classifications = [annotation.value.get("classification") for annotation in annotations]
        if not all(isinstance(classification, str) for classification in classifications):
            self.process.add_log(
                f"Skipping the task {task.id} as at least one of its last classification annotations holds an invalid value",
                logging.ERROR,
            )
            return False

        filtered_classifications = [
            classification_id for classification_id in classifications if classification_id in self.allowed_classes
        ]
        grouped_classifications = Counter(filtered_classifications)
        # Always group classifications because "Duplicated ML classes are not allowed from the same worker run." in Arkindex
        to_publish = [
            {"ml_class": self.allowed_classes[classification_id], "confidence": count / len(filtered_classifications)}
            for classification_id, count in grouped_classifications.items()
        ]

        if to_publish:
            try:
                self.arkindex_client.request(
                    "CreateClassifications",
                    body={
                        "parent": task.element.provider_object_id,
                        "worker_run_id": str(self.worker_run_id),
                        "classifications": to_publish,
                    },
                )
            except ErrorResponse as e:
                self.process.add_log(
                    f"Failed to publish classifications retrieved from the annotations on the task {task.id}: {e.status_code} - {e.content}",
                    logging.ERROR,
                )
                return False

            self.process.add_log(
                f"Successfully published {len(to_publish)} classifications with their confidence for task {task.id}",
                logging.INFO,
            )

        nb_skipped = len(classifications) - len(filtered_classifications)
        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} classification annotations for task {task.id} because no class matches them in the Arkindex corpus",
                logging.INFO,
            )

        return True

    def publish_annotations_at_element_level(self, publish_method):
        for task in (
            Task.objects.filter(campaign=self.campaign)
            .prefetch_related(
                Prefetch(
                    "user_tasks",
                    queryset=TaskUser.objects.filter(
                        state__in=self.exported_states,
                        annotations__isnull=False,
                        is_preview=False,
                    )
                    .order_by("-created", "id")
                    .distinct(),
                )
            )
            .distinct()
            .iterator(chunk_size=CHUNK_SIZE)
        ):
            # No need to publish anything if nothing is annotated for this task
            if not task.user_tasks.exists():
                continue

            last_annotations = [
                user_task.annotations.order_by("-version").first() for user_task in task.user_tasks.all()
            ]
            if not self.force_republication and any(annotation.published for annotation in last_annotations):
                self.process.add_log(
                    f"Skipping the task {task.id} as at least one of its latest version annotations has already been published",
                    logging.INFO,
                )
                continue

            published = publish_method(self, task, last_annotations)
            if published:
                for annotation in last_annotations:
                    annotation.published = True
                Annotation.objects.bulk_update(last_annotations, ["published"])

    def find_good_annotation(self, child, parent):
        # Earlier, we filtered child elements only to retrieve the ones linked to a task from the current campaign.
        # Consequently, we can use ".all()[0]" rather than "first()" as it won't reach the cached prefetched data.
        user_tasks = (
            child.tasks.all()[0]
            .user_tasks.filter(state__in=self.exported_states, annotations__isnull=False, is_preview=False)
            .distinct()
        )

        exploitable_entities = []
        # The "order_by" clause allows to retrieve Validated tasks first
        # in case the user chose to export both Annotated and Validated ones
        for user_task in user_tasks.order_by("-state"):
            last_annotation = user_task.annotations.order_by("-version").first()
            entities = last_annotation.value.get("values")
            if not isinstance(entities, list) or not entities:
                self.process.add_log(
                    f"Skipping annotation {last_annotation.id} on child {child.id} as it holds an invalid value",
                    logging.DEBUG,
                )
                continue

            exploitable_entities.append(entities)

        if not exploitable_entities:
            self.process.add_log(
                f"Couldn't find a good annotation on the child {child.id} to concatenate and publish on its {self.concat_parent_type} parent {parent.id}",
                logging.WARNING,
            )
            return

        if len(exploitable_entities) > 1:
            self.process.add_log(
                f"Found multiple good annotations on the child {child.id} to concatenate and publish on its {self.concat_parent_type} parent {parent.id}",
                logging.WARNING,
            )

        return self.sort_entities(exploitable_entities[0])

    def publish_concatenated_annotations_on_parent(self, parent, to_concatenate):
        # Forging the transcription with all the valid entities and publishing it
        transcription_list = []
        for entities in to_concatenate:
            values = [entity["value"] for entity in entities if entity.get("value")]
            if not values:
                transcription_list.append(EMPTY_SET_CHARACTER)
            else:
                transcription_list.append(" ".join(values))

        transcription_text = "\n".join(transcription_list)
        log_hint = f"the transcription forged from {len(to_concatenate)} concatenated annotations to publish on the {self.concat_parent_type} parent {parent.id}"

        transcription = self.publish_transcription(parent.provider_object_id, transcription_text, 1, log_hint)
        if not transcription:
            # No need to continue if the transcription wasn't published at all
            return

        self.process.add_log(f"Successfully published {log_hint}", logging.INFO)

        nb_skipped = 0
        entities_to_publish = []
        offset = 0
        for entities in to_concatenate:
            values = [entity["value"] for entity in entities if entity.get("value")]
            if not values:
                nb_skipped += len(entities)
                offset += len(EMPTY_SET_CHARACTER) + 1
                continue

            for entity in entities:
                # Skipping empty entities
                if not entity["value"]:
                    nb_skipped += 1
                    continue

                # Building entities_to_publish
                entity_type_id = self.get_or_create_entity_type(
                    f"from the concatenated annotations to publish on the {self.concat_parent_type} parent {parent.id}",
                    entity,
                )
                if entity_type_id:
                    entities_to_publish.append(
                        {
                            "offset": offset,
                            "length": len(entity["value"]),
                            "type_id": entity_type_id,
                            "confidence": 0.5 if entity.get("uncertain") else 1,
                        }
                    )

                # Incrementing the offset (even if there was a failure during the entity type creation)
                offset += len(entity["value"]) + 1

        if len(entities_to_publish):
            # Create the transcription entities on Arkindex using the bulk endpoint
            self.create_transcription_entities(
                f"forged from the concatenated annotations to publish on the {self.concat_parent_type} parent {parent.id}",
                entities_to_publish,
                transcription["id"],
            )

        if nb_skipped:
            self.process.add_log(
                f"Skipped {nb_skipped} empty entities from the concatenated annotations to publish on the {self.concat_parent_type} parent {parent.id}",
                logging.INFO,
            )

    def find_and_publish_concatenated_annotations(self, parent_element):
        to_concatenate = []
        # We only want children which are associated to a task from the current campaign
        valid_children = (
            parent_element.all_children()
            .filter(Exists(Task.objects.filter(element=OuterRef("pk"), campaign=self.campaign)))
            .prefetch_related(Prefetch("tasks", queryset=Task.objects.filter(campaign=self.campaign)))
        )
        if not valid_children.exists():
            self.process.add_log(
                f"Skipping the {self.concat_parent_type} parent {parent_element.id} as no annotated child elements were found on it",
                logging.WARNING,
            )
            return

        if valid_children.values("type").distinct().count() > 1:
            self.process.add_log(
                f"Skipping the {self.concat_parent_type} parent {parent_element.id} as multiple children types to concatenate were found",
                logging.ERROR,
            )
            return

        # Find a good annotation for each valid child on the current parent
        for child in valid_children:
            good_annotation = self.find_good_annotation(child, parent_element)
            if not good_annotation:
                self.process.add_log(
                    f"Skipping the {self.concat_parent_type} parent {parent_element.id} as at least one child was missing an annotation to concatenate",
                    logging.ERROR,
                )
                return
            to_concatenate.append(good_annotation)

        # Annotations are good to be concatenated and published on the parent
        self.publish_concatenated_annotations_on_parent(parent_element, to_concatenate)

    def publish_annotations_at_parent_level(self):
        self.process.add_log(
            f"Starting to export entities in concatenated transcriptions on the chosen parent type {self.concat_parent_type}",
            logging.INFO,
        )
        for parent_element in (
            Element.objects.filter(project=self.campaign.project, type=self.concat_parent_type, children__isnull=False)
            .distinct()
            .iterator(chunk_size=CHUNK_SIZE)
        ):
            self.find_and_publish_concatenated_annotations(parent_element)

    def run(self):
        publish_method = ARKINDEX_PUBLISH_METHODS.get(self.campaign.mode)

        project = self.campaign.project

        if self.campaign.mode == CampaignMode.Classification:
            if self.use_raw_publication:
                raise Exception(
                    "Duplicated ML classes are not allowed from the same worker run in Arkindex. Annotations must always be grouped before export."
                )

            self.allowed_classes = self.get_allowed_classes(project)
            if not self.allowed_classes:
                raise Exception(
                    f"No available matching class on the Arkindex corpus {self.corpus_id}, publication aborted"
                )

        if self.campaign.mode in [CampaignMode.Entity, CampaignMode.EntityForm]:
            self.entity_types = self.get_corpus_entity_types()

        if self.campaign.mode in [CampaignMode.ElementGroup, CampaignMode.Elements]:
            self.allowed_element_types = self.get_allowed_element_types(project)
            if not self.allowed_element_types:
                raise Exception(
                    f"No available matching type on the Arkindex corpus {self.corpus_id}, publication aborted"
                )

        if self.campaign.mode == CampaignMode.ElementGroup:
            if self.campaign.configuration.get("group_type") not in self.allowed_element_types:
                raise Exception(
                    f"The group type defined in the campaign configuration doesn't exist on the Arkindex corpus {self.corpus_id}, publication aborted"
                )
            self.configured_element_group_type = self.allowed_element_types[self.campaign.configuration["group_type"]]

        # Publish at element level
        self.publish_annotations_at_element_level(publish_method)

        # Extra logic for EntityForm campaigns, publish at parent level following the current configuration
        if self.campaign.mode == CampaignMode.EntityForm and self.concat_parent_type:
            self.publish_annotations_at_parent_level()


ARKINDEX_PUBLISH_METHODS = {
    CampaignMode.Transcription: ArkindexExport.publish_transcriptions,
    CampaignMode.Elements: ArkindexExport.publish_elements,
    CampaignMode.ElementGroup: ArkindexExport.publish_element_groups,
    CampaignMode.Entity: ArkindexExport.publish_entities,
    CampaignMode.EntityForm: ArkindexExport.publish_transcription_entities,
    CampaignMode.Classification: ArkindexExport.publish_classifications,
}
