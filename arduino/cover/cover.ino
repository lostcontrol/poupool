// Requires CmdParser, InputDebounce and EEPROMex
// Uncomment _EEPROMEX_DEBUG in EEPROMex.cpp to avoid the max EEPROM write limit

#include <avr/wdt.h>
#include <CmdParser.hpp>
#include <InputDebounce.h>
#include <EEPROMex.h>

class InterruptGuard {
  public:
    InterruptGuard() {
      noInterrupts();
    }
    ~InterruptGuard() {
      interrupts();
    }
};

class Cover {
  public:
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

    Cover() {
      EEPROM.readBlock(0, m_position);
    }

    void reset() {
      m_position.position = 0;
      m_position.close = 0;
      m_position.open = 0;
    }

    void setup() {
      pinMode(pins.cover_interrupt, INPUT_PULLUP);

      pinMode(pins.cover_close, OUTPUT);
      digitalWrite(pins.cover_close, HIGH);
      pinMode(pins.cover_open, OUTPUT);
      digitalWrite(pins.cover_open, HIGH);
    }

    void process_direction(unsigned long now) {
      if (m_direction != m_previous_direction) {
        switch (m_direction) {
          case Direction::OPEN:
            digitalWrite(pins.cover_close, LOW);
            delay(100);
            digitalWrite(pins.cover_open, HIGH);
            // Update the time/position for consistency check when the cover starts moving
            m_previous_position = get_position();
            m_previous_time = now;
            break;
          case Direction::CLOSE:
            digitalWrite(pins.cover_open, LOW);
            delay(100);
            digitalWrite(pins.cover_close, HIGH);
            // Update the time/position for consistency check when the cover starts moving
            m_previous_position = get_position();
            m_previous_time = now;
            break;
          case Direction::STOP:
            digitalWrite(pins.cover_close, HIGH);
            digitalWrite(pins.cover_open, HIGH);
            // Ensure the motor is stopped before saving the position
            delay(500);
            // Save the positions to EEPROM. Disable interrupts to ensure the values get not
            // updated by ISR during the process
            InterruptGuard _{};
            EEPROM.updateBlock(0, m_position);
            break;
        }
        m_previous_direction = m_direction;
      }
    }

    void ensure_consistency(unsigned long now) {
      if (m_direction != Direction::STOP) {
        // Rotation/pulse check
        if (now - m_previous_time > 500) {
          const auto position = get_position();
          // The motor is supposed to generate 3000 pulses/min so we should get around 25 pulses
          // during 500 ms. At startup, we have seen ~18 pulses for 500 ms and then 25 pulses.
          if (abs(position - m_previous_position) < 10) {
            // Emergency stop
            emergency_stop();
          }
          m_previous_position = position;
          m_previous_time = now;
        }
        // Position consistency
        if (m_set_limits == SetLimit::NONE) {
          const auto position = get_position();
          if (position < m_position.close || position > m_position.open) {
            // Emergency stop
            emergency_stop();
          }
        }
      }
    }

    Direction get_direction() const {
      return m_direction;
    }

    void set_direction(Direction direction) {
      const auto position = get_position();
      switch (direction) {
        case Direction::OPEN:
          if (m_set_limits != SetLimit::NONE || position < m_position.open) {
            m_direction = Direction::OPEN;
          }
          break;
        case Direction::CLOSE:
          if (m_set_limits != SetLimit::NONE || position > m_position.close) {
            m_direction = Direction::CLOSE;
          }
          break;
        case Direction::STOP:
          m_direction = Direction::STOP;
          break;
      }
    }

    void set_limit(Direction direction) {
      const auto position = get_position();
      switch (direction) {
        case Direction::OPEN:
          m_set_limits = SetLimit::OPEN;
          break;
        case Direction::CLOSE:
          m_set_limits = SetLimit::CLOSE;
          break;
        case Direction::STOP:
          switch (m_set_limits) {
            case SetLimit::OPEN:
              m_position.open = position;
              break;
            case SetLimit::CLOSE:
              m_position.close = position;
              break;
            case SetLimit::NONE:
              break;
          }
          m_set_limits = SetLimit::NONE;
          // Save settings to EEPROM. Update will not touch the EEPROM if the data is the same so
          // it's safe to put it here.
          InterruptGuard _{};
          EEPROM.updateBlock(0, m_position);
          break;
      }
    }

    byte get_position_percentage() const {
      const auto position = get_position();
      const auto diff = m_position.open - m_position.close;
      if (diff == 0) return 0;
      return constrain(100 * (position - m_position.close) / diff, 0, 100);
    }

    void step() {
      switch (m_direction) {
        case Direction::OPEN:
          ++m_position.position;
          if (m_set_limits == SetLimit::NONE && m_position.position >= m_position.open) {
            m_direction = Direction::STOP;
          }
          break;
        case Direction::CLOSE:
          --m_position.position;
          if (m_set_limits == SetLimit::NONE && m_position.position <= m_position.close) {
            m_direction = Direction::STOP;
          }
          break;
        case Direction::STOP:
          break;
      }
    }

    void debug() const {
      Serial.print(F("position="));
      Serial.println(m_position.position);
      Serial.print(F("open="));
      Serial.println(m_position.open);
      Serial.print(F("close="));
      Serial.println(m_position.close);
    }

  private:
    enum class SetLimit : byte {
      OPEN, CLOSE, NONE,
    };

  private:
    void emergency_stop() {
      // Emergency stop
      m_direction = Direction::STOP;
      Serial.println(F("emergency stop"));
      Serial.println(F("***"));
    }

    long get_position() const {
      // m_position.position is a long (4 bytes) which is updated in the ISR and read in the main
      // loop. We need to disable the interruptions when reading it in order to avoid getting
      // inconsistent values (e.g. half of the bytes updated by the ISR)
      InterruptGuard _{};
      return m_position.position;
    }

  private:
    volatile Position m_position;
    long m_previous_position = 0;
    unsigned long m_previous_time = 0;
    Direction m_previous_direction = Direction::STOP;
    volatile Direction m_direction = Direction::STOP;
    volatile SetLimit m_set_limits = SetLimit::NONE;
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
      constexpr InputDebounce::SwitchType type = InputDebounce::ST_NORMALLY_CLOSED;
      constexpr unsigned long limits_delay = 2000;

      m_open.registerCallbacks(open_pressed, open_close_released);
      m_open.setup(pins.button_open, DEBOUNCE_DELAY, InputDebounce::PIM_INT_PULL_UP_RES, 0, type);
      m_close.registerCallbacks(close_pressed, open_close_released);
      m_close.setup(pins.button_close, DEBOUNCE_DELAY, InputDebounce::PIM_INT_PULL_UP_RES, 0, type);
      m_save_open.registerCallbacks(nullptr, save_open_close_released, save_open_pressed);
      m_save_open.setup(pins.button_save_open, DEBOUNCE_DELAY, InputDebounce::PIM_INT_PULL_UP_RES, limits_delay, type);
      m_save_close.registerCallbacks(nullptr, save_open_close_released, save_close_pressed);
      m_save_close.setup(pins.button_save_close, DEBOUNCE_DELAY, InputDebounce::PIM_INT_PULL_UP_RES, limits_delay, type);
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

    T* get_buffer() const {
      return m_buffer;
    }

    constexpr int get_size() const {
      return S;
    }

  private:
    int m_position = 0;
    T m_buffer[S] = {0};
};

ReadBuffer<uint8_t, 32> buffer;
CmdParser cmdParser;
Water water;
Cover cover;
Button button{&cover};
HeartBeat heartbeat{5000};

void setup()
{
  // EEPROM safety during debugging
  EEPROM.setMemPool(0, EEPROMSizeUno);
  EEPROM.setMaxAllowedWrites(50);

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
  static unsigned long last_interrupt_time = 0;
  auto interrupt_time = millis();
  // Debounce
  if (interrupt_time - last_interrupt_time > 10)
  {
    cover.step();
  }
  last_interrupt_time = interrupt_time;
}

static void water_isr() {
  static unsigned long last_interrupt_time = 0;
  auto interrupt_time = millis();
  // Debounce
  if (interrupt_time - last_interrupt_time > 50)
  {
    water.step();
  }
  last_interrupt_time = interrupt_time;
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
      if (cmdParser.parseCmd(buffer.get_buffer(), buffer.get_size()) != CMDPARSER_ERROR) {
        if (cmdParser.equalCommand("open")) {
          Serial.println(F("open"));
          cover.set_direction(Cover::Direction::OPEN);
        } else if (cmdParser.equalCommand("close")) {
          Serial.println(F("close"));
          cover.set_direction(Cover::Direction::CLOSE);
        } else if (cmdParser.equalCommand("stop")) {
          Serial.println(F("stop"));
          cover.set_direction(Cover::Direction::STOP);
        } else if (cmdParser.equalCommand("position")) {
          Serial.print(F("position "));
          Serial.println(cover.get_position_percentage());
        } else if (cmdParser.equalCommand("water")) {
          Serial.print(F("water "));
          Serial.println(water.get_counter());
        } else if (cmdParser.equalCommand("debug")) {
          Serial.println(F("debug"));
          cover.debug();
        } else if (cmdParser.equalCommand("reset")) {
          Serial.println(F("reset"));
          cover.reset();
        }
      }
      Serial.println(F("***"));
      buffer.clear();
    }
  }

  const auto now = millis();

  // Handle buttons. They have an higher priority over the serial communication
  button.process(now);

  // Action
  cover.process_direction(now);
  cover.ensure_consistency(now);
}
