"""
Factory Boy factories for SequoIA models.
"""

import factory
from factory.django import DjangoModelFactory

from apps.organizations.models import Organization, OrganizationSettings
from apps.accounts.models import User
from apps.fibers.models import FiberAssignment
from apps.monitoring.models import Infrastructure
from apps.preferences.models import UserPreferences


class OrganizationFactory(DjangoModelFactory):
    class Meta:
        model = Organization

    name = factory.Sequence(lambda n: f'Organization {n}')
    is_active = True


class OrganizationSettingsFactory(DjangoModelFactory):
    class Meta:
        model = OrganizationSettings
        django_get_or_create = ('organization',)

    organization = factory.SubFactory(OrganizationFactory)
    timezone = 'Europe/Paris'


class UserFactory(DjangoModelFactory):
    class Meta:
        model = User
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f'user{n}')
    email = factory.LazyAttribute(lambda o: f'{o.username}@test.com')
    organization = factory.SubFactory(OrganizationFactory)
    role = 'admin'
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **kwargs):
        self.set_password(extracted or 'testpass123')
        if create:
            self.save()


class FiberAssignmentFactory(DjangoModelFactory):
    class Meta:
        model = FiberAssignment

    organization = factory.SubFactory(OrganizationFactory)
    fiber_id = factory.Sequence(lambda n: f'fiber-{n}')


class InfrastructureFactory(DjangoModelFactory):
    class Meta:
        model = Infrastructure

    id = factory.Sequence(lambda n: f'infra-{n}')
    organization = factory.SubFactory(OrganizationFactory)
    type = 'bridge'
    name = factory.Sequence(lambda n: f'Bridge {n}')
    fiber_id = 'fiber-carros'
    start_channel = 100
    end_channel = 200


class UserPreferencesFactory(DjangoModelFactory):
    class Meta:
        model = UserPreferences
        django_get_or_create = ('user',)

    user = factory.SubFactory(UserFactory)
    dashboard = {}
    map_config = {}
