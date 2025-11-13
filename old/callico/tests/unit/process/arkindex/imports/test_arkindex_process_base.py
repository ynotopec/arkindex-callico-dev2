import logging
import re
from urllib.parse import urljoin

import pytest
from arkindex.client import SCHEMA_ENDPOINT
from arkindex.mock import MockApiClient

from callico.process.arkindex.imports import ArkindexProcessBase

pytestmark = pytest.mark.django_db


def test_arkindex_process_base_error(responses, arkindex_provider, process):
    schema_url = urljoin(arkindex_provider.api_url, SCHEMA_ENDPOINT)
    responses.add(responses.GET, schema_url, body=Exception())

    with pytest.raises(
        Exception,
        match=re.escape(
            f'Invalid Arkindex URL for provider "{arkindex_provider}": Could not retrieve a proper OpenAPI schema from {schema_url}'
        ),
    ):
        ArkindexProcessBase(process, str(arkindex_provider.id))


def test_arkindex_process_base(caplog, mock_arkindex_client, project, process):
    base = ArkindexProcessBase(process, str(project.provider.id))

    assert base.arkindex_provider == project.provider
    assert isinstance(base.arkindex_client, MockApiClient)
    assert (
        [(level, message) for _module, level, message in caplog.record_tuples]
        == [
            (logging.INFO, 'Using Arkindex provider "Arkindex test" (https://arkindex.teklia.com/api/v1)'),
        ]
        == [(log["level"], log["content"]) for log in process.parsed_logs]
    )
