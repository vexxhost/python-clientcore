# Naming and packaging VEXXHOST clients

Decided October 2026, for clients of VEXXHOST's own services (budget,
cost-explorer, inference, and whatever comes next).

## Decision

One client package per service, on a shared core, with the `vexxhost-` prefix on
every PyPI distribution:

| What | Pattern | Budget example | Core |
|---|---|---|---|
| PyPI distribution | `vexxhost-<service>client` | `vexxhost-budgetclient` | `vexxhost-clientcore` |
| Import package | `<service>client` | `budgetclient` | `vexxhost_clientcore` |
| GitHub repository | `vexxhost/python-<service>client` | `python-budgetclient` | `python-clientcore` |
| OSC extension (`openstack.cli.extension`) | the service name, underscored | `budget` | — |
| OSC commands (`openstack.<api>.v1`) | `<service> <noun> <verb>`, entry names `<service>_<noun>_<verb>` | `openstack budget channel create` | — |
| Keystone catalog service type | the service name, hyphenated | `budget`, `cost-explorer` | — |
| `clouds.yaml` / env settings | derived from the service type by openstack.config | `budget_endpoint_override`, `OS_BUDGET_ENDPOINT` | — |

Clients depend on `vexxhost-clientcore` and on upstream `keystoneauth1` and
`osc-lib`, and nothing else.

## Why

**The prefix is on the distribution because PyPI is a global namespace.**
`python-budgetclient` and `budgetclient` were free, but they are generic words
for a VEXXHOST-only service. The prefix says who publishes the package, which is
the convention hyperscalers use: `google-cloud-*`, `azure-mgmt-*`, `ibm-*`,
`stackit-*`. It also avoids squatting names another project could
reasonably want.

**Import names stay `<service>client` because that is how OpenStack clients
look** (`python-novaclient` installs `novaclient`; Catalyst Cloud's
`python-distilclient` installs `distilclient`). Distribution and import names
commonly differ, and the existing `costexplorerclient` and `inferenceclient`
imports keep working. The core's import carries the prefix because
`clientcore` alone is too generic to put in site-packages.

**One package per service, not one package for the whole cloud.** Open Telekom
Cloud ships all of its roughly 35 services in one `otcextensions` package. That
gives one install, but every service then releases together, and a broken
plugin breaks the whole CLI. Our services are deployed and versioned
independently, so their clients should be as well. The shared core removes the
duplication that would otherwise push towards a single package.

**No namespace packages** (`vexxhost.budget`). Google, Azure and STACKIT use
them, but they break silently when any distribution ships a stray
`vexxhost/__init__.py`, and nothing in OpenStack works that way.

**Repositories keep the `python-` prefix**, matching the existing client repos
and the upstream habit (otcextensions also lives in `python-otcextensions`).

## What the core reuses from upstream, and what it does not

The core sits on the same libraries every OpenStack client uses. Before it was
published, upstream libraries were checked for code it could reuse instead:

- **keystoneauth1:** sessions, catalog lookup and retries. Our exceptions
  subclass its HTTP exceptions, so `except keystoneauth1.exceptions.NotFound`
  catches errors from our clients too. Its own error parser is not used,
  because it does not read RFC 9457 problem documents.
- **openstack.config** (openstacksdk): the OSC plugins build their adapter with
  `CloudRegion.get_session_client()`, so per-service `clouds.yaml` settings
  apply exactly as they do to built-in services.
- **osc-lib:** the plugin contract, `get_client_class`, output formatting
  columns, project lookup (`cli.identity.find_project`) and `is_uuid_like`.
- **Not used:** osc-lib's `BaseAPI`, which is deprecated in favour of
  openstacksdk, and `MultiKeyValueAction`, which merges repeated keys into
  one, so options such as budget's repeatable `channel=` would lose values.
- **openstacksdk `Proxy`/`Resource`: not used yet.** A `Proxy` only works
  inside an SDK `Connection`, so library callers who hold a plain keystoneauth
  session could no longer use the clients. `Resource` would also mean
  describing every field by hand, alongside the models generated from the
  served schema. Every upstream service client (designate, magnum, ironic,
  osc-placement) has its own keystoneauth adapter layer, which is what this
  core shares between our clients.
  If SDK users (Ansible, `openstack.connect()`) need `conn.budget`, add a
  `vendor_hook` to the profile at
  `https://vexxhost.com/.well-known/openstack/api`, which openstacksdk already
  loads for the `vexxhost` cloud. otcextensions registers its services the same
  way.

## Later

A metapackage such as `vexxhost-openstackclient`, depending on
`python-openstackclient` and every VEXXHOST client, would give customers one
install, as `cleura-openstackclient` does. It is worth adding once the
service clients are on PyPI.
