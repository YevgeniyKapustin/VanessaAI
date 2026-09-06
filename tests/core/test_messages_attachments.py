from vanessa.core.messages_attachments import (
    ImageAttachment,
    attachments_from_dicts,
    attachments_to_dicts,
    image_attachment_from_dict,
    image_attachment_to_dict,
)


def test_image_attachment_roundtrip_via_functions():
    original = ImageAttachment(
        data_url="data:image/png;base64,abc",
        mime_type="image/png",
        telegram_file_id="file-1",
        description="cat",
    )
    payload = image_attachment_to_dict(original)
    restored = image_attachment_from_dict(payload)
    assert restored == original


def test_image_attachment_class_aliases_match_functions():
    original = ImageAttachment(data_url="data:image/jpeg;base64,xyz")
    assert original.to_dict() == image_attachment_to_dict(original)
    raw = {"data_url": "data:image/jpeg;base64,xyz", "mime_type": None}
    assert ImageAttachment.from_dict(raw) == image_attachment_from_dict(raw)


def test_attachments_batch_helpers():
    items = (ImageAttachment(data_url="data:image/jpeg;base64,a"),)
    encoded = attachments_to_dicts(items)
    assert attachments_from_dicts(encoded) == items
    assert attachments_from_dicts(None) == ()
    assert attachments_from_dicts([{"data_url": "x"}, "skip"]) == (
        ImageAttachment(data_url="x"),
    )
