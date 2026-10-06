import argparse
from typing import Literal, TypedDict

import pytest
from keystoneauth1 import access, session, token_endpoint
from keystoneauth1.identity.access import AccessInfoPlugin
from typing_extensions import NotRequired

from vexxhost_clientcore import cli, codegen, exceptions, fields, osc
from vexxhost_clientcore.client import ServiceClient
from vexxhost_clientcore.http import SessionClient


def client(endpoint="https://api.example/v1", **kwargs):
    return SessionClient(
        session.Session(auth=token_endpoint.Token(endpoint, "test-token")),
        service_type="example",
        title="Example",
        endpoint_override=endpoint,
        **kwargs,
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.example",
        "https://api.example/",
        "https://api.example/v1",
        "https://api.example/v1/",
    ],
)
def test_endpoint_gets_the_version_prefix_once(requests_mock, endpoint):
    route = requests_mock.post("https://api.example/v1/things", json={})
    assert client(endpoint).post_json("things", {"a": []}) == {}
    assert route.last_request.headers["X-Auth-Token"] == "test-token"
    assert route.last_request.json() == {"a": []}


def test_identifies_the_client_in_user_agent(requests_mock):
    route = requests_mock.get("https://api.example/v1/things", json={})
    client(client_name="python-exampleclient", client_version="9.9").get_json(
        "things"
    )
    agent = route.last_request.headers["User-Agent"]
    assert agent.startswith("python-exampleclient/9.9 ")


def test_catalog_discovery_by_region_and_interface(requests_mock):
    auth_ref = access.create(
        auth_token="test-token",
        body={
            "token": {
                "expires_at": "2099-01-01T00:00:00Z",
                "methods": ["password"],
                "user": {"id": "u1", "name": "u", "domain": {"id": "d"}},
                "project": {"id": "p1", "name": "p", "domain": {"id": "d"}},
                "catalog": [
                    {
                        "type": "example",
                        "endpoints": [
                            {
                                "region": "other",
                                "interface": "internal",
                                "url": "https://wrong.example",
                            },
                            {
                                "region": "test",
                                "interface": "internal",
                                "url": "https://api.example",
                            },
                        ],
                    }
                ],
            }
        },
    )
    route = requests_mock.get("https://api.example/v1/things", json={})
    c = SessionClient(
        session.Session(auth=AccessInfoPlugin(auth_ref)),
        service_type="example",
        title="Example",
        region_name="test",
        interface="internal",
    )
    c.get_json("things")
    assert route.called


def test_missing_endpoint_names_the_override_option():
    auth_ref = access.create(
        auth_token="t",
        body={"token": {"expires_at": "2099-01-01T00:00:00Z", "catalog": []}},
    )
    c = SessionClient(
        session.Session(auth=AccessInfoPlugin(auth_ref)),
        service_type="example",
        title="Example",
        endpoint_option="--os-example-endpoint",
    )
    with pytest.raises(ValueError, match="--os-example-endpoint"):
        c.get_json("things")


@pytest.mark.parametrize(
    "endpoint",
    ["ftp://api.example", "https://u:p@api.example", "https://h/?q=1"],
)
def test_rejects_unsafe_endpoints(endpoint):
    with pytest.raises(ValueError, match="HTTP"):
        client(endpoint).get_json("things")


def test_path_segments_are_encoded(requests_mock):
    route = requests_mock.get("https://api.example/v1/things/a%2Fb", json={})
    c = client()
    c.get_json(c.path("things", "a/b"))
    assert route.called


def test_none_query_parameters_are_dropped(requests_mock):
    route = requests_mock.get("https://api.example/v1/things", json={})
    client().get_json("things", params={"a": "1", "b": None})
    assert route.last_request.qs == {"a": ["1"]}


def test_no_content(requests_mock):
    requests_mock.delete("https://api.example/v1/things/1", status_code=204)
    assert client().delete_json("things/1") is None


def test_accepted_without_body(requests_mock):
    requests_mock.post("https://api.example/v1/x", status_code=202)
    assert client().post_json("x", expect=(202,)) is None


@pytest.mark.parametrize(
    "status, kind",
    [
        (400, exceptions.BadRequest),
        (401, exceptions.Unauthorized),
        (403, exceptions.Forbidden),
        (404, exceptions.NotFound),
        (409, exceptions.Conflict),
        (422, exceptions.UnprocessableEntity),
        (429, exceptions.TooManyRequests),
        (503, exceptions.ServiceUnavailable),
        (504, exceptions.GatewayTimeout),
    ],
)
def test_problem_details(requests_mock, status, kind):
    requests_mock.get(
        "https://api.example/v1/things",
        status_code=status,
        json={
            "detail": "nope",
            "errors": [{"location": "body.start", "message": "invalid"}],
        },
        headers={"X-Request-ID": "request-123", "Retry-After": "5"},
    )
    with pytest.raises(kind) as e:
        client().get_json("things")
    assert isinstance(e.value, exceptions.ClientException)
    assert e.value.status_code == e.value.code == status
    assert e.value.request_id == "request-123"
    assert e.value.retry_after == "5"
    assert str(e.value).startswith(f"Example HTTP {status}: nope")
    assert "body.start: invalid" in str(e.value)


def test_redirect_not_followed(requests_mock):
    requests_mock.get(
        "https://api.example/v1/things",
        status_code=307,
        headers={"Location": "https://other.example/"},
    )
    with pytest.raises(exceptions.ClientException) as e:
        client().get_json("things")
    assert e.value.status_code == 307
    assert len(requests_mock.request_history) == 1


def test_non_json_error(requests_mock):
    requests_mock.get(
        "https://api.example/v1/things", status_code=502, text="<html>"
    )
    with pytest.raises(exceptions.ClientException, match="non-JSON"):
        client().get_json("things")


def test_non_object_success_is_rejected(requests_mock):
    requests_mock.get("https://api.example/v1/things", json=[1])
    with pytest.raises(exceptions.ClientException, match="invalid JSON"):
        client().get_json("things")


def test_plugin_options_and_environment(monkeypatch):
    monkeypatch.setenv("OS_COST_EXPLORER_ENDPOINT", "https://env.example")
    plugin = osc.Plugin("cost_explorer", "Cost Explorer", {"1": "x.Client"})
    args = plugin.build_option_parser(argparse.ArgumentParser()).parse_args([])
    assert args.os_cost_explorer_endpoint == "https://env.example"
    assert args.os_cost_explorer_api_version == "1"
    assert plugin.endpoint_option == "--os-cost-explorer-endpoint"


def test_versioned_factory():
    factory = osc.versioned_factory(
        "Example", {"1": "argparse.ArgumentParser"}
    )
    assert isinstance(factory("1", prog="x"), argparse.ArgumentParser)
    with pytest.raises(ValueError, match="Unsupported Example API version"):
        factory("2")


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-09-16", "2026-09-16T00:00:00Z"),
        ("2026-09-16T02:00:00+02:00", "2026-09-16T00:00:00Z"),
        ("2026-09-16T00:00:00Z", "2026-09-16T00:00:00Z"),
    ],
)
def test_timestamp(value, expected):
    assert cli.timestamp(value) == expected


def test_timestamp_requires_an_offset():
    with pytest.raises(argparse.ArgumentTypeError):
        cli.timestamp("2026-09-16T00:00:00")


def test_choices_read_literals():
    class Model(TypedDict):
        one: Literal["a", "b"]
        many: NotRequired[list[Literal["x", "y"]]]
        text: str

    assert fields.choices(Model, "one") == ["a", "b"]
    assert fields.choices(Model, "many") == ["x", "y"]
    with pytest.raises(TypeError):
        fields.choices(Model, "text")


def test_spec_version():
    text = "openapi: 3.0.3\ninfo:\n  title: X\n  version: 1966f47\npaths: {}\n"
    assert codegen.spec_version(text) == "1966f47"
    with pytest.raises(ValueError):
        codegen.spec_version("info:\n  title: X\npaths:\n  version: 1\n")


def test_errors_are_keystoneauth_http_errors(requests_mock):
    from keystoneauth1 import exceptions as ks

    requests_mock.get(
        "https://api.example/v1/things/1",
        status_code=404,
        json={"detail": "gone"},
        headers={
            "Content-Type": "application/problem+json",
            "X-OpenStack-Request-ID": "req-os",
        },
    )
    with pytest.raises(ks.NotFound) as e:
        client().get_json("things/1")
    assert isinstance(e.value, ks.HttpError)
    assert isinstance(e.value, exceptions.NotFound)
    assert e.value.http_status == 404
    assert e.value.details == "gone"
    assert e.value.request_id == "req-os"
    assert e.value.method == "GET"
    assert str(e.value) == "Example HTTP 404: gone (request ID: req-os)"


def test_unmapped_status_is_still_a_client_exception(requests_mock):
    requests_mock.get(
        "https://api.example/v1/things", status_code=418, json={}
    )
    with pytest.raises(exceptions.ClientException) as e:
        client().get_json("things")
    assert e.value.http_status == 418


class ExampleClient(ServiceClient):
    service_type = "example"
    title = "Example"
    endpoint_option = "--os-example-endpoint"
    client_name = "python-exampleclient"
    client_version = "1.2.3"

    def setup(self, http_client):
        self.api = http_client


def test_service_client_from_a_session(requests_mock):
    route = requests_mock.get("https://api.example/v1/things", json={})
    c = ExampleClient(
        session.Session(auth=token_endpoint.Token("https://x", "tok")),
        "https://api.example",
    )
    c.api.get_json("things")
    assert route.last_request.headers["User-Agent"].startswith(
        "python-exampleclient/1.2.3"
    )
    with pytest.raises(TypeError):
        ExampleClient()


def test_service_client_honours_clouds_yaml_settings(requests_mock):
    import openstack.config

    region = openstack.config.get_cloud_region(
        load_yaml_config=False,
        load_envvars=False,
        auth_type="admin_token",
        auth={"token": "tok", "endpoint": "https://unused.example"},
        example_endpoint_override="https://api.example/",
        example_status_code_retries=2,
        api_timeout=7,
    )
    route = requests_mock.get(
        "https://api.example/v1/things",
        [{"status_code": 503, "json": {}}, {"json": {"ok": True}}],
    )
    c = ExampleClient.from_cloud_region(region)
    assert c.api.timeout == 7
    assert c.api.get_json("things") == {"ok": True}
    assert route.call_count == 2
