"""
HMRC Fraud Prevention Headers — header builder for the "WEB_APP_VIA_SERVER"
connection method.

SoleTax's architecture is: user's browser -> Django server -> HMRC API.
The user never talks to HMRC directly, so per HMRC's connection-method
guidance this is WEB_APP_VIA_SERVER, NOT a direct/desktop/mobile method.
That choice affects which headers are mandatory vs optional — getting it
wrong is a common reason HMRC's validator API rejects submissions.

Reference: https://developer.service.hmrc.gov.uk/guides/fraud-prevention/
           connection-method/web-app-via-server/

THIS IS NOT A FULL CLIENT-DATA COLLECTOR. Browser-only data (screen size,
installed fonts, timezone as seen by JS, window size, do-not-track,
local IPs) cannot be observed from Django — it must be captured in the
browser via JavaScript and POSTed up with the request that triggers an
HMRC API call. See `static/js/fraud_prevention_collector.js` for that
half. This module:
  1. Builds the headers Django itself can supply (vendor info, server
     timestamp, public IP/port as seen by the server).
  2. Merges in whatever client-collected data was POSTed alongside the
     request.
  3. Validates that nothing mandatory is missing before a submission is
     allowed to proceed, so we fail loudly in our own logs rather than
     silently sending an incomplete request that HMRC bounces.

Do not log full header values containing personal data (IPs, MAC
addresses, user identifiers) outside of what's needed for debugging
rejected submissions — these are sensitive under UK GDPR even though
HMRC requires us to collect them.
"""
from __future__ import annotations
import uuid
import urllib.parse
from datetime import datetime, timezone as dt_timezone


CONNECTION_METHOD = "WEB_APP_VIA_SERVER"

# Vendor identity — these are fixed per-deployment, set from Django settings.
# (kept here as constants with safe fallbacks; real values should come from
# settings.HMRC_VENDOR_PRODUCT_NAME / settings.HMRC_VENDOR_VERSION so they
# can differ between staging/production without code changes)
DEFAULT_VENDOR_PRODUCT_NAME = "SoleTax"
DEFAULT_VENDOR_VERSION_KEY = "soletax"  # used as the key in Gov-Vendor-Version


def _percent_encode(value: str) -> str:
    """HMRC requires percent-encoding of header values per RFC 3986."""
    return urllib.parse.quote(str(value), safe='')


def _encode_kv_pairs(pairs: dict) -> str:
    """
    Encode a dict as HMRC's '<key>=<value>&<key2>=<value2>' format.
    Keys and values are percent-encoded individually; '=' and '&'
    separators are left untouched, per spec.
    """
    parts = []
    for k, v in pairs.items():
        if v is None or v == '':
            continue
        parts.append(f"{_percent_encode(k)}={_percent_encode(v)}")
    return '&'.join(parts)


def utc_timestamp() -> str:
    """yyyy-MM-ddThh:mm:ss.sssZ — HMRC's required timestamp format."""
    now = datetime.now(dt_timezone.utc)
    return now.strftime('%Y-%m-%dT%H:%M:%S.') + f"{now.microsecond // 1000:03d}Z"


def get_or_create_device_id(request) -> str:
    """
    HMRC requires a persistent per-device UUID (Gov-Client-Device-ID).
    Stored as a long-lived cookie. Callers must read `device_id` off
    the return value and set it as a response cookie if `created` is True.
    """
    existing = request.COOKIES.get('soletax_device_id')
    if existing:
        return existing, False
    return str(uuid.uuid4()), True


def server_supplied_headers(request, *, vendor_product_name: str = DEFAULT_VENDOR_PRODUCT_NAME,
                              vendor_version: str = '1.0.0') -> dict:
    """
    Headers Django can fill in itself, without any browser-collected data.
    These are the minimum viable set — submissions will still fail
    fraud-prevention validation without the client-collected headers from
    fraud_prevention_collector.js merged in via `build_full_headers`.
    """
    device_id, _ = get_or_create_device_id(request)

    # Server's view of the client's public IP — may be wrong behind a proxy
    # (PythonAnywhere, Cloudflare, etc.) unless X-Forwarded-For is trusted
    # and parsed correctly. This MUST be reviewed against actual hosting
    # infra before going to production; using REMOTE_ADDR naively behind a
    # reverse proxy will report the proxy's IP, not the user's.
    public_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() \
        or request.META.get('REMOTE_ADDR', '')

    headers = {
        'Gov-Client-Connection-Method': CONNECTION_METHOD,
        'Gov-Client-Device-ID': device_id,
        'Gov-Client-Timezone': 'UTC+00:00',  # server-side fallback; browser value should override this
        'Gov-Client-Public-IP': public_ip,
        'Gov-Client-Public-IP-Timestamp': utc_timestamp(),
        'Gov-Vendor-Version': _encode_kv_pairs({vendor_version_key(): vendor_version}),
        'Gov-Vendor-Product-Name': _percent_encode(vendor_product_name),
        'Gov-Vendor-Public-IP': request.META.get('SERVER_ADDR', ''),
    }
    return headers


def vendor_version_key() -> str:
    return DEFAULT_VENDOR_VERSION_KEY


def build_full_headers(request, client_data: dict, *,
                        vendor_product_name: str = DEFAULT_VENDOR_PRODUCT_NAME,
                        vendor_version: str = '1.0.0') -> dict:
    """
    Merge server-supplied headers with browser-collected `client_data`
    (the JSON payload posted by fraud_prevention_collector.js) into the
    final header dict ready to attach to an HMRC API request.

    `client_data` expected keys (all optional at this layer — validation
    happens separately in `validate_headers`):
        timezone            -> 'UTC+01:00'
        screens              -> [{'width':..,'height':..,'scaling_factor':..,'colour_depth':..}, ...]
        window_width, window_height
        user_agent_browser_js
        browser_plugins      -> list[str]
        do_not_track          -> bool
        local_ips             -> list[str]
        local_ips_timestamp
        multi_factor          -> list[dict] (optional, only if MFA was used this session)
    """
    headers = server_supplied_headers(
        request, vendor_product_name=vendor_product_name, vendor_version=vendor_version
    )

    if client_data.get('timezone'):
        headers['Gov-Client-Timezone'] = client_data['timezone']

    if client_data.get('screens'):
        screens_str = ','.join(
            _encode_kv_pairs({
                'width': s.get('width'),
                'height': s.get('height'),
                'scaling-factor': s.get('scaling_factor'),
                'colour-depth': s.get('colour_depth'),
            })
            for s in client_data['screens']
        )
        headers['Gov-Client-Screens'] = screens_str

    if client_data.get('window_width') and client_data.get('window_height'):
        headers['Gov-Client-Window-Size'] = _encode_kv_pairs({
            'width': client_data['window_width'],
            'height': client_data['window_height'],
        })

    if client_data.get('user_agent_browser_js'):
        headers['Gov-Client-Browser-JS-User-Agent'] = client_data['user_agent_browser_js']

    if client_data.get('browser_plugins') is not None:
        headers['Gov-Client-Browser-Plugins'] = ','.join(
            _percent_encode(p) for p in client_data['browser_plugins']
        )

    if 'do_not_track' in client_data:
        headers['Gov-Client-Browser-Do-Not-Track'] = 'true' if client_data['do_not_track'] else 'false'

    if client_data.get('local_ips'):
        headers['Gov-Client-Local-IPs'] = ','.join(
            _percent_encode(ip) for ip in client_data['local_ips']
        )
        headers['Gov-Client-Local-IPs-Timestamp'] = (
            client_data.get('local_ips_timestamp') or utc_timestamp()
        )

    if client_data.get('multi_factor'):
        mf_str = ','.join(
            _encode_kv_pairs({
                'type': m.get('type'),
                'timestamp': m.get('timestamp'),
                'unique-reference': m.get('unique_reference'),
            })
            for m in client_data['multi_factor']
        )
        headers['Gov-Client-Multi-Factor'] = mf_str

    # Gov-Client-User-IDs: who is using SoleTax, keyed by however they
    # identify (Django username). Required field — without it HMRC's
    # validator flags a missing-data error.
    if request.user.is_authenticated:
        headers['Gov-Client-User-IDs'] = _encode_kv_pairs({
            'soletax': str(request.user.pk),
        })

    return headers


# Mandatory headers for WEB_APP_VIA_SERVER per HMRC's published spec.
# (Gov-Client-Public-Port is intentionally excluded — most hosting setups,
# including PythonAnywhere-style PaaS, cannot reliably observe the client's
# *public* TCP port; HMRC's spec explicitly allows omitting headers your
# stack cannot collect, but you must be able to justify the gap if asked.)
REQUIRED_HEADERS_WEB_APP_VIA_SERVER = [
    'Gov-Client-Connection-Method',
    'Gov-Client-Device-ID',
    'Gov-Client-User-IDs',
    'Gov-Client-Timezone',
    'Gov-Client-Local-IPs',
    'Gov-Client-Screens',
    'Gov-Client-Window-Size',
    'Gov-Client-Browser-Plugins',
    'Gov-Client-Browser-JS-User-Agent',
    'Gov-Client-Browser-Do-Not-Track',
    'Gov-Vendor-Version',
    'Gov-Vendor-Product-Name',
    'Gov-Client-Public-IP',
    'Gov-Client-Public-IP-Timestamp',
]


class MissingFraudPreventionHeaders(Exception):
    """Raised when a submission is about to go out without all mandatory
    fraud-prevention data. Catch this and surface a clear error rather
    than letting an incomplete request reach HMRC and get rejected there
    (or worse, silently logged as a compliance gap)."""
    def __init__(self, missing: list[str]):
        self.missing = missing
        super().__init__(f"Missing required fraud prevention headers: {', '.join(missing)}")


def validate_headers(headers: dict, *, strict: bool = True) -> list[str]:
    """
    Check that every mandatory header for WEB_APP_VIA_SERVER is present
    and non-empty. Returns the list of missing header names.

    If strict=True, raises MissingFraudPreventionHeaders instead of
    returning silently — use strict=True right before an actual HMRC API
    call, and strict=False if you just want to display a warning to the
    user (e.g. "your browser blocked some data we need for HMRC submission").
    """
    missing = [
        name for name in REQUIRED_HEADERS_WEB_APP_VIA_SERVER
        if not headers.get(name)
    ]
    if missing and strict:
        raise MissingFraudPreventionHeaders(missing)
    return missing
