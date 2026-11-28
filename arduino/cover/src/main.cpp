// Poupool - swimming pool control software
// Copyright (C) 2019 Cyril Jaquier
//
// This program is free software; you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation; either version 2 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License along
// with this program; if not, write to the Free Software Foundation, Inc.,
// 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

// Dependencies (InputDebounce) are declared in platformio.ini

#include <Arduino.h>
#include <string.h>
#include <avr/wdt.h>
#include <InputDebounce.h>
#include <EEPROM.h>

static void water_isr();
static void cover_isr();

class InterruptGuard {
  public:
    InterruptGuard() : m_sreg{SREG} {
      noInterrupts();
      asm volatile("" ::: "memory");
    }
    ~InterruptGuard() {
      asm volatile("" ::: "memory");
      SREG = m_sreg;
    }
    InterruptGuard(const InterruptGuard&) = delete;
    InterruptGuard& operator=(const InterruptGuard&) = delete;

  private:
    const uint8_t m_sreg;
};

class Cover {
  public:
    // When stopped the motor still runs for 2-3 seconds in some cases. We need to account
    // for this otherwise we get drift.
    static constexpr unsigned long MAX_RUNNING_MARGIN_IN_MS = 3000;
    // How fast the motor is spinning.
    static constexpr unsigned long PULSES_PER_SECOND = 50;
    // This is the maximum amount of steps the motor is allowed to go past the end points.
    static constexpr long MAX_PULSE_MARGIN = PULSES_PER_SECOND * MAX_RUNNING_MARGIN_IN_MS / 1000;
    // Break-before-make dead-time before energizing a motor relay.
    static constexpr unsigned long DEAD_TIME_MS = 100;
    // Stall detection window and minimum expected pulses per window.
    static constexpr unsigned long STALL_CHECK_INTERVAL_MS = 500;
    static constexpr long MIN_PULSES_PER_CHECK = 10;

    static constexpr struct Pins {
      static constexpr byte cover_interrupt = 2;
      static constexpr byte cover_open = 4;
      static constexpr byte cover_close = 5;
    } pins = Pins{};

    struct Position {
      long position = 0;
      long close = 0;
      long open = 0;
    };

    enum class Direction : byte {
      OPEN, CLOSE, STOP,
    };

    void reset() {
      stop_relays();
      m_target_direction = Direction::STOP;
      m_active_direction = Direction::STOP;
      m_state = State::IDLE;
      {
        InterruptGuard _{};
        m_running_direction = Direction::STOP;
        m_limit_reached = false;
        m_position.position = 0;
        m_position.close = 0;
        m_position.open = 0;
      }
    }

    void setup() {
      pinMode(pins.cover_interrupt, INPUT_PULLUP);

      digitalWrite(pins.cover_close, LOW);
      pinMode(pins.cover_close, OUTPUT);
      digitalWrite(pins.cover_open, LOW);
      pinMode(pins.cover_open, OUTPUT);

      load_position();
    }

    void set_direction(Direction direction) {
      if (direction == Direction::STOP) {
        m_target_direction = Direction::STOP;
        if (m_state == State::FAULT) {
          m_state = (m_running_direction != Direction::STOP) ? State::COASTING : State::IDLE;
        }
        return;
      }
      if (m_state == State::FAULT) {
        return;
      }
      if (can_move(direction)) {
        m_target_direction = direction;
      }
    }

    void set_limit(Direction direction) {
      switch (direction) {
        case Direction::OPEN:
          m_set_limits = SetLimit::OPEN;
          break;
        case Direction::CLOSE:
          m_set_limits = SetLimit::CLOSE;
          break;
        case Direction::STOP:
          if (m_set_limits == SetLimit::NONE) {
            return;
          }
          {
            InterruptGuard _{};
            switch (m_set_limits) {
              case SetLimit::OPEN:
                m_position.open = m_position.position;
                break;
              case SetLimit::CLOSE:
                m_position.close = m_position.position;
                break;
              case SetLimit::NONE:
                break;
            }
            m_set_limits = SetLimit::NONE;
          }
          // Save settings to EEPROM outside the critical section. Put will not touch the EEPROM
          // if the data is the same so it's safe to put it here.
          save_position();
          break;
      }
    }

    void process(unsigned long now) {
      switch (m_state) {
        case State::IDLE:
          process_idle(now);
          break;
        case State::DEAD_TIME:
          process_dead_time(now);
          break;
        case State::RUNNING:
          process_running(now);
          break;
        case State::COASTING:
          process_coasting(now);
          break;
        case State::FAULT:
          process_fault(now);
          break;
      }
    }

    byte get_position_percentage() const {
      const auto position = get_position();
      const auto diff = m_position.open - m_position.close;
      if (diff <= 0) return 0;
      const long percent = 100L * (position - m_position.close) / diff;
      if (percent < 0) return 0;
      if (percent > 100) return 100;
      return static_cast<byte>(percent);
    }

    void step() {
      switch (m_running_direction) {
        case Direction::OPEN:
          ++m_position.position;
          if (m_set_limits == SetLimit::NONE && m_position.position >= m_position.open) {
            m_limit_reached = true;
          }
          break;
        case Direction::CLOSE:
          --m_position.position;
          if (m_set_limits == SetLimit::NONE && m_position.position <= m_position.close) {
            m_limit_reached = true;
          }
          break;
        case Direction::STOP:
          break;
      }
    }

    void debug() const {
      Serial.print(F("position="));
      Serial.println(get_position());
      Serial.print(F("open="));
      Serial.println(m_position.open);
      Serial.print(F("close="));
      Serial.println(m_position.close);
      Serial.print(F("state="));
      Serial.println(state_name(m_state));
    }

  private:
    enum class State : byte {
      IDLE, DEAD_TIME, RUNNING, COASTING, FAULT,
    };

    enum class SetLimit : byte {
      OPEN, CLOSE, NONE,
    };

    void process_idle(unsigned long now) {
      if (m_target_direction == Direction::STOP) {
        return;
      }
      if (can_move(m_target_direction)) {
        m_active_direction = m_target_direction;
        m_state_time = now;
        m_state = State::DEAD_TIME;
      } else {
        m_target_direction = Direction::STOP;
      }
    }

    void process_dead_time(unsigned long now) {
      if (m_target_direction != m_active_direction) {
        if (m_running_direction != Direction::STOP) {
          m_state = State::COASTING;
        } else {
          m_active_direction = Direction::STOP;
          m_state = State::IDLE;
        }
        return;
      }
      if (now - m_state_time < DEAD_TIME_MS) {
        return;
      }
      if (!can_move(m_active_direction)) {
        m_target_direction = Direction::STOP;
        if (m_running_direction != Direction::STOP) {
          m_state = State::COASTING;
        } else {
          m_active_direction = Direction::STOP;
          m_state = State::IDLE;
        }
        return;
      }
      m_limit_reached = false;
      m_running_direction = m_active_direction;
      m_previous_position = get_position();
      m_previous_time = now;
      energize_relay(m_active_direction);
      m_state = State::RUNNING;
    }

    void process_running(unsigned long now) {
      const bool limit_hit = m_limit_reached || (m_set_limits == SetLimit::NONE && at_limit(m_active_direction));
      if (limit_hit) {
        m_target_direction = Direction::STOP;
      }
      if (limit_hit || m_target_direction != m_active_direction) {
        stop_relays();
        m_limit_reached = false;
        m_coast_start_time = now;
        m_state = State::COASTING;
        return;
      }
      ensure_consistency(now);
    }

    void process_coasting(unsigned long now) {
      if (m_target_direction == m_active_direction && can_move(m_active_direction)) {
        m_state_time = now;
        m_state = State::DEAD_TIME;
        return;
      }
      if (now - m_coast_start_time >= MAX_RUNNING_MARGIN_IN_MS) {
        finish_coasting();
        m_state = State::IDLE;
      }
    }

    void process_fault(unsigned long now) {
      if (m_running_direction != Direction::STOP && (now - m_coast_start_time >= MAX_RUNNING_MARGIN_IN_MS)) {
        finish_coasting();
      }
    }

    void ensure_consistency(unsigned long now) {
      const auto position = get_position();
      // Rotation/pulse check
      if (now - m_previous_time >= STALL_CHECK_INTERVAL_MS) {
        // The motor is supposed to generate 3000 pulses/min so we should get around 25 pulses
        // during 500 ms. At startup, we have seen ~18 pulses for 500 ms and then 25 pulses.
        const long delta = (m_active_direction == Direction::OPEN)
          ? (position - m_previous_position)
          : (m_previous_position - position);
        m_previous_position = position;
        m_previous_time = now;
        if (delta < MIN_PULSES_PER_CHECK) {
          emergency_stop(now);
          return;
        }
      }
      // Position consistency: only fault when moving further beyond a calibrated limit so the
      // cover can still return into range if it coasted slightly past.
      if (m_set_limits == SetLimit::NONE) {
        const bool over_open = m_active_direction == Direction::OPEN && position > (m_position.open + MAX_PULSE_MARGIN);
        const bool over_close = m_active_direction == Direction::CLOSE && position < (m_position.close - MAX_PULSE_MARGIN);
        if (over_open || over_close) {
          emergency_stop(now);
        }
      }
    }

    void finish_coasting() {
      m_running_direction = Direction::STOP;
      m_active_direction = Direction::STOP;
      save_position();
    }

    void emergency_stop(unsigned long now) {
      stop_relays();
      m_limit_reached = false;
      m_target_direction = Direction::STOP;
      m_coast_start_time = now;
      m_state = State::FAULT;
      Serial.println(F("emergency stop"));
      Serial.println(F("***"));
    }

    bool can_move(Direction direction) const {
      if (m_set_limits != SetLimit::NONE) {
        return direction == Direction::OPEN || direction == Direction::CLOSE;
      }
      if (m_position.open <= m_position.close) {
        return false;
      }
      const auto position = get_position();
      switch (direction) {
        case Direction::OPEN:
          return position < m_position.open;
        case Direction::CLOSE:
          return position > m_position.close;
        case Direction::STOP:
          return false;
      }
      return false;
    }

    bool at_limit(Direction direction) const {
      const auto position = get_position();
      switch (direction) {
        case Direction::OPEN:
          return position >= m_position.open;
        case Direction::CLOSE:
          return position <= m_position.close;
        case Direction::STOP:
          return false;
      }
      return false;
    }

    void stop_relays() const {
      digitalWrite(pins.cover_close, LOW);
      digitalWrite(pins.cover_open, LOW);
    }

    void energize_relay(Direction direction) const {
      // Relays are active-HIGH and hardware pin wiring is inverted relative to pin names
      // (pin 5 cover_close drives OPEN; pin 4 cover_open drives CLOSE).
      switch (direction) {
        case Direction::OPEN:
          digitalWrite(pins.cover_open, LOW);
          digitalWrite(pins.cover_close, HIGH);
          break;
        case Direction::CLOSE:
          digitalWrite(pins.cover_close, LOW);
          digitalWrite(pins.cover_open, HIGH);
          break;
        case Direction::STOP:
          stop_relays();
          break;
      }
    }

    long get_position() const {
      // m_position.position is a long (4 bytes) which is updated in the ISR and read in the main
      // loop. We need to disable the interruptions when reading it in order to avoid getting
      // inconsistent values (e.g. half of the bytes updated by the ISR)
      InterruptGuard _{};
      return m_position.position;
    }

    static const __FlashStringHelper* state_name(State state) {
      switch (state) {
        case State::IDLE:
          return F("idle");
        case State::DEAD_TIME:
          return F("dead_time");
        case State::RUNNING:
          return F("running");
        case State::COASTING:
          return F("coasting");
        case State::FAULT:
          return F("fault");
      }
      return F("unknown");
    }

  private:
    // EEPROM.get/put cannot be used directly on the volatile m_position. Go through a
    // non-volatile local copy. Only the copy runs inside InterruptGuard; EEPROM.put() takes
    // several milliseconds per modified byte and must run with interrupts enabled.
    void load_position() {
      Position p;
      EEPROM.get(0, p);
      m_position.position = p.position;
      m_position.close = p.close;
      m_position.open = p.open;
    }

    void save_position() const {
      Position p;
      {
        InterruptGuard _{};
        p.position = m_position.position;
        p.close = m_position.close;
        p.open = m_position.open;
      }
      EEPROM.put(0, p);
    }

    volatile Position m_position;
    volatile Direction m_running_direction = Direction::STOP;
    volatile SetLimit m_set_limits = SetLimit::NONE;
    volatile bool m_limit_reached = false;

    State m_state = State::IDLE;
    Direction m_target_direction = Direction::STOP;
    Direction m_active_direction = Direction::STOP;
    long m_previous_position = 0;
    unsigned long m_previous_time = 0;
    unsigned long m_state_time = 0;
    unsigned long m_coast_start_time = 0;
};

class Button {
  public:
    static constexpr unsigned long DEBOUNCE_DELAY = 50;

    static constexpr struct Pins {
      static constexpr byte button_open = 6;
      static constexpr byte button_close = 7;
      static constexpr byte button_save_open = 8;
      static constexpr byte button_save_close = 9;
    } pins = Pins{};

    Button(Cover* cover) {
      s_cover = cover;
    }

    void setup() {
      constexpr InputDebounce::SwitchType type = InputDebounce::ST_NORMALLY_OPEN;
      constexpr InputDebounce::PinInMode mode = InputDebounce::PIM_INT_PULL_UP_RES;
      constexpr unsigned long limits_delay = 2000;

      m_open.registerCallbacks(open_pressed, open_close_released);
      m_open.setup(pins.button_open, DEBOUNCE_DELAY, mode, 0, type);
      m_close.registerCallbacks(close_pressed, open_close_released);
      m_close.setup(pins.button_close, DEBOUNCE_DELAY, mode, 0, type);
      m_save_open.registerCallbacks(nullptr, save_open_close_released, save_open_pressed);
      m_save_open.setup(pins.button_save_open, DEBOUNCE_DELAY, mode, limits_delay, type);
      m_save_close.registerCallbacks(nullptr, save_open_close_released, save_close_pressed);
      m_save_close.setup(pins.button_save_close, DEBOUNCE_DELAY, mode, limits_delay, type);
    }

    void process(unsigned long now) {
      m_open.process(now);
      m_close.process(now);
      m_save_open.process(now);
      m_save_close.process(now);
    }

  private:
    static void open_pressed(uint8_t pin) {
      s_cover->set_direction(Cover::Direction::OPEN);
    }

    static void close_pressed(uint8_t pin) {
      s_cover->set_direction(Cover::Direction::CLOSE);
    }

    static void open_close_released(uint8_t pin) {
      s_cover->set_direction(Cover::Direction::STOP);
    }

    static void save_open_pressed(uint8_t pin, unsigned long duration) {
      s_cover->set_limit(Cover::Direction::OPEN);
    }

    static void save_close_pressed(uint8_t pin, unsigned long duration) {
      s_cover->set_limit(Cover::Direction::CLOSE);
    }

    static void save_open_close_released(uint8_t pin) {
      s_cover->set_limit(Cover::Direction::STOP);
    }

  private:
    static Cover* s_cover;
    InputDebounce m_open;
    InputDebounce m_close;
    InputDebounce m_save_open;
    InputDebounce m_save_close;
};

Cover* Button::s_cover = nullptr;

class Water {
  public:
    static constexpr struct Pins {
      static constexpr byte water_interrupt = 3;
    } pins = Pins{};

    void setup() {
      pinMode(pins.water_interrupt, INPUT_PULLUP);
    }

    unsigned long get_counter() const {
      InterruptGuard _{};
      return m_water_counter;
    }

    void step() {
      ++m_water_counter;
    }

  private:
    volatile unsigned long m_water_counter = 0;
};

class HeartBeat {
  public:
    HeartBeat(int limit, int led = LED_BUILTIN) : m_led{led}, m_limit{limit} {}

    void setup() {
      pinMode(m_led, OUTPUT);
    }

    void tick() {
      if (++m_counter > m_limit) {
        digitalWrite(m_led, m_state ? HIGH : LOW);
        m_state = !m_state;
        m_counter = 0;
      }
    }

  private:
    const int m_led;
    const int m_limit;
    int m_counter = 0;
    bool m_state = false;
};

template<typename T, int S>
class ReadBuffer {
  public:
    bool add(byte b) {
      if (b == '\r') {
        // Ignore carriage return
        return false;
      } else if (m_position == (S - 1)) {
        // If the buffer is full, we write a null character
        // and let CmdParser deal with it.
        m_buffer[m_position++] = 0;
        return true;
      } else if (m_position >= S) {
        // Ignore, need to call clear()
        return true;
      } else if (b == '\n') {
        // CmdParser requires a null character at the end.
        m_buffer[m_position++] = 0;
        return true;
      } else {
        m_buffer[m_position++] = b;
        return false;
      }
    }

    void clear() {
      memset(m_buffer, 0, S * sizeof(T));
      m_position = 0;
    }

    operator const T*() {
      return m_buffer;
    }

    constexpr int get_size() const {
      return S;
    }

  private:
    int m_position = 0;
    T m_buffer[S] = {0};
};

ReadBuffer<char, 32> buffer;
Water water;
Cover cover;
Button button{&cover};
HeartBeat heartbeat{5000};

void setup()
{
  Serial.begin(9600);

  water.setup();
  attachInterrupt(digitalPinToInterrupt(Water::pins.water_interrupt), water_isr, RISING);

  cover.setup();
  attachInterrupt(digitalPinToInterrupt(Cover::pins.cover_interrupt), cover_isr, RISING);

  button.setup();

  heartbeat.setup();

  // Activate watchdog
  wdt_enable(WDTO_1S);
}

static void cover_isr() {
  static constexpr unsigned long DEBOUNCE_US = 10000UL;
  static unsigned long last_interrupt_time = 0;
  static bool initialized = false;
  const auto interrupt_time = micros();
  if (!initialized || interrupt_time - last_interrupt_time >= DEBOUNCE_US) {
    initialized = true;
    last_interrupt_time = interrupt_time;
    cover.step();
  }
}

static void water_isr() {
  static constexpr unsigned long DEBOUNCE_MS = 50UL;
  static unsigned long last_interrupt_time = 0;
  static bool initialized = false;
  const auto interrupt_time = millis();
  if (!initialized || interrupt_time - last_interrupt_time >= DEBOUNCE_MS) {
    initialized = true;
    last_interrupt_time = interrupt_time;
    water.step();
  }
}

void loop()
{
  heartbeat.tick();

  // Refresh watchdog
  wdt_reset();

  // Read from serial
  if (Serial.available() > 0) {
    // Use own buffer from serial input
    if (buffer.add(Serial.read())) {
      if (strcmp(buffer, "open") == 0) {
        Serial.println(F("open"));
        cover.set_direction(Cover::Direction::OPEN);
      } else if (strcmp(buffer, "close") == 0) {
        Serial.println(F("close"));
        cover.set_direction(Cover::Direction::CLOSE);
      } else if (strcmp(buffer, "stop") == 0) {
        Serial.println(F("stop"));
        cover.set_direction(Cover::Direction::STOP);
      } else if (strcmp(buffer, "position") == 0) {
        Serial.print(F("position "));
        Serial.println(cover.get_position_percentage());
      } else if (strcmp(buffer, "water") == 0) {
        Serial.print(F("water "));
        Serial.println(water.get_counter());
      } else if (strcmp(buffer, "debug") == 0) {
        Serial.println(F("debug"));
        cover.debug();
      } else if (strcmp(buffer, "reset") == 0) {
        Serial.println(F("reset"));
        cover.reset();
      } else {
        Serial.print(F("error command "));
        Serial.println(buffer);
      }
      Serial.println(F("***"));
      buffer.clear();
    }
  }

  const auto now = millis();

  // Handle buttons. They have an higher priority over the serial communication
  button.process(now);

  // Action
  cover.process(now);
}
