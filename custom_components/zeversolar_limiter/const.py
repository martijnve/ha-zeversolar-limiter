"""Constants for Zeversolar Limiter."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

DOMAIN = "zeversolar_limiter"

CONF_PRICE_ENTITY = "price_entity"
DEFAULT_PRICE_ENTITY = "sensor.current_energy_price"

SCAN_INTERVAL = timedelta(seconds=30)

# The inverter rejects limits below 5 % (zeversolar 0.4.0); 5 % of 3000 W measured as 150 W.
CURTAILED_PERCENT = 5


class Mode(StrEnum):
    """What the curtailment select can be set to."""

    AUTO = "auto"  # curtail while the price is below the threshold
    OFF = "off"  # never curtail: full output
    FORCED = "forced"  # always curtail


class Reason(StrEnum):
    """Why the integration wants the inverter curtailed."""

    PRICE = "price"
    FORCED = "forced"
