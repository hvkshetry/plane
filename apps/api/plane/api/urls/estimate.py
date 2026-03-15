# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views.estimate import (
    ProjectEstimateAPIEndpoint,
    EstimatePointListCreateAPIEndpoint,
    EstimatePointDetailAPIEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/estimates/",
        ProjectEstimateAPIEndpoint.as_view({"get": "list", "post": "create"}),
        name="project-estimates",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/estimates/<uuid:estimate_id>/",
        ProjectEstimateAPIEndpoint.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        name="project-estimate-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/estimates/<uuid:estimate_id>/estimate-points/",
        EstimatePointListCreateAPIEndpoint.as_view({"post": "create"}),
        name="estimate-point-list-create",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/estimates/<uuid:estimate_id>/estimate-points/<estimate_point_id>/",
        EstimatePointDetailAPIEndpoint.as_view({"patch": "partial_update", "delete": "destroy"}),
        name="estimate-point-detail",
    ),
]
