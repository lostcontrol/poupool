---
title: Chemistry & Control Basics
nav_order: 11
---

# Chemistry & Control Basics

A handful of hydraulic, chemical, and control concepts explain why Poupool behaves the way it does.

## Overflow hydraulics and the buffer tank

In a conventional pool, water sits 10 to 15 cm below the coping stones and passes through small wall skimmers. Dust, sunscreen, and leaves often collect along corners until circulation pulls them toward a skimmer opening.

In an overflow pool, water reaches the very top of the pool wall and spills continuously over the entire perimeter into a gutter. That sheet flow skims the whole surface at once, but it also means the water level in the circuit constantly shifts: every swimmer entering the pool pushes their own volume over the edge, evaporation drops the lowest point in the loop, and pump speed changes how much water rides above the coping lip. The buffer tank absorbs all of those swings so the main pump always has flooded suction and the pool never overflows onto the terrace.

## Why pH controls chlorine efficiency

pH runs from `0` (strongly acidic) to `14` (strongly alkaline), with `7.0` as neutral. Swimming pool water should stay between `7.0` and `7.4`.

<figure class="figure-card">
  <img src="{{ '/images/ph-scale.svg' | relative_url }}" alt="pH scale from 0 to 14 highlighting the 7.0 to 7.4 swimming pool range">
  <figcaption>Keeping pH inside 7.0 to 7.4 protects equipment and lets chlorine work properly. Poupool doses pH-minus whenever water drifts above setpoint.</figcaption>
</figure>

Beyond eye comfort and protecting heat exchanger metals from corrosion or scale, pH directly controls how much of your chlorine is in its active sanitizing form (hypochlorous acid). As pH climbs toward `7.8` or `8.0`, most free chlorine converts to a much weaker form, forcing higher chlorine consumption for less sanitizing power. That is why Poupool measures and corrects both pH and ORP together.

## ORP (millivolts) vs free chlorine (ppm)

Manual test kits usually report free chlorine concentration in parts per million (ppm). Automated pool controllers measure **ORP (Oxidation-Reduction Potential)** in millivolts (mV) instead.

ORP measures the net sanitizing and oxidizing strength of the water rather than raw chemical weight. Because pH, stabilizer (cyanuric acid), organic bather load, and temperature all affect how hard chlorine can actually work, a steady ORP reading (typically `600` to `750` mV depending on the pool) tracks sanitation quality better than ppm alone. When ORP falls below your setpoint, Poupool doses liquid chlorine until oxidizing capacity recovers.

## Hysteresis

If a controller turned a refill valve or heat pump on at `26.0 °C` and back off at `26.0 °C`, tiny sensor fluctuations would make the relay click on and off every few seconds.

Poupool avoids short-cycling by separating the turn-on threshold from the turn-off threshold (hysteresis). For example, the tank refills when level falls below `low - hysteresis` and stops only once it climbs to `low + hysteresis`; the heat pump stops at `setpoint + hysteresis_up` rather than right at `setpoint`, and then waits out `recover_period` before restarting.

## Proportional control and PWM

Turning a dosing pump on at full blast until pH hits `7.0` almost guarantees overshooting into overly acidic water, because chemicals take several minutes to mix through the whole basin.

Poupool uses a **proportional (P) controller** coupled with **Pulse Width Modulation (PWM)**. Every cycle, it computes `error = setpoint - reading`, scales it by `pterm`, and translates that result into an on-time percentage within a fixed period (`ph_pwm_period` or `cl_pwm_period`, 2 minutes by default). Far from target, the dosing pump stays on for most of the cycle; as the water approaches target, pulses automatically shrink to tiny maintenance doses until error reaches zero.
