# poupool
PouPool is a swimming pool control software.

It is based on MQTT (hbmqtt) and Python asyncio. This is meant as a personal
project and will never be a fully-featured software. It is also a playground
for me to try asyncio.

I chose MQTT because I will integrate it with [OpenHAB](https://github.com/openhab)
which has a plugin for this protocol. OpenHAB will be used for GUI, charts,
interaction with garden/house lightings, notifications, alarms, etc.

It is planned to control filtration, heating, PH and chlorination, all the
pumps and valves, cover and lights. It will be an overflow swimming pool so
that adds some complexity to the control process (e.g. monitoring of the
retention tank water level).
