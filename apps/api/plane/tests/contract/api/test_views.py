# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework import status

from plane.db.models import IssueView


@pytest.fixture
def issue_view(db, workspace, project, create_user):
    return IssueView.objects.create(
        workspace=workspace,
        project=project,
        owned_by=create_user,
        name="Existing View",
        filters={},
        query={},
    )


@pytest.mark.contract
class TestProjectViewAPIEndpoint:
    def get_views_url(self, workspace_slug, project_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/views/"

    def get_view_url(self, workspace_slug, project_id, view_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/views/{view_id}/"

    @pytest.mark.django_db
    def test_list_views_success(self, api_key_client, workspace, project, issue_view):
        response = api_key_client.get(self.get_views_url(workspace.slug, project.id))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == issue_view.id
        assert response.data[0]["name"] == issue_view.name

    @pytest.mark.django_db
    def test_create_view_success(self, api_key_client, workspace, project):
        response = api_key_client.post(
            self.get_views_url(workspace.slug, project.id),
            {"name": "External API View", "filters": {}},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        created_view = IssueView.objects.get(pk=response.data["id"])
        assert created_view.name == "External API View"
        assert created_view.project == project

    @pytest.mark.django_db
    def test_update_view_success(self, api_key_client, workspace, project, issue_view):
        response = api_key_client.patch(
            self.get_view_url(workspace.slug, project.id, issue_view.id),
            {"name": "Renamed View"},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        issue_view.refresh_from_db()
        assert issue_view.name == "Renamed View"
