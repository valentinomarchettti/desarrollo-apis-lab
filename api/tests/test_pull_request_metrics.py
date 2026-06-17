from api.services.pull_request_metrics import build_pull_request_metrics


def test_build_pull_request_metrics_calcula_resumen_tecnico_del_pr():
    pull_data = {
        "additions": 120,
        "deletions": 30,
        "changed_files": 3,
        "created_at": "2026-06-10T12:00:00Z",
        "head": {"ref": "feature/testing"},
        "base": {"ref": "main"},
        "user": {
            "id": 1,
            "login": "valen",
            "html_url": "https://github.com/valen",
        },
    }
    files_data = [
        {"filename": "api/views.py", "additions": 80, "deletions": 20},
        {"filename": "api/tests/test_views.py", "additions": 30, "deletions": 5},
        {"filename": "README.md", "additions": 10, "deletions": 5},
    ]
    commits_data = [
        {
            "sha": "abc123",
            "author": {
                "login": "valen",
                "html_url": "https://github.com/valen",
            },
            "commit": {
                "author": {
                    "name": "Valentino",
                    "email": "valen@test.com",
                    "date": "2026-06-10T10:00:00Z",
                },
            },
        },
        {
            "sha": "def456",
            "author": {
                "login": "paula",
                "html_url": "https://github.com/paula",
            },
            "commit": {
                "author": {
                    "name": "Paula",
                    "email": "paula@test.com",
                    "date": "2026-06-12T10:00:00Z",
                },
            },
        },
    ]
    commit_details = [
        {
            "sha": "def456",
            "author": {
                "login": "paula",
                "html_url": "https://github.com/paula",
            },
            "commit": {
                "author": {
                    "name": "Paula",
                    "email": "paula@test.com",
                    "date": "2026-06-12T10:00:00Z",
                },
            },
            "files": [
                {"filename": "api/tests/test_views.py"},
            ],
        },
    ]

    metricas = build_pull_request_metrics(
        pull_data,
        files_data,
        commits_data,
        commit_details,
    )

    assert metricas["ramas"] == {
        "origen": "feature/testing",
        "destino": "main",
    }
    assert metricas["archivos"]["total_modificados"] == 3
    assert metricas["archivos"]["tests_modificados"] == 1
    assert metricas["archivos"]["archivos_test"] == ["api/tests/test_views.py"]
    assert metricas["lineas"] == {
        "agregadas": 120,
        "eliminadas": 30,
        "balance_neto": 90,
    }
    assert metricas["actividad"] == {
        "primer_commit": "2026-06-10",
        "ultimo_commit": "2026-06-12",
        "dias_calendario": 3,
        "dias_con_commits": ["2026-06-10", "2026-06-12"],
    }
    assert metricas["autoria"]["autor_pr"]["github_login"] == "valen"
    assert metricas["autoria"]["autor_pr"]["fecha_creacion_pr"] == "2026-06-10"
    assert [
        author["github_login"]
        for author in metricas["autoria"]["autores_commits"]
    ] == ["paula", "valen"]
    assert metricas["autoria"]["autores_tests"][0]["github_login"] == "paula"
    assert metricas["autoria"]["autores_tests"][0]["archivos_test"] == [
        "api/tests/test_views.py"
    ]


def test_build_pull_request_metrics_usa_totales_de_archivos_si_github_no_los_envia():
    pull_data = {
        "head": {"ref": "feature/fallback"},
        "base": {"ref": "main"},
        "user": {"login": "valen"},
    }
    files_data = [
        {"filename": "src/app.py", "additions": "7", "deletions": "2"},
        {"filename": "tests/test_app.py", "additions": 3, "deletions": 1},
    ]

    metricas = build_pull_request_metrics(pull_data, files_data, [], [])

    assert metricas["archivos"]["total_modificados"] == 2
    assert metricas["archivos"]["tests_modificados"] == 1
    assert metricas["lineas"]["agregadas"] == 10
    assert metricas["lineas"]["eliminadas"] == 3
    assert metricas["lineas"]["balance_neto"] == 7
    assert metricas["actividad"]["dias_calendario"] == 0
