# OLink 2.0.6.994 — reverse engineering notes

Source: `OLink-2.0.6.994-setup.exe` (Inno Setup 5.5.6) → `OLink.exe`, Delphi/VCL,
32-bit x86. Analysed with Ghidra 12.1.4 (headless). Addresses below are VAs in
`OLink.exe` (image base `0x400000`).

Confidence markers: **[code]** = read directly from decompiled code,
**[manual]** = from JA-80 user manual / inference, **[unverified]** = needs a
capture from a real panel.

## Command dispatcher

`FUN_0058099c` is a `case` over the OLink command enum. Names live in an
`array[0..] of string[255]` at `0x62c630` (pointer `0x638ac0`). Each command
gets a *request builder* and a *response parser*. **[code]**

| idx | name | builder | parser |
|----:|------|---------|--------|
| 0 | `JA80_SEND_KEYS` | `004cc21c` | `004cbd78` |
| 1 | `JA80_RQ_EVENT_LIST` | `0057d3d8` | `0057d1ac` |
| 2 | `JA80_RQ_PERIPHERAL_LIST` | – | – |
| 5 | `JA80_RQ_ALL_TEXTS` | `0053d3d8` | `0053cfbc` |
| 6–13 | `JA80_RQ_TEXT_LIST1..8` | `0053d3d8` | `0053cfbc` |
| 19 | `JA80_SETUP_SINGLE_TEXT_UNICODE` | `0053d454` | `0053d1dc` |
| 20 | `JA80_SETUP_ALL_TEXTS_UNICODE` | `0053d704` | `0053d1dc` |
| 24 | `JA80_RQ_BYPASS_SETUP` | `0057db5c` | `0057d9d0` |
| 25 | `JA80_SETUP_BYPASS` | `0057de70` | `0057dbb4` |
| 26/27 | `JA80_RQ/SETUP_PHONE_COMMUNICATOR` | `004cc9c4`/`004cca24` | `004cc834`/`004cccec` |
| 41 | `JA80_SEND_KEYS_NO_TERMINATION` | `004cc21c` | `004cbd78` |
| 46 | `JA80_SET_PICTURE` | `0053e890` | `0053e4a0` |
| 47 | `JA80_SET_PICTURE_WITHOUT_CENTRAL` | `0053e614` | `0053e564` |

There is **no GET_PICTURE** command in this OLink version.

## Programming packets (`0xEC` family)

`FUN_004d0178(prefix, cmd, payload, out, term)` builds packets starting with
`0xEC`; panel replies also start with `0xEC`. **[code]**

| cmd | bytes |
|-----|-------|
| RQ_TEXT_LISTn (6–13) | `EC 40 0C <n-1>` |
| RQ_COMMUNICATOR (14) | `EC 40 07` |
| RQ_PCO_SETUP (15) | `EC 40 0A` |
| 16 / 17 | `EC 40 09` / `EC 40 0B` |
| ENTER_PCO_CODE (18) | `EC 40 08 <payload> 00` |
| SINGLE/ALL TEXT (19–21) | `EC <payload[1]+0x60> <payload[2..]>` |
| RQ/SETUP_PHONE_COMM (26/27) | `EC 7F 01` / `EC 7F <payload>` |
| SET_PICTURE (46/47) | `EC 10 <block#> <bytes…> [10] 00` |

Terminator: `FF` when `term == 0`, otherwise a 7-bit checksum byte + `term`.

### Checksum `FUN_0057bdf0` / `FUN_0057bdd4` **[code]**

```python
def olink_crc(data: bytes) -> int:
    r = 0x7F
    for b in data:
        for _ in range(8):
            r = (r << 1) & 0xFF
            if b & 0x80:
                r |= 1
            if r & 0x80:
                r ^= 0xA3          # poly x^7+x^5+x+1 (0x23), bit 7 cleared
            b = (b << 1) & 0xFF
    return r
```

**[verified on JA-80K capture]** The panel checksum is
`olink_crc(data + b"\x00")` where `data` = record without the checksum byte and
the `FF` terminator (one zero byte is shifted through the register to flush
it). Matches 8/8 captured records, whereas each of the two `crccheck`
variants in `JablotronMessage.check_crc` only matches about half of them —
which is why the integration currently needs both.

| record | olink_crc(data+00) |
|--------|-------|
| `ed 21 0b 04 01 00 00 32 2a ff` | `2a` |
| `ed 21 0b 0c 11 00 00 32 1f ff` | `1f` |
| `ed 40 00 00 01 00 00 28 75 ff` | `75` |

## Bypass (`JA80_RQ_BYPASS_SETUP` / `JA80_SETUP_BYPASS`)

Not a programming packet: OLink drives the **keypad menu** by sending keys via
`FUN_004cc194` (→ `JA80_SEND_KEYS`). **[code]**

* Read: send `1` repeatedly (54 iterations max). After each step the panel
  sends a status record whose first byte is `0xED` or `0xF0`
  (`FUN_004b191c`) with:
  * `rec[2] & 0x60 == 0x20` and `rec[2] & 0x1F == 1`
  * `rec[3]` = peripheral position
  * `(rec[4] >> 4) & 3` = bypass state: `0` none, `1` partial (one setting),
    `2`/`3` full (permanent)
  * loop ends when the position repeats; then `#` is sent to leave.
* Write (`FUN_0057dda4` chooses the key for the current position):

  | current → wanted | key |
  |------------------|-----|
  | 0 → 1 | `2` |
  | 0 → 2 | `3` |
  | 1 → 2 | `3` |
  | 1 → 0 | `2` |
  | 2 → any | `3` |
  | otherwise / next position | `1` |

* Entering the bypass menu (Oasis user manual MKE22103, ch. 13 + 16)
  **[manual]**: system fully unset → `*0` + master code = *Údržba*
  (maintenance) mode → `1` = Bypass menu → ▲/▼ browse, `2` = bypass for one
  setting period, `3` = permanent, `4` = clear all bypasses → `#` leaves
  Bypass, second `#` leaves maintenance. OLink's leading `1` is the "enter
  Bypass" key, so the talker assumes maintenance mode is already active.

Captured on JA-80K (2026-10-12, sensor 12 bypassed for one period and back):

```
ed 21 0b 0b 01 00 00 32 70 ff   bypass menu, position 11, state 0
ed 21 0b 0c 01 00 00 32 5a ff   position 12, state 0
ed 21 0b 0c 11 00 00 32 1f ff   position 12, state 1 (key 2)
ed 21 0b 0c 01 00 00 32 5a ff   position 12, state 0 (key 2 again)
ed 20 0b 0c 01 00 00 32 13 ff   leaving bypass (#)
ed 20 02 00 01 00 00 1e 11 ff   maintenance mode
ed 40 00 00 01 00 00 00 16 ff   normal (unset) status
```

Byte `[7]` cycles through `00/0a/14/1e/28/32` regardless of state (likely a
rotating sub-field, e.g. LED/RF info) — ignore for bypass.

UI labels (EN.lng 11800–11807): Pos / Name / Bypass (None / Partial / Full) / Type.

## Texts (device / code names)

* Read request: `EC 40 0C nn <crc7> FF`, nn = 00..07 (8 lists). **[code]**
* On a JA-80K (firmware id below) every list answers `EC 00 00` (empty) - in
  unset, maintenance and service mode alike, also right after `RQ_DEVICE_ID`.
  The keypad shows custom names, so they are stored elsewhere (the wireless
  JA-81F keypad keeps its own texts). **[tested 2026-10-12]**
* `RQ_DEVICE_ID`: `E8 0D 22 FF` -> `B7 FF`, `E5 11 11 06 05 6F FF`. OLink sends
  it before every text/picture operation (`FUN_0053caf4`). **[tested]**
* Text encoding (`FUN_0059cb40`), 7-bit safe: `20..7F` ASCII; `10..17 b1` =
  `((b0 & 7) << 7) | (b1 & 0x7F)` (U+0000..03FF, e.g. "a-acute" = `11 61`);
  `18..1B b1 b2` = `((b0 & 3) << 14) | ((b1 & 0x7F) << 7) | (b2 & 0x7F)`.
* Text address -> group: `FUN_0059cd7c` (byte 2 of the 24-bit text id).
* Upload loop: `FUN_0053caf4` (one record per packet, waits for an ack).

## Logo picture (`JA80_SET_PICTURE`)

Format fully decoded (`FUN_0053ddd8`, `FUN_0053e614`, `FUN_004d0178` case
0x2e) **[code]**:

* width <= 128, height <= 50 rows (UI hint says 128x55); a pixel is 1 when
  dark (all of R, G, B < 0x80 and R+G+B < 0x180)
* one packet per row: row bytes MSB = leftmost pixel, each byte split into two
  nibbles sent as `0x10 + nibble`; trailing zero nibbles dropped, padded to an
  even nibble count with `10`:
  `EC 10 <row> <nibbles...> 00 <crc7> FF`, ~80 ms apart
* no reply from the panel; OLink only waits for its own packet to come back
  as the bus echo - the picture goes over the wired bus straight to the keypads.

Tested on a JA-80K through its serial port (no bus echo) with a wireless
JA-81F keypad: all 48 rows sent in unset, maintenance and service mode, the
keypad kept its old logo. Wireless keypads are programmed directly
(`JA80_SET_PICTURE_WITHOUT_CENTRAL`, keypad cabled to the PC); with a wired
JA-81E on the bus it may work. There is no GET_PICTURE command.
