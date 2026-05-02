"""Coordinator for Reef Factory X3 Dosing Pump.

Connects to the Reef Factory Smart Reef WebSocket API, authenticates,
subscribes to a dosing pump device, and parses the binary data frames.

Protocol summary:
  - WebSocket: wss://api.reeffactory.com:443/controler, subprotocol "reeffactory"
  - Login: identical to KH Keeper (namespace="user", command="login")
  - Subscribe: namespace="dxConnect", command="join"
  - Data push: namespace="dxRefresh", command="settings"
    Payload starts with channel_id u8, then per-channel struct.

Per-channel struct (volume scale 1/100, all integers big-endian):
  container_current:  s32/100 ml
  container_capacity: s32/100 ml
  pump_mode:          u8
  [4 bytes skipped]
  calib_day:          u8
  calib_month:        u8
  calib_year:         u16
  calib_alert:        u8
  today_dosed:        s32/100 ml
  daily_dose_max:     s32/100 ml
  state1:             u8
  state2:             u8
  refill_curr:        s32/100 ml
  refill_tgt:         s32/100 ml
  num_doses:          u8
  [num_doses × 7 bytes schedule entries]
  queue_mode:         u8
  [16 bytes fill state]
  extra_day_index:    u8
  manual_refill_mode: u8
  history_count:      u8
  [history_count × 15 bytes history entries]
  day_flags:          u8
  alert_flags:        u8
  pump_name:          32 bytes (16 × u16 BE UTF-16, null-terminated)
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import date, datetime, timezone
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ACTION_TYPES,
    CHANNELS,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_SERIAL,
    DOMAIN,
    SCALE,
    UPDATE_INTERVAL,
    WS_MAX_MESSAGES,
    WS_PROTOCOL,
    WS_RECEIVE_TIMEOUT,
    WS_TIMEOUT,
    WS_URL,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Wire encoding / decoding (shared with KH integration)
# ---------------------------------------------------------------------------

def _encode_message(
    namespace: str,
    command: str,
    payload: bytes = b"",
    serial: str = "0000000000000000",
    session: str = "",
) -> bytes:
    out = bytearray()
    out += serial.encode("latin-1") + b"\x00"
    out += namespace.encode("latin-1") + b"\x00"
    out += command.encode("latin-1") + b"\x00"
    out += session.encode("latin-1") + b"\x00"
    out += payload
    out += b"\x00"
    return bytes(out)


def _decode_message(data: bytes) -> tuple[str, str, str, str, bytes]:
    buf = bytearray(data)
    parts: list[str] = []
    i = 0
    for _ in range(4):
        end = buf.index(0, i)
        parts.append(buf[i:end].decode("latin-1"))
        i = end + 1
    payload = bytes(buf[i:])
    if payload.endswith(b"\x00"):
        payload = payload[:-1]
    serial, namespace, command, session = parts
    return serial, namespace, command, session, payload


def _build_login_payload(email: str, password: str) -> bytes:
    out = email.encode("latin-1") + b"\x00"
    out += password.encode("latin-1") + b"\x00"
    out += b"\x00"
    return out


# ---------------------------------------------------------------------------
# Binary struct parser for dxRefresh/settings
# ---------------------------------------------------------------------------

def _parse_dx_settings(payload: bytes, today: date) -> list[dict[str, Any]]:
    """Parse a dxRefresh/settings payload into a list of per-channel data dicts.

    The device sends all channels in a single message. The first byte is the
    starting channel_id (0-indexed); the remaining bytes are sequential
    per-channel structs with no additional channel_id prefix between them.
    """
    pos = 0

    def u8() -> int:
        nonlocal pos
        if pos >= len(payload):
            raise IndexError(f"u8 read past end at pos={pos}")
        v = payload[pos]
        pos += 1
        return v

    def u16() -> int:
        nonlocal pos
        if pos + 1 >= len(payload):
            raise IndexError(f"u16 read past end at pos={pos}")
        v = (payload[pos] << 8) | payload[pos + 1]
        pos += 2
        return v

    def s32() -> float:
        nonlocal pos
        if pos + 3 >= len(payload):
            raise IndexError(f"s32 read past end at pos={pos}")
        v = int.from_bytes(payload[pos : pos + 4], "big", signed=True)
        pos += 4
        return v * SCALE

    def skip(n: int) -> None:
        nonlocal pos
        pos += n

    results: list[dict[str, Any]] = []

    try:
        starting_channel_id = u8()
        _LOGGER.debug("dxRefresh/settings starting_channel_id=%d payload_len=%d", starting_channel_id, len(payload))
        _LOGGER.debug("Full payload hex: %s", payload.hex())

        channel_index = starting_channel_id
        while pos < len(payload):
            channel_start = pos
            container_current = round(s32(), 2)
            container_capacity = round(s32(), 2)
            skip(1)   # pump_mode
            skip(4)   # 4 unknown bytes
            skip(1)   # calib_day
            skip(1)   # calib_month
            skip(2)   # calib_year
            skip(1)   # calib_alert
            today_dosed = round(s32(), 2)
            daily_dose_max = round(s32(), 2)
            skip(1)   # state1
            skip(1)   # state2
            skip(4)   # refill_curr
            skip(4)   # refill_tgt

            num_doses = u8()
            skip(num_doses * 7)  # schedule entries: s32 volume + u16 time + u8 status

            skip(1)   # queue_mode
            skip(16)  # fill state: 4 × s32
            skip(1)   # extra_day_index
            skip(1)   # manual_refill_mode

            history_count = u8()
            actions_today = 0
            for _ in range(history_count):
                _dose_value = s32()
                _manual_value = s32()
                year = u16()
                month = u8()
                day = u8()
                _hour = u8()
                _minute = u8()
                entry_type = u8()
                try:
                    entry_date = date(year, month, day)
                except (ValueError, OverflowError):
                    entry_date = None
                if entry_date == today and entry_type in ACTION_TYPES:
                    actions_today += 1

            skip(1)   # day_flags
            skip(1)   # alert_flags
            skip(32)  # pump_name: 16 × u16 BE UTF-16

            _LOGGER.debug(
                "Channel %d (bytes %d-%d): container=%.2f/%.2f ml, today_dosed=%.2f ml, actions_today=%d",
                channel_index, channel_start, pos - 1,
                container_current, container_capacity, today_dosed, actions_today,
            )

            results.append({
                "channel_id": channel_index,
                "container_current": container_current,
                "container_capacity": container_capacity,
                "today_dosed": today_dosed,
                "daily_dose_max": daily_dose_max,
                "actions_today": actions_today,
            })
            channel_index += 1

    except (IndexError, ValueError, OverflowError) as exc:
        if results:
            _LOGGER.debug("Stopped parsing after %d channels at pos=%d (trailing bytes): %s", len(results), pos, exc)
        else:
            _LOGGER.warning("Failed to parse dxRefresh/settings at pos=%d: %s", pos, exc)
            _LOGGER.debug("Full payload hex (%d bytes): %s", len(payload), payload.hex())

    return results


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class ReefFactoryDoseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetches X3 Dosing Pump data from the Reef Factory WebSocket API."""

    def __init__(self, hass: HomeAssistant, entry_data: dict[str, Any]) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"Reef Factory X3 Dose {entry_data[CONF_SERIAL]}",
            update_interval=UPDATE_INTERVAL,
        )
        self.email: str = entry_data[CONF_EMAIL]
        self.password: str = entry_data[CONF_PASSWORD]
        self.serial: str = entry_data[CONF_SERIAL]

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(
                self._fetch_dose_data(), timeout=WS_TIMEOUT
            )
        except asyncio.TimeoutError as exc:
            raise UpdateFailed("Timed out communicating with Reef Factory API") from exc

    async def _fetch_dose_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)

        async with session.ws_connect(
            WS_URL,
            protocols=[WS_PROTOCOL],
            receive_timeout=WS_RECEIVE_TIMEOUT,
        ) as ws:
            await ws.send_bytes(
                _encode_message(
                    "user", "login", _build_login_payload(self.email, self.password)
                )
            )
            await self._expect_login_ok(ws)

            join_token = f"join_{int(time.time() * 1000)}"
            await ws.send_bytes(
                _encode_message(
                    "dxConnect",
                    "join",
                    self.serial.encode("latin-1") + b"\x00",
                    self.serial,
                    join_token,
                )
            )

            return await self._collect_dx_messages(ws)

    async def _expect_login_ok(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        for _ in range(WS_MAX_MESSAGES):
            msg = await ws.receive()
            if msg.type == aiohttp.WSMsgType.BINARY:
                try:
                    _, ns, cmd, _, payload = _decode_message(msg.data)
                    _LOGGER.debug("Login rx: ns=%s cmd=%s", ns, cmd)
                    if ns == "status":
                        if payload[:2] == b"ok":
                            return
                        raise UpdateFailed(
                            "Reef Factory login rejected — check email and password"
                        )
                except UpdateFailed:
                    raise
                except Exception as exc:
                    _LOGGER.debug("Ignoring unparseable message during login: %s", exc)
            elif msg.type in (
                aiohttp.WSMsgType.ERROR,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
            ):
                raise UpdateFailed(f"WebSocket closed during login ({msg.type})")
        raise UpdateFailed("Login confirmation not received")

    async def _collect_dx_messages(
        self, ws: aiohttp.ClientWebSocketResponse
    ) -> dict[str, Any]:
        """Read dxRefresh/settings messages for all channels and merge the data."""
        today = datetime.now(tz=timezone.utc).date()
        channels_data: dict[int, dict[str, Any]] = {}

        for _ in range(WS_MAX_MESSAGES):
            try:
                msg = await ws.receive()
            except asyncio.TimeoutError:
                break

            if msg.type == aiohttp.WSMsgType.BINARY:
                try:
                    _, ns, cmd, _, payload = _decode_message(msg.data)
                    _LOGGER.debug(
                        "Data rx: ns=%s cmd=%s payload_len=%d",
                        ns, cmd, len(payload),
                    )
                    if ns == "dxRefresh" and cmd == "settings":
                        for ch_data in _parse_dx_settings(payload, today):
                            channels_data[ch_data["channel_id"]] = ch_data
                    elif ns == "dxRefresh":
                        _LOGGER.debug(
                            "UNKNOWN dxRefresh/%s payload (%d bytes): %s",
                            cmd, len(payload), payload.hex(),
                        )
                except Exception as exc:
                    _LOGGER.debug("Error parsing message: %s", exc)

            elif msg.type in (
                aiohttp.WSMsgType.ERROR,
                aiohttp.WSMsgType.CLOSE,
                aiohttp.WSMsgType.CLOSED,
            ):
                break

        if not channels_data:
            raise UpdateFailed("No dosing pump data received from device")

        # Flatten into result dict keyed by channel number 1-3.
        # Device channel_ids are 0-indexed (0,1,2); CHANNELS is 1-indexed (1,2,3).
        result: dict[str, Any] = {}
        for ch in CHANNELS:
            data = channels_data.get(ch - 1, {})
            result[f"ch{ch}_container_current"] = data.get("container_current")
            result[f"ch{ch}_container_capacity"] = data.get("container_capacity")
            result[f"ch{ch}_today_dosed"] = data.get("today_dosed")
            result[f"ch{ch}_daily_dose_max"] = data.get("daily_dose_max")
            result[f"ch{ch}_actions_today"] = data.get("actions_today", 0)

        _LOGGER.debug("Final merged dose data: %s", result)
        return result


async def async_validate_credentials(
    hass: HomeAssistant, email: str, password: str
) -> bool:
    """Try to authenticate with the Reef Factory API. Returns True on success."""
    session = async_get_clientsession(hass)
    try:
        async with session.ws_connect(
            WS_URL,
            protocols=[WS_PROTOCOL],
            receive_timeout=10,
        ) as ws:
            await ws.send_bytes(
                _encode_message(
                    "user", "login", _build_login_payload(email, password)
                )
            )
            for _ in range(10):
                msg = await ws.receive()
                if msg.type == aiohttp.WSMsgType.BINARY:
                    _, ns, _, _, payload = _decode_message(msg.data)
                    if ns == "status":
                        return payload[:2] == b"ok"
                elif msg.type in (
                    aiohttp.WSMsgType.ERROR,
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    return False
    except Exception as exc:
        _LOGGER.debug("Credential validation failed: %s", exc)
    return False
