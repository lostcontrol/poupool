# Poupool - The swimming pool controller
Poupool is a swimming pool control software.

It is based on [Transitions](https://github.com/pytransitions/transitions),
[Pykka](https://www.pykka.org) and [Paho MQTT](https://github.com/eclipse/paho.mqtt.python).
The user interface will be built using the excellent home automation server
[openHAB](http://www.openhab.org).

![The swimming pool](docs/images/pool-01.jpg)

This is meant as a personal project and will never be a fully-featured software.
Some pictures of the project will be added later.

Originally, I wanted to experiment with asyncio but finally I preferred to
go with some more traditional approach.

It is planned to control filtration, heating, pH and chlorination, all the
pumps and valves, cover and lights. It will be an overflow swimming pool so
that adds some complexity to the control process (e.g. monitoring of the
retention tank water level).

Here is an early screenshot of the main menu in openHAB:
![openHAB main menu](docs/images/openhab-01.png)

## Dependencies

These are the external dependencies that can be install via `pip`. You will also need Python 3.5.
Best is to setup a virtual environment.

Frameworks:

* Pykka
* transitions
* pygraphviz (optional for transitions)
* paho-mqtt

Raspberry Pi:

* Adafruit-ADS1x15
* RPi.GPIO

Development tools:

* autopep8
