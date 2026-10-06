"""Base class for a service's versioned client."""

from vexxhost_clientcore import http


class ServiceClient:
    """A versioned client: an http_client plus the service's managers.

    Subclasses set the class attributes and attach their managers in
    setup(http_client):

        class Client(ServiceClient):
            service_type = "budget"
            title = "Budget"
            endpoint_option = "--os-budget-endpoint"
            client_name = "vexxhost-budgetclient"
            client_version = __version__

            def setup(self, http_client):
                self.budgets = BudgetManager(http_client)

    Build it from a keystoneauth session, Client(session=..., region_name=...),
    or from openstack.config with Client.from_cloud_region(cloud_region),
    which honours the cloud's per-service settings.
    """

    service_type = None
    title = None
    api_prefix = "/v1"
    endpoint_option = None
    client_name = None
    client_version = None
    default_timeout = 60

    def __init__(
        self,
        session=None,
        endpoint_override=None,
        region_name=None,
        interface="public",
        timeout=None,
        service_type=None,
        service_name=None,
        http_client=None,
        **kwargs,
    ):
        if http_client is None:
            if session is None:
                raise TypeError("a session or an http_client is required")
            http_client = http.SessionClient(
                session,
                endpoint_override=endpoint_override,
                region_name=region_name,
                interface=interface,
                timeout=timeout or self.default_timeout,
                service_type=service_type or self.service_type,
                service_name=service_name,
                **self._identity(),
                **kwargs,
            )
        self.http_client = http_client
        self.setup(http_client)

    def setup(self, http_client):
        """Attach the service's managers."""

    @classmethod
    def _identity(cls):
        return {
            "title": cls.title,
            "api_prefix": cls.api_prefix,
            "endpoint_option": cls.endpoint_option,
            "client_name": cls.client_name,
            "client_version": cls.client_version,
        }

    @classmethod
    def from_cloud_region(cls, cloud_region, **kwargs):
        """Build the client from an openstack.config CloudRegion.

        The adapter gets the cloud's session and its settings for this
        service type: <service>_endpoint_override (or <service>_endpoint),
        _interface, _region_name, _connect_retries and _status_code_retries,
        from clouds.yaml, OS_* variables or CLI options.
        """
        timeout = cloud_region.config.get("api_timeout") or cls.default_timeout
        http_client = cloud_region.get_session_client(
            cls.service_type,
            constructor=http.SessionClient,
            timeout=float(timeout),
            **cls._identity(),
            **kwargs,
        )
        return cls(http_client=http_client)
