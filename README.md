# Zeversolar Limiter

A Home Assistant integration for a Zeversolar inverter on the local network. It shows the inverter as a device and curtails it to 5 % while the energy price is below a threshold, for example when the price goes negative. Everything is local: it talks to the web interface of the inverter's Wi-Fi module and needs no cloud.

Tested with an M11 Wi-Fi module (Zeversolar TLC series, the MXCHIP web UI with *Advanced → Power limit*).

## Entities

| # | Entity | What |
|---|---|---|
| 1 | `sensor.…_power` | AC output (W) |
| 2 | `sensor.…_energy_today` | Energy produced today (kWh) |
| 3 | `sensor.…_output_limit` | Current power limit (%), 100 when off |
| 4 | `binary_sensor.…_curtailing` | On while the limit is below 100 %; attribute `reason`: `price` or `forced` |
| 5 | `select.…_curtailment` | **Auto (price)**: curtail while the price is below the threshold · **Off**: never · **Forced**: always |
| 6 | `number.…_price_threshold` | Auto curtails while the price is strictly below this (default 0.000) |

The mode and threshold survive restarts. The price sensor is chosen when the integration is added and can be changed under *Configure*. It can be any sensor with a numeric price (for example the current all-in price of a dynamic contract). When the price isn't available, the inverter runs at full output.

## How it works

- Every 30 s the integration reads `home.cgi` (output, energy) and `adv.cgi` (power limit). It re-evaluates on every poll and on every change of the price, mode or threshold.
- It writes the inverter's power-limit form (`pwrlim.cgi`) only when the inverter differs from what is wanted, then reads the limit back to confirm it. Other settings on that form are sent back unchanged. Because every poll re-checks, a limit the inverter lost (for example after starting up in the morning) is applied again within 30 s.
- 5 % is the lowest limit the inverter accepts. It is a percentage of the rated power, so 150 W on a 3 kW inverter.
- The integration owns the power limit: a limit set by hand in the inverter's web UI is cleared again while no curtailment is wanted. Removing the integration clears the limit.
- At night the Wi-Fi module usually has no power. The readings are then unavailable, while the mode and threshold stay usable. Setup doesn't need the inverter to be online after it has been added once.
- The inverter's address is fixed in the config entry. The module doesn't announce itself over mDNS, so give it a fixed DHCP lease, and use *Reconfigure* if the address ever changes.

## Install

In HACS add this repository as a custom repository (type *Integration*), install **Zeversolar Limiter** and restart. Then go to *Settings → Devices & services → Add integration → Zeversolar Limiter* and enter the inverter's IP address and the price sensor.

## Development

```bash
devbox shell        # python 3.14 + uv; installs the dev dependencies
devbox run test     # pytest (pytest-homeassistant-custom-component)
devbox run lint     # ruff check + format check
```
