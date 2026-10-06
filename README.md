# vexxhost-clientcore

The code every VEXXHOST API client would otherwise copy: a Keystone transport,
RFC 9457 error handling, OpenStackClient plugin wiring, CLI argument parsers and
model generation. Each service keeps its own client package, version and
release cadence, and only service-specific code lives there.

| Client | Commands |
|---|---|
| [vexxhost-costexplorerclient](https://github.com/vexxhost/python-costexplorerclient) | `openstack cost report/forecast …` |
| [vexxhost-budgetclient](https://github.com/vexxhost/python-budgetclient) | `openstack budget …` |

It builds on keystoneauth1, openstack.config and osc-lib, the same libraries
every OpenStack client uses. [docs/naming.md](docs/naming.md) records how
clients are named and packaged, and which upstream code the core reuses.

```sh
pip install vexxhost-clientcore
```

## What is shared

| Module | Provides |
|---|---|
| `vexxhost_clientcore.http` | `SessionClient`, a `keystoneauth1` Adapter: catalog lookup by service type, region and interface; endpoint override with validation; the API version prefix appended once; percent-encoded path segments; redirects never followed, so the token never leaves the host; problem documents turned into exceptions; the client named in `User-Agent`. |
| `vexxhost_clientcore.client` | `ServiceClient`, the base of each service's versioned client. It is built from a keystoneauth session, or with `from_cloud_region()` from openstack.config, which applies the cloud's per-service settings (`<service>_endpoint_override`, `_interface`, `_region_name`, `_status_code_retries`, `api_timeout`). |
| `vexxhost_clientcore.exceptions` | `ClientException` carrying `status_code`, `problem`, `request_id` and `retry_after`, with `BadRequest`, `NotFound`, `Conflict`, `TooManyRequests`, `ServiceUnavailable` and others. Each is also the matching `keystoneauth1.exceptions` class, so `except keystoneauth1.exceptions.NotFound` works as it does for other OpenStack clients. |
| `vexxhost_clientcore.osc` | `Plugin`, the `make_client` and `build_option_parser` hooks OpenStackClient calls, giving every plugin `--os-<name>-endpoint` / `OS_<NAME>_ENDPOINT` and `--os-<name>-api-version`, and building the client from OSC's cloud region. `versioned_factory` builds the `Client("1", session=...)` entry point. |
| `vexxhost_clientcore.cli` | `timestamp` (dates and RFC 3339 times normalized to UTC, refusing times without an offset) and `bounded_int`. |
| `vexxhost_clientcore.fields` | `choices(Model, field)` reads the allowed values of a generated `Literal`, so CLI choices follow the API's schema. |
| `vexxhost_clientcore.codegen` | `python -m vexxhost_clientcore.codegen --service budget --spec <url> --output <models.py>` generates `TypedDict` models from the OpenAPI 3.0 schema a deployment serves, with a pinned generator and a `SPEC_VERSION` naming the server build. |
| `.github/workflows/python-client-ci.yml` | Reusable test workflow: Python 3.10/3.12/3.13, ruff, pytest, build, and a CLI smoke command. |
| `.github/workflows/release.yml` | Publishes this package to PyPI on a `v*` tag through trusted publishing. |
| `.github/workflows/regenerate-models.yml` | Reusable workflow that regenerates a client's models from its reference deployment and opens a pull request when they changed. |

Service clients keep what is specific to them: their resource managers, OSC
commands, generated models and tests.

## Writing a client

```python
# exampleclient/v1/client.py
from vexxhost_clientcore.client import ServiceClient


class Client(ServiceClient):
    service_type = "example"  # Keystone catalog type
    title = "Example"  # used in error messages
    endpoint_option = "--os-example-endpoint"
    client_name = "vexxhost-exampleclient"
    client_version = "0.1.0"

    def setup(self, http_client):
        self.things = ThingManager(http_client)


class ThingManager:
    def __init__(self, api):
        self.api = api

    def list(self):
        return self.api.get_json("things")["things"]

    def get(self, thing_id):
        return self.api.get_json(self.api.path("things", thing_id))
```

```python
# exampleclient/osc/plugin.py
from vexxhost_clientcore import osc

API_NAME = "example"
API_VERSION_OPTION = "os_example_api_version"
API_VERSIONS = {"1": "exampleclient.v1.client.Client"}

_plugin = osc.Plugin(API_NAME, "Example", API_VERSIONS)
make_client = _plugin.make_client
build_option_parser = _plugin.build_option_parser
```

Depend on `vexxhost-clientcore>=0.1,<0.2` and call the reusable workflows at a
release tag. Name the client as [docs/naming.md](docs/naming.md) describes.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]' ruff
pytest
ruff check . && ruff format --check .
```

Changes here reach every client, so keep the API small and backwards
compatible. To release, bump `version` in `pyproject.toml` and push a matching
`vX.Y.Z` tag; the release workflow publishes it to PyPI.
