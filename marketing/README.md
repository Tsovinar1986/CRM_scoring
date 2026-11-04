# Social posts

`.github/workflows/autopost.yml` runs every day at 10:00 Yerevan time and posts
the next post from [posts.json](posts.json) through each platform's official API:

| Platform | Days | Account |
|---|---|---|
| Facebook | every day | your product's Facebook **Page** |
| Threads | every day | @tina19860810 |
| LinkedIn | Mon, Wed, Fri | your personal profile |
| Instagram | Tue, Thu, Sat | @tina19860810 as a **Professional** account |

Each platform goes through the 14 posts in order, then starts over, so the same
post comes back after 2 weeks (Facebook, Threads) or about 4½ weeks
(LinkedIn, Instagram). The first posts go out on Monday 9 November 2026.

A platform without its secrets is skipped, so you can connect them one at a time.
Nothing is posted until at least one is connected.

## Change the posts

Edit [posts.json](posts.json) on GitHub. Each post has `text` and optionally an
`image` from [images/](images). To give one platform different words, add e.g.
`"linkedin": "…"` next to `text`. Keep every text under 500 characters (Threads'
limit). Instagram captions get "crmscoring.com (link in bio)" in place of the
link, and posts without a picture use the poster there.

Check what goes out on a given day without posting:

```
python marketing/autopost.py --dry-run --date 2026-11-09
```

## Connect the accounts

Secrets go in GitHub: **repository → Settings → Secrets and variables →
Actions → New repository secret**. Never put them in a file.

### LinkedIn (personal profile) → `LINKEDIN_ACCESS_TOKEN`
1. At [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps), **Create app**.
   LinkedIn asks for a Company Page to link the app to; any Page you admin works.
2. **Products** tab: add **Sign In with LinkedIn using OpenID Connect** and **Share on LinkedIn**.
3. **Auth** tab: add `http://localhost:8765/callback` under *Authorized redirect URLs*.
4. On your computer: `python marketing/linkedin_token.py`. Paste the Client ID and
   Secret from the Auth tab, sign in, and save the printed token as `LINKEDIN_ACCESS_TOKEN`.
5. **Every 60 days** the token expires: run step 4 again and replace the secret.

### Facebook Page and Instagram → `FACEBOOK_PAGE_ID`, `FACEBOOK_PAGE_TOKEN`, `INSTAGRAM_ACCOUNT_ID`
The API can only post to a **Page**, not a personal profile.
1. If you don't have one, create a Page for CRM Scoring: [facebook.com/pages/create](https://www.facebook.com/pages/create).
2. Instagram app → Settings → **Account type and tools → Switch to professional account**,
   then link it to the Page (Page settings → **Linked accounts → Instagram**).
3. At [developers.facebook.com/apps](https://developers.facebook.com/apps), create an app
   (type **Business**) and add the **Facebook Login for Business** and **Instagram** use cases.
4. Open the [Graph API Explorer](https://developers.facebook.com/tools/explorer), pick your app,
   add the permissions `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`,
   `instagram_basic`, `instagram_content_publish`, click **Generate Access Token** and tick your Page.
5. On your computer: `python marketing/facebook_token.py`. Paste the App ID and App Secret
   (app **Settings → Basic**) and the Explorer token. Save the three printed values as secrets.
   This Page token doesn't expire.

### Threads → `THREADS_ACCESS_TOKEN`
1. In the same Meta app, add the **Access the Threads API** use case with
   `threads_basic` and `threads_content_publish`.
2. Under that use case's **Settings**, add @tina19860810 as a **Threads Tester**, then accept it
   in Threads: Settings → Account → **Website permissions → Invites**.
3. Generate a token there, then run `python marketing/threads_token.py` with the
   **Threads App Secret** to get a 60-day token. Save it as `THREADS_ACCESS_TOKEN`.
4. **Every 60 days**: generate a fresh one and replace the secret.

## Try it

**Actions → Social posts → Run workflow**. With *Only show what would be posted* ticked
(the default), it just prints today's posts. Untick it to post now.

If a token has expired, the run fails and GitHub emails you. The message names the platform.
GitHub turns off scheduled workflows after 60 days with no commits to the repository;
re-enable it on the Actions tab if that happens.
