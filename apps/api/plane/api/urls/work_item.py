# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.api.views import (
    IssueListCreateAPIEndpoint,
    IssueDetailAPIEndpoint,
    IssueRelationAPIEndpoint,
    IssueLinkListCreateAPIEndpoint,
    IssueLinkDetailAPIEndpoint,
    IssueCommentListCreateAPIEndpoint,
    IssueCommentDetailAPIEndpoint,
    IssueActivityListAPIEndpoint,
    IssueActivityDetailAPIEndpoint,
    IssueAttachmentListCreateAPIEndpoint,
    IssueAttachmentDetailAPIEndpoint,
    WorkspaceIssueAPIEndpoint,
    IssueSearchEndpoint,
    IssueCoordinationStateAPIEndpoint,
    IssueCoordinationActionAPIEndpoint,
)

urlpatterns = [
    path(
        "workspaces/<str:slug>/work-items/search/",
        IssueSearchEndpoint.as_view(http_method_names=["get"]),
        name="work-item-search",
    ),
    path(
        "workspaces/<str:slug>/work-items/<str:project_identifier>-<str:issue_identifier>/",
        WorkspaceIssueAPIEndpoint.as_view(http_method_names=["get"]),
        name="work-item-by-identifier",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/",
        IssueListCreateAPIEndpoint.as_view(http_method_names=["get", "post", "put"]),
        name="work-item-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:pk>/",
        IssueDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="work-item-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/coordination/",
        IssueCoordinationStateAPIEndpoint.as_view(http_method_names=["get", "patch"]),
        name="work-item-coordination",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/coordination/<str:action>/",
        IssueCoordinationActionAPIEndpoint.as_view(http_method_names=["post"]),
        name="work-item-coordination-action",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/links/",
        IssueLinkListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="work-item-link-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/links/<uuid:pk>/",
        IssueLinkDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="work-item-link-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/relations/",
        IssueRelationAPIEndpoint.as_view({"get": "list", "post": "create"}),
        name="work-item-relation-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/relations/remove/",
        IssueRelationAPIEndpoint.as_view({"post": "remove_relation"}),
        name="work-item-relation-remove",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/comments/",
        IssueCommentListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="work-item-comment-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/comments/<uuid:pk>/",
        IssueCommentDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="work-item-comment-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/activities/",
        IssueActivityListAPIEndpoint.as_view(http_method_names=["get"]),
        name="work-item-activity-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/activities/<uuid:pk>/",
        IssueActivityDetailAPIEndpoint.as_view(http_method_names=["get"]),
        name="work-item-activity-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/attachments/",
        IssueAttachmentListCreateAPIEndpoint.as_view(http_method_names=["get", "post"]),
        name="work-item-attachment-list",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/work-items/<uuid:issue_id>/attachments/<uuid:pk>/",
        IssueAttachmentDetailAPIEndpoint.as_view(http_method_names=["get", "patch", "delete"]),
        name="work-item-attachment-detail",
    ),
]
