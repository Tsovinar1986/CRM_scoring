import datetime as dt

import autopost
from autopost import START, linkedin_escape, load_posts, post_for


def test_facebook_goes_through_every_post_once_before_repeating():
    posts = load_posts()
    days = [START + dt.timedelta(days=i) for i in range(len(posts))]
    shown = [posts.index(post_for("facebook", d, posts)) for d in days]
    assert shown == list(range(len(posts)))
    assert post_for("facebook", START + dt.timedelta(days=len(posts)), posts) is posts[0]


def test_linkedin_posts_monday_wednesday_friday_in_order():
    posts = load_posts()
    week = [post_for("linkedin", START + dt.timedelta(days=i), posts) for i in range(14)]
    assert [d is not None for d in week[:7]] == [True, False, True, False, True, False, False]
    assert [posts.index(p) for p in week if p] == [0, 1, 2, 3, 4, 5]


def test_nothing_before_the_start_date():
    assert post_for("facebook", START - dt.timedelta(days=1), load_posts()) is None


def test_linkedin_reserved_characters_are_escaped():
    assert linkedin_escape("Hot (75+) #sales @team") == r"Hot \(75+\) \#sales \@team"


def test_every_post_has_text_and_its_image_exists():
    for post in load_posts():
        assert post["text"].strip()
        assert len(post["text"]) <= 500  # Threads' limit; the others allow more
        autopost.image_for(post)


def test_instagram_points_to_the_bio_link_and_always_has_a_picture():
    posts = load_posts()
    text_only = next(p for p in posts if not p.get("image"))
    assert "link in bio" in autopost.text_for("instagram", text_only)
    assert "https://" not in autopost.text_for("instagram", text_only)
    assert (autopost.HERE / autopost.INSTAGRAM_DEFAULT_IMAGE).is_file()
