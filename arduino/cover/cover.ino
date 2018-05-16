// Requires CmdParser, InputDebounce and EEPROMex
// Uncomment _EEPROMEX_DEBUG in EEPROMex.cpp to avoid the max EEPROM write limit

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
      volatile long position = 0;
      volatile long close = 0;
      volatile long open = 0;
    };

    enum class Direction : byte {
      OPEN, CLOSE, STOP,
    };

    Cover() {
      EEPROM.readBlock(0, m_position);
    }

    void reset() {
      m_position = {};
    }

    void setup() {
      pinMode(pins.cover_interrupt, INPUT_PULLUP);

      pinMode(pins.cover_close, OUTPUT);
      pinMode(pins.cover_open, OUTPUT);
    }

    void process_direction() {
      if (m_direction != m_previous_direction) {
        switch (m_direction) {
          case Direction::OPEN:
            digitalWrite(pins.cover_close, LOW);
            digitalWrite(pins.cover_open, HIGH);
            break;
          case Direction::CLOSE:
            digitalWrite(pins.cover_open, LOW);
            digitalWrite(pins.cover_close, HIGH);
            break;
          case Direction::STOP:
            digitalWrite(pins.cover_close, LOW);
            digitalWrite(pins.cover_open, LOW);
            // Save the positions to EEPROM
            EEPROM.updateBlock(0, m_position);
            break;
        }
        m_previous_direction = m_direction;
      }
    }

    Direction get_direction() const {
      return m_direction;
    }

    bool set_direction(Direction direction) {
      switch (direction) {
        case Direction::OPEN:
          if (m_set_limits || m_position.position < m_position.open) {
            m_direction = Direction::OPEN;
          }
          break;
        case Direction::CLOSE:
          if (m_set_limits || m_position.position > m_position.close) {
            m_direction = Direction::CLOSE;
          }
          break;
        case Direction::STOP:
          m_direction = Direction::STOP;
          break;
      }
    }

    void set_limit(Direction direction) {
      switch (direction) {
        case Direction::OPEN:
          m_set_limits = true;
          m_position.open = m_position.position;
          break;
        case Direction::CLOSE:
          m_set_limits = true;
          m_position.close = m_position.position;
          break;
        case Direction::STOP:
          m_set_limits = false;
          break;
      }
    }

    byte get_position() const {
      InterruptGuard _();
      const auto diff = m_position.open - m_position.close;
      if (diff == 0) return 0;
      return constrain(100 * (m_position.position - m_position.close) / diff, 0, 100);
    }

    void step() {
      Serial.println((int)m_direction);
      switch (m_direction) {
        case Direction::OPEN:
          ++m_position.position;
          if (!m_set_limits && m_position.position >= m_position.open) {
            m_direction = Direction::STOP;
          }
          break;
        case Direction::CLOSE:
          --m_position.position;
          if (!m_set_limits && m_position.position <= m_position.close) {
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
    Position m_position;
    Direction m_previous_direction = Direction::STOP;
    volatile Direction m_direction = Direction::STOP;
    volatile bool m_set_limits = false;
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
      m_open.registerCallbacks(open_pressed, open_close_released);
      m_open.setup(pins.button_open, DEBOUNCE_DELAY);
      m_close.registerCallbacks(close_pressed, open_close_released);
      m_close.setup(pins.button_close, DEBOUNCE_DELAY);
      m_save_open.registerCallbacks(nullptr, save_open_close_released, save_open_pressed);
      m_save_open.setup(pins.button_save_open, DEBOUNCE_DELAY);
      m_save_close.registerCallbacks(nullptr, save_open_close_released, save_close_pressed);
      m_save_close.setup(pins.button_save_close, DEBOUNCE_DELAY);
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

    static void save_open_pressed(uint8_t pin) {
      s_cover->set_limit(Cover::Direction::OPEN);
    }

    static void save_close_pressed(uint8_t pin) {
      s_cover->set_limit(Cover::Direction::CLOSE);
    }

    static void save_open_close_released(uint8_t pin) {
      s_cover->set_limit(Cover::Direction::STOP);
    }

    static Cover* s_cover;
    InputDebounce m_open;
    InputDebounce m_close;
    InputDebounce m_save_open;
    InputDebounce m_save_close;
};

static Cover* Button::s_cover = nullptr;

class Water {
  public:
    static constexpr struct Pins {
      static constexpr byte water_interrupt = 3;
    } pins = Pins{};

    void setup() {
      pinMode(pins.water_interrupt, INPUT_PULLUP);
    }

    unsigned long get_counter() const {
      InterruptGuard _();
      return m_water_counter;
    }

    void step() {
      ++m_water_counter;
    }

  private:
    volatile unsigned long m_water_counter = 0;
};

CmdParser cmdParser;
Water water;
Cover cover;
Button button{&cover};

void setup()
{
  // EEPROM safety during debugging
  EEPROM.setMemPool(0, EEPROMSizeUno);
  EEPROM.setMaxAllowedWrites(50);

  Serial.begin(9600);

  water.setup();
  attachInterrupt(digitalPinToInterrupt(Water::pins.water_interrupt), water_isr, FALLING);

  cover.setup();
  attachInterrupt(digitalPinToInterrupt(Cover::pins.cover_interrupt), cover_isr, FALLING);

  button.setup();
}

static void cover_isr() {
  static unsigned long last_interrupt_time = 0;
  auto interrupt_time = millis();
  // Debounce
  if (interrupt_time - last_interrupt_time > 40)
  {
    cover.step();
  }
  last_interrupt_time = interrupt_time;
}

static void water_isr() {
  static unsigned long last_interrupt_time = 0;
  auto interrupt_time = millis();
  // Debounce
  if (interrupt_time - last_interrupt_time > 40)
  {
    water.step();
  }
  last_interrupt_time = interrupt_time;
}

void loop()
{
  // Read from serial
  if (Serial.available() > 0) {
    // Use own buffer from serial input
    CmdBuffer<32> buffer;
    if (buffer.readFromSerial(&Serial, 30000)) {
      if (cmdParser.parseCmd(&buffer) != CMDPARSER_ERROR) {
        if (cmdParser.equalCommand("open")) {
          Serial.println("open");
          cover.set_direction(Cover::Direction::OPEN);
        } else if (cmdParser.equalCommand("close")) {
          Serial.println("close");
          cover.set_direction(Cover::Direction::CLOSE);
        } else if (cmdParser.equalCommand("stop")) {
          Serial.println("stop");
          cover.set_direction(Cover::Direction::STOP);
        } else if (cmdParser.equalCommand("position")) {
          Serial.print("position ");
          Serial.println(cover.get_position());
        } else if (cmdParser.equalCommand("water")) {
          Serial.print("water ");
          Serial.println(water.get_counter());
        } else if (cmdParser.equalCommand("debug")) {
          Serial.println("debug");
          cover.debug();
        } else if (cmdParser.equalCommand("reset")) {
          Serial.println("reset");
          cover.reset();
        }
      } else {
        Serial.println("error");
      }
    }
  }

  // Handle buttons. They have an higher priority over the serial communication
  button.process(millis());

  // Action
  cover.process_direction();
}
