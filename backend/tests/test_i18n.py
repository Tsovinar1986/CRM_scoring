"""Server messages follow the app's language (Accept-Language), see app/i18n.py."""

from app.i18n import request_lang, translate


def _login_unknown(client, language=None):
    headers = {"Accept-Language": language} if language else {}
    return client.post(
        "/api/accounts/login", json={"email": "nobody@nowhere.com", "password": "Correct-Horse9"}, headers=headers
    )


def test_error_messages_follow_the_requested_language(client):
    assert _login_unknown(client).json()["detail"] == "Incorrect email or password."
    assert _login_unknown(client, "hy").json()["detail"] == "Էլ. փոստը կամ գաղտնաբառը սխալ է։"
    assert _login_unknown(client, "ru-RU,ru;q=0.9,en;q=0.8").json()["detail"] == "Неверная почта или пароль."
    # Status codes and anything else about the response stay the same.
    assert _login_unknown(client, "ru").status_code == 401


def test_messages_with_variable_parts_are_translated(client):
    resp = client.post(
        "/api/leads/upload",
        files={"file": ("leads.exe", b"not a real csv", "application/octet-stream")},
        headers={"Accept-Language": "ru"},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("Неподдерживаемый тип файла — допустимы: ")


def test_status_messages_are_translated(client):
    resp = client.post("/api/accounts/forgot-password", json={"email": "nobody@nowhere.com"}, headers={"Accept-Language": "hy"})

    assert resp.json()["detail"] == "Եթե այդ էլ. հասցեով հաշիվ կա, վերականգնման հղումն արդեն ճանապարհին է։"


def test_unknown_languages_and_texts_stay_english():
    assert translate("Incorrect email or password.", "en") == "Incorrect email or password."
    assert translate("Something we never translated.", "hy") == "Something we never translated."
    assert translate("File has 6000 rows -- max 5000 per upload. Split it into smaller files.", "hy").startswith("Ֆայլն ունի 6000 տող")


def test_request_language_parsing():
    class FakeRequest:
        def __init__(self, value):
            self.headers = {"accept-language": value} if value is not None else {}

    assert request_lang(FakeRequest("hy")) == "hy"
    assert request_lang(FakeRequest("de-DE,ru;q=0.8")) == "ru"
    assert request_lang(FakeRequest("de-DE")) == "en"
    assert request_lang(FakeRequest(None)) == "en"
