"""Posts the next marketing post to LinkedIn, Facebook, Instagram, Threads and Reddit.

Run once a day by .github/workflows/autopost.yml. Each platform works
through posts.json in order, one post per posting day, and starts over
after the last one: Facebook and Threads post every day, LinkedIn on
Mondays, Wednesdays and Fridays, Instagram on Tuesdays, Thursdays and
Saturdays, Reddit on Tuesdays and Thursdays. Which post comes next is worked out from the date, so nothing
needs to be stored between runs.

Uses the platforms' official APIs only, with tokens from the environment
(GitHub Secrets in the workflow). A platform without its tokens is skipped,
so the workflow can be switched on before every account is set up.

    python marketing/autopost.py --dry-run          # show today's posts
    python marketing/autopost.py --date 2026-11-09  # as if it were that day
"""

import argparse
import datetime as dt
import json
import mimetypes
import os
import re
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
START = dt.date(2026, 11, 9)  # a Monday: post 1 goes out on this day
# Day numbers as date.weekday() gives them: Monday is 0.
SCHEDULE = {
    "facebook": {0, 1, 2, 3, 4, 5, 6},
    "threads": {0, 1, 2, 3, 4, 5, 6},
    "linkedin": {0, 2, 4},
    "instagram": {1, 3, 5},
    "reddit": {1, 3},
}
SITE = "https://www.crmscoring.com"
# Instagram and Threads fetch images from a public address rather than taking
# an upload; the repository is public, so they're served straight from it.
RAW_BASE = os.getenv("IMAGE_BASE_URL", "https://raw.githubusercontent.com/Tsovinar1986/CRM_scoring/main/marketing/")
# Instagram has no text-only posts: those get this picture.
INSTAGRAM_DEFAULT_IMAGE = "images/poster.png"

# Versioned APIs: LinkedIn supports each monthly version for about a year,
# Meta each Graph version for about two. Override in the workflow when one ages out.
LINKEDIN_VERSION = os.getenv("LINKEDIN_VERSION", "202606")
GRAPH_VERSION = os.getenv("FACEBOOK_GRAPH_VERSION", "v23.0")


class PostError(Exception):
    pass


def load_posts() -> list[dict]:
    posts = json.loads((HERE / "posts.json").read_text(encoding="utf-8"))
    if not posts:
        raise PostError("posts.json has no posts.")
    return posts


def post_for(platform: str, day: dt.date, posts: list[dict]) -> dict | None:
    """The post due on this platform on this day, or None if it doesn't post then."""
    if day < START or day.weekday() not in SCHEDULE[platform]:
        return None
    # How many posting days came before this one.
    earlier = sum(
        1 for i in range((day - START).days) if (START + dt.timedelta(days=i)).weekday() in SCHEDULE[platform]
    )
    return posts[earlier % len(posts)]


def text_for(platform: str, post: dict) -> str:
    text = post.get(platform) or post["text"]
    if platform == "instagram":
        # Links in Instagram captions aren't clickable; the bio link is.
        text = text.replace(SITE, "crmscoring.com (link in bio)")
    return text


def image_for(post: dict) -> Path | None:
    if not post.get("image"):
        return None
    path = HERE / post["image"]
    if not path.is_file():
        raise PostError(f"Image not found: {post['image']}")
    return path


def _check(resp: requests.Response, what: str) -> requests.Response:
    if resp.status_code == 401:
        raise PostError(f"{what}: the access token was rejected (401). It may have expired; see marketing/README.md.")
    if resp.status_code >= 400:
        raise PostError(f"{what}: {resp.status_code} {resp.text[:400]}")
    return resp


# --- LinkedIn --------------------------------------------------------------

# LinkedIn post text is "little text": these characters must be escaped or the
# post is rejected or cut off where they appear.
_LITTLE_TEXT = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def linkedin_escape(text: str) -> str:
    return _LITTLE_TEXT.sub(r"\\\1", text)


def post_linkedin(text: str, image: Path | None, token: str) -> str:
    auth = {"Authorization": f"Bearer {token}"}
    rest = {**auth, "LinkedIn-Version": LINKEDIN_VERSION, "X-Restli-Protocol-Version": "2.0.0"}
    me = _check(requests.get("https://api.linkedin.com/v2/userinfo", headers=auth, timeout=30), "LinkedIn profile").json()
    author = f"urn:li:person:{me['sub']}"

    body = {
        "author": author,
        "commentary": linkedin_escape(text),
        "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }
    if image:
        upload = _check(
            requests.post(
                "https://api.linkedin.com/rest/images?action=initializeUpload",
                headers=rest,
                json={"initializeUploadRequest": {"owner": author}},
                timeout=30,
            ),
            "LinkedIn image upload",
        ).json()["value"]
        _check(requests.put(upload["uploadUrl"], headers=auth, data=image.read_bytes(), timeout=120), "LinkedIn image upload")
        body["content"] = {"media": {"id": upload["image"], "altText": "CRM Scoring"}}

    resp = _check(requests.post("https://api.linkedin.com/rest/posts", headers=rest, json=body, timeout=30), "LinkedIn post")
    return resp.headers.get("x-restli-id", "posted")


# --- Facebook Page -----------------------------------------------------------

def post_facebook(text: str, image: Path | None, page_id: str, token: str) -> str:
    base = f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}"
    if image:
        mime = mimetypes.guess_type(image.name)[0] or "image/png"
        with image.open("rb") as f:
            resp = requests.post(
                f"{base}/photos",
                data={"message": text, "access_token": token},
                files={"source": (image.name, f, mime)},
                timeout=120,
            )
    else:
        resp = requests.post(f"{base}/feed", data={"message": text, "access_token": token}, timeout=30)
    body = _check(resp, "Facebook post").json()
    return body.get("post_id") or body.get("id", "posted")


# --- Instagram (a Professional account linked to the Facebook Page) -------------

def post_instagram(text: str, image_path: str, account_id: str, token: str) -> str:
    base = f"https://graph.facebook.com/{GRAPH_VERSION}/{account_id}"
    container = _check(
        requests.post(f"{base}/media", data={"image_url": RAW_BASE + image_path, "caption": text, "access_token": token}, timeout=60),
        "Instagram post",
    ).json()["id"]
    # Instagram fetches the image first; publishing waits until it's ready.
    for _ in range(12):
        status = requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{container}",
            params={"fields": "status_code", "access_token": token},
            timeout=30,
        ).json().get("status_code")
        if status == "FINISHED":
            break
        if status == "ERROR":
            raise PostError("Instagram post: Instagram couldn't process the image.")
        time.sleep(5)
    body = _check(requests.post(f"{base}/media_publish", data={"creation_id": container, "access_token": token}, timeout=60), "Instagram post")
    return body.json().get("id", "posted")


# --- Threads ---------------------------------------------------------------

def post_threads(text: str, image_path: str | None, token: str) -> str:
    base = "https://graph.threads.net/v1.0/me"
    data = {"text": text, "access_token": token, "media_type": "TEXT"}
    if image_path:
        data.update(media_type="IMAGE", image_url=RAW_BASE + image_path)
    container = _check(requests.post(f"{base}/threads", data=data, timeout=60), "Threads post").json()["id"]
    if image_path:
        # Threads asks for a short wait while it fetches the image.
        time.sleep(30)
    body = _check(requests.post(f"{base}/threads_publish", data={"creation_id": container, "access_token": token}, timeout=60), "Threads post")
    return body.json().get("id", "posted")


# --- Reddit ----------------------------------------------------------------

# Reddit posts go to your own profile (u/<username>) unless REDDIT_SUBREDDIT
# names your own subreddit. Never point this at a community like r/salesforce:
# the same promotional post on a schedule there is spam under Reddit's rules
# and can get the account and crmscoring.com banned site-wide.
REDDIT_USER_AGENT = "crmscoring-autopost/1.0 (by u/{username})"


def reddit_title_and_body(text: str) -> tuple[str, str]:
    """First line becomes the title (Reddit allows 300 characters), the rest the body."""
    first, _, rest = text.strip().partition("\n")
    title = first.strip()
    if len(title) > 300:
        title = title[:297].rstrip() + "..."
    return title, rest.strip()


def reddit_target(username: str, subreddit: str | None) -> str:
    """Where to post: the subreddit's name without r/, or u_<username> for the profile."""
    name = (subreddit or "").strip().removeprefix("/").removeprefix("r/")
    return name or f"u_{username}"


def post_reddit(text: str, client_id: str, secret: str, username: str, password: str, subreddit: str | None) -> str:
    agent = {"User-Agent": REDDIT_USER_AGENT.format(username=username)}
    auth = _check(
        requests.post(
            "https://www.reddit.com/api/v1/access_token",
            auth=(client_id, secret),
            data={"grant_type": "password", "username": username, "password": password},
            headers=agent,
            timeout=30,
        ),
        "Reddit sign-in",
    ).json()
    if "access_token" not in auth:
        raise PostError(f"Reddit sign-in: {auth.get('error', auth)}")
    title, body = reddit_title_and_body(text)
    resp = _check(
        requests.post(
            "https://oauth.reddit.com/api/submit",
            headers={**agent, "Authorization": f"bearer {auth['access_token']}"},
            data={"sr": reddit_target(username, subreddit), "kind": "self", "title": title, "text": body, "api_type": "json"},
            timeout=30,
        ),
        "Reddit post",
    ).json()
    errors = resp.get("json", {}).get("errors") or []
    if errors:
        raise PostError(f"Reddit post: {errors}")
    return resp.get("json", {}).get("data", {}).get("url", "posted")


# --- Run -------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="show what would be posted, post nothing")
    parser.add_argument("--date", type=dt.date.fromisoformat, help="pretend today is this date (YYYY-MM-DD)")
    parser.add_argument("--only", choices=sorted(SCHEDULE), help="post to this platform only")
    args = parser.parse_args()

    # The schedule follows Yerevan's calendar (UTC+4, no daylight saving).
    today = args.date or (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=4)).date()
    posts = load_posts()
    failed = False
    for platform in sorted(SCHEDULE):
        if args.only and platform != args.only:
            continue
        post = post_for(platform, today, posts)
        if post is None:
            print(f"{platform}: nothing scheduled for {today:%a %Y-%m-%d}")
            continue
        text, image = text_for(platform, post), image_for(post)
        image_path = post.get("image") or (INSTAGRAM_DEFAULT_IMAGE if platform == "instagram" else None)
        if platform == "reddit":
            image_path = None  # Reddit gets text posts; the link shows a preview of the site
        label = f"{platform}: post {posts.index(post) + 1}/{len(posts)}" + (f" with {Path(image_path).name}" if image_path else "")
        if args.dry_run:
            print(f"{label} (dry run)\n{text}\n")
            continue
        try:
            if platform == "linkedin":
                token = os.getenv("LINKEDIN_ACCESS_TOKEN")
                if not token:
                    print(f"{platform}: skipped, LINKEDIN_ACCESS_TOKEN isn't set")
                    continue
                post_id = post_linkedin(text, image, token)
            elif platform == "facebook":
                page_id, token = os.getenv("FACEBOOK_PAGE_ID"), os.getenv("FACEBOOK_PAGE_TOKEN")
                if not (page_id and token):
                    print(f"{platform}: skipped, FACEBOOK_PAGE_ID / FACEBOOK_PAGE_TOKEN aren't set")
                    continue
                post_id = post_facebook(text, image, page_id, token)
            elif platform == "instagram":
                account_id, token = os.getenv("INSTAGRAM_ACCOUNT_ID"), os.getenv("FACEBOOK_PAGE_TOKEN")
                if not (account_id and token):
                    print(f"{platform}: skipped, INSTAGRAM_ACCOUNT_ID / FACEBOOK_PAGE_TOKEN aren't set")
                    continue
                post_id = post_instagram(text, image_path, account_id, token)
            elif platform == "reddit":
                creds = [os.getenv(k) for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USERNAME", "REDDIT_PASSWORD")]
                if not all(creds):
                    print(f"{platform}: skipped, REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USERNAME / REDDIT_PASSWORD aren't set")
                    continue
                post_id = post_reddit(text, *creds, os.getenv("REDDIT_SUBREDDIT"))
            else:
                token = os.getenv("THREADS_ACCESS_TOKEN")
                if not token:
                    print(f"{platform}: skipped, THREADS_ACCESS_TOKEN isn't set")
                    continue
                post_id = post_threads(text, image_path, token)
            print(f"{label}: published ({post_id})")
        except (PostError, requests.RequestException) as exc:
            # One platform failing shouldn't stop the other.
            print(f"{label}: FAILED: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
