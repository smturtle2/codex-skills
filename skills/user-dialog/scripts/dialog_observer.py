"""Confirm an exact submitted response in the originating server's history."""

import time


class ResponseReader:
    def __init__(self, server):
        self.server = server

    def page(self, cursor=None, limit=100):
        params = {"threadId": self.server.origin["thread_id"], "limit": limit, "sortDirection": "desc"}
        if cursor is not None:
            params["cursor"] = cursor
        return self.server.call("thread/items/list", params)

    def bookmark(self):
        entries = self.page(limit=1)["data"]
        return entries[0]["item"]["id"] if entries else None

    def find_response(self, delivery, message):
        cursor, visited, matches = None, set(), []
        while True:
            page = self.page(cursor)
            for entry in page["data"]:
                item = entry["item"]
                if item["id"] == delivery["boundary_item_id"]:
                    return self.unique_match(matches)
                if matches_response(item, delivery, message):
                    matches.append({"item_id": item["id"], "turn_id": entry["turnId"]})
            cursor = page.get("nextCursor")
            if cursor is None:
                if matches or delivery["boundary_item_id"] is None:
                    return self.unique_match(matches)
                raise ValueError("The pre-send history position is no longer available")
            if cursor in visited:
                raise ValueError("Response lookup returned a repeated cursor")
            visited.add(cursor)

    @staticmethod
    def unique_match(matches):
        if len(matches) > 1:
            raise ValueError("Multiple responses matched; automatic confirmation is ambiguous")
        return matches[0] if matches else None

    def wait(self, delivery, message, timeout=60):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.server.check()
            match = self.find_response(delivery, message)
            if match:
                return match
            self.server.cancel.wait(0.25)
        raise TimeoutError("The response has not appeared in task history yet")


def matches_response(item, delivery, message):
    content = item.get("content", [])
    return (item.get("type") == "userMessage" and item.get("clientId") == delivery["client_message_id"]
            and len(content) == 1 and content[0].get("type") == "text"
            and content[0].get("text") == message)
