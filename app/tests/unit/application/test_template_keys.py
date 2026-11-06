"""Ключі шаблонів — типізований набір, значення якого безпечно мапиться на файл."""

import re

from application.ports.templates import TemplateKey

AREA_AND_NAME = re.compile(r"^[a-z0-9_-]+/[a-z0-9_-]+$")


def test_every_key_is_an_area_and_a_name() -> None:
    assert [
        key.value for key in TemplateKey if not AREA_AND_NAME.fullmatch(key.value)
    ] == []


def test_login_page_keys_live_in_the_oauth_area() -> None:
    assert {key.value for key in TemplateKey} >= {
        "oauth/login",
        "oauth/login_form",
        "oauth/login_expired",
    }
