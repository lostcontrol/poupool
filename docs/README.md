# Poupool User Manual
## Introduction
Poupool is an overflow swimming pool control software. It takes care of everything: tank (the buffer of an overflow pool), filtration, disinfection (pH and ORP monitoring), heating (with a heat pump), cover, lights, temperature monitoring and counter current pump (with variable speed).

All the hardware is COTS (commercial off-the-shelf) based on Raspberry Pi 3, Arduino, relay boards and electronic components easily available from the Internet.

## Modes
Poupool uses the concept of *modes* to switch between functions. Some modes are only reachable via other modes and a requested mode might not be triggered if some pre-conditions are not met. You can always check the current mode in the user interface.

The modes can be split in two categories: the main modes which are most often used and the advanced modes which are used for special purposes.

### Main modes
#### Eco
This is the standard mode when the pool is not in use. In this mode, the filtration and disinfection will run automatically at given intervals and heating will be activated if required.

This mode is internally subdivided into several states. The standard flow is first to wait, then to filter the pool and finally to filter the tank. Those steps are repeated several times a day based on your configuration. The main settings are the total amount of hours of filtration per day and the number of periods.

##### Pool status
* Filtration is automatic
* Disinfection is automatic (pH and chlorine)
* Cover is closed
* Heat pump can run if needed
* Light is off
* Counter current pump is off

##### Reachable from
* Halt
* Stand-by
* Overflow

#### Stand-by
#### Overflow
#### Comfort

### Advanced modes
#### Sweep
#### Backwash
#### Wintering
#### Halt

## Heating

## Disinfection
### pH
### ORP

## Tank

## Swimming pump

## Light
