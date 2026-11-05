"""Keypad logo upload, checked against what OLink 2.0.6 sent (capture 2026-11-05)."""

import pytest

from custom_components.jablotron80 import jablotron
from custom_components.jablotron80.jablotron import (
    JablotronConnectionSerial,
    JablotronKeypadImage,
    JablotronMenuError,
)
from tests.test_bypass import _build_unit

# rows of the uploaded logo as OLink sent them
CAPTURED = [
    "ec 10 00 00 2c ff",
    "ec 10 01 10 10 10 10 10 10 1c 10 00 21 ff",
    "ec 10 02 10 10 10 10 10 11 1e 10 00 5f ff",
    "ec 10 2e 13 1f 1f 1f 1f 10 11 1f 1f 1f 1f 1f 10 11 10 11 14 12 14 12 14 18 14 14 12 11 19 10 14 14 00 71 ff",
    "ec 10 2f 13 1f 1f 1f 1f 18 11 1f 1f 1f 1f 1f 10 11 10 11 13 1c 13 1c 14 17 18 13 11 1e 19 10 14 13 00 28 ff",
]


def _pixels(record: bytes) -> list:
    """The dark pixels of one captured row (the inverse of the encoding)."""
    nibbles = [b - 0x10 for b in record[3:-3]]
    row = [False] * JablotronKeypadImage.WIDTH
    for i, nibble in enumerate(nibbles):
        for bit in range(4):
            if nibble & (0x8 >> bit):
                row[i * 4 + bit] = True
    return row


@pytest.mark.parametrize("captured", CAPTURED)
def test_row_matches_olink(captured):
    record = bytes.fromhex(captured)
    assert JablotronKeypadImage.row_record(record[2], _pixels(record)) == record


def test_sends_at_most_49_rows_like_olink():
    blank = [[False] * 128 for _ in range(50)]
    rows = JablotronKeypadImage.rows(blank)
    assert len(rows) == 49
    assert rows[0] == bytes.fromhex("ec 10 00 00 2c ff")
    assert rows[-1] == bytes.fromhex("ec 10 30 00 58 ff")


@pytest.mark.parametrize("width, height", [(129, 10), (128, 51), (0, 0)])
def test_rejects_wrong_size(width, height):
    with pytest.raises(ValueError):
        JablotronKeypadImage.rows([[False] * width for _ in range(height)])


@pytest.mark.parametrize(
    "rgb, dark",
    [((0, 0, 0), True), ((0x7F, 0x7F, 0x7F), True), ((0x80, 0, 0), False), ((0x1B, 0xBB, 0xF0), False)],
)
def test_dark_threshold(rgb, dark):
    assert JablotronKeypadImage.is_dark(*rgb) is dark


class FakeSerial(JablotronConnectionSerial):
    def __init__(self):
        super().__init__("socket://test")
        self.sent = []

    async def add_command(self, command):
        assert command.raw
        self.sent.append(command.code)
        command.confirm(True)


def _upload(loop, state, pixels):
    jablotron._loop = loop
    unit = _build_unit()
    unit._connection = FakeSerial()
    unit._last_state = state
    JablotronKeypadImage.ROW_INTERVAL = 0
    loop.run_until_complete(unit.upload_keypad_image(pixels))
    return unit._connection.sent


def test_upload_in_service_mode(event_loop_for_setters):
    pixels = [_pixels(bytes.fromhex(CAPTURED[1]))] * 3
    sent = _upload(event_loop_for_setters, 0x00, pixels)
    assert len(sent) == 3
    assert sent[1] == JablotronKeypadImage.row_record(1, pixels[1])


@pytest.mark.parametrize("state", [0x40, 0x20, None])
def test_upload_refused_outside_service_mode(event_loop_for_setters, state):
    with pytest.raises(JablotronMenuError):
        _upload(event_loop_for_setters, state, [[False] * 128])
