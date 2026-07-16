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
The Stand-by mode is used when the pool is open but not actively being used or overflowing. In this mode, the water circulates through the gravity line rather than overflowing into the tank. Filtration and disinfection can run depending on your settings. It is possible to activate a boost for increased circulation.

##### Pool status
* Pool is open (cover rolled up)
* Water circulates via the gravity line (no overflow)
* Filtration pump speed is configurable
* Disinfection runs if pump speed is greater than 0
* Heat pump operates if required and constraints are met

#### Overflow
The Overflow mode is similar to Stand-by, but the water actively overflows into the buffer tank instead of using the gravity line. This mode provides the best aesthetic look of the overflow pool.

##### Pool status
* Pool is open (cover rolled up)
* Water overflows into the tank
* Filtration pump runs at an intermediate or high speed
* Disinfection runs at appropriate flow speeds
* Boost can be activated

#### Comfort
Comfort mode is designed for when people are swimming in the pool. The pump runs at an adequate speed, the heating is forced to maintain a comfortable temperature, and disinfection remains active to keep the water clean. Depending on your configuration, the pool can either overflow or use the gravity line.

##### Pool status
* Pool is open
* Heating is forced to maintain temperature
* Higher filtration speed
* Disinfection is active

### Advanced modes
#### Sweep
Sweep mode is intended for cleaning the pool, either manually or using a robot cleaner. The pump runs at high speed using the gravity line, and disinfection is temporarily halted to prioritize cleaning operations.

#### Backwash
Backwash mode is an automated maintenance mode to clean the filter. It reverses the water flow through the filter using water from the buffer tank at high speed, discharging the dirty water to the drain. This is immediately followed by a rinse phase to settle the sand before returning to standard operation.

#### Wintering
Wintering mode protects the pool and equipment from freezing during cold weather. The cover is fully opened to avoid damage from ice. When the air temperature drops below a safety threshold, the system automatically starts stirring the water periodically at a set speed to prevent freezing.

#### Halt
Halt mode completely stops the entire Poupool system. All pumps are turned off, valves are closed, and heating and disinfection are halted. This is used for maintenance or complete shutdown.

## Heating
Poupool manages the pool temperature using a connected heat pump. The system monitors the water temperature and compares it against a configured setpoint. Heating only activates when the filtration system is running, and the air temperature is above a minimum threshold (to ensure heat pump efficiency). The system uses hysteresis to avoid turning the heat pump on and off too rapidly and can be configured with a daily start timer.

## Disinfection
Disinfection in Poupool is completely automated using PWM-controlled dosing pumps for both pH reduction and liquid chlorine (based on ORP).
The system operates in a loop: it waits, adjusts the dosage by reading current sensor values and comparing them to the setpoints (using Proportional controllers), and then treats the water.

### pH
The pH controller reads the current pH value from the sensor. If the pH is higher than the setpoint (defaulting to a setpoint like 7.0), it calculates a required dose of "pH minus" chemical and injects it using the pH dosing pump.

### ORP
The Oxidation-Reduction Potential (ORP) controller measures the sanitizing capability of the water. If the ORP drops below the configured setpoint (e.g., 600 mV), it triggers the chlorine dosing pump to inject liquid chlorine and restore the required sanitation levels.

## Tank
The tank acts as the buffer for the overflow pool. Its level is continuously monitored by a sensor.
The tank has multiple states: Low, Normal, High, and Fill. Poupool uses different minimum and maximum level thresholds based on whether the pool is in Eco or Overflow mode. If the water level drops below the minimum threshold (minus a hysteresis margin), the system automatically opens the main water valve to refill the tank.

## Swimming pump
Poupool can control a counter-current swimming pump. The pump can run in a `timed` mode (turning off automatically after a set duration) or `continuous` mode. It only operates when the pool is open (e.g., in Stand-by, Overflow, or Comfort modes). It also features its own wintering mode, periodically starting the pump if the water drops below freezing thresholds to prevent the pipes from freezing.

## Light
Pool lights can be toggled via the user interface. The controller simply switches the lighting circuit between `on` and `halt` states.
