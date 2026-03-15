# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

from plane.app.permissions.base import ROLE


VALID_ROLE_VALUES = [ROLE.ADMIN.value, ROLE.MEMBER.value, ROLE.GUEST.value]
VALID_INACTIVE_MEMBERSHIP_STRATEGIES = ["reactivate", "purge"]


class ProvisioningWorkspaceMembershipSerializer(serializers.Serializer):
    slug = serializers.CharField(required=True)
    role = serializers.IntegerField(required=False, default=ROLE.ADMIN.value)

    def validate_role(self, value):
        if value not in VALID_ROLE_VALUES:
            raise serializers.ValidationError("Invalid workspace role")
        return value


class ProvisioningProjectMembershipSerializer(serializers.Serializer):
    project_id = serializers.UUIDField(required=True)
    role = serializers.IntegerField(required=False, default=ROLE.ADMIN.value)

    def validate_role(self, value):
        if value not in VALID_ROLE_VALUES:
            raise serializers.ValidationError("Invalid project role")
        return value


class ProvisioningIdentitySerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    first_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    last_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    display_name = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    user_timezone = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    inactive_membership_strategy = serializers.ChoiceField(
        required=False,
        choices=VALID_INACTIVE_MEMBERSHIP_STRATEGIES,
        default="reactivate",
    )
    is_instance_admin = serializers.BooleanField(required=False, default=False)
    create_api_token = serializers.BooleanField(required=False, default=True)
    api_token_label = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    api_token_description = serializers.CharField(required=False, allow_blank=True, allow_null=True, default=None)
    expired_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    workspace_memberships = ProvisioningWorkspaceMembershipSerializer(many=True, required=False, default=list)
    project_memberships = ProvisioningProjectMembershipSerializer(many=True, required=False, default=list)


class ProvisioningRequestSerializer(serializers.Serializer):
    users = ProvisioningIdentitySerializer(many=True, required=True)

    def validate_users(self, value):
        emails = [item["email"].strip().lower() for item in value]
        if len(emails) != len(set(emails)):
            raise serializers.ValidationError("Duplicate emails are not allowed in a single provisioning request")
        return value
