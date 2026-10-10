# Cover controller

Arduino firmware (ATmega328P, `uno` board) driving the pool cover. Built with [PlatformIO](https://platformio.org/).

## Prerequisites

PlatformIO is a development dependency of the project: run `uv sync` at the repository root, then use `uv run pio ...` (or activate `.venv`). Alternatively install it standalone, see the [installation guide](https://docs.platformio.org/en/latest/core/installation/). The library (`InputDebounce`) and the toolchain are downloaded automatically on the first build.

## Build

```sh
pio run
```

The firmware is generated in `.pio/build/uno/firmware.hex`.

## Flash

The board is expected at `/dev/arduino` (see `raspberrypi/50-arduino.rules` for the udev rule). The upload settings (`arduino` protocol, 115200 baud) are in `platformio.ini`.

```sh
pio run -t upload
```

To use a different port:

```sh
pio run -t upload --upload-port /dev/ttyUSB0
```

## Serial monitor

```sh
pio device monitor -b 9600
```
