"""Brew (brewweb) helpers for VPN connectivity checks."""

import logging

import requests
import urllib3

ERRATA_PROBE_URL = "https://errata.devel.redhat.com/"

logger = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def check_vpn():
    """Check VPN connectivity by probing errata.devel.redhat.com.

    Returns:
        bool: True if VPN is connected.
    """
    try:
        response = requests.get(
            ERRATA_PROBE_URL, verify=False, timeout=5,
            allow_redirects=False,
        )
        return response.status_code < 500
    except requests.RequestException:
        return False
