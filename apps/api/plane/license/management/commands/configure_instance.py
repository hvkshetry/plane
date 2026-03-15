# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
import os

# Django imports
from django.core.management.base import BaseCommand, CommandError

# Module imports
from plane.license.models import InstanceConfiguration
from plane.utils.cache import invalidate_cache_directly
from plane.utils.instance_config_variables import instance_config_variables


class Command(BaseCommand):
    help = "Configure instance variables"

    @staticmethod
    def _normalize_value(value):
        return "" if value is None else str(value)

    def _sync_instance_configuration(self, item, encrypt_data, decrypt_data):
        key = item.get("key")
        env_present = key in os.environ
        target_value = os.environ.get(key) if env_present else item.get("value")
        target_category = item.get("category")
        target_is_encrypted = item.get("is_encrypted", False)

        obj, created = InstanceConfiguration.objects.get_or_create(key=key)

        if created:
            obj.category = target_category
            obj.is_encrypted = target_is_encrypted
            obj.value = encrypt_data(target_value) if target_is_encrypted else target_value
            obj.save()
            self.stdout.write(self.style.SUCCESS(f"{obj.key} loaded with value from environment variable."))
            return True

        # Only force-sync existing values when that key was explicitly provided to the container.
        if not env_present:
            self.stdout.write(self.style.WARNING(f"{obj.key} configuration already exists"))
            return False

        current_value = decrypt_data(obj.value) if obj.is_encrypted and obj.value else obj.value
        should_update = any(
            [
                obj.category != target_category,
                obj.is_encrypted != target_is_encrypted,
                self._normalize_value(current_value) != self._normalize_value(target_value),
            ]
        )

        if not should_update:
            self.stdout.write(self.style.WARNING(f"{obj.key} configuration already exists"))
            return False

        obj.category = target_category
        obj.is_encrypted = target_is_encrypted
        obj.value = encrypt_data(target_value) if target_is_encrypted else target_value
        update_fields = ["category", "is_encrypted", "value"]
        if hasattr(obj, "updated_at"):
            update_fields.append("updated_at")
        obj.save(update_fields=update_fields)
        self.stdout.write(self.style.SUCCESS(f"{obj.key} updated from environment variable."))
        return True

    def handle(self, *args, **options):
        from plane.license.utils.encryption import decrypt_data, encrypt_data
        from plane.license.utils.instance_value import get_configuration_value

        mandatory_keys = ["SECRET_KEY"]
        cache_paths_to_invalidate = {"/api/instances/", "/api/instances/configurations/"}
        did_update_configuration = False

        for item in mandatory_keys:
            if not os.environ.get(item):
                raise CommandError(f"{item} env variable is required.")

        for item in instance_config_variables:
            did_update_configuration = (
                self._sync_instance_configuration(item, encrypt_data, decrypt_data) or did_update_configuration
            )

        keys = ["IS_GOOGLE_ENABLED", "IS_GITHUB_ENABLED", "IS_GITLAB_ENABLED", "IS_GITEA_ENABLED"]
        if not InstanceConfiguration.objects.filter(key__in=keys).exists():
            for key in keys:
                if key == "IS_GOOGLE_ENABLED":
                    GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET = get_configuration_value(
                        [
                            {
                                "key": "GOOGLE_CLIENT_ID",
                                "default": os.environ.get("GOOGLE_CLIENT_ID", ""),
                            },
                            {
                                "key": "GOOGLE_CLIENT_SECRET",
                                "default": os.environ.get("GOOGLE_CLIENT_SECRET", "0"),
                            },
                        ]
                    )
                    if bool(GOOGLE_CLIENT_ID) and bool(GOOGLE_CLIENT_SECRET):
                        value = "1"
                    else:
                        value = "0"
                    InstanceConfiguration.objects.create(
                        key=key,
                        value=value,
                        category="AUTHENTICATION",
                        is_encrypted=False,
                    )
                    self.stdout.write(self.style.SUCCESS(f"{key} loaded with value from environment variable."))
                if key == "IS_GITHUB_ENABLED":
                    GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET = get_configuration_value(
                        [
                            {
                                "key": "GITHUB_CLIENT_ID",
                                "default": os.environ.get("GITHUB_CLIENT_ID", ""),
                            },
                            {
                                "key": "GITHUB_CLIENT_SECRET",
                                "default": os.environ.get("GITHUB_CLIENT_SECRET", "0"),
                            },
                        ]
                    )
                    if bool(GITHUB_CLIENT_ID) and bool(GITHUB_CLIENT_SECRET):
                        value = "1"
                    else:
                        value = "0"
                    InstanceConfiguration.objects.create(
                        key="IS_GITHUB_ENABLED",
                        value=value,
                        category="AUTHENTICATION",
                        is_encrypted=False,
                    )
                    self.stdout.write(self.style.SUCCESS(f"{key} loaded with value from environment variable."))
                if key == "IS_GITLAB_ENABLED":
                    GITLAB_HOST, GITLAB_CLIENT_ID, GITLAB_CLIENT_SECRET = get_configuration_value(
                        [
                            {
                                "key": "GITLAB_HOST",
                                "default": os.environ.get("GITLAB_HOST", "https://gitlab.com"),
                            },
                            {
                                "key": "GITLAB_CLIENT_ID",
                                "default": os.environ.get("GITLAB_CLIENT_ID", ""),
                            },
                            {
                                "key": "GITLAB_CLIENT_SECRET",
                                "default": os.environ.get("GITLAB_CLIENT_SECRET", ""),
                            },
                        ]
                    )
                    if bool(GITLAB_HOST) and bool(GITLAB_CLIENT_ID) and bool(GITLAB_CLIENT_SECRET):
                        value = "1"
                    else:
                        value = "0"
                    InstanceConfiguration.objects.create(
                        key="IS_GITLAB_ENABLED",
                        value=value,
                        category="AUTHENTICATION",
                        is_encrypted=False,
                    )
                    self.stdout.write(self.style.SUCCESS(f"{key} loaded with value from environment variable."))
                if key == "IS_GITEA_ENABLED":
                    GITEA_HOST, GITEA_CLIENT_ID, GITEA_CLIENT_SECRET = get_configuration_value(
                        [
                            {
                                "key": "GITEA_HOST",
                                "default": os.environ.get("GITEA_HOST", ""),
                            },
                            {
                                "key": "GITEA_CLIENT_ID",
                                "default": os.environ.get("GITEA_CLIENT_ID", ""),
                            },
                            {
                                "key": "GITEA_CLIENT_SECRET",
                                "default": os.environ.get("GITEA_CLIENT_SECRET", ""),
                            },
                        ]
                    )
                    if bool(GITEA_HOST) and bool(GITEA_CLIENT_ID) and bool(GITEA_CLIENT_SECRET):
                        value = "1"
                    else:
                        value = "0"
                    InstanceConfiguration.objects.create(
                        key="IS_GITEA_ENABLED",
                        value=value,
                        category="AUTHENTICATION",
                        is_encrypted=False,
                    )
                    self.stdout.write(self.style.SUCCESS(f"{key} loaded with value from environment variable."))
        else:
            for key in keys:
                self.stdout.write(self.style.WARNING(f"{key} configuration already exists"))

        if did_update_configuration:
            for path in cache_paths_to_invalidate:
                invalidate_cache_directly(path=path, user=False)
