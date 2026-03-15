# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from datetime import timedelta
from uuid import uuid4

import pytest
from rest_framework import status
from django.utils import timezone

from plane.db.models import Issue, IssueCoordinationState, ProjectMember


@pytest.fixture
def issue(db, workspace, project, create_user):
    return Issue.objects.create(
        workspace=workspace,
        project=project,
        name="Coordinated Work Item",
        created_by=create_user,
        updated_by=create_user,
    )


@pytest.fixture
def approver(db, workspace, project):
    from plane.db.models import User

    user = User.objects.create(
        email="approver@plane.so",
        username=f"approver_{uuid4().hex[:8]}",
        first_name="Approver",
        last_name="User",
    )
    ProjectMember.objects.create(
        project=project,
        member=user,
        role=20,
        is_active=True,
    )
    return user


@pytest.mark.contract
class TestIssueCoordinationAPIEndpoint:
    def get_coordination_url(self, workspace_slug, project_id, issue_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{issue_id}/coordination/"

    def get_action_url(self, workspace_slug, project_id, issue_id, action):
        return (
            f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{issue_id}/"
            f"coordination/{action}/"
        )

    @pytest.mark.django_db
    def test_get_creates_default_coordination_state(self, api_key_client, workspace, project, issue):
        response = api_key_client.get(self.get_coordination_url(workspace.slug, project.id, issue.id))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["coordination_status"] == "new"
        assert IssueCoordinationState.objects.filter(issue=issue).exists()

    @pytest.mark.django_db
    def test_patch_updates_coordination_state(self, api_key_client, workspace, project, issue):
        response = api_key_client.patch(
            self.get_coordination_url(workspace.slug, project.id, issue.id),
            {
                "route_to": "estate",
                "reply_identity": "cos",
                "coordination_status": "triaged",
                "metadata": {"source": "gmail"},
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.route_to == "estate"
        assert issue.coordination_state.reply_identity == "cos"
        assert issue.coordination_state.coordination_status == "triaged"
        assert issue.coordination_state.metadata["source"] == "gmail"

    @pytest.mark.django_db
    def test_handoff_updates_route_and_assignee(self, api_key_client, workspace, project, issue, approver):
        response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "handoff"),
            {
                "route_to": "hersh",
                "reply_identity": "cos",
                "coordination_status": "delegated",
                "assignee_ids": [str(approver.id)],
                "comment_html": "<p>Please take this next step.</p>",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.route_to == "hersh"
        assert issue.coordination_state.coordination_status == "delegated"
        assert list(issue.assignees.values_list("id", flat=True)) == [approver.id]
        assert issue.issue_comments.count() == 1

    @pytest.mark.django_db
    def test_claim_and_request_approval_actions(self, api_key_client, workspace, project, issue, create_user, approver):
        claim_response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "claim"),
            {"lease_seconds": 900},
            format="json",
        )
        assert claim_response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.claimed_by_id == create_user.id
        assert issue.coordination_state.coordination_status == "claimed"

        approval_response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "request-approval"),
            {"approver_id": str(approver.id)},
            format="json",
        )
        assert approval_response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.approver_id == approver.id
        assert issue.coordination_state.coordination_status == "awaiting_approval"
        assert issue.coordination_state.waiting_on == "approval"

    @pytest.mark.django_db
    def test_approve_reject_and_record_reply_actions(self, api_key_client, workspace, project, issue, approver):
        IssueCoordinationState.objects.create(
            issue=issue,
            project=project,
            workspace=workspace,
            approver=approver,
            coordination_status="awaiting_approval",
            waiting_on="approval",
            waiting_since=timezone.now(),
        )

        approve_response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "approve"),
            {"comment_html": "<p>Approved.</p>"},
            format="json",
        )
        assert approve_response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.coordination_status == "approved"
        assert issue.coordination_state.waiting_on is None

        reject_response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "reject"),
            {"comment_html": "<p>Needs revision.</p>"},
            format="json",
        )
        assert reject_response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.coordination_status == "rejected"
        assert issue.coordination_state.waiting_on is None

        reply_response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "record-reply"),
            {
                "channel": "gmail",
                "message_id": "msg-123",
                "note": "Sent follow-up",
                "reply_identity": "cos",
            },
            format="json",
        )
        assert reply_response.status_code == status.HTTP_200_OK
        issue.refresh_from_db()
        assert issue.coordination_state.coordination_status == "replied"
        assert issue.coordination_state.reply_identity == "cos"
        assert issue.coordination_state.metadata["last_reply"]["channel"] == "gmail"
        assert issue.coordination_state.metadata["last_reply"]["message_id"] == "msg-123"

    @pytest.mark.django_db
    def test_claim_rejects_active_claim_by_another_actor(self, api_key_client, workspace, project, issue, approver):
        IssueCoordinationState.objects.create(
            issue=issue,
            project=project,
            workspace=workspace,
            claimed_by=approver,
            claim_expires_at=timezone.now() + timedelta(minutes=5),
            coordination_status="claimed",
        )

        response = api_key_client.post(
            self.get_action_url(workspace.slug, project.id, issue.id, "claim"),
            {"lease_seconds": 900},
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["claimed_by"] == str(approver.id)

    @pytest.mark.django_db
    def test_work_item_expand_and_filter_include_coordination(self, api_key_client, workspace, project, issue):
        IssueCoordinationState.objects.create(
            issue=issue,
            project=project,
            workspace=workspace,
            route_to="estate",
            coordination_status="triaged",
        )

        response = api_key_client.get(
            f"/api/v1/workspaces/{workspace.slug}/projects/{project.id}/work-items/",
            {"route_to": "estate", "expand": "coordination"},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["results"][0]["coordination"]["route_to"] == "estate"
        assert response.data["results"][0]["coordination"]["coordination_status"] == "triaged"
