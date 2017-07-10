# poupool
PouPool is a swimming pool control software.

It is based on Transition [1], Pykka [2] and Paho MQTT. This is meant as a
personal project and will never be a fully-featured software. Some pictures
of the project will be added later.

Originally, I wanted to experiment with asyncio but finally I preferred to
go with some more traditional approach.

It is planned to control filtration, heating, PH and chlorination, all the
pumps and valves, cover and lights. It will be an overflow swimming pool so
that adds some complexity to the control process (e.g. monitoring of the
retention tank water level).

[1] https://github.com/pytransitions/transitions
[2] https://www.pykka.org
[3] https://github.com/eclipse/paho.mqtt.python
