# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework import status

from plane.db.models import Issue, IssueRelation


@pytest.fixture
def relation_issues(db, workspace, project, create_user):
    current_issue = Issue.objects.create(
        workspace=workspace,
        project=project,
        name="Current Work Item",
        created_by=create_user,
        updated_by=create_user,
    )
    related_issue = Issue.objects.create(
        workspace=workspace,
        project=project,
        name="Related Work Item",
        created_by=create_user,
        updated_by=create_user,
    )
    return current_issue, related_issue


@pytest.fixture
def blocked_by_relation(db, workspace, project, create_user, relation_issues):
    current_issue, related_issue = relation_issues
    return IssueRelation.objects.create(
        workspace=workspace,
        project=project,
        issue=current_issue,
        related_issue=related_issue,
        relation_type="blocked_by",
        created_by=create_user,
        updated_by=create_user,
    )


@pytest.mark.contract
class TestIssueRelationAPIEndpoint:
    def get_relations_url(self, workspace_slug, project_id, issue_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{issue_id}/relations/"

    def get_relations_remove_url(self, workspace_slug, project_id, issue_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/work-items/{issue_id}/relations/remove/"

    @pytest.mark.django_db
    def test_list_relations_success(self, api_key_client, workspace, project, relation_issues, blocked_by_relation):
        current_issue, related_issue = relation_issues

        response = api_key_client.get(self.get_relations_url(workspace.slug, project.id, current_issue.id))

        assert response.status_code == status.HTTP_200_OK
        assert response.data["blocked_by"][0]["id"] == related_issue.id

    @pytest.mark.django_db
    def test_create_relation_success(self, api_key_client, workspace, project, relation_issues):
        current_issue, related_issue = relation_issues

        response = api_key_client.post(
            self.get_relations_url(workspace.slug, project.id, current_issue.id),
            {
                "relation_type": "blocked_by",
                "issues": [str(related_issue.id)],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert IssueRelation.objects.filter(
            issue=current_issue,
            related_issue=related_issue,
            relation_type="blocked_by",
            deleted_at__isnull=True,
        ).exists()

    @pytest.mark.django_db
    def test_remove_relation_success(self, api_key_client, workspace, project, relation_issues, blocked_by_relation):
        current_issue, related_issue = relation_issues

        response = api_key_client.post(
            self.get_relations_remove_url(workspace.slug, project.id, current_issue.id),
            {"related_issue": str(related_issue.id)},
            format="json",
        )

        assert response.status_code == status.HTTP_204_NO_CONTENT
        assert not IssueRelation.objects.filter(pk=blocked_by_relation.id).exists()
