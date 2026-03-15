# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import pytest
from uuid import uuid4

from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from plane.db.models import APIToken, Profile, ProjectMember, ProjectUserProperty, User, WorkspaceMember, WorkspaceMemberInvite
from plane.license.models import Instance, InstanceAdmin
from plane.tests.factories import ProjectFactory


def create_instance_with_admin(user):
    instance = Instance.objects.create(
        instance_name="Test Instance",
        instance_id=uuid4().hex,
        current_version="1.2.3",
        latest_version="1.2.3",
        last_checked_at=timezone.now(),
        is_setup_done=True,
    )
    InstanceAdmin.objects.create(instance=instance, user=user, role=20)
    return instance


@pytest.mark.contract
class TestInstanceAdminProvisionIdentitiesEndpoint:
    @pytest.mark.django_db
    def test_instance_admin_can_provision_user_memberships_and_pat(self, session_client, create_user, workspace):
        create_instance_with_admin(create_user)
        session_client.force_authenticate(user=create_user)
        project = ProjectFactory(workspace=workspace, created_by=workspace.owner, updated_by=workspace.owner)
        url = reverse("instance-admin-provision-identities")

        response = session_client.post(
            url,
            {
                "users": [
                    {
                        "email": "kshetry.singh.agent+cos@gmail.com",
                        "first_name": "Chief",
                        "last_name": "Agent",
                        "display_name": "Chief of Staff Agent",
                        "workspace_memberships": [{"slug": workspace.slug, "role": 20}],
                        "project_memberships": [{"project_id": str(project.id), "role": 20}],
                        "create_api_token": True,
                        "api_token_label": "Chief of Staff Agent PAT",
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 1
        result = response.data["results"][0]
        assert result["user_status"] == "created"
        assert result["api_token"]["token"].startswith("plane_api_")
        assert result["workspace_memberships"][0]["status"] == "created"
        assert result["project_memberships"][0]["status"] == "created"

        user = User.objects.get(email="kshetry.singh.agent+cos@gmail.com")
        assert user.is_active is True
        assert user.is_managed is True
        assert user.display_name == "Chief of Staff Agent"
        assert Profile.objects.filter(user=user).exists()
        assert WorkspaceMember.objects.filter(workspace=workspace, member=user, is_active=True, role=20).exists()
        assert ProjectMember.objects.filter(project=project, member=user, is_active=True, role=20).exists()
        assert APIToken.objects.filter(user=user, label="Chief of Staff Agent PAT").exists()

    @pytest.mark.django_db
    def test_provisioning_reactivates_existing_user_and_memberships(self, session_client, create_user, workspace):
        create_instance_with_admin(create_user)
        session_client.force_authenticate(user=create_user)
        project = ProjectFactory(workspace=workspace, created_by=workspace.owner, updated_by=workspace.owner)
        existing_user = User.objects.create(
            email="kshetry.singh.agent+estate@gmail.com",
            username=uuid4().hex,
            first_name="Estate",
            last_name="Legacy",
            is_active=False,
        )
        Profile.objects.create(user=existing_user)
        workspace_member = WorkspaceMember.objects.create(
            workspace=workspace,
            member=existing_user,
            role=5,
            is_active=False,
        )
        project_member = ProjectMember.objects.create(
            project=project,
            workspace=workspace,
            member=existing_user,
            role=5,
            is_active=False,
        )
        WorkspaceMemberInvite.objects.create(
            workspace=workspace,
            email=existing_user.email,
            token="stale-token",
            role=5,
        )

        url = reverse("instance-admin-provision-identities")
        response = session_client.post(
            url,
            {
                "users": [
                    {
                        "email": existing_user.email,
                        "first_name": "Estate",
                        "last_name": "Counsel",
                        "display_name": "Estate Counsel",
                        "workspace_memberships": [{"slug": workspace.slug, "role": 20}],
                        "project_memberships": [{"project_id": str(project.id), "role": 20}],
                        "create_api_token": True,
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.data["results"][0]
        assert result["user_status"] == "updated"
        assert result["workspace_memberships"][0]["status"] == "reactivated"
        assert result["project_memberships"][0]["status"] == "reactivated"
        assert result["api_token"]["token"].startswith("plane_api_")

        existing_user.refresh_from_db()
        workspace_member.refresh_from_db()
        project_member.refresh_from_db()
        assert existing_user.is_active is True
        assert existing_user.display_name == "Estate Counsel"
        assert workspace_member.is_active is True
        assert workspace_member.role == 20
        assert project_member.is_active is True
        assert project_member.role == 20
        assert not WorkspaceMemberInvite.objects.filter(workspace=workspace, email=existing_user.email).exists()

    @pytest.mark.django_db
    def test_provisioning_can_purge_inactive_memberships_instead_of_reactivating(
        self,
        session_client,
        create_user,
        workspace,
    ):
        create_instance_with_admin(create_user)
        session_client.force_authenticate(user=create_user)
        project = ProjectFactory(workspace=workspace, created_by=workspace.owner, updated_by=workspace.owner)
        existing_user = User.objects.create(
            email="kshetry.singh.agent+wellness@gmail.com",
            username=uuid4().hex,
            first_name="Wellness",
            last_name="Legacy",
            is_active=True,
        )
        Profile.objects.create(user=existing_user)
        workspace_member = WorkspaceMember.objects.create(
            workspace=workspace,
            member=existing_user,
            role=5,
            is_active=False,
        )
        project_member = ProjectMember.objects.create(
            project=project,
            workspace=workspace,
            member=existing_user,
            role=5,
            is_active=False,
        )
        project_property = ProjectUserProperty.objects.get(project=project, user=existing_user)
        WorkspaceMemberInvite.objects.create(
            workspace=workspace,
            email=existing_user.email,
            token="stale-token",
            role=5,
        )

        url = reverse("instance-admin-provision-identities")
        response = session_client.post(
            url,
            {
                "users": [
                    {
                        "email": existing_user.email,
                        "display_name": "Wellness Advisor",
                        "inactive_membership_strategy": "purge",
                        "workspace_memberships": [{"slug": workspace.slug, "role": 20}],
                        "project_memberships": [{"project_id": str(project.id), "role": 20}],
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        result = response.data["results"][0]
        assert result["workspace_memberships"][0]["status"] == "recreated"
        assert result["project_memberships"][0]["status"] == "recreated"
        assert result["workspace_memberships"][0]["id"] != str(workspace_member.id)
        assert result["project_memberships"][0]["id"] != str(project_member.id)

        assert not WorkspaceMember.all_objects.filter(id=workspace_member.id).exists()
        assert not ProjectMember.all_objects.filter(id=project_member.id).exists()
        assert not ProjectUserProperty.all_objects.filter(id=project_property.id).exists()
        assert WorkspaceMember.objects.filter(workspace=workspace, member=existing_user, is_active=True, role=20).exists()
        assert ProjectMember.objects.filter(project=project, member=existing_user, is_active=True, role=20).exists()
        assert ProjectUserProperty.objects.filter(project=project, user=existing_user).count() == 1
        assert not WorkspaceMemberInvite.all_objects.filter(workspace=workspace, email=existing_user.email).exists()

    @pytest.mark.django_db
    def test_non_instance_admin_cannot_provision_identities(self, session_client, create_user, workspace):
        Instance.objects.create(
            instance_name="Test Instance",
            instance_id=uuid4().hex,
            current_version="1.2.3",
            latest_version="1.2.3",
            last_checked_at=timezone.now(),
            is_setup_done=True,
        )
        session_client.force_authenticate(user=create_user)
        url = reverse("instance-admin-provision-identities")

        response = session_client.post(
            url,
            {
                "users": [
                    {
                        "email": "kshetry.singh.agent+ra@gmail.com",
                        "workspace_memberships": [{"slug": workspace.slug, "role": 20}],
                    }
                ]
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
