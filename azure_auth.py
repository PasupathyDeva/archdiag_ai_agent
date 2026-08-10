"""
Robust Azure AD authentication for the Azure AI Foundry image endpoints.

Shared by generate_image.py and edit_image.py.

Why this module exists
---------------------
`DefaultAzureCredential()` on a Windows corporate machine fails intermittently:

  * The Azure CLI probe has a 10 second subprocess timeout by default. A cold
    `az account get-access-token` behind a corporate proxy regularly exceeds it,
    surfacing as "AzureCliCredential: Failed to invoke the Azure CLI".
  * ManagedIdentityCredential probes the IMDS endpoint and SharedTokenCache /
    AzurePowerShell / azd each add latency and noise before the chain reaches the
    credential that actually works.
  * `subprocess.run(["az", ...])` raises FileNotFoundError on Windows because the
    CLI shim is `az.cmd`, and CreateProcess only resolves `az` / `az.exe`.

Strategy: try the cheapest credential that works on this machine first, fall back
through progressively broader options, cache the token in-process, and retry
transient failures instead of aborting.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import subprocess
import sys
import time
from typing import Callable, Optional

from azure.core.credentials import AccessToken
from azure.core.exceptions import ClientAuthenticationError

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCOPE = "https://ai.azure.com/.default"

ENDPOINT = os.environ.get(
    "AZURE_AI_IMAGE_ENDPOINT",
    "https://<foundryproject>.services.ai.azure.com/openai/v1",
)
DEPLOYMENT = os.environ.get("AZURE_AI_IMAGE_DEPLOYMENT", "gpt-image-2")

# Subprocess timeout for CLI-based credentials. The azure-identity default of
# 10s is the single biggest cause of spurious auth failures on this machine.
PROCESS_TIMEOUT = int(os.environ.get("AZ_PROCESS_TIMEOUT", "90"))

# Refresh the cached token this many seconds before it actually expires.
_EXPIRY_SKEW = 300

# Automatic `az login` is OFF by default: an unexpected browser popup is worse
# than a clear error message. Opt in with AZ_AUTO_LOGIN=1.
AUTO_LOGIN = os.environ.get("AZ_AUTO_LOGIN", "").strip().lower() in ("1", "true", "yes")

_cached_token: Optional[AccessToken] = None

# Guard: `az login` is attempted at most once per process, ever. Without this a
# failing credential chain will re-launch the browser login in a loop.
_login_attempted = False


def _log(message: str) -> None:
    print(f"  {message}")


# ---------------------------------------------------------------------------
# Azure CLI discovery
# ---------------------------------------------------------------------------

def find_az() -> Optional[str]:
    """Return an absolute path to the Azure CLI executable, or None.

    Handles the Windows case where the CLI is a `.cmd` shim that bare
    `subprocess.run(["az", ...])` cannot execute.
    """
    for name in ("az", "az.cmd", "az.bat", "az.exe"):
        found = shutil.which(name)
        if found:
            return found

    candidates = [
        r"C:\Program Files (x86)\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd",
        os.path.expandvars(
            r"%LOCALAPPDATA%\Programs\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
        ),
        "/usr/bin/az",
        "/usr/local/bin/az",
        "/opt/homebrew/bin/az",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def _run_az(args: list[str], timeout: int = PROCESS_TIMEOUT,
            capture: bool = True) -> subprocess.CompletedProcess:
    """Run the Azure CLI with an explicitly resolved executable path."""
    az = find_az()
    if az is None:
        raise FileNotFoundError(
            "Azure CLI not found. Install it from https://aka.ms/installazurecli"
        )
    return subprocess.run(
        [az, *args],
        capture_output=capture,
        text=True,
        timeout=timeout,
        check=False,
    )


def az_is_logged_in() -> bool:
    """True if the Azure CLI has an active account."""
    try:
        return _run_az(["account", "show", "-o", "none"], timeout=30).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def az_login() -> bool:
    """Run `az login` interactively. Returns True on success."""
    if find_az() is None:
        print(
            "  Error: Azure CLI not found. Install it from "
            "https://aka.ms/installazurecli",
            file=sys.stderr,
        )
        return False

    _log("Launching 'az login' (a browser window will open)...")
    try:
        # capture=False so the device/browser prompt reaches the terminal.
        result = _run_az(["login"], timeout=300, capture=False)
    except subprocess.TimeoutExpired:
        print("  Error: 'az login' timed out.", file=sys.stderr)
        return False
    except (FileNotFoundError, OSError) as exc:
        print(f"  Error: could not start 'az login': {exc}", file=sys.stderr)
        return False

    if result.returncode == 0:
        _log("az login successful.")
        return True
    print(f"  'az login' failed with exit code {result.returncode}", file=sys.stderr)
    return False


# ---------------------------------------------------------------------------
# Token acquisition strategies
# ---------------------------------------------------------------------------

def _token_via_azure_cli_credential() -> AccessToken:
    """AzureCliCredential with a generous subprocess timeout."""
    from azure.identity import AzureCliCredential

    return AzureCliCredential(process_timeout=PROCESS_TIMEOUT).get_token(SCOPE)


def _token_via_az_cli_direct() -> AccessToken:
    """Shell out to `az account get-access-token`, bypassing azure-identity."""
    result = _run_az(
        ["account", "get-access-token", "--scope", SCOPE, "-o", "json"]
    )
    if result.returncode != 0:
        raise ClientAuthenticationError(
            f"az account get-access-token failed: {(result.stderr or '').strip()}"
        )

    payload = json.loads(result.stdout)
    token = payload["accessToken"]

    # Newer CLI versions expose an epoch int; older ones only a local timestamp.
    expires_on = payload.get("expires_on")
    if expires_on is None:
        raw = payload.get("expiresOn", "")
        try:
            expires_on = int(
                _dt.datetime.fromisoformat(raw).timestamp()
            )
        except ValueError:
            expires_on = int(time.time()) + 3600
    return AccessToken(token, int(expires_on))


def _token_via_default_credential() -> AccessToken:
    """DefaultAzureCredential with the slow/irrelevant probes disabled.

    EnvironmentCredential is kept so CI service principals and OIDC still work.
    """
    from azure.identity import DefaultAzureCredential

    credential = DefaultAzureCredential(
        process_timeout=PROCESS_TIMEOUT,
        exclude_managed_identity_credential=True,
        exclude_shared_token_cache_credential=True,
        exclude_developer_cli_credential=True,
        exclude_interactive_browser_credential=True,
    )
    return credential.get_token(SCOPE)


_STRATEGIES: list[tuple[str, Callable[[], AccessToken]]] = [
    ("Azure CLI credential", _token_via_azure_cli_credential),
    ("Azure CLI direct", _token_via_az_cli_direct),
    ("DefaultAzureCredential", _token_via_default_credential),
]


def _is_interactive() -> bool:
    """True only if we can actually prompt a human."""
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _try_strategies() -> tuple[Optional[AccessToken], list[str]]:
    """Try every strategy once. Returns (token_or_None, error_messages)."""
    errors: list[str] = []
    for name, strategy in _STRATEGIES:
        try:
            token = strategy()
            if name != _STRATEGIES[0][0]:
                _log(f"Authenticated via {name}.")
            return token, errors
        except Exception as exc:  # noqa: BLE001 - collect and continue
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    return None, errors


def _acquire_token() -> AccessToken:
    """Acquire a token. Never recurses; never loops on interactive login."""
    global _login_attempted

    token, errors = _try_strategies()
    if token is not None:
        return token

    # One bounded retry: covers genuinely transient CLI/network hiccups.
    _log("Token acquisition failed, retrying once in 2s...")
    time.sleep(2)
    token, more_errors = _try_strategies()
    errors.extend(more_errors)
    if token is not None:
        return token

    # Interactive login: opt-in, interactive shells only, at most once per process.
    if AUTO_LOGIN and not _login_attempted and _is_interactive() and not az_is_logged_in():
        _login_attempted = True
        if az_login():
            token, more_errors = _try_strategies()
            errors.extend(more_errors)
            if token is not None:
                return token

    detail = "\n    ".join(errors)
    hint = (
        "Run 'az login', confirm 'az account show' works, then retry."
        if not AUTO_LOGIN
        else "Interactive login did not resolve the problem."
    )
    raise ClientAuthenticationError(
        f"Unable to acquire an Azure AD token for {SCOPE}.\n    {detail}\n  Fix: {hint}"
    )


def get_token(force_refresh: bool = False) -> str:
    """Return a valid bearer token, using the in-process cache when possible."""
    global _cached_token

    if not force_refresh and _cached_token is not None:
        if _cached_token.expires_on - _EXPIRY_SKEW > time.time():
            return _cached_token.token

    _cached_token = _acquire_token()
    return _cached_token.token


def invalidate_token() -> None:
    """Drop the cached token so the next call re-authenticates."""
    global _cached_token
    _cached_token = None


def get_token_provider() -> Callable[[], str]:
    """Return the callable the OpenAI SDK expects for `api_key`.

    The SDK accepts `api_key: str | Callable[[], str]` and invokes the callable
    per request, so token refresh is handled transparently.
    """
    return get_token


# ---------------------------------------------------------------------------
# Client construction and call retry
# ---------------------------------------------------------------------------

def build_client(timeout: float = 900.0):
    """Build an OpenAI client pointed at the Foundry endpoint.

    The generous timeout accommodates high-quality 1792x1024 generations.
    """
    from openai import OpenAI

    # Fail fast with a clear message if auth is broken, rather than on first use.
    get_token()

    return OpenAI(
        base_url=ENDPOINT,
        api_key=get_token_provider(),
        timeout=timeout,
        max_retries=3,
    )


def call_with_auth_retry(operation: Callable[[], object], attempts: int = 3) -> object:
    """Invoke `operation`, refreshing credentials on auth errors and backing off.

    Handles the case where a token is accepted at request time but rejected by
    the service, and retries transient rate-limit / server errors.
    """
    import openai

    last_error: Optional[Exception] = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (openai.AuthenticationError, openai.PermissionDeniedError,
                ClientAuthenticationError) as exc:
            last_error = exc
            _log(f"Authentication rejected (attempt {attempt}/{attempts}). Refreshing token...")
            invalidate_token()
            if attempt == attempts:
                break
            # Deliberately no az_login() here: _acquire_token owns that decision
            # and enforces the once-per-process guard.
            try:
                get_token(force_refresh=True)
            except ClientAuthenticationError as auth_exc:
                raise RuntimeError(str(auth_exc)) from auth_exc
        except (openai.RateLimitError, openai.APITimeoutError,
                openai.InternalServerError, openai.APIConnectionError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            backoff = 5 * (2 ** (attempt - 1))
            _log(
                f"{type(exc).__name__} (attempt {attempt}/{attempts}). "
                f"Retrying in {backoff}s..."
            )
            time.sleep(backoff)

    raise RuntimeError(f"Request failed after {attempts} attempts: {last_error}")


def fail(message: str) -> None:
    """Print an error and exit with a non-zero status."""
    print(f"Error: {message}", file=sys.stderr)
    sys.exit(1)
