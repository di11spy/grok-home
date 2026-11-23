# Vendored PyCarLink

This folder is a vendored copy of [PyCarLink](https://github.com/angel12/PyCarLink)
by angel12, MIT licensed. The license is in `LICENSE`.

Pinned upstream commit: `a11d551491fc8e6025c7d68314cc7666d040cbac`
(merge of pull request #12, response validation).

PyCarLink is not published on PyPI. It is included here so Home Assistant can
install CL6 from this one repository, including a private HACS install.

## Changes from upstream

The default constructor still logs in, selects the first vehicle, and fetches
status. These additions are for Home Assistant:

- `asset_id` selects a vehicle by id instead of always using the first one.
- `load_status=False` logs in without picking a vehicle, so setup can list cars.
- `list_assets()` and `select_asset()` read the account's vehicles.
- `submit_command()` posts one command and returns its id. It does not sleep
  or poll. Home Assistant polls with `command_status()` between async sleeps.
- `relogin()` refreshes the API key and does not send a vehicle command.
- `__repr__` hides the email, password, API key, and headers.
- `start_engine`, `stop_engine`, `lock_doors`, and `unlock_doors` still poll
  for about 20 seconds. Home Assistant does not call those methods.

The M2M command names are unchanged, including `DoorUnLock`. A polling result
of `Command Timed Out` still means the outcome is unknown. Nothing here retries
a command.
