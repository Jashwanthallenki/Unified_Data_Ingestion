import logging

from django.conf import settings
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def json_exception_handler(exc, context):
    """Return JSON for API errors, including unexpected 500s in local dev."""
    response = exception_handler(exc, context)
    if response is not None:
        return response

    view = context.get("view")
    logger.exception("Unhandled API exception in %s", view.__class__.__name__ if view else "unknown", exc_info=exc)

    detail = "Internal server error."
    if settings.DEBUG:
        detail = f"{exc.__class__.__name__}: {exc}"

    return Response(
        {"detail": detail},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
