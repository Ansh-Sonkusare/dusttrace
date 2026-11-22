// DustTrace Node (PRD F9): ESP32 + Plantower PMS5003 + Sensirion SHT31.
// Written for Arduino-ESP32 core 3.x with the Adafruit SHT31 library. Not compiled in CI.
//
// Wiring: PMS5003 TX -> GPIO16 (RX2), RX -> GPIO17 (TX2), 5 V and GND.
//         SHT31 SDA -> GPIO21, SCL -> GPIO22, 3.3 V and GND.
// The server corrects PM for humidity, so send raw PM and the RH the SHT31 measured.

#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_SHT31.h>
#include <time.h>

// Fill these in before flashing; NODE_KEY comes from `python -m dusttrace node-add ...`.
const char* WIFI_SSID = "your-wifi";
const char* WIFI_PASS = "your-password";
const char* NODE_ID   = "node-marol-school";
const char* NODE_KEY  = "paste-the-key-node-add-printed";
const char* ENDPOINT  = "https://dusttrace-mumbai.vercel.app/api/node";
// The root CA certificate (PEM) the server's chain ends at, not an intermediate: intermediates rotate.
//   openssl s_client -showcerts -connect dusttrace-mumbai.vercel.app:443 </dev/null
// prints the chain up to the intermediate; the issuer of its last certificate names the root.
// Download that root from its CA (for Let's Encrypt, ISRG Root X1 at letsencrypt.org/certificates).
const char* ROOT_CA = "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----\n";

struct Reading { time_t ts; uint16_t pm25; uint16_t pm10; float rh; float temp; };
const int MAX_BUF = 60;               // the API accepts up to 60 readings per post
Reading buf[MAX_BUF];
int nbuf = 0;

Adafruit_SHT31 sht31;
HardwareSerial pms(2);

// One 32-byte PMS5003 frame; returns true with atmospheric PM2.5/PM10 (µg/m³) on a valid checksum.
bool readPms(uint16_t& pm25, uint16_t& pm10) {
  uint8_t f[32];
  unsigned long until = millis() + 3000;
  while (millis() < until) {
    if (pms.available() >= 32 && pms.peek() == 0x42) {
      pms.readBytes(f, 32);
      if (f[1] != 0x4D) continue;
      uint16_t sum = 0;
      for (int i = 0; i < 30; i++) sum += f[i];
      if (sum != ((f[30] << 8) | f[31])) continue;
      pm25 = (f[12] << 8) | f[13];
      pm10 = (f[14] << 8) | f[15];
      return true;
    } else if (pms.available() && pms.peek() != 0x42) {
      pms.read();
    }
    delay(10);
  }
  return false;
}

String iso(time_t t) {
  char s[25];
  strftime(s, sizeof s, "%Y-%m-%dT%H:%M:%SZ", gmtime(&t));
  return String(s);
}

bool postBuffer() {
  if (WiFi.status() != WL_CONNECTED || nbuf == 0) return false;
  String body = String("{\"node_id\":\"") + NODE_ID + "\",\"readings\":[";
  for (int i = 0; i < nbuf; i++) {
    if (i) body += ",";
    body += "{\"ts\":\"" + iso(buf[i].ts) + "\",\"pm25\":" + buf[i].pm25 + ",\"pm10\":" + buf[i].pm10;
    if (!isnan(buf[i].rh)) body += ",\"rh\":" + String(buf[i].rh, 1) + ",\"temp\":" + String(buf[i].temp, 1);
    body += "}";
  }
  body += "]}";
  WiFiClientSecure tls;
  tls.setCACert(ROOT_CA);
  HTTPClient http;
  http.begin(tls, ENDPOINT);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("Authorization", String("Bearer ") + NODE_KEY);
  int code = http.POST(body);
  http.end();
  // 200: stored (re-sent minutes are ignored server-side). 400: the server refused a reading, and 401:
  // the key is wrong; both fail again on retry, so drop the batch. Anything else: keep it and retry.
  if (code == 200 || code == 400 || code == 401) { nbuf = 0; return code == 200; }
  Serial.printf("post failed: %d\n", code);
  return false;
}

void setup() {
  Serial.begin(115200);
  pms.begin(9600, SERIAL_8N1, 16, 17);
  sht31.begin(0x44);
  WiFi.begin(WIFI_SSID, WIFI_PASS);
  configTime(0, 0, "pool.ntp.org", "time.google.com");
}

bool clockIsSet(time_t t) { return t > 1700000000; }  // 2023-11-14: before NTP answers, time() is near 1970

void dropOldest() {
  memmove(buf, buf + 1, sizeof(Reading) * (MAX_BUF - 1));
  nbuf--;
}

void loop() {
  static unsigned long next = 0;
  if (millis() < next) { delay(200); return; }
  next = millis() + 60000;
  time_t now = time(nullptr);
  uint16_t pm25, pm10;
  if (clockIsSet(now) && readPms(pm25, pm10)) {
    if (nbuf == MAX_BUF) dropOldest();
    buf[nbuf++] = { now, pm25, pm10, sht31.readHumidity(), sht31.readTemperature() };
  }
  if (WiFi.status() != WL_CONNECTED) WiFi.reconnect();
  postBuffer();
}
