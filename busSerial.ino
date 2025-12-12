// Bus-servo control via SoftwareSerial; host commands arrive on Serial.
// Host command format: "<id>,<pulse_us>[,<time_ms>]" e.g. "0,1640,1000".
// Bus frame sent: ASCII "#<iii>P<pppp>T<tttt>!" e.g. "#000P1640T1000!".

#include <SoftwareSerial.h>

// Adjust to the pins wired to the bus servo (RX, TX).
constexpr uint8_t BUS_RX_PIN = 10;
constexpr uint8_t BUS_TX_PIN = 11;

// Baud rate for the bus servo; adjust if your servo expects a different rate.
constexpr unsigned long BUS_BAUD = 115200;

// Bounds for pulse width in microseconds; keep servos safe.
const uint16_t PULSE_MIN_US = 500;
const uint16_t PULSE_MAX_US = 2500;

// Global default time in ms, can be set via "ct<value>" command.
uint16_t defaultTimeMs = 1000;

SoftwareSerial busSerial(BUS_RX_PIN, BUS_TX_PIN);

void setup() {
  Serial.begin(115200);            // Host interface
  busSerial.begin(BUS_BAUD);        // Servo bus
  Serial.println("Ready: send <id>,<pulse_us>");
}

// Send move command to bus servo using ASCII format: #000P1640T1000!
// Returns the frame sent so it can be logged once.
String sendServoMove(uint16_t id, uint16_t pulseUs, uint16_t timeMs) {
  if (pulseUs < PULSE_MIN_US) pulseUs = PULSE_MIN_US;
  if (pulseUs > PULSE_MAX_US) pulseUs = PULSE_MAX_US;
  if (timeMs == 0) timeMs = 1; // avoid zero-time moves if servo dislikes it
  if (id > 999) id = 999;      // protocol expects 3 digits

  // Build full frame then send in one write: #<iii>P<pppp>T<tttt>!
  // ID: 3 digits, PulseUs: 4 digits, TimeMs: 4 digits (all left-padded with zeros)
  String frame = "#";
  if (id < 100) frame += "0";
  if (id < 10)  frame += "0";
  frame += id;
  frame += 'P';
  if (pulseUs < 1000) frame += "0";
  if (pulseUs < 100)  frame += "0";
  if (pulseUs < 10)   frame += "0";
  frame += pulseUs;
  frame += 'T';
  if (timeMs < 1000) frame += "0";
  if (timeMs < 100)  frame += "0";
  if (timeMs < 10)   frame += "0";
  frame += timeMs;
  frame += '!';

  busSerial.print(frame);
  return frame;
}

// Read a full line from Serial into outLine; returns true when a line is complete.
bool readLine(String &outLine) {
  static String buf;
  while (Serial.available()) {
    char c = static_cast<char>(Serial.read());
    if (c == '\r') continue;
    if (c == '\n') {
      outLine = buf;
      buf = "";
      return outLine.length() > 0;
    }
    buf += c;
  }
  return false;
}

// Handle C#...! pass-through (case-insensitive 'C'): send full command after 'C' to bus and echo any reply.
bool handlePassthrough(const String &line) {
  if (line.length() < 3) return false;
  char c0 = line.charAt(0);
  if (!(c0 == 'C' || c0 == 'c')) return false;
  if (line.charAt(1) != '#') return false;
  if (!line.endsWith("!")) {
    Serial.println("Invalid C# command (missing !)");
    return true; // consumed
  }

  String payload = line.substring(1); // keep leading # for the servo frame
  busSerial.print(payload);
  

  // Briefly read any available response and print it.
  delay(5);
  while (busSerial.available()) {
    int ch = busSerial.read();
    if (ch >= 0) Serial.write(ch);
  }
  Serial.print("C# sent -> ");
  Serial.println(payload);
  if (busSerial.available() == 0) Serial.println();
  return true;
}

// Parse one segment "id,pulse[,time]"; returns true if valid.
bool parseSegment(const String &seg, uint16_t &idOut, uint16_t &pulseOut, uint16_t &timeOut) {
  int comma1 = seg.indexOf(',');
  int comma2 = seg.indexOf(',', comma1 + 1);
  if (comma1 < 0) return false;

  long id = seg.substring(0, comma1).toInt();
  long pulse = comma2 > 0 ? seg.substring(comma1 + 1, comma2).toInt()
                          : seg.substring(comma1 + 1).toInt();
  long timeMs = comma2 > 0 ? seg.substring(comma2 + 1).toInt() : defaultTimeMs;

  if (id < 0 || id > 999 || pulse <= 0) return false;
  if (timeMs <= 0) timeMs = 1; // avoid zero time moves

  idOut = static_cast<uint16_t>(id);
  pulseOut = static_cast<uint16_t>(pulse);
  timeOut = static_cast<uint16_t>(timeMs);
  return true;
}

void loop() {
  String line;
  if (readLine(line)) {
    // Passthrough command: C#...!
    if (handlePassthrough(line)) return;

    // Check for 'ct' command to set default timeMs (e.g., "ct100" sets defaultTimeMs=100)
    if (line.startsWith("ct")) {
      String timeStr = line.substring(2);
      long newTime = timeStr.toInt();
      if (newTime > 0) {
        defaultTimeMs = static_cast<uint16_t>(newTime);
        Serial.print("Default time set to: ");
        Serial.println(defaultTimeMs);
      } else {
        Serial.println("Invalid time value for ct command.");
      }
      return;
    }

    // Parse servo commands
    int start = 0;
    while (start < line.length()) {
      int sep = line.indexOf(';', start);
      String seg = sep >= 0 ? line.substring(start, sep) : line.substring(start);
      seg.trim();
      if (seg.length() > 0) {
        uint16_t id, pulse, timeMs;
        if (parseSegment(seg, id, pulse, timeMs)) {
          String frame = sendServoMove(id, pulse, timeMs);
          Serial.print("Sent -> ");
          Serial.println(frame);
        } else {
          Serial.print("Skip invalid segment: ");
          Serial.println(seg);
        }
      }
      if (sep < 0) break;
      start = sep + 1;
    }
  }
}