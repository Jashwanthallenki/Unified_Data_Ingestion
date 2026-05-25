"""Analyst review API."""
from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timezone

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from ingestion.services.confidence import score_from_method_and_flags
from ingestion.services.tenant_resolver import get_tenant

from .models import NormalizedActivity, ReviewLog, ValidationIssue
from .serializers import (
    NormalizedActivityDetailSerializer,
    NormalizedActivityListSerializer,
)
from .services.groq_suggestion import suggest_for_activity


def _flag_filter(code: str) -> Q:
    """Cross-DB filter for `flags JSONField contains code`."""
    engine = settings.DATABASES["default"]["ENGINE"]
    if "postgresql" in engine:
        return Q(flags__contains=[code])
    # SQLite/MySQL fallback: match the quoted form in the serialized JSON text.
    return Q(flags__icontains=f'"{code}"')

logger = logging.getLogger(__name__)
User = get_user_model()


def _current_user():
    """Return the seeded 'analyst' user as the implicit reviewer."""
    try:
        return User.objects.get(username="analyst")
    except User.DoesNotExist:
        return None


def _get_activity(activity_id):
    tenant = get_tenant()
    return get_object_or_404(
        NormalizedActivity.objects.select_related("batch", "raw_record"),
        tenant=tenant, id=activity_id,
    )


def _now():
    return datetime.now(tz=timezone.utc)


def _log(activity, action, reviewer, *, comment=None, old_value=None, new_value=None):
    return ReviewLog.objects.create(
        tenant=activity.tenant,
        activity=activity,
        action=action,
        reviewer=reviewer,
        comment=comment,
        old_value=old_value,
        new_value=new_value,
    )


# -------- List & detail --------

class ActivityListView(ListAPIView):
    serializer_class = NormalizedActivityListSerializer

    def get_queryset(self):
        tenant = get_tenant()
        qs = NormalizedActivity.objects.filter(tenant=tenant).annotate(issue_count=Count("issues"))
        qp = self.request.query_params

        if (source := qp.get("source")):
            qs = qs.filter(source_type=source.lower())
        if (batch_id := qp.get("batch")):
            qs = qs.filter(batch_id=batch_id)
        if (status_filter := qp.get("status")):
            qs = qs.filter(review_status=status_filter.upper())
        if (eligibility := qp.get("eligibility")):
            qs = qs.filter(eligibility_status=eligibility.upper())
        if (confidence := qp.get("confidence")):
            qs = qs.filter(confidence_level=confidence.upper())
        if (flag := qp.get("flag")):
            qs = qs.filter(_flag_filter(flag))
        if (suspicious := qp.get("suspicious")) and suspicious.lower() in {"1", "true", "yes"}:
            qs = qs.filter(
                _flag_filter("SUSPICIOUS_HIGH_QUANTITY")
                | _flag_filter("USAGE_SPIKE_AFTER_DAY_NORMALIZATION")
            )
        if (locked := qp.get("locked")):
            if locked.lower() in {"1", "true"}:
                qs = qs.exclude(locked_at__isnull=True)
            else:
                qs = qs.filter(locked_at__isnull=True)
        if (search := qp.get("search")):
            qs = qs.filter(
                Q(facility_name__icontains=search)
                | Q(vendor__icontains=search)
                | Q(reference_id__icontains=search)
                | Q(origin__icontains=search)
                | Q(destination__icontains=search)
            )

        return qs.order_by("-activity_date", "-created_at")


class ActivityDetailView(RetrieveAPIView):
    serializer_class = NormalizedActivityDetailSerializer
    lookup_url_kwarg = "activity_id"

    def get_object(self):
        return _get_activity(self.kwargs["activity_id"])


# -------- Action endpoints --------

class ActivityApproveView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        # Cannot approve while unreviewed LLM suggestions exist
        if activity.llm_suggestions and not activity.llm_suggestion_reviewed:
            return Response(
                {"detail": "Row has unreviewed LLM suggestions. Accept or reject them first."},
                status=status.HTTP_409_CONFLICT,
            )
        comment = (request.data or {}).get("comment")
        user = _current_user()
        activity.review_status = "APPROVED"
        activity.reviewed_by = user
        activity.reviewed_at = _now()
        activity.review_comment = comment
        activity.approved_by = user
        activity.approved_at = _now()
        activity.save(update_fields=[
            "review_status", "reviewed_by", "reviewed_at",
            "review_comment", "approved_by", "approved_at", "updated_at",
        ])
        _log(activity, "APPROVED", user, comment=comment)
        _bump_batch_count(activity)
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ActivityRejectView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        comment = (request.data or {}).get("comment")
        if not comment:
            return Response({"detail": "Reject requires a comment."}, status=status.HTTP_400_BAD_REQUEST)
        user = _current_user()
        activity.review_status = "REJECTED"
        activity.reviewed_by = user
        activity.reviewed_at = _now()
        activity.review_comment = comment
        activity.save(update_fields=[
            "review_status", "reviewed_by", "reviewed_at", "review_comment", "updated_at",
        ])
        _log(activity, "REJECTED", user, comment=comment)
        _bump_batch_count(activity)
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ActivityMarkNotRelevantView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        comment = (request.data or {}).get("comment")
        user = _current_user()
        activity.review_status = "MARKED_NOT_RELEVANT"
        activity.eligibility_status = "NOT_RELEVANT"
        activity.reviewed_by = user
        activity.reviewed_at = _now()
        activity.review_comment = comment
        activity.save(update_fields=[
            "review_status", "eligibility_status",
            "reviewed_by", "reviewed_at", "review_comment", "updated_at",
        ])
        _log(activity, "MARKED_NOT_RELEVANT", user, comment=comment)
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ActivityRequestClarificationView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        comment = (request.data or {}).get("comment")
        if not comment:
            return Response({"detail": "Clarification request requires a comment."},
                            status=status.HTTP_400_BAD_REQUEST)
        user = _current_user()
        activity.review_status = "CLARIFICATION_REQUESTED"
        activity.reviewed_by = user
        activity.reviewed_at = _now()
        activity.review_comment = comment
        activity.save(update_fields=[
            "review_status", "reviewed_by", "reviewed_at", "review_comment", "updated_at",
        ])
        _log(activity, "CLARIFICATION_REQUESTED", user, comment=comment)
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ActivityOverrideView(APIView):
    """Override a field value with analyst justification."""

    ALLOWED_OVERRIDE_FIELDS = {
        "activity_subtype", "facility_name", "facility_country",
        "scope", "scope_category",
        "calculation_method", "emission_method",
    }

    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        data = request.data or {}
        field = (data.get("field") or "").strip()
        new_value = data.get("value")
        comment = data.get("comment")
        if field not in self.ALLOWED_OVERRIDE_FIELDS:
            return Response(
                {"detail": f"Field '{field}' is not overridable.",
                 "allowed": sorted(self.ALLOWED_OVERRIDE_FIELDS)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not comment:
            return Response({"detail": "Override requires a comment."}, status=status.HTTP_400_BAD_REQUEST)

        old_value = getattr(activity, field)
        setattr(activity, field, new_value)

        # Update field_provenance
        provenance = dict(activity.field_provenance or {})
        provenance[field] = {
            "method": "ANALYST_OVERRIDDEN",
            "reason": comment,
            "confidence": 0.99,
        }
        activity.field_provenance = provenance

        user = _current_user()
        activity.reviewed_by = user
        activity.reviewed_at = _now()
        activity.save(update_fields=[
            field, "field_provenance", "reviewed_by", "reviewed_at", "updated_at",
        ])
        _log(activity, "VALUE_OVERRIDDEN", user, comment=comment,
             old_value={"field": field, "value": str(old_value) if old_value is not None else None},
             new_value={"field": field, "value": new_value})
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ActivityLockView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Already locked."}, status=status.HTTP_409_CONFLICT)
        if activity.review_status != "APPROVED":
            return Response({"detail": "Only approved rows can be locked."},
                            status=status.HTTP_409_CONFLICT)
        if activity.llm_suggestions and not activity.llm_suggestion_reviewed:
            return Response({"detail": "Locked rows must have all LLM suggestions reviewed."},
                            status=status.HTTP_409_CONFLICT)
        user = _current_user()
        snapshot = {
            "field_provenance": deepcopy(activity.field_provenance or {}),
            "flags": list(activity.flags or []),
            "eligibility_status": activity.eligibility_status,
            "source_hierarchy_rank": activity.source_hierarchy_rank,
            "source_of_truth": activity.source_of_truth,
            "data_quality_score": activity.data_quality_score,
            "confidence_level": activity.confidence_level,
            "emission_factor": str(activity.emission_factor) if activity.emission_factor is not None else None,
            "emission_factor_source": activity.emission_factor_source,
            "co2e_kg": str(activity.co2e_kg) if activity.co2e_kg is not None else None,
            "issues": list(activity.issues.values_list("issue_code", flat=True)),
        }
        activity.locked_at = _now()
        activity.locked_snapshot = snapshot
        activity.review_status = "LOCKED"
        activity.save(update_fields=["locked_at", "locked_snapshot", "review_status", "updated_at"])
        _log(activity, "LOCKED", user, new_value=snapshot)
        _bump_batch_count(activity)
        return Response(NormalizedActivityDetailSerializer(activity).data)


# -------- Groq suggestions --------

class ActivityGroqSuggestView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        # Only invoke Groq for low-band rows.
        if activity.confidence_level not in ("LOW", "MEDIUM", "FAILED") and not request.data.get("force"):
            return Response(
                {"detail": f"Groq suggestion is intended for LOW/MEDIUM rows; this row is {activity.confidence_level}. Pass force=true to override."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = suggest_for_activity(activity)
        if not result.ok:
            # Record validation issue
            ValidationIssue.objects.create(
                tenant=activity.tenant, activity=activity,
                issue_code="LLM_SUGGESTION_FAILED", severity="WARNING",
                message=result.error or "Groq call failed",
            )
            return Response(
                {"ok": False, "error": result.error, "notes": result.notes},
                status=status.HTTP_200_OK,
            )

        # Store suggestions on the activity
        activity.llm_suggestions = result.suggestions
        activity.llm_suggestion_reviewed = False
        if result.suggestions:
            activity.flags = list(activity.flags or [])
            if "LLM_SUGGESTED_FIELD" not in activity.flags:
                activity.flags.append("LLM_SUGGESTED_FIELD")
        activity.save(update_fields=["llm_suggestions", "llm_suggestion_reviewed", "flags", "updated_at"])
        return Response({
            "ok": True,
            "cached": result.cached,
            "model": result.model_used,
            "suggestions": result.suggestions,
            "notes": result.notes,
        })


class ActivityAcceptLlmView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        data = request.data or {}
        field = (data.get("field") or "").strip()
        if not field:
            return Response({"detail": "field is required"}, status=status.HTTP_400_BAD_REQUEST)
        # Find matching suggestion
        match = None
        for s in activity.llm_suggestions or []:
            if s.get("field") == field:
                match = s
                break
        if match is None:
            return Response({"detail": f"No LLM suggestion for field '{field}'."},
                            status=status.HTTP_404_NOT_FOUND)
        # Apply the suggestion
        target_field = _llm_target_field(field)
        suggested_value = _coerce_llm_value(field, match.get("suggested_value"))
        old = getattr(activity, target_field, None) if hasattr(activity, target_field) else None
        if hasattr(activity, target_field):
            setattr(activity, target_field, suggested_value)
            provenance = dict(activity.field_provenance or {})
            provenance[target_field] = {
                "method": "ANALYST_OVERRIDDEN",
                "rule": f"AcceptedLLMSuggestion:{field}",
                "reason": match.get("reason"),
                "confidence": 0.95,
            }
            activity.field_provenance = provenance
        # Remove from llm_suggestions list
        activity.llm_suggestions = [s for s in (activity.llm_suggestions or []) if s.get("field") != field]
        if not activity.llm_suggestions:
            activity.llm_suggestion_reviewed = True
        old_quality = {
            "data_quality_score": activity.data_quality_score,
            "confidence_level": activity.confidence_level,
        }
        _refresh_quality_after_llm_review(activity)
        new_quality = {
            "data_quality_score": activity.data_quality_score,
            "confidence_level": activity.confidence_level,
        }
        user = _current_user()
        activity.save()
        _log(activity, "LLM_SUGGESTION_ACCEPTED", user,
             comment=match.get("reason"),
             old_value={"field": target_field, "value": str(old) if old is not None else None},
             new_value={
                 **match,
                 "applied_field": target_field,
                 "applied_value": suggested_value,
                 "old_quality": old_quality,
                 "new_quality": new_quality,
             })
        _bump_batch_count(activity)
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ActivityRejectLlmView(APIView):
    def post(self, request, activity_id, *args, **kwargs):
        activity = _get_activity(activity_id)
        if activity.locked_at is not None:
            return Response({"detail": "Locked rows cannot be modified."}, status=status.HTTP_409_CONFLICT)
        data = request.data or {}
        field = (data.get("field") or "").strip()
        if not field:
            return Response({"detail": "field is required"}, status=status.HTTP_400_BAD_REQUEST)
        match = next((s for s in activity.llm_suggestions or [] if s.get("field") == field), None)
        if match is None:
            return Response({"detail": f"No LLM suggestion for field '{field}'."},
                            status=status.HTTP_404_NOT_FOUND)
        activity.llm_suggestions = [s for s in (activity.llm_suggestions or []) if s.get("field") != field]
        if not activity.llm_suggestions:
            activity.llm_suggestion_reviewed = True
        _refresh_quality_after_llm_review(activity)
        user = _current_user()
        activity.save(update_fields=[
            "llm_suggestions", "llm_suggestion_reviewed", "flags",
            "data_quality_score", "confidence_level", "updated_at",
        ])
        _log(activity, "LLM_SUGGESTION_REJECTED", user, comment=data.get("comment"), new_value=match)
        _bump_batch_count(activity)
        return Response(NormalizedActivityDetailSerializer(activity).data)


class ReviewSummaryView(APIView):
    def get(self, request, *args, **kwargs):
        tenant = get_tenant()
        qs = NormalizedActivity.objects.filter(tenant=tenant)
        out = {
            "total": qs.count(),
            "pending": qs.filter(review_status="PENDING").count(),
            "approved": qs.filter(review_status="APPROVED").count(),
            "rejected": qs.filter(review_status="REJECTED").count(),
            "clarification_requested": qs.filter(review_status="CLARIFICATION_REQUESTED").count(),
            "marked_not_relevant": qs.filter(review_status="MARKED_NOT_RELEVANT").count(),
            "locked": qs.filter(review_status="LOCKED").count(),
            "high_confidence": qs.filter(confidence_level="HIGH").count(),
            "medium_confidence": qs.filter(confidence_level="MEDIUM").count(),
            "low_confidence": qs.filter(confidence_level="LOW").count(),
            "failed_confidence": qs.filter(confidence_level="FAILED").count(),
            "suspicious": qs.filter(
                _flag_filter("SUSPICIOUS_HIGH_QUANTITY")
                | _flag_filter("USAGE_SPIKE_AFTER_DAY_NORMALIZATION")
            ).count(),
            "llm_suggested": qs.filter(_flag_filter("LLM_SUGGESTED_FIELD")).count(),
            "estimated": qs.filter(is_estimate=True).count(),
            "spend_based": qs.filter(calculation_method="spend_based").count(),
            "by_source": {
                s: qs.filter(source_type=s).count()
                for s in ("sap", "utility", "travel")
            },
        }
        return Response(out)


def _bump_batch_count(activity: NormalizedActivity) -> None:
    """Recompute pending/approved/rejected/locked counts on the parent batch."""
    batch = activity.batch
    qs = NormalizedActivity.objects.filter(batch=batch)
    activities = list(qs.values("flags", "confidence_level"))
    batch.pending_rows = qs.filter(review_status="PENDING").count()
    batch.approved_rows = qs.filter(review_status="APPROVED").count()
    batch.rejected_rows = qs.filter(review_status="REJECTED").count()
    batch.locked_rows = qs.filter(review_status="LOCKED").count()
    batch.flagged_rows = sum(1 for row in activities if row.get("flags"))
    batch.suspicious_rows = sum(
        1
        for row in activities
        if any(
            flag in {"SUSPICIOUS_HIGH_QUANTITY", "SUSPICIOUS_HIGH_VALUE", "USAGE_SPIKE_AFTER_DAY_NORMALIZATION"}
            for flag in (row.get("flags") or [])
        )
    )
    batch.low_confidence_rows = sum(
        1 for row in activities if row.get("confidence_level") in {"LOW", "FAILED"}
    )
    batch.llm_suggested_rows = sum(
        1 for row in activities if "LLM_SUGGESTED_FIELD" in (row.get("flags") or [])
    )
    batch.save(update_fields=[
        "pending_rows", "approved_rows", "rejected_rows", "locked_rows",
        "flagged_rows", "suspicious_rows", "low_confidence_rows",
        "llm_suggested_rows", "updated_at",
    ])


def _llm_target_field(field: str) -> str:
    if field == "fuel_type":
        return "activity_subtype"
    if field == "is_esg_relevant":
        return "eligibility_status"
    if field == "spend_category":
        return "activity_subtype"
    return field


def _coerce_llm_value(field: str, value):
    if field == "is_esg_relevant":
        if isinstance(value, bool):
            return "ELIGIBLE" if value else "NOT_RELEVANT"
        text = str(value).strip().lower()
        if text in {"true", "yes", "eligible", "relevant", "esg_relevant"}:
            return "ELIGIBLE"
        if text in {"false", "no", "not_relevant", "not relevant", "irrelevant"}:
            return "NOT_RELEVANT"
        return "NEEDS_REVIEW"
    return value


def _refresh_quality_after_llm_review(activity: NormalizedActivity) -> None:
    """Keep AI audit flags, but do not penalize reviewed AI suggestions."""
    ignored_flags = {"LLM_SUGGESTED_FIELD"} if activity.llm_suggestion_reviewed else set()
    activity.data_quality_score, activity.confidence_level = score_from_method_and_flags(
        calculation_method=activity.calculation_method,
        emission_method=activity.emission_method,
        flags=list(activity.flags or []),
        ignored_flags=ignored_flags,
    )
