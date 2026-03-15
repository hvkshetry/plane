# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.test.utils import override_settings

from plane.license.models import InstanceConfiguration
from plane.license.utils.encryption import decrypt_data, encrypt_data


@pytest.mark.unit
@pytest.mark.django_db
class TestConfigureInstanceCommand:
    @pytest.fixture(autouse=True)
    def locmem_cache(self):
        with override_settings(
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                    "LOCATION": "plane-test-cache",
                }
            }
        ):
            yield

    def test_updates_explicit_env_backed_values_and_invalidates_instance_cache(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")
        monkeypatch.setenv("EMAIL_HOST", "smtp-relay.brevo.com")
        monkeypatch.setenv("EMAIL_HOST_PASSWORD", "new-smtp-password")

        InstanceConfiguration.objects.create(
            key="EMAIL_HOST",
            value="old-host.invalid",
            category="SMTP",
            is_encrypted=False,
        )
        InstanceConfiguration.objects.create(
            key="EMAIL_HOST_PASSWORD",
            value=encrypt_data("old-smtp-password"),
            category="SMTP",
            is_encrypted=True,
        )

        cache.set("/api/instances/", {"data": {"stale": True}, "status": 200}, 300)
        cache.set("/api/instances/configurations/", {"data": {"stale": True}, "status": 200}, 300)

        call_command("configure_instance")

        email_host = InstanceConfiguration.objects.get(key="EMAIL_HOST")
        assert email_host.value == "smtp-relay.brevo.com"

        email_host_password = InstanceConfiguration.objects.get(key="EMAIL_HOST_PASSWORD")
        assert decrypt_data(email_host_password.value) == "new-smtp-password"

        assert cache.get("/api/instances/") is None
        assert cache.get("/api/instances/configurations/") is None

    def test_does_not_overwrite_existing_values_for_absent_env_keys(self, monkeypatch):
        monkeypatch.setenv("SECRET_KEY", "test-secret-key")
        monkeypatch.delenv("EMAIL_FROM", raising=False)

        InstanceConfiguration.objects.create(
            key="EMAIL_FROM",
            value="Plane Admin <admin@example.com>",
            category="SMTP",
            is_encrypted=False,
        )

        call_command("configure_instance")

        email_from = InstanceConfiguration.objects.get(key="EMAIL_FROM")
        assert email_from.value == "Plane Admin <admin@example.com>"
