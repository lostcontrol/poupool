# AGENTS.md

Guidelines for AI agents and developers working on **Poupool**. For feature and logic details, read the code and [`docs/README.md`](docs/README.md) rather than relying on this file.

## Golden Rules

1. **Update documentation in the same change** as any feature, config, MQTT topic or hardware change:
   - [`README.md`](README.md): feature overview, dependencies, tooling.
   - [`docs/README.md`](docs/README.md): user manual, published at https://lostcontrol.github.io/poupool/. Keep it functional and user-oriented; no internal algorithm constants (those belong in code docstrings).
   - [`arduino/cover/README.md`](arduino/cover/README.md): firmware changes.
   - [`home-assistant/mqtt.yaml`](home-assistant/mqtt.yaml) / [`dashboard.yaml`](home-assistant/dashboard.yaml): entity, topic or card changes.
2. **Never commit (or push) unless explicitly asked.** Present changes first.
3. **Conventional, scoped, atomic commits**: `<type>(<scope>): <subject>`, e.g. `feat(disinfection): ...`. Check `git log` for style. Don't mix unrelated changes.
4. **Zero cruft**:
   - No code written only for testing purposes (hooks, properties, getters); test through public interfaces.
   - When replacing a subsystem or dependency, remove all old config and references.
   - Imports go at the top of Python files.
5. **Stay coherent**: code and documentation style must always match the rest of the application (naming, structure, tone, level of detail). Read the surrounding code and docs before writing.

## Tooling

Python 3.11+, managed with `uv`. Always run tools through `uv run`:

```bash
uv run pytest
uv run ruff check . && uv run ruff format .
uv run ty check
uv run pre-commit run --all-files
uv run pio run -d arduino/cover   # Arduino firmware
```

Tests, `ruff` and `ty` must be clean before a task is considered done.

## Code Style

- Keep `try..except` blocks short: wrap only the call that can fail, and extract the rest into methods.
- Avoid deeply nested `try..except` and `if..else`; use early returns and small helper methods.

## Architecture

- **Pykka actors**: components run as actors. Proxy calls return futures (`.get()` to wait for the result).
- **No `.defer()`**: use a normal proxy call and ignore the returned future if the result isn't needed, with a comment saying so explicitly.
- **Data containers**: prefer `dataclass` over `NamedTuple`/`namedtuple`.
- **`transitions` state machines**: it manages `state`; never add a separate state variable.
- **Encapsulation**: use `__` for private attributes and methods. Prefer public or private; use a single `_` (protected) only when really needed.
- **Proxies**: never access attributes through a Pykka proxy; add a getter method to the actor instead.
- **MQTT**: `/status/...` for telemetry, `/settings/...` for commands. Routing lives in `controller/dispatcher.py`; defaults in `default_settings.py`. Use retained messages for state that must survive a restart.
- **Home Assistant**: entity names, unique IDs and topics must match the dispatcher. Device is `identifiers: "Poupool01"`, `name: "Poupool"`.

## Environment Constraints

- Target: Raspberry Pi 3 Model B+ (Linux), GPIO via `rpi-lgpio`.
- Arduino firmware uses PlatformIO. Avoid unnecessary EEPROM writes (keep `_EEPROMEX_DEBUG` off; use `put`/`get`).
- `docker-compose.development.yml` is for workstation simulation only; it does not run on the Pi. Don't adapt it to Pi-specific hardware.
