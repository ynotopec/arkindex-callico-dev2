import logging

from apistar.exceptions import ErrorResponse
from arkindex import ArkindexClient
from arkindex.exceptions import SchemaError

from callico.projects.models import Provider, ProviderType


def is_500_error(exception: Exception):
    return isinstance(exception, ErrorResponse) and 500 <= exception.status_code


class ArkindexProcessBase:
    """Setup an ArkindexClient instance for Arkindex processes"""

    def __init__(self, process, arkindex_provider):
        self.process = process

        self.arkindex_provider = Provider.objects.get(id=arkindex_provider, type=ProviderType.Arkindex)
        self.setup_arkindex_client()

        self.process.add_log(
            f'Using Arkindex provider "{self.arkindex_provider}" ({self.arkindex_provider.api_url})', logging.INFO
        )

    def setup_arkindex_client(self):
        try:
            self.arkindex_client = ArkindexClient(
                base_url=self.arkindex_provider.api_url,
                token=self.arkindex_provider.api_token,
            )
        except SchemaError as e:
            raise Exception(f'Invalid Arkindex URL for provider "{self.arkindex_provider}": {e}')
