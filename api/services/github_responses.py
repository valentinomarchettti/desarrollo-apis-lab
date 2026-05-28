from rest_framework import status
from rest_framework.response import Response

from api.clients import github as github_client
from api.services.github_connections import deactivate_active_github_connection


def github_error_response(error, github_response, github_data):
    if github_response.status_code == status.HTTP_401_UNAUTHORIZED:
        deactivate_active_github_connection()

    return Response(
        {
            "error": error,
            "github_response": github_data,
        },
        status=github_client.error_status(github_response.status_code),
    )


def unexpected_github_response(error, github_data):
    return Response(
        {
            "error": error,
            "github_response": github_data,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def paginated_or_error(access_token, url, github_error, unexpected_error, params=None):
    data, error_response, error_data = github_client.get_paginated_json(
        access_token,
        url,
        params=params,
    )
    if error_response is None:
        return data, None

    if error_response.status_code >= status.HTTP_400_BAD_REQUEST:
        return None, github_error_response(github_error, error_response, error_data)

    return None, unexpected_github_response(unexpected_error, error_data)
