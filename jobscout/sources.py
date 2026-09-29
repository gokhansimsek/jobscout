"""Alert source: where LinkedIn job-alert emails come from.

Interface: any object with ``alerts() -> Iterable[Alert]``.

Adapters:
    FolderSource: .eml / .msg / .html files on disk (the Job store's inbox, manual samples).
    GraphSource: Outlook.com via Microsoft Graph (sign in once with ``python -m jobscout login``).
"""

import email
import hashlib
import os
import time
from collections.abc import Callable, Iterable, Iterator
from datetime import UTC, datetime, timedelta
from email import policy
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Protocol, cast

import extract_msg
import msal
import requests

from jobscout.config import ROOT
from jobscout.models import Alert

ALERT_SENDER = "jobalerts-noreply@linkedin.com"


class AlertSource(Protocol):
    """Anything that can list LinkedIn alert emails."""

    def alerts(self) -> Iterable[Alert]:
        """List the available alert emails.

        Returns:
            The alerts, each with a stable, filename-safe id.
        """
        ...


# --- FolderSource -----------------------------------------------------------------


def _html_from_eml(path: Path) -> str:
    """Read the HTML part of a .eml file.

    Args:
        path: The .eml file.

    Returns:
        The HTML body, or "" if the email has no HTML part.
    """
    msg = cast("EmailMessage", email.message_from_bytes(path.read_bytes(), policy=policy.default))
    part = msg.get_body(preferencelist=("html",))
    return str(part.get_content()) if part else ""


def _html_from_msg(path: Path) -> str:
    """Read the HTML body of an Outlook .msg file.

    Args:
        path: The .msg file.

    Returns:
        The HTML body, or "" if there is none.
    """
    msg: Any = extract_msg.openMsg(str(path))
    try:
        html = msg.htmlBody or b""
    finally:
        msg.close()
    return html.decode("utf-8", errors="replace") if isinstance(html, bytes) else html


def _html_from_html(path: Path) -> str:
    """Read a saved .html alert.

    Args:
        path: The .html file.

    Returns:
        The file's contents.
    """
    return path.read_text(encoding="utf-8")


_LOADERS: dict[str, Callable[[Path], str]] = {
    ".eml": _html_from_eml,
    ".msg": _html_from_msg,
    ".html": _html_from_html,
}


class FolderSource:
    """Alerts saved as files in one or more folders."""

    def __init__(self, *dirs: Path):
        """Create a source over the given folders.

        Args:
            *dirs: Folders to read, in order. Missing folders are treated as empty.
        """
        self.dirs = dirs

    def alerts(self) -> Iterator[Alert]:
        """Read every .eml, .msg and .html file; other files are ignored.

        Yields:
            One Alert per file, with the file name (without suffix) as its id.
        """
        for d in self.dirs:
            for path in sorted(d.glob("*")):
                if loader := _LOADERS.get(path.suffix.lower()):
                    yield Alert(id=path.stem, html=loader(path))


# --- GraphSource ------------------------------------------------------------------

TOKEN_CACHE = ROOT / ".token_cache.json"
SCOPES = ["Mail.Read"]  # MSAL adds offline_access itself
GRAPH_MESSAGES = "https://graph.microsoft.com/v1.0/me/messages"


MAX_GRAPH_ATTEMPTS = 5

# (url, params) -> (status, retry_after_seconds, page). page is the decoded JSON body
# for 2xx and {} otherwise; retry_after is only set for 429. Raises AlertSourceError
# on network failure.
GraphGetter = Callable[[str, dict[str, str] | None], tuple[int, int | None, dict]]


class LoginRequired(RuntimeError):
    """No usable cached sign-in; a human has to run ``python -m jobscout login`` once."""


class AlertSourceError(RuntimeError):
    """The mailbox could not be read (network, Graph error, throttling). Stored alerts still work."""


def get_token(interactive: bool = False) -> str:
    """Get a Microsoft Graph access token for the user's mailbox.

    Uses the cached refresh token silently when possible. The refresh token renews
    itself on each use and only expires after ~90 days without a run, a password
    change, or revoked consent. Reads ``MS_CLIENT_ID`` and ``MS_AUTHORITY`` from
    the environment.

    Args:
        interactive: If no cached sign-in works, print a device code and block until
            the user signs in. Leave False for unattended runs, so they fail fast.

    Returns:
        A bearer token with the Mail.Read scope.

    Raises:
        LoginRequired: If not interactive and there is no usable cached sign-in.
        RuntimeError: If the device flow cannot start or the sign-in fails.
    """
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE.exists():
        cache.deserialize(TOKEN_CACHE.read_text())

    app = msal.PublicClientApplication(
        os.environ["MS_CLIENT_ID"],
        authority=os.environ.get("MS_AUTHORITY", "https://login.microsoftonline.com/consumers"),
        token_cache=cache,
    )

    result = None
    if accounts := app.get_accounts():
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
    if not result:
        if not interactive:
            raise LoginRequired("Outlook sign-in needed: run `python -m jobscout login` once")
        flow = app.initiate_device_flow(SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Device flow failed: {flow.get('error_description')}")
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)  # blocks until you sign in

    if cache.has_state_changed:
        TOKEN_CACHE.write_text(cache.serialize())
    if "access_token" not in result:
        raise RuntimeError(f"Login failed: {result.get('error_description')}")
    return result["access_token"]


def graph_getter(token_provider: Callable[[], str] = get_token) -> GraphGetter:
    """Build the production Graph getter: one signed-in requests session.

    Args:
        token_provider: Returns a Graph bearer token; defaults to the cached sign-in.

    Returns:
        A function that GETs one Graph page.

    Raises:
        LoginRequired: If there is no usable cached sign-in.
    """
    session = requests.Session()
    session.headers.update(
        {
            "Authorization": f"Bearer {token_provider()}",
            "Prefer": 'outlook.body-content-type="html"',
        }
    )

    def get(url: str, params: dict[str, str] | None) -> tuple[int, int | None, dict]:
        """GET one Graph page.

        Args:
            url: Page URL.
            params: Query parameters, or None when the URL already has them.

        Returns:
            The HTTP status, the Retry-After seconds for a 429, and the decoded page.

        Raises:
            AlertSourceError: On any network-level failure.
        """
        try:
            resp = session.get(url, params=params, timeout=30)
        except requests.RequestException as e:
            raise AlertSourceError(f"Graph unreachable: {e}") from e
        retry_after = (
            int(resp.headers.get("Retry-After", "10")) if resp.status_code == 429 else None
        )
        return resp.status_code, retry_after, resp.json() if resp.ok else {}

    return get


class GraphSource:
    """Alert emails from an Outlook.com mailbox, read through Microsoft Graph."""

    def __init__(
        self,
        days: int = 14,
        *,
        get: GraphGetter | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        """Create a source for recent alerts.

        Args:
            days: How far back to look, by received date.
            get: Graph page getter; defaults to one signed in with the cached token.
            sleep: Called to wait out throttling.
        """
        self.days = days
        self._get = get
        self._sleep = sleep

    def alerts(self) -> Iterator[Alert]:
        """Page through the mailbox for alerts from LinkedIn's job-alert sender.

        Yields:
            One Alert per email. The id is a hash of Graph's message id, which is
            not filename-safe itself.

        Raises:
            LoginRequired: If there is no usable cached sign-in.
            AlertSourceError: If Graph is unreachable, returns an error, or keeps throttling.
        """
        get = self._get or graph_getter()
        since = (datetime.now(UTC) - timedelta(days=self.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # No $orderby: combined with this $filter Graph can reject it as "InefficientFilter".
        url: str | None = GRAPH_MESSAGES
        params: dict[str, str] | None = {
            "$filter": f"from/emailAddress/address eq '{ALERT_SENDER}' "
            f"and receivedDateTime ge {since}",
            "$select": "id,body",
            "$top": "50",
        }
        while url:
            page = self._page(get, url, params)
            for msg in page["value"]:
                alert_id = hashlib.sha1(msg["id"].encode()).hexdigest()[:16]
                yield Alert(id=alert_id, html=msg["body"]["content"])
            # nextLink already carries the query, so params are dropped after page 1.
            url, params = page.get("@odata.nextLink"), None

    def _page(self, get: GraphGetter, url: str, params: dict[str, str] | None) -> dict:
        """GET a Graph page, waiting out throttling.

        Args:
            get: Graph page getter.
            url: Page URL.
            params: Query parameters, or None when the URL already has them.

        Returns:
            The decoded JSON page.

        Raises:
            AlertSourceError: On an error status, or if Graph still throttles after
                MAX_GRAPH_ATTEMPTS attempts.
        """
        for _ in range(MAX_GRAPH_ATTEMPTS):
            status, retry_after, page = get(url, params)
            if status == 429:
                self._sleep(retry_after or 10)
                continue
            if status >= 400:
                raise AlertSourceError(f"Graph returned HTTP {status}")
            return page
        raise AlertSourceError("Graph kept throttling (429); try again later")
