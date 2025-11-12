import logging
from typing import Dict, List

from apistar.exceptions import ErrorResponse

from callico.process.arkindex.base import ArkindexProcessBase
from callico.process.models import Process
from callico.projects.models import Class, Element, Image, Project, TextOrientation, Type


class ArkindexFetchExtraInfo(ArkindexProcessBase):
    def __init__(
        self,
        process: Process,
        arkindex_provider: str,
        project_id: str,
    ):
        self.project = Project.objects.get(id=project_id)
        process.add_log(f'Using project "{self.project}"', logging.INFO)
        super().__init__(process, arkindex_provider)

    def create_classes(self, project):
        ml_classes = self.arkindex_client.paginate("ListCorpusMLClasses", id=project.provider_object_id)
        for ml_class in ml_classes:
            self.process.add_log(f'Processing class "{ml_class["name"]}"...', logging.DEBUG)
            Class.objects.update_or_create(
                project_id=project.id,
                name=ml_class["name"],
                defaults={
                    "provider_id": self.arkindex_provider.id,
                    "provider_object_id": ml_class["id"],
                },
            )
            self.process.add_log(f'Class "{ml_class["name"]}" processed', logging.INFO)

    def create_types(self, project):
        corpus = self.arkindex_client.request("RetrieveCorpus", id=project.provider_object_id)

        for element_type in corpus["types"]:
            self.process.add_log(f'Processing element type "{element_type["display_name"]}"...', logging.DEBUG)
            Type.objects.update_or_create(
                project_id=project.id,
                name=element_type["display_name"],
                defaults={
                    "folder": element_type["folder"],
                    "color": element_type["color"],
                    "provider_id": self.arkindex_provider.id,
                    "provider_object_id": element_type["slug"],
                },
            )
            self.process.add_log(f'Type "{element_type["display_name"]}" processed', logging.INFO)

    def store_worker_runs(self, project):
        worker_runs = self.arkindex_client.paginate("ListCorpusWorkerRuns", id=project.provider_object_id)
        project.provider_extra_information.update({"worker_runs": list(worker_runs)})
        project.save()
        self.process.add_log("Worker runs stored", logging.INFO)

    def store_entity_types(self, project):
        entity_types = self.arkindex_client.paginate("ListCorpusEntityTypes", id=project.provider_object_id)
        project.provider_extra_information.update({"entity_types": list(entity_types)})
        project.save()
        self.process.add_log("Entity types stored", logging.INFO)

    def run(self):
        if not self.project.provider_object_id:
            self.process.add_log(
                "Skipping the retrieval of additional information as the project does not have a corpus", logging.INFO
            )
            return

        try:
            self.create_classes(self.project)
        except ErrorResponse as e:
            raise Exception(f"Failed creating classes: {e.status_code} - {e.content}")

        try:
            self.create_types(self.project)
        except ErrorResponse as e:
            raise Exception(f"Failed creating element types: {e.status_code} - {e.content}")

        try:
            self.store_worker_runs(self.project)
        except ErrorResponse as e:
            raise Exception(
                f"Failed adding worker runs to the project extra information: {e.status_code} - {e.content}"
            )

        try:
            self.store_entity_types(self.project)
        except ErrorResponse as e:
            raise Exception(
                f"Failed adding entity types to the project extra information: {e.status_code} - {e.content}"
            )


class ArkindexImport(ArkindexProcessBase):
    corpus = None

    def __init__(
        self,
        process: Process,
        arkindex_provider: str,
        project_id: str,
        types: List[str],
        class_name: str,
        metadata: List[str],
        elements_worker_run: Dict[str, str],
        transcriptions: List[str],
        entities: List[str],
        dataset_sets: List[str],
    ):
        self.project = Project.objects.get(id=project_id)
        process.add_log(f'Using project "{self.project}"', logging.INFO)

        super().__init__(process, arkindex_provider)

        self.types = types
        self.class_name = class_name
        self.metadata = metadata
        self.elements_worker_run = elements_worker_run
        self.trs_sources = transcriptions
        self.entities_sources = entities
        self.dataset_sets = dataset_sets

    @staticmethod
    def from_configuration(process, config):
        return ArkindexImport(
            process=process,
            arkindex_provider=config["arkindex_provider"],
            project_id=config["project_id"],
            types=config["types"],
            class_name=config["class_name"],
            metadata=config["metadata"],
            elements_worker_run=config["elements_worker_run"],
            transcriptions=config["transcriptions"],
            entities=config["entities"],
            dataset_sets=config["dataset_sets"],
        )

    def get_project(self, project_id):
        try:
            return Project.objects.get(id=project_id)
        except Project.DoesNotExist:
            raise Exception("Project doesn't exist")

    def get_arkindex_object(self, operation_id, object_id, object_type):
        try:
            return self.arkindex_client.request(operation_id, id=object_id)
        except ErrorResponse as e:
            if e.status_code == 403:
                raise Exception(f'Invalid Arkindex token for provider "{self.arkindex_provider}"')
            if e.status_code == 404:
                raise Exception(
                    f"Arkindex {object_type} ({object_id}) doesn't exist or you don't have the reading rights on the corpus"
                )
            raise Exception(f"Failed retrieving {object_type}: {e.status_code} - {e.content}")

    def get_full_polygon(self, image):
        if not image:
            return
        return [[0, 0], [0, image.height], [image.width, image.height], [image.width, 0], [0, 0]]

    def create_image(self, zone):
        if not zone:
            return None, 0
        return Image.objects.get_or_create(
            iiif_url=zone["image"]["url"],
            defaults={
                "width": zone["image"]["width"],
                "height": zone["image"]["height"],
            },
        )

    def get_transcription(self, element):
        try:
            transcriptions = list(
                self.arkindex_client.paginate(
                    "ListTranscriptions",
                    id=element["id"],
                )
            )
        except ErrorResponse as e:
            # If any error occurs, log the error and continue anyway
            self.process.add_log(
                f'Failed to retrieve transcriptions for element "{element["name"]}": {e.status_code} - {e.content}',
                logging.DEBUG,
            )
            return {}

        # Filtering out transcriptions produced by a worker to only keep manual ones
        manual_transcriptions = [transcription for transcription in transcriptions if not transcription["worker_run"]]

        preferred_transcriptions = []
        for trs_source in self.trs_sources:
            filtered_transcriptions = (
                manual_transcriptions
                if trs_source == "manual"
                else [
                    transcription
                    for transcription in transcriptions
                    if transcription["worker_run"] and transcription["worker_run"]["id"] == trs_source
                ]
            )
            if filtered_transcriptions:
                preferred_transcriptions = filtered_transcriptions
                break

        if preferred_transcriptions:
            best_transcription = max(preferred_transcriptions, key=lambda tr: tr["confidence"] or 0.0)
            return {
                "transcription": best_transcription,
                "text_orientation": TextOrientation.RightToLeft
                if best_transcription["orientation"].endswith("-rl")
                else TextOrientation.LeftToRight,
            }

        # No transcriptions produced by the specified sources was found on the element
        return {}

    def get_entities(self, transcription_id):
        try:
            tr_entities = list(
                self.arkindex_client.paginate(
                    "ListTranscriptionEntities",
                    id=transcription_id,
                )
            )
        except ErrorResponse as e:
            # If any error occurs, log the error and continue anyway
            self.process.add_log(
                f'Failed to retrieve transcription entities for transcription "{transcription_id}": {e.status_code} - {e.content}',
                logging.DEBUG,
            )
            return []

        # Filtering out entities produced by a worker to only keep manual ones
        manual_tr_entities = [tr_entity for tr_entity in tr_entities if not tr_entity["worker_run"]]

        for entities_source in self.entities_sources:
            filtered_tr_entities = (
                manual_tr_entities
                if entities_source == "manual"
                else [
                    tr_entity
                    for tr_entity in tr_entities
                    if tr_entity["worker_run"] and tr_entity["worker_run"]["id"] == entities_source
                ]
            )
            if filtered_tr_entities:
                return [
                    {
                        "provider_object_id": tr_entity["entity"]["id"],
                        "name": tr_entity["entity"]["name"],
                        "type": tr_entity["entity"]["type"]["name"],
                        "offset": tr_entity["offset"],
                        "length": tr_entity["length"],
                        "confidence": tr_entity["confidence"],
                    }
                    for tr_entity in filtered_tr_entities
                ]

        # No entities produced by the specified sources was found on the element
        return []

    def get_metadata(self, element):
        """Look for metadata matching the given keys among the imported element and its parents.
        Duplicated keys are arbitrarily ignored.
        """
        try:
            metadata = list(
                self.arkindex_client.paginate(
                    "ListElementMetaData",
                    id=element["id"],
                    load_parents=True,
                )
            )
        except ErrorResponse as e:
            self.process.add_log(
                f"""Failed to retrieve metadata for element "{element['name']}": {e.status_code} - {e.content}""",
                logging.DEBUG,
            )
            return {}

        return {md["name"]: str(md["value"]) for md in metadata if md["name"] in self.metadata}

    def create_element(self, project, element, parent, image):
        full_polygon = self.get_full_polygon(image)
        transcription_fields = self.get_transcription(element) if self.trs_sources else {}
        metadata = self.get_metadata(element) if self.metadata else {}
        entities = (
            self.get_entities(transcription_fields["transcription"]["id"])
            if transcription_fields and self.entities_sources
            else []
        )

        try:
            # The type should already exist on the Project
            type = project.types.get(provider_id=self.arkindex_provider.id, provider_object_id=element["type"])
        except Type.DoesNotExist:
            raise Exception(
                f"Failed retrieving the type \"{element['type']}\" to link to the element, you should update your project in the admin to launch a new task to retrieve extra information (types included) from Arkindex"
            )

        return Element.objects.update_or_create(
            project_id=project.id,
            provider_object_id=element["id"],
            provider_id=self.arkindex_provider.id,
            defaults={
                "name": element["name"],
                "type": type,
                "parent": parent,
                "image": image,
                "polygon": element["zone"]["polygon"] if image and element["zone"]["polygon"] != full_polygon else None,
                "order": None,
                **transcription_fields,
                "metadata": metadata,
                "entities": entities,
            },
        )

    def create_elements(self, project, elements, parent=None):
        for element in list(elements):
            if (
                (not self.types or element["type"] in self.types)
                and (not self.class_name or self.class_name in [cls["ml_class"]["name"] for cls in element["classes"]])
                and (
                    element["type"] not in self.elements_worker_run
                    or (
                        element["worker_run"]
                        and element["worker_run"]["id"] == self.elements_worker_run[element["type"]]
                    )
                )
            ):
                self.process.add_log(f'Processing element "{element["name"]}"...', logging.DEBUG)
                image, _created = self.create_image(element["zone"])
                next_parent, _created = self.create_element(project, element, parent, image)
                self.process.add_log(f'Element "{element["name"]}" processed', logging.INFO)
            else:
                self.process.add_log(f'Element "{element["name"]}" ignored', logging.DEBUG)
                next_parent = parent

            if element["has_children"]:
                # On the frontend, in a parent, elements are ordered by "position" by default
                children = self.arkindex_client.paginate(
                    "ListElementChildren",
                    id=element["id"],
                    order="position",
                    with_has_children=True,
                    with_classes=True,
                )
                self.create_elements(project, children, parent=next_parent)

    def get_element(self, element_id, get_element_log=False):
        element = self.get_arkindex_object("RetrieveElement", element_id, "element")
        if get_element_log:
            self.process.add_log(
                f'Using Arkindex element "{element["type"].capitalize()} {element["name"]}"', logging.INFO
            )

        return {
            **element,
            # Force has_children to True, as it is not being sent in the RetrieveElement response
            "has_children": True,
            # RetrieveElement and ListElementChildren do not return the same attributes
            "classes": element["classifications"],
        }

    def get_corpus_elements(self, corpus_id):
        corpus = self.get_arkindex_object("RetrieveCorpus", corpus_id, "corpus")
        self.process.add_log(f'Using Arkindex corpus "{corpus["name"]}"', logging.INFO)
        # On the frontend, at root level on a corpus, elements are ordered by "name" by default not "position"
        return self.arkindex_client.paginate(
            "ListElements",
            corpus=corpus_id,
            top_level=True,
            with_has_children=True,
            with_classes=True,
        )

    def get_dataset(self, dataset_id):
        dataset = self.get_arkindex_object("RetrieveDataset", dataset_id, "dataset")
        self.process.add_log(f'Using Arkindex dataset "{dataset["name"]}"', logging.INFO)

        # Check that the sets given in the configuration, if any, are present in the dataset
        dataset_set_names = [item["name"] for item in dataset["sets"]]
        if self.dataset_sets and any(set_name not in dataset_set_names for set_name in self.dataset_sets):
            raise Exception(
                f'Some of the dataset sets provided in the configuration ({"/".join(self.dataset_sets)}) are not part of dataset {dataset["name"]}'
            )

        return dataset

    def get_dataset_elements(self, dataset_id):
        kwargs = {}
        # If there is only one selected set, we can filter directly in the API request
        if len(self.dataset_sets) == 1:
            kwargs = {"set": self.dataset_sets[0]}

        dataset_elements = self.arkindex_client.paginate("ListDatasetElements", id=dataset_id, **kwargs)

        # If there are more than one set in the configuration, filter the returned elements
        if len(self.dataset_sets) > 1:
            dataset_elements = filter(
                lambda dataset_element: dataset_element["set"] in self.dataset_sets, dataset_elements
            )

        return [self.get_element(dataset_element["element"]["id"]) for dataset_element in dataset_elements]

    def run(self, element_id=None, dataset_id=None, corpus_id=None):
        if element_id and dataset_id:
            raise Exception("Only one of dataset_id and element_id can be provided to start an Arkindex import")

        if element_id:
            element = self.get_element(str(element_id), get_element_log=True)

            if self.project.provider_object_id and self.project.provider_object_id != element["corpus"]["id"]:
                raise Exception("The element provided in the configuration is not part of the project corpus")

            elements = [element]

        elif dataset_id:
            dataset = self.get_dataset(str(dataset_id))
            if self.project.provider_object_id and self.project.provider_object_id != dataset["corpus_id"]:
                raise Exception("The dataset provided in the configuration is not part of the project corpus")

            self.process.add_log(f'Retrieving elements from Arkindex dataset "{dataset["name"]}"', logging.INFO)
            elements = self.get_dataset_elements(str(dataset_id))
        else:
            elements = self.get_corpus_elements(str(corpus_id))

        try:
            self.create_elements(self.project, elements)
        except ErrorResponse as e:
            raise Exception(f"Failed creating elements: {e.status_code} - {e.content}")
