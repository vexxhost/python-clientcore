"""A keystoneauth adapter for JSON APIs that answer errors with problem documents.

Each service client subclasses SessionClient, or constructs it directly, and
supplies its catalog service type and a human-readable title. Catalog lookup,
region and interface selection and token handling come from keystoneauth.
"""

from urllib.parse import quote, urlsplit

from keystoneauth1 import adapter
from keystoneauth1 import exceptions as ks_exceptions

from vexxhost_clientcore import exceptions

ACCEPT = "application/json, application/problem+json"

# openstack.config's CloudRegion.get_session_client() passes these to the
# adapter it builds. Our services serve no version discovery document, so
# the version arguments are dropped and api_prefix is used instead; the rest
# configure openstacksdk's Proxy metrics, which a plain Adapter lacks.
_IGNORED = (
    "version",
    "min_version",
    "max_version",
    "default_microversion",
    "statsd_client",
    "statsd_prefix",
    "prometheus_counter",
    "prometheus_histogram",
    "influxdb_config",
    "influxdb_client",
)


class SessionClient(adapter.Adapter):
    """Send authenticated JSON requests to one service's versioned API.

    The endpoint comes from endpoint_override when given, and otherwise from
    the Keystone catalog entry for service_type. api_prefix (for example
    "/v1") is appended unless the endpoint already ends with it, so both
    "https://host" and "https://host/v1" work as catalog URLs or overrides.
    """

    def __init__(
        self,
        session,
        service_type,
        title,
        api_prefix="/v1",
        endpoint_override=None,
        region_name=None,
        interface="public",
        timeout=60,
        service_name=None,
        endpoint_option=None,
        client_name=None,
        client_version=None,
        **kwargs,
    ):
        for name in _IGNORED:
            kwargs.pop(name, None)
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        super().__init__(
            session=session,
            service_type=service_type,
            service_name=service_name,
            endpoint_override=endpoint_override,
            region_name=region_name,
            interface=interface,
            client_name=client_name,
            client_version=client_version,
            **kwargs,
        )
        self.title = title
        self.api_prefix = "/" + api_prefix.strip("/") if api_prefix else ""
        self.timeout = timeout
        self.endpoint_option = endpoint_option

    def api_endpoint(self):
        """Return the validated base URL, ending with api_prefix."""
        try:
            endpoint = self.get_endpoint()
        except ks_exceptions.CatalogException:
            endpoint = None
        if not endpoint:
            hint = (
                f"; set {self.endpoint_option}" if self.endpoint_option else ""
            )
            raise ValueError(
                f"No {self.title} endpoint found in the service catalog "
                f"for service type {self.service_type!r}{hint}"
            )
        parts = urlsplit(endpoint)
        if (
            parts.scheme not in ("http", "https")
            or not parts.netloc
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
        ):
            raise ValueError(
                f"{self.title} endpoint must be an HTTP(S) URL without "
                "credentials, query or fragment"
            )
        endpoint = endpoint.rstrip("/")
        if self.api_prefix and not endpoint.endswith(self.api_prefix):
            endpoint += self.api_prefix
        return endpoint

    @staticmethod
    def path(*segments):
        """Join path segments, percent-encoding each one.

        Use this for identifiers that come from users, so "a/b" cannot reach
        a different resource.
        """
        return "/".join(quote(str(s), safe="") for s in segments)

    def json_request(
        self, method, path, *, json=None, params=None, expect=(200,)
    ):
        """Send a request and return the decoded JSON object.

        path is relative to the versioned endpoint. Query parameters whose
        value is None are dropped. A status outside expect raises the
        matching ClientException subclass. A 204, or an expected response
        without a body, returns None. Redirects are never followed, so the
        token is never sent to another host.
        """
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        response = self.request(
            self.api_endpoint() + "/" + path.lstrip("/"),
            method,
            json=json,
            params=params or None,
            headers={"Accept": ACCEPT},
            authenticated=True,
            raise_exc=False,
            redirect=False,
            timeout=self.timeout,
        )
        try:
            data = response.json() if response.content else None
        except ValueError:
            data = None
            invalid = True
        else:
            invalid = False
        if response.status_code not in expect:
            problem = (
                data
                if isinstance(data, dict)
                else {"detail": "Server returned a non-JSON error"}
            )
            raise exceptions.from_response(response, problem, self.title)
        if response.status_code == 204 or (data is None and not invalid):
            return None
        if not isinstance(data, dict):
            raise exceptions.ClientException(
                response.status_code,
                {"detail": "Server returned an invalid JSON response"},
                exceptions.request_id(response),
                service=self.title,
                response=response,
            )
        return data

    def get_json(self, path, params=None):
        return self.json_request("GET", path, params=params)

    def post_json(self, path, body=None, expect=(200,)):
        return self.json_request("POST", path, json=body, expect=expect)

    def put_json(self, path, body):
        return self.json_request("PUT", path, json=body)

    def delete_json(self, path):
        return self.json_request("DELETE", path, expect=(204,))
