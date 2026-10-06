"""Exceptions for APIs that report failures as RFC 9457 problem documents.

Every class here is also the matching keystoneauth1 HTTP exception, so code
written for other OpenStack clients keeps working:

    try:
        client.budgets.get(budget_id)
    except keystoneauth1.exceptions.NotFound:
        ...

keystoneauth1's own parser does not read problem documents (it expects
{"error": {...}} bodies served as application/json), so the message, the
field errors and the problem itself are taken from the body here.
"""

from keystoneauth1.exceptions import http as ks_http


class ClientException(ks_http.HttpError):
    """An API failure, carrying the HTTP status, problem and request ID.

    Attributes: status_code (also code and http_status), problem (the
    decoded problem document), details (its "detail" text), request_id,
    retry_after (the Retry-After header as sent), service, method and url.
    """

    def __init__(
        self,
        status_code,
        problem,
        request_id=None,
        retry_after=None,
        service=None,
        response=None,
        method=None,
        url=None,
    ):
        detail = problem.get("detail") or problem.get("title")
        super().__init__(
            message=detail or "Request failed",
            details=problem.get("detail"),
            response=response,
            request_id=request_id,
            url=url,
            method=method,
            http_status=status_code,
        )
        # keystoneauth replaces message with its own formatted text.
        self.message = detail or "Request failed"
        self.status_code = status_code
        self.code = status_code
        self.problem = problem
        self.retry_after = retry_after
        self.service = service

        prefix = f"{service} HTTP" if service else "HTTP"
        text = f"{prefix} {status_code}: {self.message}"
        errors = problem.get("errors", [])
        if isinstance(errors, list):
            for error in errors:
                if isinstance(error, dict):
                    location = error.get("location", "request")
                    message = error.get("message", "invalid value")
                    text += f"; {location}: {message}"
        if request_id:
            text += f" (request ID: {request_id})"
        if retry_after:
            text += f"; retry after {retry_after} seconds"
        self.args = (text,)

    def __str__(self):
        return self.args[0]


class BadRequest(ClientException, ks_http.BadRequest):
    pass


class Unauthorized(ClientException, ks_http.Unauthorized):
    pass


class Forbidden(ClientException, ks_http.Forbidden):
    pass


class NotFound(ClientException, ks_http.NotFound):
    pass


class MethodNotAllowed(ClientException, ks_http.MethodNotAllowed):
    pass


class Conflict(ClientException, ks_http.Conflict):
    """Raised for 409, such as an update made against a stale revision."""


class PreconditionFailed(ClientException, ks_http.PreconditionFailed):
    pass


class RequestEntityTooLarge(ClientException, ks_http.RequestEntityTooLarge):
    pass


class UnprocessableEntity(ClientException, ks_http.UnprocessableEntity):
    pass


class TooManyRequests(ClientException, ks_http.TooManyRequests):
    pass


class InternalServerError(ClientException, ks_http.InternalServerError):
    pass


class BadGateway(ClientException, ks_http.BadGateway):
    pass


class ServiceUnavailable(ClientException, ks_http.ServiceUnavailable):
    pass


class GatewayTimeout(ClientException, ks_http.GatewayTimeout):
    pass


_BY_STATUS = {
    cls.http_status: cls
    for cls in (
        BadRequest,
        Unauthorized,
        Forbidden,
        NotFound,
        MethodNotAllowed,
        Conflict,
        PreconditionFailed,
        RequestEntityTooLarge,
        UnprocessableEntity,
        TooManyRequests,
        InternalServerError,
        BadGateway,
        ServiceUnavailable,
        GatewayTimeout,
    )
}


def request_id(response):
    """The request ID, from the OpenStack header or the generic one."""
    return response.headers.get(
        "X-OpenStack-Request-ID"
    ) or response.headers.get("X-Request-ID")


def from_response(response, problem, service=None):
    """Build the exception matching a response's status code."""
    exception_class = _BY_STATUS.get(response.status_code, ClientException)
    request = getattr(response, "request", None)
    return exception_class(
        response.status_code,
        problem,
        request_id(response),
        response.headers.get("Retry-After"),
        service,
        response=response,
        method=getattr(request, "method", None),
        url=getattr(request, "url", None),
    )
