from __future__ import annotations

import asyncio
import base64
from unittest.mock import patch

from nocfo_toolkit.mcp.curated.bookkeeping.tag_file import bookkeeping_file_upload
from nocfo_toolkit.mcp.curated.schema.bookkeeping.tag_file import (
    FileUploadSpec,
    FileUploadsInput,
)


def test_file_upload_spec_accepts_legacy_name_alias() -> None:
    spec = FileUploadSpec.model_validate(
        {
            "name": "legacy-name.txt",
            "file_base64": base64.b64encode(b"payload").decode("ascii"),
        }
    )
    assert spec.filename == "legacy-name.txt"


def test_bookkeeping_file_upload_sends_required_name_form_field() -> None:
    captured: dict[str, object] = {}

    class _FakeClient:
        async def request_multipart(
            self,
            path: str,
            *,
            files: dict[str, object],
            data: dict[str, object] | None = None,
            business_slug: str | None = None,
        ) -> dict[str, object]:
            captured["path"] = path
            captured["files"] = files
            captured["data"] = data
            captured["business_slug"] = business_slug
            return {"id": 1, "name": "legacy-name.txt", "file_name": "legacy-name.txt"}

    async def _run() -> None:
        params = FileUploadsInput.model_validate(
            {
                "business": "demo",
                "files": [
                    {
                        "filename": "legacy-name.txt",
                        "content_type": "text/plain",
                        "file_base64": base64.b64encode(b"payload").decode("ascii"),
                    }
                ],
            }
        )
        with (
            patch(
                "nocfo_toolkit.mcp.curated.bookkeeping.tag_file.business_slug",
                return_value="demo",
            ),
            patch(
                "nocfo_toolkit.mcp.curated.bookkeeping.tag_file.get_client",
                return_value=_FakeClient(),
            ),
        ):
            result = await bookkeeping_file_upload(params)
        assert result["results"][0]["result"]["name"] == "legacy-name.txt"

    asyncio.run(_run())
    assert captured["path"] == "/v1/business/demo/file_upload/"
    assert captured["business_slug"] == "demo"
    assert captured["data"] == {"name": "legacy-name.txt", "type": "text/plain"}
