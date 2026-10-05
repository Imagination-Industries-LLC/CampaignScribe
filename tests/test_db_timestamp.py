import re
import warnings

from app.data import db


def test_utc_now_iso_format_is_naive_seconds():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        value = db._utc_now_iso()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", value)
