# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.app.views.estimate.base import BulkEstimatePointEndpoint, EstimatePointEndpoint


class ProjectEstimateAPIEndpoint(BulkEstimatePointEndpoint):
    """Expose project estimates through the external API with API key auth."""

    authentication_classes = [APIKeyAuthentication]


class EstimatePointListCreateAPIEndpoint(EstimatePointEndpoint):
    """Expose estimate points through the external API with API key auth."""

    authentication_classes = [APIKeyAuthentication]


class EstimatePointDetailAPIEndpoint(EstimatePointEndpoint):
    """Expose estimate point detail updates through the external API."""

    authentication_classes = [APIKeyAuthentication]
