// Requires CmdParser and InputDebounce

#include <CmdParser.hpp>
#include <InputDebounce.h>

CmdParser cmdParser;

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
      static constexpr byte button_open = 8;
      static constexpr byte button_close = 9;
      static constexpr byte button_save_open = 10;
      static constexpr byte button_save_close = 11;
    } pins = Pins{};

    struct Position {
      volatile long position = 0;
      volatile long close = 0;
      volatile long open = 20;
    };

    enum class Direction : byte {
      OPEN, CLOSE, STOP,
    };

    Cover() {}
    Cover(Position position) : m_position{position} {}


    void setup() {
      pinMode(pins.cover_interrupt, INPUT_PULLUP);

      pinMode(pins.cover_close, OUTPUT);
      pinMode(pins.cover_open, OUTPUT);
    }

    void process_direction() {
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
          break;
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
          m_position.close = m_position.close;
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
      return 100 * (m_position.position - m_position.close) / diff;
    }

    void step() {
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

  private:
    Position m_position;
    volatile Direction m_direction = Direction::STOP;
    volatile bool m_set_limits = false;
};

struct Button {
  InputDebounce open;
  InputDebounce close;
  InputDebounce save_open;
  InputDebounce save_close;
} buttons;

Cover cover;

void open_pressed(uint8_t pin) {
  cover.set_direction(Cover::Direction::OPEN);
}

void close_pressed(uint8_t pin) {
  cover.set_direction(Cover::Direction::CLOSE);
}

void open_close_released(uint8_t pin) {
  cover.set_direction(Cover::Direction::STOP);
}


void save_open_pressed(uint8_t pin) {
  cover.set_limit(Cover::Direction::OPEN);
}

void save_close_pressed(uint8_t pin) {
  cover.set_limit(Cover::Direction::CLOSE);
}

void save_open_close_released(uint8_t pin) {
  cover.set_limit(Cover::Direction::STOP);
}


void setup()
{
  cover.setup();
  attachInterrupt(digitalPinToInterrupt(Cover::pins.cover_interrupt), cover_isr, FALLING);

  buttons.open.registerCallbacks(open_pressed, open_close_released);
  buttons.open.setup(Cover::pins.button_open);
  buttons.close.registerCallbacks(close_pressed, open_close_released);
  buttons.close.setup(Cover::pins.button_close);
  buttons.save_open.registerCallbacks(nullptr, save_open_close_released, save_open_pressed);
  buttons.save_open.setup(Cover::pins.button_save_open);
  buttons.save_close.registerCallbacks(nullptr, save_open_close_released, save_close_pressed);
  buttons.save_close.setup(Cover::pins.button_save_close);

  Serial.begin(9600);
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


void loop()
{
  // Use own buffer from serial input
  CmdBuffer<32> buffer;

  // Read from serial
  if (Serial.available() > 0) {
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
          Serial.println("water");
        }
      } else {
        Serial.println("Parser error!");
      }
    } else {
      //Serial.println("TIMEOUT!");
    }
  }

  // Handle buttons
  auto now = millis();
  buttons.open.process(now);
  buttons.close.process(now);
  buttons.save_open.process(now);
  buttons.save_close.process(now);

  // Action
  cover.process_direction();
}
