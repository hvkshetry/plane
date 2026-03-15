# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework import status

from plane.db.models import Page, ProjectPage


@pytest.fixture
def page(db, workspace, project, create_user):
    page = Page.objects.create(
        workspace=workspace,
        owned_by=create_user,
        name="Existing Page",
        description_html="<p>Existing</p>",
    )
    ProjectPage.objects.create(project=project, page=page, workspace=workspace)
    return page


@pytest.mark.contract
class TestPageAPIEndpoint:
    def get_pages_url(self, workspace_slug, project_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/"

    def get_page_url(self, workspace_slug, project_id, page_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/{page_id}/"

    def get_page_archive_url(self, workspace_slug, project_id, page_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/pages/{page_id}/archive/"

    @pytest.mark.django_db
    def test_list_pages_success(self, api_key_client, workspace, project, page):
        response = api_key_client.get(self.get_pages_url(workspace.slug, project.id))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == page.id
        assert response.data[0]["name"] == page.name

    @pytest.mark.django_db
    def test_create_page_success(self, api_key_client, mock_celery, workspace, project):
        response = api_key_client.post(
            self.get_pages_url(workspace.slug, project.id),
            {"name": "New External Page", "description_html": "<p>Hello</p>"},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        created_page = Page.objects.get(pk=response.data["id"])
        assert created_page.name == "New External Page"
        assert ProjectPage.objects.filter(project=project, page=created_page, deleted_at__isnull=True).exists()

    @pytest.mark.django_db
    def test_archive_page_success(self, api_key_client, workspace, project, page):
        response = api_key_client.post(self.get_page_archive_url(workspace.slug, project.id, page.id), format="json")

        assert response.status_code == status.HTTP_200_OK
        assert "archived_at" in response.data
        page.refresh_from_db()
        assert page.archived_at is not None
