"""HTTP client for Trello REST API v1."""

from __future__ import annotations

import logging
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

from app.config import HTTP_TIMEOUT_SECONDS, TRELLO_BASE_URL, TRELLO_KEY, TRELLO_TOKEN

logger = logging.getLogger(__name__)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError))


_client_singleton: TrelloClient | None = None


def get_client() -> TrelloClient:
    """Lazy singleton for graph nodes and CLI."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = TrelloClient()
    return _client_singleton


class TrelloClient:
    """Thin wrapper with key/token query params and retry on transient failures."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=TRELLO_BASE_URL,
            timeout=HTTP_TIMEOUT_SECONDS,
            params={"key": TRELLO_KEY, "token": TRELLO_TOKEN},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TrelloClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        merged: dict[str, Any] = {}
        if params:
            merged.update(params)
        resp = self._client.request(method, path, params=merged, json=json)
        status = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = {"_raw": resp.text}
        if status >= 500:
            logger.warning("Trello API 5xx %s %s: %s", method, path, status)
            resp.raise_for_status()
        if status >= 400:
            logger.warning("Trello API client error %s %s: %s", method, path, status)
        return status, data

    def list_boards(self) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", "/members/me/boards")
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_lists(self, board_id: str) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/lists", params={"cards": "none"})
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_list_cards(self, list_id: str) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/lists/{list_id}/cards")
        if not isinstance(data, list):
            return status, []
        return status, data

    def create_card(
        self,
        id_list: str,
        name: str,
        desc: str | None = None,
        due: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body: dict[str, Any] = {"idList": id_list, "name": name}
        if desc:
            body["desc"] = desc
        if due:
            body["due"] = due
        status, data = self._request("POST", "/cards", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_card(self, card_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/cards/{card_id}", json=fields)
        return status, data if isinstance(data, dict) else {"_data": data}

    def move_card(self, card_id: str, id_list: str) -> tuple[int, dict[str, Any]]:
        return self.update_card(card_id, idList=id_list)

    def delete_card(self, card_id: str) -> tuple[int, Any]:
        status, data = self._request("DELETE", f"/cards/{card_id}")
        return status, data

    def get_card_details(self, card_id: str) -> tuple[int, dict[str, Any]]:
        """Full card: description, due, labels, checklists, members, attachments."""
        status, data = self._request(
            "GET",
            f"/cards/{card_id}",
            params={
                "fields": (
                    "name,desc,due,dueComplete,start,idBoard,idList,labels,"
                    "shortUrl,url,pos,badges"
                ),
                "checklists": "all",
                "members": "true",
                "member_fields": "fullName,username,initials",
            },
        )
        return status, data if isinstance(data, dict) else {"_data": data}
