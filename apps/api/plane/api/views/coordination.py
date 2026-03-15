# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response

from plane.api.serializers import (
    IssueCoordinationActionSerializer,
    IssueCoordinationStateSerializer,
)
from plane.app.permissions import ProjectEntityPermission
from plane.bgtasks.webhook_task import webhook_activity
from plane.db.models import (
    Issue,
    IssueAssignee,
    IssueComment,
    IssueCoordinationState,
    ProjectMember,
)
from plane.utils.host import base_host

from .base import BaseAPIView


class BaseIssueCoordinationAPIView(BaseAPIView):
    model = IssueCoordinationState
    webhook_event = "issue"
    permission_classes = [ProjectEntityPermission]
    serializer_class = IssueCoordinationStateSerializer

    def _get_issue(self, slug: str, project_id: str, work_item_id: str) -> Issue:
        return Issue.issue_objects.select_related("project", "workspace").get(
            workspace__slug=slug,
            project_id=project_id,
            pk=work_item_id,
        )

    def _get_or_create_state(self, issue: Issue) -> IssueCoordinationState:
        state, _ = IssueCoordinationState.objects.get_or_create(
            issue=issue,
            defaults={
                "project": issue.project,
                "workspace": issue.workspace,
                "coordination_status": "new",
                "last_transition_at": timezone.now(),
            },
        )
        return state

    def _serialize_state(self, state: IssueCoordinationState) -> dict:
        return IssueCoordinationStateSerializer(state).data

    def _sync_assignees(self, issue: Issue, assignee_ids: list[str]) -> None:
        IssueAssignee.objects.filter(issue=issue).delete()
        valid_assignees = list(
            ProjectMember.objects.filter(
                project_id=issue.project_id,
                is_active=True,
                role__gte=15,
                member_id__in=assignee_ids,
            ).values_list("member_id", flat=True)
        )
        IssueAssignee.objects.bulk_create(
            [
                IssueAssignee(
                    issue=issue,
                    project=issue.project,
                    workspace=issue.workspace,
                    assignee_id=assignee_id,
                )
                for assignee_id in valid_assignees
            ],
            ignore_conflicts=True,
        )

    def _add_comment(self, issue: Issue, comment_html: str, actor_id: str) -> None:
        if not comment_html:
            return
        IssueComment.objects.create(
            issue=issue,
            project=issue.project,
            workspace=issue.workspace,
            actor_id=actor_id,
            comment_html=comment_html,
        )

    def _emit_coordination_webhook(
        self,
        request,
        *,
        issue: Issue,
        old_value: dict | None,
        new_value: dict | None,
    ) -> None:
        webhook_activity.delay(
            event="issue",
            verb="updated",
            field="coordination",
            old_value=old_value,
            new_value=new_value,
            actor_id=request.user.id,
            slug=issue.workspace.slug,
            current_site=base_host(request=request, is_app=True),
            event_id=issue.id,
            old_identifier=None,
            new_identifier=None,
        )


class IssueCoordinationStateAPIEndpoint(BaseIssueCoordinationAPIView):
    def get(self, request, slug, project_id, issue_id):
        issue = self._get_issue(slug, project_id, issue_id)
        state = self._get_or_create_state(issue)
        return Response(self._serialize_state(state), status=status.HTTP_200_OK)

    def patch(self, request, slug, project_id, issue_id):
        issue = self._get_issue(slug, project_id, issue_id)
        state = self._get_or_create_state(issue)
        old_value = self._serialize_state(state)
        serializer = IssueCoordinationStateSerializer(state, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        updated = serializer.save(last_actor=request.user, last_transition_at=timezone.now())
        new_value = self._serialize_state(updated)
        self._emit_coordination_webhook(request, issue=issue, old_value=old_value, new_value=new_value)
        return Response(new_value, status=status.HTTP_200_OK)


class IssueCoordinationActionAPIEndpoint(BaseIssueCoordinationAPIView):
    def post(self, request, slug, project_id, issue_id, action):
        issue = self._get_issue(slug, project_id, issue_id)
        state = self._get_or_create_state(issue)
        old_value = self._serialize_state(state)
        serializer = IssueCoordinationActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        now = timezone.now()

        if action == "claim":
            claimant = data.get("claimed_by") or request.user
            if (
                state.claimed_by_id
                and state.claim_expires_at
                and state.claim_expires_at > now
                and str(state.claimed_by_id) != str(claimant.id)
            ):
                return Response(
                    {
                        "error": "Work item is already claimed by another actor.",
                        "claimed_by": str(state.claimed_by_id),
                        "claim_expires_at": state.claim_expires_at,
                    },
                    status=status.HTTP_409_CONFLICT,
                )
            state.claimed_by = claimant
            state.claim_expires_at = now + timedelta(seconds=data.get("lease_seconds", 3600))
            state.coordination_status = data.get("coordination_status") or "claimed"
            state.last_actor = claimant
        elif action == "handoff":
            if "route_to" in data:
                state.route_to = data.get("route_to") or None
            if "reply_identity" in data:
                state.reply_identity = data.get("reply_identity") or None
            if "allowed_responder" in data:
                state.allowed_responder = data.get("allowed_responder") or None
            if "waiting_on" in data:
                state.waiting_on = data.get("waiting_on") or None
            if "waiting_since" in data:
                state.waiting_since = data.get("waiting_since")
            if "assignee_ids" in data:
                self._sync_assignees(issue, [str(assignee.id) for assignee in data["assignee_ids"]])
            elif data.get("clear_assignees"):
                self._sync_assignees(issue, [])
            self._add_comment(issue, data.get("comment_html", ""), str(request.user.id))
            state.claimed_by = None
            state.claim_expires_at = None
            state.coordination_status = data.get("coordination_status") or "delegated"
            state.last_actor = request.user
        elif action == "release":
            state.claimed_by = None
            state.claim_expires_at = None
            state.coordination_status = data.get("coordination_status") or "triaged"
            state.last_actor = request.user
        elif action == "request-approval":
            state.approver = data.get("approver")
            state.waiting_on = data.get("waiting_on") or "approval"
            state.waiting_since = data.get("waiting_since") or now
            state.coordination_status = data.get("coordination_status") or "awaiting_approval"
            self._add_comment(issue, data.get("comment_html", ""), str(request.user.id))
            state.last_actor = request.user
        elif action == "approve":
            state.waiting_on = None
            state.waiting_since = None
            state.coordination_status = data.get("coordination_status") or "approved"
            self._add_comment(issue, data.get("comment_html", ""), str(request.user.id))
            state.last_actor = request.user
        elif action == "reject":
            state.waiting_on = None
            state.waiting_since = None
            state.coordination_status = data.get("coordination_status") or "rejected"
            self._add_comment(issue, data.get("comment_html", ""), str(request.user.id))
            state.last_actor = request.user
        elif action == "record-reply":
            metadata = dict(state.metadata or {})
            metadata["last_reply"] = {
                "channel": data.get("channel") or "unknown",
                "message_id": data.get("message_id") or "",
                "note": data.get("note") or "",
                "reply_identity": data.get("reply_identity") or state.reply_identity,
                "sent_at": now.isoformat(),
                "actor_id": str(request.user.id),
            }
            state.metadata = metadata
            if "reply_identity" in data:
                state.reply_identity = data.get("reply_identity") or state.reply_identity
            state.waiting_on = None
            state.waiting_since = None
            state.coordination_status = data.get("coordination_status") or "replied"
            state.last_actor = request.user
        else:
            return Response(
                {"error": f"Unknown coordination action '{action}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if "metadata" in data and action != "record-reply":
            state.metadata = data["metadata"]
        if "approver" in data and action not in {"request-approval"}:
            state.approver = data.get("approver")
        if "route_to" in data and action not in {"handoff"}:
            state.route_to = data.get("route_to") or None
        if "reply_identity" in data and action not in {"handoff", "record-reply"}:
            state.reply_identity = data.get("reply_identity") or None
        if "allowed_responder" in data and action not in {"handoff"}:
            state.allowed_responder = data.get("allowed_responder") or None
        if "waiting_on" in data and action not in {"handoff", "request-approval"}:
            state.waiting_on = data.get("waiting_on") or None
        if "waiting_since" in data and action not in {"handoff", "request-approval"}:
            state.waiting_since = data.get("waiting_since")

        state.last_transition_at = now
        state.save()

        new_value = self._serialize_state(state)
        self._emit_coordination_webhook(request, issue=issue, old_value=old_value, new_value=new_value)
        return Response(new_value, status=status.HTTP_200_OK)
