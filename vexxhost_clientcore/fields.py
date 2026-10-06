"""Read allowed values from the generated models, so the CLI cannot drift from the API."""

from typing_extensions import (
    Literal,
    NotRequired,
    Required,
    get_args,
    get_origin,
    get_type_hints,
)


def choices(model, field):
    """Return the values a model field allows, in schema order.

    The field must be a Literal, or a list of one, optionally NotRequired.
    """
    hint = get_type_hints(model, include_extras=True)[field]
    while get_origin(hint) in (NotRequired, Required):
        hint = get_args(hint)[0]
    if get_origin(hint) is list:
        hint = get_args(hint)[0]
    if get_origin(hint) is not Literal:
        raise TypeError(f"{model.__name__}.{field} is not an enumeration")
    return list(get_args(hint))
