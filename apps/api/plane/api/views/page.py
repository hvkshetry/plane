# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from plane.api.middleware.api_authentication import APIKeyAuthentication
from plane.app.views.page.base import PageViewSet


class PageAPIEndpoint(PageViewSet):
    """Expose project pages through the external API with API key auth."""

    authentication_classes = [APIKeyAuthentication]
