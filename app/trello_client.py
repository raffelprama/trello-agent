"""HTTP client for Trello REST API v1 — rate limiting, 429 handling, PRD v2 + v3 surface."""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from typing import Any

import httpx

from app.config import HTTP_TIMEOUT_SECONDS, LOG_TRELLO_FULL, TRELLO_BASE_URL, TRELLO_KEY, TRELLO_TOKEN
from app.observability import json_preview, redact_query_params

logger = logging.getLogger(__name__)


def _log_trello_roundtrip(
    method: str,
    path: str,
    status: int,
    data: Any,
    elapsed_ms: float,
    *,
    extra_params: dict[str, Any] | None = None,
    request_json: dict[str, Any] | None = None,
) -> None:
    """One INFO line per completed request; optional full body when LOG_TRELLO_FULL."""
    approx = len(json.dumps(data, default=str)) if data is not None else 0
    extra = ""
    if isinstance(data, list):
        extra = f" list_len={len(data)}"
    elif isinstance(data, dict):
        extra = f" dict_keys={list(data.keys())[:12]}"
    logger.info(
        "[trello] %s %s -> HTTP %s in %.0fms ~%d chars%s",
        method,
        path,
        status,
        elapsed_ms,
        approx,
        extra,
    )
    if extra_params:
        logger.debug("[trello] query_params=%s", redact_query_params(extra_params))
    if LOG_TRELLO_FULL:
        if request_json is not None:
            logger.info("[trello] request_json=%s", json_preview(request_json))
        logger.info("[trello] response_body=%s", json_preview(data))


# Trello: ~100 requests per 10 seconds per token (PRD v2 §7)
RATE_LIMIT_WINDOW_SEC = 10.0
RATE_LIMIT_MAX_REQUESTS = 100

_client_singleton: TrelloClient | None = None


def get_client() -> TrelloClient:
    """Lazy singleton for graph nodes and CLI."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = TrelloClient()
    return _client_singleton


class TrelloClient:
    """Wrapper with key/token, rolling rate limit, 429 Retry-After, and retries on 5xx."""

    def __init__(self) -> None:
        self._client = httpx.Client(
            base_url=TRELLO_BASE_URL,
            timeout=HTTP_TIMEOUT_SECONDS,
            params={"key": TRELLO_KEY, "token": TRELLO_TOKEN},
        )
        self._req_times: deque[float] = deque()
        self._http_trace: list[dict[str, Any]] = []

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TrelloClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _throttle(self) -> None:
        now = time.monotonic()
        cutoff = now - RATE_LIMIT_WINDOW_SEC
        while self._req_times and self._req_times[0] < cutoff:
            self._req_times.popleft()
        if len(self._req_times) >= RATE_LIMIT_MAX_REQUESTS:
            wait = RATE_LIMIT_WINDOW_SEC - (now - self._req_times[0]) + 0.05
            if wait > 0:
                logger.info("Rate limit window full (%s reqs/%.0fs); sleeping %.2fs", RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_SEC, wait)
                time.sleep(wait)
                now = time.monotonic()
                cutoff = now - RATE_LIMIT_WINDOW_SEC
                while self._req_times and self._req_times[0] < cutoff:
                    self._req_times.popleft()
        self._req_times.append(time.monotonic())

    def _request_once(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> tuple[int, Any, httpx.Response]:
        merged: dict[str, Any] = {}
        if params:
            merged.update(params)
        self._throttle()
        resp = self._client.request(method, path, params=merged, json=json)
        status = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = {"_raw": resp.text}
        return status, data, resp

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        max_429_retries: int = 8,
        max_5xx_retries: int = 4,
    ) -> tuple[int, Any]:
        """HTTP request with 429 (Retry-After) and 5xx retries."""
        t0 = time.perf_counter()
        attempt_429 = 0
        attempt_5xx = 0
        while True:
            status, data, resp = self._request_once(method, path, params=params, json=json)
            if status == 429 and attempt_429 < max_429_retries:
                ra = resp.headers.get("Retry-After")
                if ra:
                    try:
                        wait_s = float(ra)
                    except ValueError:
                        wait_s = 1.0
                else:
                    wait_s = min(2.0 ** attempt_429, 60.0)
                logger.warning("Trello 429 %s %s — retry in %.1fs (attempt %s)", method, path, wait_s, attempt_429 + 1)
                time.sleep(wait_s)
                attempt_429 += 1
                continue
            if status >= 500 and attempt_5xx < max_5xx_retries:
                wait_s = min(0.5 * (2**attempt_5xx), 8.0)
                logger.warning("Trello API 5xx %s %s: %s — retry in %.1fs", method, path, status, wait_s)
                time.sleep(wait_s)
                attempt_5xx += 1
                continue
            if status >= 500:
                logger.warning("Trello API 5xx %s %s: %s", method, path, status)
            if status >= 400 and status != 429:
                logger.warning("Trello API client error %s %s: %s", method, path, status)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            merged_params = dict(params) if params else None
            _log_trello_roundtrip(
                method,
                path,
                status,
                data,
                elapsed_ms,
                extra_params=merged_params,
                request_json=json,
            )
            self._http_trace.append({"method": method, "path": path, "status": status})
            return status, data

    def consume_http_trace(self) -> list[dict[str, Any]]:
        out = list(self._http_trace)
        self._http_trace.clear()
        return out

    # --- Member ---

    def get_member_me(self) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", "/members/me")
        return status, data if isinstance(data, dict) else {"_data": data}

    def list_boards(self, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", "/members/me/boards", params=dict(params) if params else None)
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_member_cards(self, member_id: str = "me", **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/members/{member_id}/cards", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def update_member_me(self, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", "/members/me", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_my_notifications(self, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", "/members/me/notifications", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_my_organizations(self, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", "/members/me/organizations", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    # --- Board ---

    def get_board(self, board_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/boards/{board_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def create_board(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        status, data = self._request("POST", "/boards", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_board(self, board_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/boards/{board_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_board(self, board_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/boards/{board_id}")

    def get_board_memberships(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/memberships", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def add_board_member(self, board_id: str, member_id: str, member_type: str = "normal") -> tuple[int, dict[str, Any]]:
        status, data = self._request(
            "PUT",
            f"/boards/{board_id}/members/{member_id}",
            json={"type": member_type},
        )
        return status, data if isinstance(data, dict) else {"_data": data}

    def remove_board_member(self, board_id: str, member_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/boards/{board_id}/members/{member_id}")

    def get_board_custom_fields(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/customFields", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_lists(
        self,
        board_id: str,
        *,
        cards: str = "none",
        fields: str | None = None,
    ) -> tuple[int, list[dict[str, Any]]]:
        p: dict[str, Any] = {"cards": cards}
        if fields:
            p["fields"] = fields
        status, data = self._request("GET", f"/boards/{board_id}/lists", params=p)
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_cards(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/cards", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_members(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/members", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_labels(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/labels", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_checklists(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/checklists", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_board_actions(self, board_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/boards/{board_id}/actions", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def create_board_label(self, board_id: str, name: str, color: str | None = None) -> tuple[int, dict[str, Any]]:
        body: dict[str, Any] = {"name": name}
        if color:
            body["color"] = color
        status, data = self._request("POST", f"/boards/{board_id}/labels", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    def create_list_on_board(self, board_id: str, name: str, pos: str | float | None = None) -> tuple[int, dict[str, Any]]:
        """POST /1/lists — official Trello API."""
        body: dict[str, Any] = {"name": name, "idBoard": board_id}
        if pos is not None:
            body["pos"] = pos
        status, data = self._request("POST", "/lists", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    # --- List ---

    def get_list(self, list_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/lists/{list_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_list(self, list_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/lists/{list_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def archive_list(self, list_id: str, closed: bool = True) -> tuple[int, dict[str, Any]]:
        return self.update_list(list_id, closed=closed)

    def put_list_closed(self, list_id: str, value: bool) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/lists/{list_id}/closed", json={"value": value})
        return status, data if isinstance(data, dict) else {"_data": data}

    def put_list_pos(self, list_id: str, value: str | float) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/lists/{list_id}/pos", json={"value": value})
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_list_cards(self, list_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/lists/{list_id}/cards", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def archive_all_cards_in_list(self, list_id: str) -> tuple[int, Any]:
        return self._request("POST", f"/lists/{list_id}/archiveAllCards")

    def move_all_cards(self, list_id: str, body: dict[str, Any]) -> tuple[int, Any]:
        return self._request("POST", f"/lists/{list_id}/moveAllCards", json=body)

    # --- Card ---

    def get_card(self, card_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/cards/{card_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_card_details(self, card_id: str) -> tuple[int, dict[str, Any]]:
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
        status, data = self._request("PUT", f"/cards/{card_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def move_card(self, card_id: str, id_list: str) -> tuple[int, dict[str, Any]]:
        return self.update_card(card_id, idList=id_list)

    def delete_card(self, card_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/cards/{card_id}")

    def put_card_closed(self, card_id: str, value: bool) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/cards/{card_id}/closed", json={"value": value})
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_card_member(self, card_id: str, member_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/cards/{card_id}/idMembers/{member_id}")

    def get_card_custom_field_items(self, card_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/cards/{card_id}/customFieldItems", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def set_card_custom_field_item(
        self,
        card_id: str,
        custom_field_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """PUT /cards/{id}/customField/{idCustomField}/item — body per PRD §6.10.2."""
        status, data = self._request(
            "PUT",
            f"/cards/{card_id}/customField/{custom_field_id}/item",
            json=body,
        )
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_card_checklists(self, card_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/cards/{card_id}/checklists", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def post_card_checklist(self, card_id: str, name: str) -> tuple[int, dict[str, Any]]:
        status, data = self._request("POST", f"/cards/{card_id}/checklists", json={"name": name})
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_card_actions(self, card_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/cards/{card_id}/actions", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_card_attachments(self, card_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/cards/{card_id}/attachments", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_card_attachment(self, card_id: str, attachment_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request(
            "GET",
            f"/cards/{card_id}/attachments/{attachment_id}",
            params=dict(params),
        )
        return status, data if isinstance(data, dict) else {"_data": data}

    def post_card_attachment_url(
        self,
        card_id: str,
        url: str,
        name: str | None = None,
        mime_type: str | None = None,
    ) -> tuple[int, dict[str, Any]]:
        body: dict[str, Any] = {"url": url}
        if name:
            body["name"] = name
        if mime_type:
            body["mimeType"] = mime_type
        status, data = self._request("POST", f"/cards/{card_id}/attachments", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_card_attachment(self, card_id: str, attachment_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/cards/{card_id}/attachments/{attachment_id}")

    def post_card_comment(self, card_id: str, text: str) -> tuple[int, dict[str, Any]]:
        status, data = self._request("POST", f"/cards/{card_id}/actions/comments", json={"text": text})
        return status, data if isinstance(data, dict) else {"_data": data}

    def post_card_member(self, card_id: str, member_id: str) -> tuple[int, Any]:
        return self._request("POST", f"/cards/{card_id}/idMembers", params={"value": member_id})

    def post_card_label(self, card_id: str, label_id: str) -> tuple[int, Any]:
        return self._request("POST", f"/cards/{card_id}/idLabels", params={"value": label_id})

    def delete_card_label(self, card_id: str, label_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/cards/{card_id}/idLabels/{label_id}")

    def put_card_due(self, card_id: str, due: str | None) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/cards/{card_id}/due", json={"value": due})
        return status, data if isinstance(data, dict) else {"_data": data}

    def put_card_due_complete(self, card_id: str, due_complete: bool) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/cards/{card_id}/dueComplete", json={"value": due_complete})
        return status, data if isinstance(data, dict) else {"_data": data}

    def put_check_item_state(self, card_id: str, check_item_id: str, state: str) -> tuple[int, dict[str, Any]]:
        """state: 'complete' | 'incomplete' (PRD v2 §5.5)."""
        status, data = self._request(
            "PUT",
            f"/cards/{card_id}/checkItem/{check_item_id}",
            json={"state": state},
        )
        return status, data if isinstance(data, dict) else {"_data": data}

    # --- Checklist ---

    def get_checklist(self, checklist_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/checklists/{checklist_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_checklist(self, checklist_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/checklists/{checklist_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_checklist(self, checklist_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/checklists/{checklist_id}")

    def get_checklist_check_items(self, checklist_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/checklists/{checklist_id}/checkItems", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def create_check_item(self, checklist_id: str, name: str, pos: str | None = "bottom") -> tuple[int, dict[str, Any]]:
        body: dict[str, Any] = {"name": name}
        if pos:
            body["pos"] = pos
        status, data = self._request("POST", f"/checklists/{checklist_id}/checkItems", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_check_item(self, checklist_id: str, check_item_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/checklists/{checklist_id}/checkItems/{check_item_id}")

    # --- Actions ---

    def get_action(self, action_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/actions/{action_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_action_comment(self, action_id: str, text: str) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/actions/{action_id}", json={"text": text})
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_action(self, action_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/actions/{action_id}")

    # --- Labels ---

    def get_label(self, label_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/labels/{label_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_label(self, label_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/labels/{label_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_label(self, label_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/labels/{label_id}")

    # --- Custom fields (PRD v3 §6.10) ---

    def create_custom_field(self, board_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """POST /customFields — body must include idModel (board id), name, type."""
        payload = dict(body)
        payload.setdefault("idModel", board_id)
        status, data = self._request("POST", "/customFields", json=payload)
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_custom_field(self, custom_field_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/customFields/{custom_field_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_custom_field(self, custom_field_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/customFields/{custom_field_id}")

    def get_custom_field_options(self, custom_field_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/customFields/{custom_field_id}/options", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def add_custom_field_option(self, custom_field_id: str, text: str) -> tuple[int, dict[str, Any]]:
        status, data = self._request(
            "POST",
            f"/customFields/{custom_field_id}/options",
            json={"value": {"text": text}},
        )
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_custom_field_option(self, custom_field_id: str, option_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/customFields/{custom_field_id}/options/{option_id}")

    # --- Webhooks (PRD v3 §6.11) ---

    def list_token_webhooks(self) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/tokens/{TRELLO_TOKEN}/webhooks")
        if not isinstance(data, list):
            return status, []
        return status, data

    def create_webhook(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        status, data = self._request("POST", "/webhooks", json=body)
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_webhook(self, webhook_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/webhooks/{webhook_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_webhook(self, webhook_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/webhooks/{webhook_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def delete_webhook(self, webhook_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/webhooks/{webhook_id}")

    # --- Organizations (PRD v3 §6.12) ---

    def get_organization(self, org_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/organizations/{org_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def get_organization_boards(self, org_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/organizations/{org_id}/boards", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_organization_members(self, org_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/organizations/{org_id}/members", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def get_organization_memberships(self, org_id: str, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", f"/organizations/{org_id}/memberships", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    def update_organization_member(self, org_id: str, member_id: str, member_type: str) -> tuple[int, dict[str, Any]]:
        status, data = self._request(
            "PUT",
            f"/organizations/{org_id}/members/{member_id}",
            json={"type": member_type},
        )
        return status, data if isinstance(data, dict) else {"_data": data}

    def remove_organization_member(self, org_id: str, member_id: str) -> tuple[int, Any]:
        return self._request("DELETE", f"/organizations/{org_id}/members/{member_id}")

    # --- Search (PRD v3 §6.13) ---

    def search(self, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", "/search", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def search_members(self, **params: Any) -> tuple[int, list[dict[str, Any]]]:
        status, data = self._request("GET", "/search/members", params=dict(params))
        if not isinstance(data, list):
            return status, []
        return status, data

    # --- Notifications (PRD v3 §6.14) ---

    def get_notification(self, notification_id: str, **params: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("GET", f"/notifications/{notification_id}", params=dict(params))
        return status, data if isinstance(data, dict) else {"_data": data}

    def update_notification(self, notification_id: str, **fields: Any) -> tuple[int, dict[str, Any]]:
        status, data = self._request("PUT", f"/notifications/{notification_id}", json=dict(fields))
        return status, data if isinstance(data, dict) else {"_data": data}

    def mark_all_notifications_read(self) -> tuple[int, Any]:
        return self._request("PUT", "/notifications/all/read")
