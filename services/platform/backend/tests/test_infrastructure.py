"""
Tests for infrastructure endpoint.
"""

import pytest
from rest_framework import status

from tests.factories import InfrastructureFactory


pytestmark = pytest.mark.django_db


class TestInfrastructureList:
    url = '/api/infrastructure'

    def test_list_infrastructure(self, authenticated_client, infrastructure):
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data) == 2

        # Verify camelCase field names match frontend type
        item = data[0]
        assert 'id' in item
        assert 'type' in item
        assert 'name' in item
        assert 'fiberId' in item
        assert 'startChannel' in item
        assert 'endChannel' in item

    def test_infrastructure_types(self, authenticated_client, infrastructure):
        response = authenticated_client.get(self.url)
        data = response.json()
        types = {item['type'] for item in data}
        assert types == {'bridge', 'tunnel'}

    def test_infrastructure_unauthenticated(self, api_client):
        response = api_client.get(self.url)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_infrastructure_tenant_isolation(self, authenticated_client, other_org_client, org, other_org):
        # Create infra in org A
        InfrastructureFactory(organization=org, id='org-a-bridge', name='Org A Bridge')
        # Create infra in org B
        InfrastructureFactory(organization=other_org, id='org-b-bridge', name='Org B Bridge')

        # Org A user should only see org A infrastructure
        response = authenticated_client.get(self.url)
        data = response.json()
        names = [item['name'] for item in data]
        assert 'Org A Bridge' in names
        assert 'Org B Bridge' not in names

        # Org B user should only see org B infrastructure
        response = other_org_client.get(self.url)
        data = response.json()
        names = [item['name'] for item in data]
        assert 'Org B Bridge' in names
        assert 'Org A Bridge' not in names

    def test_empty_infrastructure(self, authenticated_client):
        response = authenticated_client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == []
