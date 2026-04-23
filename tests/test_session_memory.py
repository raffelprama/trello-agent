"""Session memory merge and extraction."""

from app.session.session_memory import empty_memory, extract_from_plan_parsed, merge_memory


def test_merge_memory_settings_deep() -> None:
    a = empty_memory()
    a["settings"]["dry_run"] = True
    b = merge_memory(a, {"settings": {"timezone": "UTC"}})
    assert b["settings"]["dry_run"] is True
    assert b["settings"]["timezone"] == "UTC"


def test_extract_custom_fields_and_mentions() -> None:
    parsed = {
        "custom_fields": [{"id": "cf1", "name": "Priority"}],
        "webhooks": [{"id": "w1", "description": "hook", "idModel": "b1"}],
        "card": {"id": "c1", "name": "T"},
    }
    ent = {"list_id": "l1", "card_id": "c1"}
    out = extract_from_plan_parsed(parsed, ent)
    assert out["custom_field_map"] == [{"id": "cf1", "name": "Priority"}]
    assert out["webhook_map"][0]["id"] == "w1"
    assert out["last_mentioned_list_id"] == "l1"
    assert out["last_mentioned_card_id"] == "c1"
