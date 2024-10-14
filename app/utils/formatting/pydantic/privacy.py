from enum import Enum


class PrivacyOptions(str, Enum):
    public = "public"
    private = "private"
    local = "local"