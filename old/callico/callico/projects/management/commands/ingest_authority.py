# -*- coding: utf-8 -*-
import csv
import logging
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from callico.projects.models import Authority, AuthorityValue

logger = logging.getLogger(__name__)

BATCH_SIZE = 1000


class Command(BaseCommand):
    help = "Ingest a CSV file as Authority and AuthorityValue objects."

    def add_arguments(self, parser):
        super().add_arguments(parser)

        parser.add_argument(
            "csv_path",
            help="Path to the CSV file to ingest in Callico as a new authority",
            type=Path,
        )
        parser.add_argument(
            "--name",
            help="Name of the authority to ingest",
            type=str,
            required=True,
        )
        parser.add_argument(
            "--description",
            help="Optional description of the authority to ingest",
            type=str,
            default="",
        )
        parser.add_argument(
            "--no-header",
            help="If set, the first line in the CSV file will be ingested as a value, this is useful for CSV without header",
            action="store_true",
        )
        parser.add_argument(
            "--value-column",
            help="Index (1-based) of the column containing the authority values",
            type=int,
            required=True,
        )
        parser.add_argument(
            "--id-column",
            help="Index (1-based) of the column containing the values identifier in the authority, if any",
            type=int,
        )

    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        if not csv_path.exists():
            raise CommandError(f'Provided file at "{csv_path}" does not exist')

        if not csv_path.is_file():
            raise CommandError(f'Provided path "{csv_path}" is not a proper file')

        if csv_path.suffix != ".csv":
            raise CommandError(f'Provided file at "{csv_path}" is not a CSV')

        with csv_path.open("r") as csv_file:
            # Detect the delimiter used in the CSV file
            dialect = csv.Sniffer().sniff(csv_file.read(), delimiters=",;")
            csv_file.seek(0)

            reader = csv.reader(csv_file, dialect=dialect)

            header = {}
            perform_checks = True
            authority = None
            to_create = []
            for index, row in enumerate(reader):
                # There is a header in the file, we ignore the first line
                if not options["no_header"] and index == 0:
                    header = {index: column for index, column in enumerate(row, start=1)}
                    logger.warning(
                        "Skipping the first line in the CSV file as it has a header, set the --no-header option if you wish to ingest it"
                    )
                    continue

                id_column, value_column = options["id_column"], options["value_column"]
                # Perform integrity checks (once) on the CSV
                if perform_checks:
                    if id_column and (id_column < 1 or id_column > len(row)):
                        raise CommandError(
                            f'The CSV file at "{csv_path}" has no column at index {id_column} to retrieve the values identifier'
                        )

                    if value_column < 1 or value_column > len(row):
                        raise CommandError(
                            f'The CSV file at "{csv_path}" has no column at index {value_column} to retrieve authority values'
                        )

                    # No need to check the integrity more than once
                    perform_checks = False

                if not authority:
                    authority = Authority.objects.create(name=options["name"], description=options["description"])
                    logger.info(f'The authority "{authority}" has been successfully created with ID {authority.id}')

                to_create.append(
                    AuthorityValue(
                        authority=authority,
                        authority_value_id=row[id_column - 1] if id_column is not None else "",
                        value=row[value_column - 1],
                        metadata={
                            header.get(column, column): value
                            for column, value in enumerate(row, start=1)
                            if column not in [id_column, value_column]
                        },
                    )
                )

                # Once we have 1000 authority values to create, we do it and clear the list
                if len(to_create) >= BATCH_SIZE:
                    AuthorityValue.objects.bulk_create(to_create)
                    to_create = []
                    logger.info(f'{BATCH_SIZE} values have been added to the authority "{authority}"')

        # We don't forget to create the remaining authority values
        if to_create:
            AuthorityValue.objects.bulk_create(to_create)
            logger.info(f'{len(to_create)} values have been added to the authority "{authority}"')
