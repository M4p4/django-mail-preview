from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from django_mail_preview.templatetags.mail_preview import ago, sender

NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    ("elapsed", "words"),
    [
        (timedelta(0), "just now"),
        (timedelta(seconds=59), "just now"),
        (timedelta(minutes=1), "1 minute ago"),
        (timedelta(minutes=4, seconds=59), "4 minutes ago"),
        (timedelta(minutes=59, seconds=59), "59 minutes ago"),
        (timedelta(hours=1), "1 hour ago"),
        (timedelta(hours=23, minutes=59), "23 hours ago"),
        (timedelta(days=1), "1 day ago"),
        (timedelta(days=6, hours=23), "6 days ago"),
        (timedelta(days=7), "1 week ago"),
        (timedelta(days=29), "4 weeks ago"),
        (timedelta(days=30), "1 month ago"),
        (timedelta(days=364), "12 months ago"),
        (timedelta(days=365), "1 year ago"),
        (timedelta(days=800), "2 years ago"),
    ],
)
def test_ago_says_the_elapsed_time_in_one_whole_unit(elapsed, words):
    assert ago(NOW - elapsed, NOW) == words


def test_ago_reads_a_time_in_the_future_as_just_now():
    assert ago(NOW + timedelta(minutes=5), NOW) == "just now"


def test_ago_measures_from_the_current_time_by_default():
    then = datetime.now(timezone.utc) - timedelta(hours=2)

    assert ago(then) == "2 hours ago"


@pytest.mark.parametrize(
    ("header", "shown"),
    [
        ("Scratch <orders@example.com>", "Scratch"),
        ('"Scratch Billing" <billing@example.com>', "Scratch Billing"),
        ("orders@example.com", "orders@example.com"),
        ("<orders@example.com>", "orders@example.com"),
        ("", ""),
    ],
)
def test_sender_is_the_name_or_else_the_address(header, shown):
    assert sender(header) == shown
