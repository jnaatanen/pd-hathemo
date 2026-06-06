"""Constants for the pd_hathemo (Themo) integration."""

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "pd_hathemo"
BASE_URL = "https://connect.themo.io"
API_VERSION = "2.1"
REQUEST_TIMEOUT = 30

PLATFORMS = [Platform.CLIMATE, Platform.SENSOR, Platform.LIGHT]

STATE_SCAN_INTERVAL = timedelta(minutes=2)
ENERGY_SCAN_INTERVAL = timedelta(minutes=10)
ENERGY_BACKFILL_DAYS = 14
ENERGY_INCREMENTAL_DAYS = 2  # overlap window on incremental runs; dedup makes it safe

# Themo modes
MODE_OFF = "Off"
MODE_MANUAL = "Manual"
MODE_SLS = "SLS"
