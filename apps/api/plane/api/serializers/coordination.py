# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from rest_framework import serializers

from plane.db.models import IssueCoordinationState, User

from .base import BaseSerializer


class IssueCoordinationStateSerializer(BaseSerializer):
    approver_id = serializers.PrimaryKeyRelatedField(
        source="approver",
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    claimed_by_id = serializers.PrimaryKeyRelatedField(
        source="claimed_by",
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    last_actor_id = serializers.PrimaryKeyRelatedField(
        source="last_actor",
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )

    class Meta:
        model = IssueCoordinationState
        fields = [
            "id",
            "issue",
            "route_to",
            "reply_identity",
            "coordination_status",
            "approver_id",
            "allowed_responder",
            "waiting_on",
            "waiting_since",
            "claimed_by_id",
            "claim_expires_at",
            "last_actor_id",
            "last_transition_at",
            "metadata",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "issue",
            "created_at",
            "updated_at",
        ]


class IssueCoordinationActionSerializer(serializers.Serializer):
    route_to = serializers.CharField(required=False, allow_blank=True)
    reply_identity = serializers.CharField(required=False, allow_blank=True)
    coordination_status = serializers.CharField(required=False, allow_blank=True)
    approver_id = serializers.PrimaryKeyRelatedField(
        source="approver",
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    allowed_responder = serializers.CharField(required=False, allow_blank=True)
    waiting_on = serializers.CharField(required=False, allow_blank=True)
    waiting_since = serializers.DateTimeField(required=False, allow_null=True)
    claimed_by_id = serializers.PrimaryKeyRelatedField(
        source="claimed_by",
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    claim_expires_at = serializers.DateTimeField(required=False, allow_null=True)
    last_actor_id = serializers.PrimaryKeyRelatedField(
        source="last_actor",
        queryset=User.objects.all(),
        required=False,
        allow_null=True,
    )
    metadata = serializers.JSONField(required=False)
    lease_seconds = serializers.IntegerField(required=False, min_value=1, max_value=86400)
    assignee_ids = serializers.ListField(
        child=serializers.PrimaryKeyRelatedField(queryset=User.objects.all()),
        required=False,
    )
    clear_assignees = serializers.BooleanField(required=False, default=False)
    comment_html = serializers.CharField(required=False, allow_blank=True)
    channel = serializers.CharField(required=False, allow_blank=True)
    message_id = serializers.CharField(required=False, allow_blank=True)
    note = serializers.CharField(required=False, allow_blank=True)
