"""Small persistent app state (onboarding completion, CLI path override) via QSettings."""

from PySide6.QtCore import QSettings

_ORG = "AI_Mabinogi"
_APP = "MabiNobi"


def settings() -> QSettings:
    return QSettings(_ORG, _APP)


def is_onboarding_complete() -> bool:
    return settings().value("onboarding/complete", False, type=bool)


def set_onboarding_complete(value: bool = True) -> None:
    settings().setValue("onboarding/complete", value)
