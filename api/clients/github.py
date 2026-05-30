import requests
from rest_framework import status


AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
REPOS_URL = "https://api.github.com/user/repos"
PULLS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls"
PULL_DETAIL_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
PULL_FILES_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/files"
PULL_COMMITS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/commits"
COMMIT_DETAIL_URL = "https://api.github.com/repos/{owner}/{repo}/commits/{sha}"
PULL_REVIEWS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/reviews"
PULL_REVIEW_COMMENTS_URL = "https://api.github.com/repos/{owner}/{repo}/pulls/{number}/comments"
ISSUE_COMMENTS_URL = "https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments"
OAUTH_SCOPES = "repo read:user user:email"
STATE_CACHE_PREFIX = "github_oauth_state:"
STATE_TTL_SECONDS = 600
REQUEST_TIMEOUT_SECONDS = 10


def api_headers(access_token):
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def response_data(response):
    try:
        return response.json()
    except ValueError:
        return {"raw_response": response.text}


def error_status(github_status_code):
    if github_status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        return github_status_code
    if status.HTTP_400_BAD_REQUEST <= github_status_code < status.HTTP_500_INTERNAL_SERVER_ERROR:
        return status.HTTP_400_BAD_REQUEST
    return status.HTTP_502_BAD_GATEWAY


def get_json(access_token, url, params=None):
    response = requests.get(
        url,
        headers=api_headers(access_token),
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response, response_data(response)


def get_commit_detail(access_token, owner, repo, sha):
    url = COMMIT_DETAIL_URL.format(owner=owner, repo=repo, sha=sha)
    return get_json(access_token, url)


def patch_json(access_token, url, payload):
    response = requests.patch(
        url,
        headers=api_headers(access_token),
        json=payload,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response, response_data(response)


def get_paginated_json(access_token, url, params=None):
    results = []
    page = 1

    while True:
        page_params = {
            **(params or {}),
            "per_page": 100,
            "page": page,
        }
        response, data = get_json(access_token, url, params=page_params)

        if response.status_code >= status.HTTP_400_BAD_REQUEST:
            return None, response, data

        if not isinstance(data, list):
            return None, response, data

        results.extend(data)

        if "next" not in response.links:
            return results, None, None
        page += 1


def get_diff(access_token, url):
    headers = api_headers(access_token)
    headers["Accept"] = "application/vnd.github.v3.diff"

    response = requests.get(
        url,
        headers=headers,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return response, response.text
