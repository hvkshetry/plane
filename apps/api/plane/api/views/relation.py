# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.app.views.issue.relation import IssueRelationViewSet


class IssueRelationAPIEndpoint(IssueRelationViewSet):
    """Expose work item dependency relations through the external API."""

    authentication_classes = [APIKeyAuthentication]
