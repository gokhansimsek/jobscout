"""Alert source: where LinkedIn job-alert emails come from.

Interface: any object with ``alerts() -> Iterable[Alert]``.

Adapters:
    FolderSource: .eml / .msg / .html files on disk (the Job store's inbox, manual samples).
    GraphSource: Outlook.com via Microsoft Graph (first use prints a device code to sign in).
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


class LoginRequired(RuntimeError):
    """No usable cached sign-in; a human has to run ``python -m jobscout login`` once."""


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


class GraphSource:
    """Alert emails from an Outlook.com mailbox, read through Microsoft Graph."""

    def __init__(self, days: int = 14, token_provider: Callable[[], str] = get_token):
        """Create a source for recent alerts.

        Args:
            days: How far back to look, by received date.
            token_provider: Returns a Graph bearer token; defaults to the cached sign-in
                (raises LoginRequired if there is none).
        """
        self.days = days
        self.token_provider = token_provider

    def alerts(self) -> Iterator[Alert]:
        """Page through the mailbox for alerts from LinkedIn's job-alert sender.

        Yields:
            One Alert per email. The id is a hash of Graph's message id, which is
            not filename-safe itself.

        Raises:
            requests.HTTPError: If Graph returns an error other than throttling.
            RuntimeError: If Graph keeps throttling.
        """
        since = (datetime.now(UTC) - timedelta(days=self.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {self.token_provider()}",
                "Prefer": 'outlook.body-content-type="html"',
            }
        )
        # No $orderby: combined with this $filter Graph can reject it as "InefficientFilter".
        url: str | None = GRAPH_MESSAGES
        params: dict[str, str] | None = {
            "$filter": f"from/emailAddress/address eq '{ALERT_SENDER}' "
            f"and receivedDateTime ge {since}",
            "$select": "id,body",
            "$top": "50",
        }
        while url:
            page = self._get(session, url, params)
            for msg in page["value"]:
                alert_id = hashlib.sha1(msg["id"].encode()).hexdigest()[:16]
                yield Alert(id=alert_id, html=msg["body"]["content"])
            # nextLink already carries the query, so params are dropped after page 1.
            url, params = page.get("@odata.nextLink"), None

    @staticmethod
    def _get(session: requests.Session, url: str, params: dict[str, str] | None) -> dict:
        """GET a Graph page, waiting out throttling.

        Args:
            session: Session carrying the auth headers.
            url: Page URL.
            params: Query parameters, or None when the URL already has them.

        Returns:
            The decoded JSON page.

        Raises:
            requests.HTTPError: On any non-throttling error status.
            RuntimeError: If Graph still throttles after 5 attempts.
        """
        for _ in range(5):
            resp = session.get(url, params=params, timeout=30)
            if resp.status_code == 429:
                time.sleep(int(resp.headers.get("Retry-After", "10")))
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError("Graph kept throttling (429); try again later")
