# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

# Python imports
from urllib.parse import urlencode, urljoin
import uuid
from zxcvbn import zxcvbn

# Django imports
from django.http import HttpResponseRedirect
from django.views import View
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.contrib.auth.hashers import make_password
from django.contrib.auth import logout
from django.db import transaction

# Third party imports
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

# Module imports
from .base import BaseAPIView
from plane.license.api.permissions import InstanceAdminPermission
from plane.license.api.serializers import (
    InstanceAdminMeSerializer,
    InstanceAdminSerializer,
    ProvisioningRequestSerializer,
)
from plane.license.models import Instance, InstanceAdmin
from plane.db.models import (
    APIToken,
    Profile,
    Project,
    ProjectMember,
    ProjectUserProperty,
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceMemberInvite,
)
from plane.utils.cache import cache_response, invalidate_cache, invalidate_cache_directly
from plane.authentication.utils.login import user_login
from plane.authentication.utils.host import base_host, user_ip
from plane.authentication.adapter.error import (
    AUTHENTICATION_ERROR_CODES,
    AuthenticationException,
)
from plane.utils.ip_address import get_client_ip
from plane.utils.path_validator import get_safe_redirect_url


class InstanceAdminEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    @invalidate_cache(path="/api/instances/", user=False)
    # Create an instance admin
    def post(self, request):
        email = request.data.get("email", False)
        role = request.data.get("role", 20)

        if not email:
            return Response({"error": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)

        instance = Instance.objects.first()
        if instance is None:
            return Response(
                {"error": "Instance is not registered yet"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Fetch the user
        user = User.objects.get(email=email)

        instance_admin = InstanceAdmin.objects.create(instance=instance, user=user, role=role)
        serializer = InstanceAdminSerializer(instance_admin)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @cache_response(60 * 60 * 2, user=False)
    def get(self, request):
        instance = Instance.objects.first()
        if instance is None:
            return Response(
                {"error": "Instance is not registered yet"},
                status=status.HTTP_403_FORBIDDEN,
            )
        instance_admins = InstanceAdmin.objects.filter(instance=instance)
        serializer = InstanceAdminSerializer(instance_admins, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @invalidate_cache(path="/api/instances/", user=False)
    def delete(self, request, pk):
        instance = Instance.objects.first()
        InstanceAdmin.objects.filter(instance=instance, pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InstanceAdminProvisionIdentitiesEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    @staticmethod
    def _set_optional_field(model, field_name, value, update_fields):
        if value is None or getattr(model, field_name) == value:
            return
        setattr(model, field_name, value)
        update_fields.append(field_name)

    def _upsert_user(self, identity, actor):
        email = identity["email"].strip().lower()
        user = User.objects.filter(email=email).first()
        created = user is None
        update_fields = []

        if created:
            user = User(
                email=email,
                username=uuid.uuid4().hex,
                first_name=identity.get("first_name") or "",
                last_name=identity.get("last_name") or "",
                display_name=identity.get("display_name") or "",
                user_timezone=identity.get("user_timezone") or "UTC",
                is_active=True,
                is_managed=True,
                is_password_autoset=True,
                is_password_reset_required=True,
            )
            user.password = make_password(uuid.uuid4().hex)
            user.save(created_by_id=actor.id, disable_auto_set_user=True)
            Profile.objects.get_or_create(user=user)
            return user, "created"

        if not user.is_active:
            user.is_active = True
            update_fields.append("is_active")
        if not user.is_managed:
            user.is_managed = True
            update_fields.append("is_managed")

        self._set_optional_field(user, "first_name", identity.get("first_name"), update_fields)
        self._set_optional_field(user, "last_name", identity.get("last_name"), update_fields)
        self._set_optional_field(user, "display_name", identity.get("display_name"), update_fields)
        self._set_optional_field(user, "user_timezone", identity.get("user_timezone"), update_fields)

        if update_fields:
            if hasattr(user, "updated_at"):
                update_fields.append("updated_at")
            user.save(update_fields=list(dict.fromkeys(update_fields)))

        Profile.objects.get_or_create(user=user)
        return user, "updated" if update_fields else "existing"

    def _upsert_instance_admin(self, user):
        instance = Instance.objects.first()
        instance_admin, created = InstanceAdmin.objects.get_or_create(
            instance=instance,
            user=user,
            defaults={"role": 20},
        )
        updated = False
        if not created and instance_admin.role != 20:
            instance_admin.role = 20
            instance_admin.save(update_fields=["role", "updated_at"] if hasattr(instance_admin, "updated_at") else ["role"])
            updated = True
        return {
            "id": str(instance_admin.id),
            "status": "created" if created else "updated" if updated else "existing",
            "role": instance_admin.role,
        }

    def _purge_inactive_workspace_membership(self, workspace, user):
        WorkspaceMember.all_objects.filter(workspace=workspace, member=user).exclude(
            is_active=True,
            deleted_at__isnull=True,
        ).delete(soft=False)
        WorkspaceMemberInvite.all_objects.filter(workspace=workspace, email=user.email).delete(soft=False)

    def _purge_inactive_project_membership(self, project, user):
        purged_memberships = ProjectMember.all_objects.filter(project=project, member=user).exclude(
            is_active=True,
            deleted_at__isnull=True,
        )
        if purged_memberships.exists():
            purged_memberships.delete(soft=False)
            ProjectUserProperty.all_objects.filter(project=project, user=user).delete(soft=False)

    def _upsert_workspace_member(self, user, membership, strategy="reactivate", sync_role=True):
        workspace = Workspace.objects.get(slug=membership["slug"])
        active_workspace_member = WorkspaceMember.objects.filter(workspace=workspace, member=user).first()
        if active_workspace_member is not None:
            workspace_member = active_workspace_member
            previous_state = {
                "role": workspace_member.role,
            }
            update_fields = []
            if sync_role and workspace_member.role != membership["role"]:
                workspace_member.role = membership["role"]
                update_fields.append("role")
            if update_fields:
                if hasattr(workspace_member, "updated_at"):
                    update_fields.append("updated_at")
                workspace_member.save(update_fields=list(dict.fromkeys(update_fields)))
            status_label = "updated" if sync_role and previous_state["role"] != membership["role"] else "existing"
        else:
            workspace_member = WorkspaceMember.all_objects.filter(workspace=workspace, member=user).first()
            previous_state = None

        if active_workspace_member is None and workspace_member is None:
            workspace_member = WorkspaceMember.objects.create(
                workspace=workspace,
                member=user,
                role=membership["role"],
            )
            status_label = "created"
        elif active_workspace_member is None and strategy == "purge":
            self._purge_inactive_workspace_membership(workspace, user)
            workspace_member = WorkspaceMember.objects.create(
                workspace=workspace,
                member=user,
                role=membership["role"],
            )
            status_label = "recreated"
        elif active_workspace_member is None:
            previous_state = {
                "deleted": workspace_member.deleted_at is not None,
                "inactive": workspace_member.is_active is False,
                "role": workspace_member.role,
            }
            update_fields = []
            if workspace_member.deleted_at is not None:
                workspace_member.deleted_at = None
                update_fields.append("deleted_at")
            if workspace_member.is_active is False:
                workspace_member.is_active = True
                update_fields.append("is_active")
            if sync_role and workspace_member.role != membership["role"]:
                workspace_member.role = membership["role"]
                update_fields.append("role")
            if update_fields:
                if hasattr(workspace_member, "updated_at"):
                    update_fields.append("updated_at")
                workspace_member.save(update_fields=list(dict.fromkeys(update_fields)))
            status_label = (
                "reactivated"
                if previous_state["deleted"] or previous_state["inactive"]
                else "updated"
                if sync_role and previous_state["role"] != membership["role"]
                else "existing"
            )

        WorkspaceMemberInvite.all_objects.filter(workspace=workspace, email=user.email).delete(soft=False)
        return {
            "id": str(workspace_member.id),
            "workspace_id": str(workspace.id),
            "workspace_slug": workspace.slug,
            "role": workspace_member.role,
            "status": status_label,
        }

    def _upsert_project_member(self, user, membership, strategy="reactivate"):
        project = Project.objects.get(pk=membership["project_id"])
        # Ensure the user is an active workspace member before granting project access.
        existing_workspace_member = WorkspaceMember.all_objects.filter(workspace=project.workspace, member=user).first()
        should_sync_workspace_role = (
            existing_workspace_member is None
            or existing_workspace_member.deleted_at is not None
            or existing_workspace_member.is_active is False
            or existing_workspace_member.role < membership["role"]
        )
        self._upsert_workspace_member(
            user,
            {
                "slug": project.workspace.slug,
                "role": membership["role"],
            },
            strategy=strategy,
            sync_role=should_sync_workspace_role,
        )

        active_project_member = ProjectMember.objects.filter(project=project, member=user).first()
        if active_project_member is not None:
            project_member = active_project_member
            was_inactive = False
            was_deleted = False
            role_changed = project_member.role != membership["role"]
            update_fields = []
            if role_changed:
                project_member.role = membership["role"]
                update_fields.append("role")
            if update_fields:
                if hasattr(project_member, "updated_at"):
                    update_fields.append("updated_at")
                project_member.save(update_fields=list(dict.fromkeys(update_fields)))
            status_label = "updated" if role_changed else "existing"
        else:
            project_member = ProjectMember.all_objects.filter(project=project, member=user).first()

        if active_project_member is None and project_member is None:
            project_member = ProjectMember.objects.create(
                project=project,
                workspace=project.workspace,
                member=user,
                role=membership["role"],
            )
            status_label = "created"
        elif active_project_member is None and strategy == "purge":
            self._purge_inactive_project_membership(project, user)
            project_member = ProjectMember.objects.create(
                project=project,
                workspace=project.workspace,
                member=user,
                role=membership["role"],
            )
            status_label = "recreated"
        elif active_project_member is None:
            was_inactive = project_member.is_active is False
            was_deleted = project_member.deleted_at is not None
            role_changed = project_member.role != membership["role"]
            update_fields = []
            if project_member.deleted_at is not None:
                project_member.deleted_at = None
                update_fields.append("deleted_at")
            if project_member.is_active is False:
                project_member.is_active = True
                update_fields.append("is_active")
            if role_changed:
                project_member.role = membership["role"]
                update_fields.append("role")
            if update_fields:
                if hasattr(project_member, "updated_at"):
                    update_fields.append("updated_at")
                project_member.save(update_fields=list(dict.fromkeys(update_fields)))
            status_label = "reactivated" if was_inactive or was_deleted else "updated" if role_changed else "existing"

        return {
            "id": str(project_member.id),
            "project_id": str(project.id),
            "workspace_slug": project.workspace.slug,
            "role": project_member.role,
            "status": status_label,
        }

    def _mint_api_token(self, user, identity):
        label = identity.get("api_token_label") or f"{user.display_name or user.email} API Token"
        description = identity.get("api_token_description") or "Provisioned by instance admin"
        api_token = APIToken.objects.create(
            label=label,
            description=description,
            user=user,
            user_type=1 if user.is_bot else 0,
            expired_at=identity.get("expired_at"),
        )
        return {
            "id": str(api_token.id),
            "label": api_token.label,
            "token": api_token.token,
            "expired_at": api_token.expired_at,
        }

    def post(self, request):
        serializer = ProvisioningRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        results = []
        touched_workspaces = set()

        for identity in serializer.validated_data["users"]:
            with transaction.atomic():
                user, user_status = self._upsert_user(identity, request.user)
                result = {
                    "email": user.email,
                    "user_id": str(user.id),
                    "user_status": user_status,
                    "workspace_memberships": [],
                    "project_memberships": [],
                    "api_token": None,
                    "instance_admin": None,
                }

                if identity.get("is_instance_admin"):
                    result["instance_admin"] = self._upsert_instance_admin(user)

                membership_strategy = identity.get("inactive_membership_strategy", "reactivate")
                for membership in identity.get("workspace_memberships", []):
                    membership_result = self._upsert_workspace_member(
                        user,
                        membership,
                        strategy=membership_strategy,
                    )
                    result["workspace_memberships"].append(membership_result)
                    touched_workspaces.add(membership_result["workspace_slug"])

                for membership in identity.get("project_memberships", []):
                    membership_result = self._upsert_project_member(
                        user,
                        membership,
                        strategy=membership_strategy,
                    )
                    result["project_memberships"].append(membership_result)
                    touched_workspaces.add(membership_result["workspace_slug"])

                if identity.get("create_api_token", True):
                    result["api_token"] = self._mint_api_token(user, identity)

                results.append(result)

        for workspace_slug in touched_workspaces:
            invalidate_cache_directly(
                path=f"/api/workspaces/{workspace_slug}/members/",
                user=False,
                multiple=True,
            )

        return Response({"results": results}, status=status.HTTP_200_OK)


class InstanceAdminSignUpEndpoint(View):
    permission_classes = [AllowAny]

    @invalidate_cache(path="/api/instances/", user=False)
    def post(self, request):
        # Check instance first
        instance = Instance.objects.first()
        if instance is None:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"],
                error_message="INSTANCE_NOT_CONFIGURED",
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # check if the instance has already an admin registered
        if InstanceAdmin.objects.first():
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_ALREADY_EXIST"],
                error_message="ADMIN_ALREADY_EXIST",
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Get the email and password from all the user
        email = request.POST.get("email", False)
        password = request.POST.get("password", False)
        first_name = request.POST.get("first_name", False)
        last_name = request.POST.get("last_name", "")
        company_name = request.POST.get("company_name", "")
        is_telemetry_enabled = request.POST.get("is_telemetry_enabled", True)

        # return error if the email and password is not present
        if not email or not password or not first_name:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME"],
                error_message="REQUIRED_ADMIN_EMAIL_PASSWORD_FIRST_NAME",
                payload={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "company_name": company_name,
                    "is_telemetry_enabled": is_telemetry_enabled,
                },
            )
            url = urljoin(
                base_host(
                    request=request,
                    is_admin=True,
                ),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Validate the email
        email = email.strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INVALID_ADMIN_EMAIL"],
                error_message="INVALID_ADMIN_EMAIL",
                payload={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "company_name": company_name,
                    "is_telemetry_enabled": is_telemetry_enabled,
                },
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Check if already a user exists or not
        # Existing user
        if User.objects.filter(email=email).exists():
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_USER_ALREADY_EXIST"],
                error_message="ADMIN_USER_ALREADY_EXIST",
                payload={
                    "email": email,
                    "first_name": first_name,
                    "last_name": last_name,
                    "company_name": company_name,
                    "is_telemetry_enabled": is_telemetry_enabled,
                },
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)
        else:
            results = zxcvbn(password)
            if results["score"] < 3:
                exc = AuthenticationException(
                    error_code=AUTHENTICATION_ERROR_CODES["PASSWORD_TOO_WEAK"],
                    error_message="PASSWORD_TOO_WEAK",
                    payload={
                        "email": email,
                        "first_name": first_name,
                        "last_name": last_name,
                        "company_name": company_name,
                        "is_telemetry_enabled": is_telemetry_enabled,
                    },
                )
                url = urljoin(
                    base_host(request=request, is_admin=True),
                    "?" + urlencode(exc.get_error_dict()),
                )
                return HttpResponseRedirect(url)

            user = User.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                username=uuid.uuid4().hex,
                password=make_password(password),
                is_password_autoset=False,
            )
            _ = Profile.objects.create(user=user, company_name=company_name)
            # settings last active for the user
            user.is_active = True
            user.last_active = timezone.now()
            user.last_login_time = timezone.now()
            user.last_login_ip = get_client_ip(request=request)
            user.last_login_uagent = request.META.get("HTTP_USER_AGENT")
            user.token_updated_at = timezone.now()
            user.save()

            # Register the user as an instance admin
            _ = InstanceAdmin.objects.create(user=user, instance=instance)
            # Make the setup flag True
            instance.is_setup_done = True
            instance.instance_name = company_name
            instance.is_telemetry_enabled = is_telemetry_enabled
            instance.save()

            # get tokens for user
            user_login(request=request, user=user, is_admin=True)
            url = urljoin(base_host(request=request, is_admin=True), "general/")
            return HttpResponseRedirect(url)


class InstanceAdminSignInEndpoint(View):
    permission_classes = [AllowAny]

    @invalidate_cache(path="/api/instances/", user=False)
    def post(self, request):
        # Check instance first
        instance = Instance.objects.first()
        if instance is None:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INSTANCE_NOT_CONFIGURED"],
                error_message="INSTANCE_NOT_CONFIGURED",
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Get email and password
        email = request.POST.get("email", False)
        password = request.POST.get("password", False)

        # return error if the email and password is not present
        if not email or not password:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["REQUIRED_ADMIN_EMAIL_PASSWORD"],
                error_message="REQUIRED_ADMIN_EMAIL_PASSWORD",
                payload={"email": email},
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Validate the email
        email = email.strip().lower()
        try:
            validate_email(email)
        except ValidationError:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["INVALID_ADMIN_EMAIL"],
                error_message="INVALID_ADMIN_EMAIL",
                payload={"email": email},
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Fetch the user
        user = User.objects.filter(email=email).first()

        # Error out if the user is not present
        if not user:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_USER_DOES_NOT_EXIST"],
                error_message="ADMIN_USER_DOES_NOT_EXIST",
                payload={"email": email},
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # is_active
        if not user.is_active:
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_USER_DEACTIVATED"],
                error_message="ADMIN_USER_DEACTIVATED",
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Check password of the user
        if not user.check_password(password):
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_AUTHENTICATION_FAILED"],
                error_message="ADMIN_AUTHENTICATION_FAILED",
                payload={"email": email},
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)

        # Check if the user is an instance admin
        if not InstanceAdmin.objects.filter(instance=instance, user=user):
            exc = AuthenticationException(
                error_code=AUTHENTICATION_ERROR_CODES["ADMIN_AUTHENTICATION_FAILED"],
                error_message="ADMIN_AUTHENTICATION_FAILED",
                payload={"email": email},
            )
            url = urljoin(
                base_host(request=request, is_admin=True),
                "?" + urlencode(exc.get_error_dict()),
            )
            return HttpResponseRedirect(url)
        # settings last active for the user
        user.is_active = True
        user.last_active = timezone.now()
        user.last_login_time = timezone.now()
        user.last_login_ip = get_client_ip(request=request)
        user.last_login_uagent = request.META.get("HTTP_USER_AGENT")
        user.token_updated_at = timezone.now()
        user.save()

        # get tokens for user
        user_login(request=request, user=user, is_admin=True)
        url = urljoin(base_host(request=request, is_admin=True), "general/")
        return HttpResponseRedirect(url)


class InstanceAdminUserMeEndpoint(BaseAPIView):
    permission_classes = [InstanceAdminPermission]

    def get(self, request):
        serializer = InstanceAdminMeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


class InstanceAdminUserSessionEndpoint(BaseAPIView):
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated and InstanceAdmin.objects.filter(user=request.user).exists():
            serializer = InstanceAdminMeSerializer(request.user)
            data = {"is_authenticated": True}
            data["user"] = serializer.data
            return Response(data, status=status.HTTP_200_OK)
        else:
            return Response({"is_authenticated": False}, status=status.HTTP_200_OK)


class InstanceAdminSignOutEndpoint(View):
    permission_classes = [InstanceAdminPermission]

    def post(self, request):
        # Get user
        try:
            user = User.objects.get(pk=request.user.id)
            user.last_logout_ip = user_ip(request=request)
            user.last_logout_time = timezone.now()
            user.save()
            # Log the user out
            logout(request)
            url = get_safe_redirect_url(base_url=base_host(request=request, is_admin=True), next_path="")
            return HttpResponseRedirect(url)
        except Exception:
            url = get_safe_redirect_url(base_url=base_host(request=request, is_admin=True), next_path="")
            return HttpResponseRedirect(url)
