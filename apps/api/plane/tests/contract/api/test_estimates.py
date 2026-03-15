# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from rest_framework import status

from plane.db.models import Estimate, EstimatePoint


@pytest.fixture
def estimate(db, workspace, project):
    estimate = Estimate.objects.create(
        workspace=workspace,
        project=project,
        name="Story Points",
        type="categories",
    )
    EstimatePoint.objects.create(
        workspace=workspace,
        project=project,
        estimate=estimate,
        key=0,
        value="S",
    )
    EstimatePoint.objects.create(
        workspace=workspace,
        project=project,
        estimate=estimate,
        key=1,
        value="M",
    )
    return estimate


@pytest.mark.contract
class TestEstimateAPIEndpoint:
    def get_estimates_url(self, workspace_slug, project_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/estimates/"

    def get_estimate_url(self, workspace_slug, project_id, estimate_id):
        return f"/api/v1/workspaces/{workspace_slug}/projects/{project_id}/estimates/{estimate_id}/"

    @pytest.mark.django_db
    def test_list_estimates_success(self, api_key_client, workspace, project, estimate, mock_redis):
        response = api_key_client.get(self.get_estimates_url(workspace.slug, project.id))

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) == 1
        assert response.data[0]["id"] == estimate.id
        assert response.data[0]["points"][0]["value"] in {"S", "M"}

    @pytest.mark.django_db
    def test_create_estimate_success(self, api_key_client, workspace, project, mock_redis):
        response = api_key_client.post(
            self.get_estimates_url(workspace.slug, project.id),
            {
                "estimate": {"name": "T-Shirt", "type": "categories"},
                "estimate_points": [
                    {"key": 0, "value": "XS"},
                    {"key": 1, "value": "S"},
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        created_estimate = Estimate.objects.get(pk=response.data["id"])
        assert created_estimate.name == "T-Shirt"
        assert EstimatePoint.objects.filter(estimate=created_estimate).count() == 2

    @pytest.mark.django_db
    def test_update_estimate_success(self, api_key_client, workspace, project, estimate, mock_redis):
        first_point = estimate.points.order_by("key").first()

        response = api_key_client.patch(
            self.get_estimate_url(workspace.slug, project.id, estimate.id),
            {
                "estimate": {"name": "Updated Story Points"},
                "estimate_points": [
                    {"id": str(first_point.id), "key": 0, "value": "XS"},
                ],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        estimate.refresh_from_db()
        first_point.refresh_from_db()
        assert estimate.name == "Updated Story Points"
        assert first_point.value == "XS"
