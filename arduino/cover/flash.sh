#!/bin/sh

avrdude -v -patmega328p -carduino -P/dev/arduino -b115200 -D -Uflash:w:cover.ino.standard.hex:i
