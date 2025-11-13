import logging
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.utils import IntegrityError

from callico.projects.models import Authority, AuthorityValue

pytestmark = pytest.mark.django_db

SAMPLES = Path(__file__).parent / "samples"
WITH_HEADER = SAMPLES / "authority_with_header.csv"


@pytest.mark.parametrize(
    "path, error",
    [
        ("oops.csv", 'Provided file at "oops.csv" does not exist'),
        (SAMPLES, f'Provided path "{SAMPLES}" is not a proper file'),
        (__file__, f'Provided file at "{__file__}" is not a CSV'),
    ],
)
def test_ingest_authority_wrong_csv_path(path, error):
    with pytest.raises(CommandError, match=error):
        call_command(
            "ingest_authority",
            path,
            "--name",
            "My authority",
            "--value-column",
            2,
        )


@pytest.mark.parametrize("index", [-10, 4])
def test_ingest_authority_missing_id_column(index):
    with pytest.raises(
        CommandError,
        match=f'The CSV file at "{WITH_HEADER}" has no column at index {index} to retrieve the values identifier',
    ):
        call_command(
            "ingest_authority",
            WITH_HEADER,
            "--name",
            "My authority",
            "--value-column",
            2,
            "--id-column",
            index,
        )


@pytest.mark.parametrize("index", [-10, 4])
def test_ingest_authority_missing_value_column(index):
    with pytest.raises(
        CommandError,
        match=f'The CSV file at "{WITH_HEADER}" has no column at index {index} to retrieve authority value',
    ):
        call_command(
            "ingest_authority",
            WITH_HEADER,
            "--name",
            "My authority",
            "--value-column",
            index,
        )


def test_ingest_authority_already_exists(authority):
    with pytest.raises(
        IntegrityError, match='duplicate key value violates unique constraint "projects_authority_name_key"'
    ):
        call_command(
            "ingest_authority",
            WITH_HEADER,
            "--name",
            authority.name,
            "--value-column",
            2,
        )


@pytest.mark.parametrize("with_header", [False, True])
@pytest.mark.parametrize("delimiter", [",", ";"])
@pytest.mark.parametrize("with_id", [False, True])
def test_ingest_authority(with_header, delimiter, with_id, tmp_path, caplog):
    csv_path = WITH_HEADER
    # 6 lines = 1 header + 5 authority values
    assert len(csv_path.read_text().splitlines()) == 6

    # Removing the header from our sample CSV file
    if not with_header:
        content = csv_path.read_text()
        csv_path = tmp_path / "without_header.csv"
        csv_path.write_text("\n".join(content.splitlines()[1:]))

        # 5 lines = no header + 5 authority values
        assert len(csv_path.read_text().splitlines()) == 5

    # Changing the "," default delimiter to ";" (to assert the Sniffer works well)
    if delimiter == ";":
        content = csv_path.read_text()
        csv_path = tmp_path / "change_delimiter.csv"
        csv_path.write_text(content.replace(",", ";"))

    extras = []
    # Do not skip the first line in the CSV
    if not with_header:
        extras.extend(["--no-header"])

    # Extract a specific column as `authority_value_id`
    if with_id:
        extras.extend(["--id-column", 1])

    call_command(
        "ingest_authority",
        csv_path,
        "--name",
        "My authority",
        "--description",
        "My beautiful authority record",
        *extras,
        "--value-column",
        2,
    )

    # Assert all objects were properly created in database
    assert Authority.objects.count() == 1
    assert AuthorityValue.objects.count() == 5

    created_authority = Authority.objects.get()
    assert created_authority.name == "My authority"
    assert created_authority.description == "My beautiful authority record"

    # When an header is available we namely store metadata, otherwise we simply use the column index
    extra_col = ["3", "EXTRAS"][with_header]
    if with_id:
        expected = [
            ("1111", "France", {extra_col: "beautiful"}),
            ("2222", "Germany", {extra_col: "amazing"}),
            ("3333", "Italy", {extra_col: "wow"}),
            ("4444", "Japan", {extra_col: "kawaii"}),
            ("5555", "Spain", {extra_col: "cute"}),
        ]
    else:
        # When an header is available we namely store metadata, otherwise we simply use the column index
        id_col = ["1", "ID"][with_header]
        expected = [
            ("", "France", {id_col: "1111", extra_col: "beautiful"}),
            ("", "Germany", {id_col: "2222", extra_col: "amazing"}),
            ("", "Italy", {id_col: "3333", extra_col: "wow"}),
            ("", "Japan", {id_col: "4444", extra_col: "kawaii"}),
            ("", "Spain", {id_col: "5555", extra_col: "cute"}),
        ]

    assert list(created_authority.values.values_list("authority_value_id", "value", "metadata")) == expected

    extra_logs = []
    if with_header:
        extra_logs.append(
            (
                logging.WARNING,
                "Skipping the first line in the CSV file as it has a header, set the --no-header option if you wish to ingest it",
            )
        )

    assert [(level, message) for _module, level, message in caplog.record_tuples] == [
        *extra_logs,
        (logging.INFO, f'The authority "My authority" has been successfully created with ID {created_authority.id}'),
        (logging.INFO, '5 values have been added to the authority "My authority"'),
    ]
