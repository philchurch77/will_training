"""Login throttling.

This exists because the app is published to the internet. The old
session-based lockout was bypassed by throwing away a cookie, which is fine on
a home network and useless on a public URL - so these tests pin the behaviour
that actually matters: clearing cookies must not buy you more guesses.
"""

import pytest
from django.core.cache import cache
from django.urls import reverse

pytestmark = pytest.mark.django_db

LOGIN = "training:login"


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def wrong(client, times=1):
    for _ in range(times):
        response = client.post(reverse(LOGIN), {"pin": "0000"})
    return response


class TestLockout:
    def test_a_few_wrong_tries_just_say_wrong(self, client, will, settings):
        body = wrong(client, settings.PIN_MAX_ATTEMPTS - 1).content.decode()
        assert "Wrong code" in body
        assert "Too many" not in body

    def test_too_many_wrong_tries_locks_out(self, client, will, settings):
        body = wrong(client, settings.PIN_MAX_ATTEMPTS).content.decode()
        assert "Too many tries" in body

    def test_the_right_code_is_refused_while_locked(self, client, will, settings):
        wrong(client, settings.PIN_MAX_ATTEMPTS)
        response = client.post(reverse(LOGIN), {"pin": "1234"})
        assert response.status_code == 200
        assert "Too many tries" in response.content.decode()

    def test_clearing_cookies_does_not_reset_the_lockout(self, client, will, settings):
        """The whole point of moving the counter out of the session."""
        wrong(client, settings.PIN_MAX_ATTEMPTS)

        client.cookies.clear()
        response = client.post(reverse(LOGIN), {"pin": "1234"})
        assert "Too many tries" in response.content.decode()

    def test_a_different_address_is_not_punished(self, client, will, settings):
        wrong(client, settings.PIN_MAX_ATTEMPTS)

        response = client.post(
            reverse(LOGIN), {"pin": "1234"}, REMOTE_ADDR="10.0.0.99"
        )
        assert response.status_code == 302  # straight in

    def test_the_right_code_still_works_before_any_lockout(self, client, will):
        wrong(client, 2)
        response = client.post(reverse(LOGIN), {"pin": "1234"})
        assert response.status_code == 302

    def test_a_success_wipes_the_counter(self, client, will, settings):
        from training import throttle

        wrong(client, settings.PIN_MAX_ATTEMPTS - 1)
        client.post(reverse(LOGIN), {"pin": "1234"})
        client.post(reverse("training:logout"))

        # A clean slate: one more wrong guess must not trip the lockout.
        body = wrong(client, 1).content.decode()
        assert "Wrong code" in body
        assert "Too many" not in body


class TestEscalation:
    def test_each_lockout_is_longer_than_the_last(self, client, will, settings, rf):
        from training import throttle

        request = rf.post("/login/")
        request.META["REMOTE_ADDR"] = "10.1.2.3"

        waits = []
        for _ in range(3):
            for _ in range(settings.PIN_MAX_ATTEMPTS - 1):
                assert throttle.record_failure(request) == 0
            waits.append(throttle.record_failure(request))
            cache.delete(f"pin-locked-until:{'10.1.2.3'}")  # skip the wait

        assert waits == sorted(waits)
        assert waits[1] > waits[0]

    def test_lockouts_are_capped(self, client, will, settings, rf):
        from training import throttle

        request = rf.post("/login/")
        request.META["REMOTE_ADDR"] = "10.1.2.4"

        wait = 0
        for _ in range(12):
            for _ in range(settings.PIN_MAX_ATTEMPTS):
                wait = throttle.record_failure(request) or wait
            cache.delete("pin-locked-until:10.1.2.4")

        assert wait <= settings.PIN_MAX_LOCKOUT_SECONDS


class TestGlobalCap:
    def test_enough_failures_from_everywhere_locks_everyone(
        self, client, will, settings, rf
    ):
        """Rotating IPs should not make the code brute-forceable."""
        from training import throttle

        for i in range(settings.PIN_GLOBAL_MAX_ATTEMPTS):
            request = rf.post("/login/")
            request.META["REMOTE_ADDR"] = f"10.2.{i // 250}.{i % 250}"
            throttle.record_failure(request)

        # A brand new address is now refused too.
        response = client.post(
            reverse(LOGIN), {"pin": "1234"}, REMOTE_ADDR="10.9.9.9"
        )
        assert response.status_code == 200
        assert "Too many tries" in response.content.decode()


class TestProxyHandling:
    def test_the_forwarded_header_is_ignored_without_a_proxy(self, rf, settings):
        """Otherwise anyone could spoof it and dodge the throttle entirely."""
        from training import throttle

        settings.SECURE_PROXY_SSL_HEADER = None
        request = rf.post("/login/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4"

        assert throttle.client_ip(request) == "10.0.0.1"

    def test_the_forwarded_header_is_used_behind_a_proxy(self, rf, settings):
        from training import throttle

        settings.SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
        request = rf.post("/login/")
        request.META["REMOTE_ADDR"] = "10.0.0.1"
        request.META["HTTP_X_FORWARDED_FOR"] = "1.2.3.4, 10.0.0.1"

        assert throttle.client_ip(request) == "1.2.3.4"


class TestWording:
    def test_short_waits_are_in_seconds(self):
        from training import throttle

        assert "60 seconds" in throttle.describe(60)

    def test_long_waits_are_in_minutes(self):
        from training import throttle

        assert "5 minutes" in throttle.describe(300)
