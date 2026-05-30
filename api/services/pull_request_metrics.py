from datetime import datetime


TEST_FILE_MARKERS = (
    "/tests/",
    ".test.",
    ".spec.",
)


def is_test_file(filename):
    normalized = (filename or "").replace("\\", "/").lower()
    basename = normalized.rsplit("/", 1)[-1]

    return (
        normalized.startswith("tests/")
        or any(marker in f"/{normalized}" for marker in TEST_FILE_MARKERS)
        or basename == "tests.py"
        or basename.startswith("test_")
        or basename.endswith("_test.py")
    )


def build_pull_request_metrics(pull_data, files_data, commits_data, commit_details):
    files_data = files_data or []
    commits_data = commits_data or []
    commit_details = commit_details or []

    test_files = sorted(
        {
            file_data.get("filename")
            for file_data in files_data
            if file_data.get("filename") and is_test_file(file_data.get("filename"))
        }
    )

    additions = _number_or_fallback(
        pull_data.get("additions"),
        sum(_number(file_data.get("additions")) for file_data in files_data),
    )
    deletions = _number_or_fallback(
        pull_data.get("deletions"),
        sum(_number(file_data.get("deletions")) for file_data in files_data),
    )
    commit_dates = sorted(
        date_value
        for date_value in (_commit_date(commit_data) for commit_data in commits_data)
        if date_value
    )

    return {
        "ramas": {
            "origen": (pull_data.get("head") or {}).get("ref"),
            "destino": (pull_data.get("base") or {}).get("ref"),
        },
        "archivos": {
            "total_modificados": _number_or_fallback(
                pull_data.get("changed_files"),
                len(files_data),
            ),
            "tests_modificados": len(test_files),
            "archivos_test": test_files,
        },
        "lineas": {
            "agregadas": additions,
            "eliminadas": deletions,
            "balance_neto": additions - deletions,
        },
        "actividad": _build_activity(commit_dates),
        "autoria": {
            "autor_pr": _build_pull_request_author(pull_data),
            "autores_commits": _build_commit_authors(commits_data),
            "autores_tests": _build_test_authors(commits_data, commit_details),
        },
    }


def _number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _number_or_fallback(value, fallback):
    if value is None:
        return fallback
    return _number(value)


def _parse_datetime(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _date_string(value):
    parsed = _parse_datetime(value)
    if not parsed:
        return None
    return parsed.date().isoformat()


def _commit_date(commit_data):
    commit = commit_data.get("commit") or {}
    author = commit.get("author") or {}
    committer = commit.get("committer") or {}
    return _date_string(author.get("date") or committer.get("date"))


def _build_activity(commit_dates):
    unique_dates = sorted(set(commit_dates))
    first_date = unique_dates[0] if unique_dates else None
    last_date = unique_dates[-1] if unique_dates else None
    days_span = 0

    if first_date and last_date:
        first = datetime.fromisoformat(first_date).date()
        last = datetime.fromisoformat(last_date).date()
        days_span = (last - first).days + 1

    return {
        "primer_commit": first_date,
        "ultimo_commit": last_date,
        "dias_calendario": days_span,
        "dias_con_commits": unique_dates,
    }


def _build_pull_request_author(pull_data):
    user = pull_data.get("user") or {}

    return {
        "github_id": user.get("id"),
        "github_login": user.get("login"),
        "html_url": user.get("html_url"),
        "fecha_creacion_pr": _date_string(pull_data.get("created_at")),
    }


def _author_from_commit(commit_data, fallback=None):
    fallback = fallback or {}
    github_author = commit_data.get("author") or {}
    commit = commit_data.get("commit") or {}
    declared_author = commit.get("author") or {}

    return {
        "github_login": github_author.get("login") or fallback.get("github_login"),
        "nombre": (
            declared_author.get("name")
            or fallback.get("nombre")
            or github_author.get("login")
        ),
        "email": declared_author.get("email") or fallback.get("email"),
        "html_url": github_author.get("html_url") or fallback.get("html_url"),
    }


def _author_key(author):
    return (
        author.get("github_login")
        or author.get("email")
        or author.get("nombre")
        or "autor_desconocido"
    )


def _new_author_bucket(author):
    return {
        "github_login": author.get("github_login"),
        "nombre": author.get("nombre"),
        "email": author.get("email"),
        "html_url": author.get("html_url"),
        "commits": 0,
        "_dates": set(),
        "_files": set(),
    }


def _build_commit_authors(commits_data):
    authors = {}

    for commit_data in commits_data:
        author = _author_from_commit(commit_data)
        key = _author_key(author)
        bucket = authors.setdefault(key, _new_author_bucket(author))
        bucket["commits"] += 1

        commit_date = _commit_date(commit_data)
        if commit_date:
            bucket["_dates"].add(commit_date)

    return _finalize_authors(authors.values())


def _build_test_authors(commits_data, commit_details):
    summary_by_sha = {
        commit_data.get("sha"): commit_data
        for commit_data in commits_data
        if commit_data.get("sha")
    }
    authors = {}

    for commit_detail in commit_details:
        test_files = sorted(
            {
                file_data.get("filename")
                for file_data in commit_detail.get("files", [])
                if file_data.get("filename") and is_test_file(file_data.get("filename"))
            }
        )
        if not test_files:
            continue

        fallback_author = _author_from_commit(summary_by_sha.get(commit_detail.get("sha"), {}))
        author = _author_from_commit(commit_detail, fallback=fallback_author)
        key = _author_key(author)
        bucket = authors.setdefault(key, _new_author_bucket(author))
        bucket["commits"] += 1
        bucket["_files"].update(test_files)

        commit_date = _commit_date(commit_detail) or _commit_date(
            summary_by_sha.get(commit_detail.get("sha"), {})
        )
        if commit_date:
            bucket["_dates"].add(commit_date)

    return _finalize_authors(authors.values(), include_test_files=True)


def _finalize_authors(author_buckets, include_test_files=False):
    finalized = []

    for bucket in author_buckets:
        dates = sorted(bucket.pop("_dates"))
        files = sorted(bucket.pop("_files"))
        bucket["primer_commit"] = dates[0] if dates else None
        bucket["ultimo_commit"] = dates[-1] if dates else None
        bucket["dias_con_commits"] = dates
        if include_test_files:
            bucket["archivos_test"] = files
        finalized.append(bucket)

    return sorted(
        finalized,
        key=lambda author: (
            -author["commits"],
            author.get("github_login") or author.get("email") or author.get("nombre") or "",
        ),
    )
