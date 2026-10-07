import io

SAMPLE_CSV = b"company_name,domain\nAcme Inc,acme.com\n"


def _upload(client, content=SAMPLE_CSV, filename="leads.csv"):
    return client.post(
        "/api/leads/upload",
        files={"file": (filename, io.BytesIO(content), "text/csv")},
    )


def test_security_headers_present_on_every_response(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"
    assert resp.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in resp.headers["permissions-policy"]
    assert "default-src 'self'" in resp.headers["content-security-policy"]


def test_hsts_not_sent_over_plain_http(client):
    # TestClient talks to the app over plain http -- HSTS only means
    # anything over an actually-secure connection, so it shouldn't appear.
    resp = client.get("/api/health")
    assert "strict-transport-security" not in resp.headers


def test_cors_preflight_only_allows_get_and_post(client):
    resp = client.options(
        "/api/leads",
        headers={
            "Origin": "http://localhost:5000",
            "Access-Control-Request-Method": "DELETE",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    # Starlette's CORSMiddleware answers preflight itself; a method outside
    # allow_methods gets a 400, not the wildcard "sure, anything goes".
    assert resp.status_code == 400


def test_cors_preflight_allows_post_from_configured_origin(client):
    resp = client.options(
        "/api/leads/upload",
        headers={
            "Origin": "http://localhost:5000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5000"


def test_upload_rejects_disallowed_file_extension(client):
    resp = _upload(client, content=b"not a real csv", filename="leads.exe")
    assert resp.status_code == 400
    assert "unsupported file type" in resp.json()["detail"].lower()


def test_upload_rejects_oversized_file(client, monkeypatch):
    from app.services import upload_validation

    monkeypatch.setattr(upload_validation, "MAX_UPLOAD_SIZE_MB", 0)  # anything nonzero is "too big"

    resp = _upload(client, content=SAMPLE_CSV)
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_upload_rejects_too_many_rows(client, monkeypatch):
    from app.services import upload_validation

    monkeypatch.setattr(upload_validation, "MAX_UPLOAD_ROWS", 1)

    content = b"company_name,domain\nAcme,acme.com\nGlobex,globex.com\n"
    resp = _upload(client, content=content)
    assert resp.status_code == 400
    assert "max 1 per upload" in resp.json()["detail"].lower()


def test_upload_rate_limit_returns_429_after_the_configured_cap(client):
    # Default is 10/minute (RATE_LIMIT_UPLOAD) -- the sample file is well
    # under every other limit, so this exercises the rate limiter only.
    responses = [_upload(client) for _ in range(11)]
    assert [r.status_code for r in responses[:10]] == [200] * 10
    assert responses[10].status_code == 429


def test_frontend_files_cannot_escape_the_build_directory(tmp_path):
    from app.main import frontend_file

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("app")
    (dist / "assets" / "app.js").write_text("js")
    (tmp_path / ".env").write_text("SECRET=1")

    assert frontend_file(dist, "assets/app.js") == (dist / "assets" / "app.js").resolve()
    assert frontend_file(dist, "purchase-complete") == (dist / "index.html").resolve()
    for attack in ["../.env", "assets/../../.env", str(tmp_path / ".env")]:
        assert frontend_file(dist, attack) == (dist / "index.html").resolve(), attack
