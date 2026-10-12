"""The panel's record checksum (reverse engineered from OLink, FUN_0057bdd4).

Every record below was captured on a JA-80K (2026-10-12); the checksum from
#152 matches all of them (the CRC8 guesses used before only matched part).
"""

import pytest

from custom_components.jablotron80.jablotron import JablotronMessage

CAPTURED = [
    "ed 21 0b 03 01 00 00 32 00 ff",
    "ed 21 0b 03 01 00 00 1e 3d ff",
    "ed 21 0b 04 01 00 00 32 2a ff",
    "ed 21 0b 04 01 00 00 00 47 ff",
    "ed 21 0b 04 01 00 00 0a 77 ff",
    "ed 21 0b 04 01 00 00 1e 17 ff",
    "ed 21 0b 02 01 00 00 32 0e ff",
    "ed 21 0b 02 01 00 00 00 63 ff",
    "ed 21 0b 02 01 00 00 1e 33 ff",
    "ed 21 0b 02 01 00 00 0a 53 ff",
    "ed 21 0b 05 01 00 00 32 24 ff",
    "ed 21 0b 05 01 00 00 00 49 ff",
    "ed 21 0b 05 01 00 00 1e 19 ff",
    "ed 21 0b 06 01 00 00 32 36 ff",
    "ed 21 0b 06 01 00 00 1e 0b ff",
    "ed 21 0b 06 01 00 00 00 5b ff",
    "ed 21 0b 06 01 00 00 0a 6b ff",
    "ed 21 0b 07 01 00 00 32 38 ff",
    "ed 21 0b 07 01 00 00 0a 65 ff",
    "ed 21 0b 07 01 00 00 00 55 ff",
    "ed 21 0b 07 01 00 00 1e 05 ff",
    "ed 21 0b 07 01 00 00 14 35 ff",
    "ed 21 0b 08 01 00 00 32 62 ff",
    "ed 21 0b 08 01 00 00 00 0f ff",
    "ed 21 0b 08 01 00 00 1e 5f ff",
    "ed 21 0b 09 01 00 00 32 6c ff",
    "ed 21 0b 09 01 00 00 0a 31 ff",
    "ed 21 0b 0a 01 00 00 32 7e ff",
    "ed 21 0b 0a 01 00 00 1e 43 ff",
    "ed 21 0b 0a 01 00 00 00 13 ff",
    "ed 21 0b 0b 01 00 00 32 70 ff",
    "ed 21 0b 0b 01 00 00 1e 4d ff",
    "ed 21 0b 0b 01 00 00 00 1d ff",
    "ed 21 0b 0b 01 00 00 0a 2d ff",
    "ed 21 0b 0c 01 00 00 32 5a ff",
    "ed 21 0b 0c 01 00 00 1e 67 ff",
    "ed 21 0b 0c 01 00 00 0a 07 ff",
    "ed 21 0b 0c 01 00 00 14 57 ff",
    "ed 21 0b 0c 01 00 00 00 37 ff",
    "ed 21 0b 0c 11 00 00 32 1f ff",
    "ed 21 0b 0c 11 00 00 1e 22 ff",
    "ed 21 0b 0c 11 00 00 00 72 ff",
    "ed 21 0b 0c 11 00 00 0a 42 ff",
    "ed 20 0b 0c 01 00 00 32 13 ff",
    "ed 20 02 00 01 00 00 1e 11 ff",
    "ed 20 02 00 01 00 00 0a 71 ff",
    "ed 20 02 00 01 00 00 14 21 ff",
    "ed 40 00 00 01 00 00 00 16 ff",
    "ed 40 00 00 01 00 00 28 75 ff",
    "ed 40 00 00 01 00 00 1e 46 ff",
    "ed 40 00 00 01 00 00 0a 26 ff",
]


@pytest.mark.parametrize("record", CAPTURED)
def test_checksum_of_captured_record_is_zero(record):
    packet = bytes.fromhex(record)
    assert JablotronMessage.checksum(packet[:-1]) == 0


@pytest.mark.parametrize("record", CAPTURED)
def test_check_crc_accepts_captured_record(record):
    assert JablotronMessage.check_crc(bytes.fromhex(record))


def test_check_crc_rejects_corrupted_record():
    packet = bytearray.fromhex("ed 21 0b 0c 11 00 00 32 1f ff")
    packet[3] = 0x0D  # wrong position, checksum no longer fits
    assert not JablotronMessage.check_crc(bytes(packet))


@pytest.mark.parametrize("record", ["a0 ff", "ff"])
def test_check_crc_accepts_records_without_checksum(record):
    assert JablotronMessage.check_crc(bytes.fromhex(record))


def test_checksum_never_sets_top_bit():
    for value in range(256):
        assert JablotronMessage.checksum(bytes([0xED, value])) < 0x80
