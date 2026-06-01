from datetime import datetime, timezone as datetime_timezone

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_filters import rest_framework as filters

from api.models import PullRequest, Repositorio, SummaryTecnico


class RepositorioFilter(filters.FilterSet):
    github_owner = filters.CharFilter(lookup_expr="icontains")
    github_repo = filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = Repositorio
        fields = [
            "activo",
            "github_owner",
            "github_repo",
        ]


class PullRequestFilter(filters.FilterSet):
    titulo = filters.CharFilter(lookup_expr="icontains")
    autor_github = filters.CharFilter(lookup_expr="icontains")
    rama_destino = filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = PullRequest
        fields = [
            "estado",
            "repositorio",
            "numero",
            "titulo",
            "autor_github",
            "rama_destino",
        ]


class SummaryTecnicoFilter(filters.FilterSet):
    class Meta:
        model = SummaryTecnico
        fields = [
            "estado",
            "pull_request",
        ]


GITHUB_PULL_REQUEST_ESTADOS = {
    PullRequest.ESTADO_OPEN,
    PullRequest.ESTADO_CLOSED,
    PullRequest.ESTADO_MERGED,
}
GITHUB_PULL_REQUEST_TEXT_FILTERS = (
    "titulo",
    "autor_github",
    "rama_destino",
)
GITHUB_PULL_REQUEST_ORDERING_FIELDS = {
    "numero",
    "created_at",
    "updated_at",
}


def filter_github_pull_requests(pull_requests, query_params):
    filtered_pull_requests = list(pull_requests)

    estado = query_params.get("estado")
    if estado:
        if estado not in GITHUB_PULL_REQUEST_ESTADOS:
            return None, {
                "error": "El parametro estado es invalido.",
                "detail": "Usa uno de estos valores: open, closed, merged.",
            }
        filtered_pull_requests = [
            pull_request
            for pull_request in filtered_pull_requests
            if pull_request.get("estado") == estado
        ]

    numero = query_params.get("numero")
    if numero:
        try:
            numero = int(numero)
        except ValueError:
            return None, {
                "error": "El parametro numero es invalido.",
                "detail": "Usa un numero entero de pull request.",
            }
        filtered_pull_requests = [
            pull_request
            for pull_request in filtered_pull_requests
            if pull_request.get("numero") == numero
        ]

    for field_name in GITHUB_PULL_REQUEST_TEXT_FILTERS:
        field_value = query_params.get(field_name)
        if field_value:
            filtered_pull_requests = [
                pull_request
                for pull_request in filtered_pull_requests
                if _contains(pull_request.get(field_name), field_value)
            ]

    return _order_github_pull_requests(filtered_pull_requests, query_params), None


def _contains(value, expected):
    return expected.lower() in str(value or "").lower()


def _order_github_pull_requests(pull_requests, query_params):
    ordering = query_params.get("ordering")
    if not ordering:
        return pull_requests

    ordering_fields = [field.strip() for field in ordering.split(",") if field.strip()]
    ordered_pull_requests = pull_requests

    for ordering_field in reversed(ordering_fields):
        reverse = ordering_field.startswith("-")
        field_name = ordering_field[1:] if reverse else ordering_field
        if field_name not in GITHUB_PULL_REQUEST_ORDERING_FIELDS:
            continue

        ordered_pull_requests = sorted(
            ordered_pull_requests,
            key=lambda pull_request: _github_ordering_value(pull_request, field_name),
            reverse=reverse,
        )

    return ordered_pull_requests


def _github_ordering_value(pull_request, field_name):
    value = pull_request.get(field_name)
    if field_name in {"created_at", "updated_at"}:
        return _parse_github_datetime(value)
    if field_name == "numero":
        return value if value is not None else 0
    return value if value is not None else ""


def _parse_github_datetime(value):
    parsed_datetime = parse_datetime(value or "")
    if parsed_datetime is None:
        return datetime.min.replace(tzinfo=datetime_timezone.utc)
    if timezone.is_naive(parsed_datetime):
        return timezone.make_aware(parsed_datetime, timezone=datetime_timezone.utc)
    return parsed_datetime
