# ipx800v4 component for Home Assistant

![GitHub release (with filter)](https://img.shields.io/github/v/release/aohzan/ipx800) ![GitHub](https://img.shields.io/github/license/aohzan/ipx800) [![Donate](https://img.shields.io/badge/$-support-ff69b4.svg?style=flat)](https://github.com/sponsors/Aohzan) [![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)

This a _custom component_ for [Home Assistant](https://www.home-assistant.io/).
The `ipx800v4` integration allows you to get information and control the [IPX800 v4 and its extensions](http://gce-electronics.com/).

![README en français](README.fr.md) :fr:

## Installation

### HACS

HACS > Integrations > Explore & Add Repositories > GCE IPX800 V4 > Install this repository

### Manually

Copy `custom_components/ipx800` in `config/custom_components` of your Home Assistant (you must have `*.py` files in `config/custom_components/ipx800v4`).
Add the `ipx800v4` entry in your `configuration.yml` (see example below).

Setup requires a successful full read. If the IPX800 cannot be reached, Home Assistant retries setup automatically; entities are not made available without valid data.

### Communication failures

After a successful read, the first two consecutive communication failures retain the last valid states. Each schedules another read after `min(scan_interval, 15)` seconds, using the effective interval from integration options or YAML. The third failure makes coordinator-backed entities unavailable and restores normal polling. With `scan_interval: 300`, the two retries are about 15 seconds apart, excluding request durations; with `scan_interval: 10`, they remain 10 seconds apart.

A successful full read resets recovery immediately, including reads requested through the refresh-push endpoint (still batched for 0.5 seconds) or a manual refresh. Cached states do not count as successful acquisitions. Authentication/configuration errors are not tolerated this way, and commands are not replayed by this recovery mechanism. No additional YAML option is needed.

### Temporarily missing fields

If a successful response omits a previously valid input/output or extension field (or supplies an invalid value), only that field enters recovery. Its last value is retained for at most two further successful reads or `2 × min(scan_interval, 15)` seconds from the first detected omission, whichever comes first. This is at most 30 seconds with `scan_interval: 300`. All missing fields share the communication recovery scheduler; HTTP failures do not count as successful omissions. Expiration is published even if no further read succeeds.

Only entities depending on an expired field become unavailable; healthy fields keep updating. Fields never received remain unavailable. Normal polling resumes after recovery ends, including for a permanently absent extension. A valid read or direct push restores the supplied fields immediately, without renewing unrelated fields. This policy covers the configured input/output and extension entities; XML diagnostics keep their separate behavior below.

## Controller diagnostics

The general IPX800 device automatically contains three diagnostic entities:

- **Last boot**: a timestamp calculated from the `wuc0` uptime in seconds, using Home Assistant's clock. It does not depend on the IPX clock being correct. The timestamp is kept stable within five seconds of polling jitter and recalculated after an uptime reset or a larger discrepancy.
- **Load**: the raw `lps0` value in loops per second. Lower values indicate higher load; this is **not a CPU percentage**.
- **Clock in sync**: on when the IPX date and time differ from Home Assistant's configured local time by no more than 60 seconds. The signed difference is available as `clock_offset_seconds`. Configure both devices for the same time zone. This checks the actual clock, not NTP configuration.

The MAC address is added to the general device's network connections.

These values use `/user/status.xml` once at setup, then on a separate timer following the YAML `scan_interval` (or its integration-options override). Pushes, I/O commands and read-recovery attempts do not refresh diagnostics or postpone their timer. XML failures or slow responses do not delay ongoing I/O updates. No additional YAML device entries are needed.

### Credentials for controller information

If the IPX web interface is password-protected, **set both `username` and `password` to the credentials you use to open that interface in your browser**. The JSON API key alone cannot authenticate requests to `/user/status.xml`, which supplies the boot time, load, clock and MAC information.

| Parameter | Purpose |
| --- | --- |
| `api_key` | Access to the IPX JSON API for I/O data and API commands. |
| `username` / `password` | IPX web interface credentials, required for protected XML diagnostics; also used for X-PWM control. |
| `push_password` | Separate password chosen for IPX-to-Home Assistant pushes. It does not authenticate XML diagnostics. |

Add the credentials to your **existing IPX gateway entry**, at the same indentation as `host` and `api_key`, not under `devices`:

```yaml
ipx800v4:
  - name: IPX800
    host: "192.168.1.240"
    api_key: "your_ipx_api_key"
    username: "your_ipx_web_username"
    password: "your_ipx_web_password"
    scan_interval: 300
    devices: []  # Keep your existing device list here
```

Keep your existing gateway name and device list. After editing `configuration.yaml` (or its included file), **restart Home Assistant** to import the updated YAML configuration. The diagnostic entities are created automatically on the general IPX device; do not add them under `devices`.

With `scan_interval: 300`, diagnostics are read at setup, then approximately every five minutes. An interval set in the integration options takes precedence over YAML. Pushes do not trigger XML reads.

### Missing or unavailable information

- If the XML endpoint is accessible without authentication, `username` and `password` can be omitted.
- If XML access fails, the three diagnostic entities become unavailable without invalidating I/O data. The next diagnostics cycle retries; with no username configured, requests stop after five consecutive failures until the integration is reloaded or Home Assistant is restarted. A successful XML read resets that counter.
- With a username configured, failed XML requests continue to be retried at the diagnostics polling interval. Check the web credentials if the information stays unavailable.
- An absent or invalid XML field makes only its corresponding diagnostic entity unavailable. The MAC address is added to the device information when a valid value is received.

If relays and inputs work but controller information is unavailable, first check `username` / `password` and the integration logs for XML access failures. `api_key` and `push_password` cannot replace those web credentials.


## Description

You can control by setting the type of the device:

- `relay` as switch and light or climate (with https://www.gce-electronics.com/fr/nos-produits/314-module-diode-fil-pilote-.html)
- `virtualout` as switch and binarysensor
- `virtualin` as switch
- `digitalin` as binarysensor
- `analogin` as sensor
- `virtualanalogin` as sensor or number
- `xdimmer` as light
- `xeno` as sensor
- `xpwm` as light
- `xpwm_rgb` as light (use 3 xpwm channels)
- `xpwm_rgbw` as light (use 4 xpwm channels)
- `x4vr` as cover
- `x4vr_bso` as cover with BSO/tilt support
- `xthl` as sensors
- `x4fp` as climate
- `counter` as sensor or number

## Example

```yaml
# Example configuration.yaml entry
ipx800v4:
  - name: IPX800
    host: "192.168.1.240"
    api_key: "apikey"
    # Required for diagnostics if the IPX web interface is protected
    username: "your_ipx_web_username"
    password: "your_ipx_web_password"
    devices:
      - name: Chaudière
        icon: mdi:water-boiler
        type: "relay"
        component: "switch"
        id: 3
      - name: Lumière Garage
        type: relay
        component: light
        id: 9
      - name: Lumière Salle à Manger
        type: xdimmer
        component: light
        id: 1
      - component: light
        name: Spots Cuisine
        type: xpwm
        id: 1
      - component: light
        name: "Bandeau de LED Salon"
        type: xpwm_rgbw
        ids: [9, 10, 11, 12]
        transition: 1.5
      - component: binary_sensor
        device_class: motion
        name: Présence Cuisine
        type: virtualout
        id: 1
      - component: binary_sensor
        name: Sonnette
        type: digitalin
        icon: mdi:bell-circle-outline
        id: 1
      - component: binary_sensor
        name: Porte garage
        type: digitalin
        icon: mdi:garage
        id: 2
        invert_value: true
      - component: sensor
        device_class: illuminance
        name: Luminosité Cuisine
        icon: mdi:white-balance-sunny
        type: analogin
        id: 1
        unit_of_measurement: "lx"
      - component: sensor
        name: Capteur Rez-de-Chaussée
        type: xthl
        id: 1
      - component: cover
        name: Volet Salon
        type: x4vr
        ext_id: 1
        id: 1
      - component: climate
        name: Radiateur Salon
        type: x4fp
        ext_id: 1
        id: 1
      - component: climate
        name: Radiateur Salle de Bains
        type: relay
        ids: [7, 8]
      - component: number
        name: Compteur
        type: counter
        id: 1
      - component: sensor
        device_class: humidity
        name: Humidité Salle de Bains
        type: xeno
        id: 123
        unit_of_measurement: "%"
      - component: sensor
        device_class: temperature
        name: Température Salle de Bains
        type: xeno
        id: 124
        unit_of_measurement: "C"
```

## List of configuration parameters

```yaml
name:
  description: Name of the IPX800.
  required: true
  type: name
host:
  description: Hostname or IP address of the IPX800.
  required: true
  type: host
port:
  description: HTTP port.
  required: false
  default: 80
  type: port
api_key:
  description: API key (need to be activate in Network => API)
  required: true
  type: string
username:
  description: IPX web interface username; required with password for protected XML diagnostics, also used for X-PWM control
  required: false
  type: string
password:
  description: IPX web interface password paired with username, not the API key or push_password
  required: false
  type: string
scan_interval:
  description: Time in seconds between two polling, small value can cause error from the IPX800
  required: false
  default: 10
  type: int
push_password:
  description: Define a password to allow API calls from IPX800 PUSH
  required: false
  type: string
push_check_host:
  description: Check the host of the IPX800 when receiving a push command
  required: false
  default: true
  type: bool
devices:
  description: List of your devices configuration (switch of relays, light of X-Dimmer...), see below
  required: true
  type: list
```

### Devices configuration

```yaml
component:
  description: device type
  required: true
  type: string
  values: "switch", "light", "cover", "sensor" or "binary_sensor"
name:
  description: friendly name of the device
  required: true
  type: string
device_class:
  description: custom device_class for binary_sensor and sensor only, see Home Assistant
  required: false
  type: string
unit_of_measurement:
  description: set a unit of measurement for sensor only
  required: false
  type: string
transition:
  description: transition time in millisecond, for lights only trough X-Dimmer or X-PWM
  required: false
  default: 500
  type: int
icon:
  description: custom icon
  required: false
  type: string
# Type to control/Get value, only one otherwise the device will not be added
type:
  description: type of input/output on the IPX800 or an extension.
  required: true
  type: string
  values: "relay", "analogin", "virtualanalogin", "digitalin", "virtualin", "virtualout", "xdimmer", "xpwm", "xpwm_rgb", "xpwm_rgbw", "xthl", "x4vr", "x4fp", "relay_fp", "counter"
id:
  description: id of type output, required for all except xpwm_rgb and xpwm_rgbw type
  required: false
  type: int
ext_id:
  description: id of X-4VR extension, required only for x4vr and x4fp type
  required: false
  type: int
ids:
  description: ids of channel for xpwm_rgb, xpwm_rgbw type or relay as climate component
  required: false
  type: list of int
default_brightness:
  description: default brightness for xpwm, xpwm_rgb and xpwm_rgbw only for turn on command (must be between 1 and 255)
  required: false
  type: int
invert_value:
  description: invert the value returned for binary_sensors (on become off and vice versa)
  required: false
  type: bool
  default: false
```

## Push data from the IPX800

First, if you want to push data from your IPX800, you have to set a password on `push_password` config parameter.
Then in your IPX800 PUSH configuration, in the `Identifiant` field, set : `ipx800:mypassword`.

By calling the URL `/api/ipx800v4_refresh/on` from the IPX800, you ask a state refresh of the IPX800 I/O entities (excluding XML diagnostics).

You can update value of a entity by set a Push command in a IPX800 scenario. Usefull to update directly binary_sensor and switch.
In `URL ON` and `URL_OFF` set `/api/ipx800v4/entity_id/state`:

![PUSH configuration example](ipx800_push_configuration_example.jpg)

You can update values of multiple entities with one request (see official wiki: https://wiki.gce-electronics.com/index.php?title=API_V4#Inclure_des_.C3.A9tiquettes_dans_les_notifications_.28mail.2C_push_et_GSM.29)

You have to set the `entity_id=$XXYY` separate by a `&`, example : `/api/ipx800v4_data/binary_sensor.presence_couloir=$VO005&light.spots_couloir=$XPWM06`.

![PUSH data configuration example](ipx800_push_data_configuration_example.jpg)

Finally, you can also push the states of all IPX entities directly and without naming them using bulk update. For example to update all relays from the IPX800v4 : `/api/ipx800v4_bulk/relay/$R`.

![PUSH bulk configuration example](ipx800_push_bulk_configuration_example.jpg)

The labels tested are as follows:

- Relays: `/api/ipx800v4_bulk/relay/$R`
- Digital In: `/api/ipx800v4_bulk/digitalin/$D`
- Virtual In: `/api/ipx800v4_bulk/virtualin/$VI`
- Virtual Out: `/api/ipx800v4_bulk/virtualout/$VO`

See official wiki for [more information](https://wiki.gce-electronics.com/index.php?title=API_V4#Inclure_des_.C3.A9tiquettes_dans_les_notifications_.28mail.2C_push_et_GSM.29).

In case you have multiple IPX entries in your configuration, you can specify the name of the IPX in the route: `/api/ipx800v4_bulk/<MY_IPX_NAME>/relay/$R`.

This parameter in the URL is also available for each routes described above:

- `/api/ipx800v4_refresh/<MY_IPX_NAME>/on` : you request a status update to the I/O entities of the IPX800 named "MY_IPX_NAME"
- `/api/ipx800v4/<MY_IPX_NAME>/entity_id/state` : you update the status of the "entity_id" on the IPX named "MY_IPX_NAME"
- `/api/ipx800v4_data/<MY_IPX_NAME>/binary_sensor.presence_couloir=$VO005&light.spots_couloir=$XPWM06` : you update the statuses of several entities on the IPX named MY_IPX_NAME
- `/api/ipx800v4_bulk/<MY_IPX_NAME>/relay/$R` : you update the statuses of all relays on the IPX named MY_IPX_NAME

## Dependency

[pypix800 python package](https://github.com/Aohzan/pypx800) (installed by Home-Assistant itself, nothing to do here)

Push routes resolve the currently loaded IPX configuration on every request. Reloading one controller updates its credentials, device list and refresh target without replacing another controller's routes. Requests for an unloaded controller are rejected. Existing named and unnamed URLs remain supported; an unnamed URL must identify exactly one loaded IPX through its credentials and host check. If multiple IPXs match, use the named URL to remove the ambiguity.


### Direct push values and availability

Direct pushes update the coordinator's raw fields and publish normal entity updates. Single-entity and `_data` URLs use the current entity registry IDs (including renamed IDs) and only accept loaded entities belonging to the authenticated IPX. A malformed batch, invalid value, conflicting shared-field update or foreign target rejects the whole request.

- Binary sensors, switches and relay lights accept `on/off`, `true/false` and `1/0` as entity states. Binary sensor inversion is reversed when storing the raw value, then applied normally when displaying it; switches and relay lights follow their existing non-inverted platform semantics.
- Sensors and numbers accept finite numeric field values. Single-channel PWM lights accept the actual IPX percentage (0–100), or `off/false` for zero. An `on` value alone cannot supply a PWM level.
- Bulk endpoints retain their existing raw bit-string format for relays, digital inputs, virtual inputs and virtual outputs. Bit positions identify hardware channels; binary sensor inversion is applied only by the entity.
- Composite or ambiguous states (covers, climates, dimmers, RGB/RGBW lights) require the existing refresh endpoint: a state string alone cannot reliably reconstruct their raw data. Unsupported direct values return HTTP 400; unknown, unloaded or foreign entity targets return HTTP 404.

A valid push records freshness only for the included fields. It does not reset full-read failures, change API health, or postpone polling/recovery. During a read outage, an entity is available only while **all** its required fields have recent push data. Push freshness lasts one configured scan interval plus the two bounded recovery delays: `scan_interval + 2 × min(scan_interval, 15)` seconds (330 seconds for a 300-second scan). Expiry is published even if polling keeps failing.

A successful full read reconciles all fields. A push received while a read is already in flight takes precedence over that response; the next successful read reconciles it normally. The refresh endpoint still requests a debounced full pull, and commands still wait for confirmed data.


## Command retries

Explicit state/value commands retry transient communication failures at most twice,
with non-blocking waits of 1 then 2 seconds (three attempts total per write).
This applies to relay/virtual ON/OFF, dimmer/PWM levels, RGB/RGBW channels,
heating modes and virtual analog values. Timeouts (including response-body reads), missing success confirmations and
unexpected/malformed response content are retried. Authentication errors, invalid
URLs and definitive HTTP errors fail immediately. Final errors include the failure
category, exception type and actual attempt/retry counts for the failed write. A failed refresh after a successful
write never replays that write. Failed commands still raise `HomeAssistantError`.

For X4VR, open/close send absolute positions 0/100, a requested position sends
its absolute target, and stop sends 101. These commands may retry; BSO tilt
uses relative pulses and never retries. See the [GCE API reference](https://wiki.gce-electronics.com/index.php?title=API_V4).
Toggles and counter writes also remain single-attempt operations.

A newer command on any overlapping output supersedes older pending retries and
remaining channel writes, including across entity aliases. An already in-flight
request finishes before the new write; backoff does not hold the output lock.
The superseded caller receives an error. Unloading stops pending retries.
Transitions can restart if their first response was lost; a successful API response
acknowledges the request, not completion of the physical movement.

For an output driving a pulse, timer or IPX scenario where repeated ON/OFF has
side effects, add `retry_commands: false` to that device's YAML configuration.
The default is `true`; this only enables retries for the eligible commands above,
never for toggles or pulses. External IPX scenarios/manual commands cannot be
ordered by Home Assistant's command manager.

The command client retains `request_retries=1`. Its CGI path avoids the blocking
`time.sleep()` in pypx800 2.5.1; integration retries use `await asyncio.sleep()`.
