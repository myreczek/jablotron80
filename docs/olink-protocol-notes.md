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

* Read: `EC 40 0C 00` … `EC 40 0C 07` (8 lists). Parser `FUN_0053cfbc`:
  reply `EC 00 00` = end of list → next list; `EC 38 04 …` = error/status
  (`rec[4]/100 < 8` …); `EC 20..27 …` = data. **[code]** Record layout of the
  data replies still to be decoded.
* Write: `SETUP_SINGLE_TEXT_UNICODE` sends one text record; reply `EC 00 00` =
  OK, `EC 00 xx` = error. Record encoding: `FUN_0059b810` / `FUN_0059b744`
  (to do).

## Logo picture (`JA80_SET_PICTURE`)

* UI: 128×55 px, monochrome (EN.lng 02242).
* `FUN_0053e614`: source is a text buffer — chars 1–3 = block length,
  chars 5–7 = block count (max 49), data from char 9; block *i* is sent as
  `EC 10 <i> <bytes…>`, ~80 ms apart. Bytes are written as comma-separated
  numbers (`$` = hex) and parsed by `FUN_004cffd4`. **[code]**
* Bitmap → buffer conversion (bit order, packing) not located yet.
