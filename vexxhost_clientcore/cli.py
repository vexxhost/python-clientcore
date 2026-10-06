"""argparse helpers shared by the OpenStack CLI plugins."""

import argparse
import datetime


def timestamp(value):
    """Parse a CLI time as UTC RFC 3339.

    A bare YYYY-MM-DD means midnight UTC. Anything else must be an ISO 8601
    timestamp with an explicit offset, so a local time is never guessed.
    """
    try:
        if len(value) == 10:
            return (
                datetime.date.fromisoformat(value).isoformat() + "T00:00:00Z"
            )
        parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return (
            parsed.astimezone(datetime.timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except ValueError:
        raise argparse.ArgumentTypeError(
            "use YYYY-MM-DD (UTC) or an RFC3339 timestamp with a timezone"
        ) from None


def parse_timestamp(value):
    """Turn a value produced by timestamp() back into an aware datetime."""
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def bounded_int(low, high, what):
    """Return an argparse type accepting integers in [low, high]."""

    def parse(value):
        try:
            result = int(value)
            if not low <= result <= high:
                raise ValueError
            return result
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"{what} must be between {low} and {high}"
            ) from None

    return parse
