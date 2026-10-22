import re

from django.conf import settings
from django.core.exceptions import ValidationError

_SEPARATORS = re.compile(r"[\s\-().]")
_E164 = re.compile(r"^\+[1-9]\d{7,14}$")


def normalise_phone(raw: str) -> str:
    """Normalise to E.164. Local numbers (07..., 01...) get the default country code."""
    country = settings.DEFAULT_PHONE_COUNTRY_CODE
    value = _SEPARATORS.sub("", (raw or "").strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    if value.startswith("+"):
        pass
    elif value.startswith("0"):
        value = f"+{country}{value[1:]}"
    elif value.startswith(country):
        value = f"+{value}"
    else:
        raise ValidationError("Enter a valid phone number.")
    if not _E164.match(value):
        raise ValidationError("Enter a valid phone number.")
    return value
