"""OpenStackClient extension hooks shared by the service plugins.

OpenStackClient loads each plugin module from the openstack.cli.extension
entry point and reads API_NAME, API_VERSION_OPTION, API_VERSIONS,
make_client and build_option_parser from it. A plugin module defines the
constants and takes the two functions from a Plugin:

    API_NAME = "budget"
    API_VERSION_OPTION = "os_budget_api_version"
    API_VERSIONS = {"1": "budgetclient.v1.client.Client"}

    _plugin = osc.Plugin(API_NAME, "Budget", API_VERSIONS)
    make_client = _plugin.make_client
    build_option_parser = _plugin.build_option_parser

That gives every plugin --os-<name>-api-version and --os-<name>-endpoint
options and the matching OS_<NAME>_API_VERSION and OS_<NAME>_ENDPOINT
variables. The client is built by openstack.config from the same cloud
region OSC uses, so per-service clouds.yaml settings such as
budget_endpoint_override, budget_interface or budget_status_code_retries
apply as they do to every built-in service. The client class must be a
vexxhost_clientcore.client.ServiceClient.
"""

import importlib
import os

from osc_lib import utils


class Plugin:
    def __init__(self, api_name, title, api_versions, default_version="1"):
        self.api_name = api_name
        self.title = title
        self.api_versions = api_versions
        self.default_version = default_version
        self.option = api_name.replace("_", "-")
        self.env = "OS_" + api_name.upper()

    @property
    def endpoint_option(self):
        return f"--os-{self.option}-endpoint"

    def make_client(self, instance):
        client_class = utils.get_client_class(
            self.api_name,
            instance._api_version[self.api_name],
            self.api_versions,
        )
        return client_class.from_cloud_region(instance._cli_options)

    def build_option_parser(self, parser):
        parser.add_argument(
            f"--os-{self.option}-api-version",
            choices=sorted(self.api_versions),
            default=os.environ.get(
                f"{self.env}_API_VERSION", self.default_version
            ),
            help=f"{self.title} API version ({self.env}_API_VERSION)",
        )
        parser.add_argument(
            self.endpoint_option,
            default=os.environ.get(f"{self.env}_ENDPOINT"),
            help=(
                f"{self.title} base URL ({self.env}_ENDPOINT); otherwise "
                "use the service catalog"
            ),
        )
        return parser


def versioned_factory(title, api_versions):
    """Return a Client(version, **kwargs) function, as OpenStack clients have.

    api_versions maps a version string to the dotted path of its client class.
    """

    def Client(version="1", **kwargs):
        try:
            path = api_versions[str(version)]
        except KeyError:
            raise ValueError(
                f"Unsupported {title} API version: {version} "
                f"(supported: {', '.join(sorted(api_versions))})"
            ) from None
        module, _, name = path.rpartition(".")
        return getattr(importlib.import_module(module), name)(**kwargs)

    return Client
