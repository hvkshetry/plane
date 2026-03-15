# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest

from plane.db.models import Project, ProjectMember


@pytest.fixture(autouse=True)
def _mock_background_tasks(mock_celery):
    """Prevent API contract tests from waiting on a live Celery broker."""

    return mock_celery


@pytest.fixture(autouse=True)
def _use_locmem_cache(settings):
    """Keep API contract tests independent from a live Redis cache."""

    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "plane-api-contract-tests",
        }
    }


@pytest.fixture
def project(db, workspace, create_user):
    """Create a test project with the user as an active admin member."""

    project = Project.objects.create(
        name="Test Project",
        identifier="TP",
        workspace=workspace,
        created_by=create_user,
        issue_views_view=True,
        page_view=True,
    )
    ProjectMember.objects.create(
        project=project,
        member=create_user,
        role=20,
        is_active=True,
    )
    return project
