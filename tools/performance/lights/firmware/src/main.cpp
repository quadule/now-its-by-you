// The lanterns' firmware: the same on every T-Display. A board whose USB the laptop talks to is the host: it
// broadcasts each packet the laptop sends over ESP-NOW. Every board with an id (1-8) is a lantern: it shows its
// part of each packet on its strip, and tells the host its battery once a second. The host can be a lantern too.
//
// A packet, over the serial line and over the air alike:
//   'S' 'B' version(1) kind seq(u16 LE) body...     at most 250 bytes
//   kind 1, pixels:      body = segments of [id][start][count][r g b] x count
//   kind 2, brightness:  body = pairs of [id][max 0-255], id 255 for every lantern
//   kind 3, dark:        no body; every lantern goes dark
//   kind 4, screen:      body = 20-byte records [id][scene][r g b][r2 g2 b2][a][b][c][d][e][f][g][h][i][j][k][backlight]
//                        (scenes.h)
//   kind 0x80, status:   body = [id][mV u16][received u16][lost u16][uptime s u16], lantern to host, once a second
// The laptop frames a packet as 0xA5, length, the packet, the XOR of the packet's bytes; the host stamps seq.
// The host writes text lines back: "lantern id=2 mv=3712 rx=50 lost=0 up=123" for each status it hears.
// Text commands on the serial line: "id N" (0 = host only, kept in flash), "rot" (turns the screen upside down,
// kept in flash) and "status".
//
// The screen shows the scene the packets ask for; with packets but no scene it is off; with no packets at all it
// shows the lantern's id, battery and reception. Without a packet for 2 s a lantern goes dark. Left button held 1 s: next id. Right button held: the strip
// lights as many LEDs as its id, white, to check a lantern alone.

#include <NeoPixelBus.h>
#include <Preferences.h>
#include <TFT_eSPI.h>
#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#include "scenes.h"

#define BAT_PIN 34
#define BAT_EN_PIN 14
#define BTN_LEFT 0
#define BTN_RIGHT 35
#define CHANNEL 1
#define MAX_ID 8
#define TIMEOUT_MS 2000

// I2S with DMA: the whole strip goes out in hardware, so the radio's and the serial line's interrupts can't
// stretch a bit (the RMT driver garbled frames while packets were coming in)
NeoPixelBus<NeoGrbFeature, NeoEsp32I2s1Ws2812xMethod> strip(NUM_LEDS, LED_PIN);
TFT_eSPI tft;
TFT_eSprite frame(&tft);
Preferences prefs;
const uint8_t BROADCAST[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};

uint8_t myId = 0;
uint8_t pixels[NUM_LEDS * 3];  // what the packets have asked for
uint8_t maxLevel = 255;
volatile bool dirty = false;
volatile uint32_t lastRx = 0, lastSerial = 0;
volatile uint16_t rxCount = 0, lostCount = 0, lastSeq = 0;
volatile bool seqKnown = false;
uint16_t rxRate = 0, lostRate = 0, sendFails = 0, hostSent = 0, hostRate = 0;
uint32_t mv = 0;
bool dark = true;
Scene scene = {};
volatile bool sceneDirty = false;
volatile uint32_t lastScene = 0;
uint8_t rot = 0;
uint32_t renderMs = 0;
bool radioOn = true;  // "radio": the host stops (or starts) broadcasting, to tell the radio's effect on the strip
bool localFade = false;  // "fade": the board fades its own strip, no packets involved, to tell the strip's faults
                         // from the link's
portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;

// ms from `then` to `now`, 0 when `then` came after `now` (a packet can arrive after the loop read the clock)
int32_t since(uint32_t then, uint32_t now) { return max((int32_t)(now - then), (int32_t)0); }

uint32_t readBattery() {
  uint32_t sum = 0;
  for (int i = 0; i < 8; i++) sum += analogReadMilliVolts(BAT_PIN);
  return sum / 8 * 2;
}

// A packet from the air or from the host's own serial line.
void handle(const uint8_t *p, int len) {
  if (len < 6 || p[0] != 'S' || p[1] != 'B' || p[2] != 1) return;
  uint8_t kind = p[3];
  uint16_t seq = p[4] | (p[5] << 8);
  if (kind == 0x80) {
    if (len >= 15)
      Serial.printf("lantern id=%u mv=%u rx=%u lost=%u up=%u\n", p[6], p[7] | (p[8] << 8), p[9] | (p[10] << 8),
                    p[11] | (p[12] << 8), p[13] | (p[14] << 8));
    return;
  }
  portENTER_CRITICAL(&lock);
  if (seqKnown && seq != (uint16_t)(lastSeq + 1)) {
    uint16_t gap = seq - lastSeq - 1;
    if (gap < 1000) lostCount += gap;
  }
  lastSeq = seq, seqKnown = true;
  rxCount++;
  lastRx = millis();
  if (kind == 1) {
    int i = 6;
    while (i + 3 <= len) {
      uint8_t id = p[i], start = p[i + 1], count = p[i + 2];
      i += 3;
      if (i + count * 3 > len) break;
      if (id == myId && myId) {
        for (int k = 0; k < count && start + k < NUM_LEDS; k++) memcpy(&pixels[(start + k) * 3], &p[i + k * 3], 3);
        dirty = true;
      }
      i += count * 3;
    }
  } else if (kind == 2) {
    for (int i = 6; i + 2 <= len; i += 2)
      if (p[i] == myId || p[i] == 255) maxLevel = p[i + 1], dirty = true;
  } else if (kind == 3) {
    memset(pixels, 0, sizeof pixels);
    dirty = true;
    scene = {};
    sceneDirty = true;
    lastScene = millis();
  } else if (kind == 4) {
    for (int i = 6; i + 1 + (int)sizeof(Scene) <= len; i += 1 + sizeof(Scene))
      if (p[i] == myId && myId) {
        memcpy(&scene, &p[i + 1], sizeof scene);
        sceneDirty = true;
        lastScene = millis();
      }
  }
  portEXIT_CRITICAL(&lock);
}

void onReceive(const uint8_t *mac, const uint8_t *data, int len) { handle(data, len); }

void setId(int id) {
  myId = constrain(id, 0, MAX_ID);
  prefs.putUChar("id", myId);
  memset(pixels, 0, sizeof pixels);
  dirty = true;
  Serial.printf("id=%u\n", myId);
}

// The serial line: binary packets framed by 0xA5, text commands between them.
void readSerial() {
  static uint8_t buf[256];
  static int want = -1, got = 0;  // want: the packet's length once read; -1 between packets
  static bool inFrame = false;
  static String line;
  while (Serial.available()) {
    uint8_t c = Serial.read();
    if (!inFrame) {
      if (c == 0xA5) { inFrame = true, want = -1, got = 0; continue; }
      if (c == '\n') {
        line.trim();
        if (line.startsWith("id ")) setId(line.substring(3).toInt());
        else if (line == "fade") localFade = !localFade, Serial.printf("fade=%d\n", localFade);
        else if (line == "radio") radioOn = !radioOn, Serial.printf("radio=%d\n", radioOn);
        else if (line == "rot") {
          rot = rot ? 0 : 2;
          prefs.putUChar("rot", rot);
          tft.setRotation(rot);
          Serial.printf("rot=%u\n", rot);
        } else if (line == "status")
          Serial.printf("host id=%u mv=%u sent=%u/s fails=%u screen=%ums\n", myId, mv, hostRate, sendFails, renderMs);
        line = "";
      } else if (c >= 32 && c < 127 && line.length() < 40) line += (char)c;
      continue;
    }
    if (want < 0) {
      want = c;
      if (want < 6 || want > 250) inFrame = false;
      continue;
    }
    if (got < want) { buf[got++] = c; continue; }
    inFrame = false;
    uint8_t x = 0;
    for (int i = 0; i < want; i++) x ^= buf[i];
    if (x != c) continue;
    static uint16_t seq = 0;
    seq++;
    buf[4] = seq & 0xff, buf[5] = seq >> 8;
    if (radioOn && esp_now_send(BROADCAST, buf, want) != ESP_OK) sendFails++;
    hostSent++;
    lastSerial = millis();
    handle(buf, want);
  }
}

void show(bool identify) {
  if (identify) {
    for (int i = 0; i < NUM_LEDS; i++) strip.SetPixelColor(i, i < max(1, (int)myId) ? RgbColor(60) : RgbColor(0));
    strip.Show();
    return;
  }
  uint8_t copy[NUM_LEDS * 3];
  portENTER_CRITICAL(&lock);
  memcpy(copy, pixels, sizeof copy);
  uint16_t scale = maxLevel + 1;
  dirty = false;
  portEXIT_CRITICAL(&lock);
  for (int i = 0; i < NUM_LEDS; i++)
    strip.SetPixelColor(i, RgbColor(copy[i * 3] * scale >> 8, copy[i * 3 + 1] * scale >> 8, copy[i * 3 + 2] * scale >> 8));
  strip.Show();
}

void sendStatus(uint32_t now) {
  uint8_t p[15] = {'S', 'B', 1, 0x80, 0, 0, myId};
  uint16_t v[] = {(uint16_t)mv, rxRate, lostRate, (uint16_t)(now / 1000)};
  for (int i = 0; i < 4; i++) p[7 + i * 2] = v[i] & 0xff, p[8 + i * 2] = v[i] >> 8;
  esp_now_send(BROADCAST, p, sizeof p);
}

// The status screen, for setting up: no packets are coming.
void draw(uint32_t now) {
  bool host = since(lastSerial, now) < TIMEOUT_MS;
  frame.fillSprite(TFT_BLACK);
  frame.setTextColor(TFT_WHITE, TFT_BLACK);
  frame.setTextFont(7);  // the big digits
  frame.setCursor(6, 6);
  frame.print(myId);
  frame.setTextFont(4);
  frame.setCursor(6, 66);
  frame.setTextColor(mv < 3500 ? TFT_RED : mv < 3700 ? TFT_YELLOW : TFT_GREEN, TFT_BLACK);
  frame.printf("%.2fV", mv / 1000.0);
  frame.setCursor(6, 96);
  frame.setTextColor(host ? TFT_CYAN : TFT_RED, TFT_BLACK);
  frame.print(host ? "host" : "no signal");
  frame.setTextFont(2);
  frame.setTextColor(TFT_WHITE, TFT_BLACK);
  frame.setCursor(6, 130);
  if (host) frame.printf("sent %u/s", hostRate);
  frame.setCursor(6, 150);
  frame.printf("max %u%%", maxLevel * 100 / 255);
  if (!myId) {
    frame.setCursor(6, 170);
    frame.print("id 0: shows nothing");
  }
  // the strip as it is, one dot an LED
  for (int i = 0; i < NUM_LEDS; i++) {
    RgbColor c = strip.GetPixelColor(i);
    frame.fillRect(6 + (i % 20) * 6, 200 + (i / 20) * 8, 5, 6, frame.color565(c.R, c.G, c.B));
  }
  frame.pushSprite(0, 0);
}

void backlight(uint8_t level) {
  static int now = -1;
  if (level != now) ledcWrite(0, level), now = level;
}

// What the screen shows: the packets' scene, nothing, or the status screen.
void screen(uint32_t now) {
  static uint32_t lastDraw = 0;
  if (since(lastScene, now) < TIMEOUT_MS) {
    if (!sceneDirty || now - lastDraw < 30) return;  // at most about 30 frames a second
    lastDraw = now;
    Scene s;
    portENTER_CRITICAL(&lock);
    s = scene;
    sceneDirty = false;
    portEXIT_CRITICAL(&lock);
    uint32_t t0 = millis();
    if (s.backlight) {
      // the last frame may still be going out to the screen by DMA: wait for it before drawing over it
      tft.dmaWait();
      tft.endWrite();
      scenes::render(frame, s);
      tft.startWrite();
      tft.pushImageDMA(0, 0, scenes::W, scenes::H, (uint16_t *)frame.getPointer());
    }
    backlight(s.backlight);
    renderMs = millis() - t0;
  } else if (since(lastRx, now) < TIMEOUT_MS && since(lastSerial, now) >= TIMEOUT_MS) {
    backlight(0);  // packets for the strip only: the screen stays dark on stage
  } else if (now - lastDraw >= 100) {
    lastDraw = now;
    tft.dmaWait();
    tft.endWrite();
    draw(now);
    backlight(255);
  }
}

void setup() {
  Serial.setRxBufferSize(4096);
  Serial.begin(460800);
  pinMode(BTN_LEFT, INPUT_PULLUP);
  pinMode(BTN_RIGHT, INPUT);
  pinMode(BAT_EN_PIN, OUTPUT);
  digitalWrite(BAT_EN_PIN, HIGH);
  analogSetPinAttenuation(BAT_PIN, ADC_11db);

  prefs.begin("lantern");
  myId = prefs.getUChar("id", 0);
  rot = prefs.getUChar("rot", 0);

  strip.Begin();
  strip.ClearTo(RgbColor(0));
  strip.Show();
  tft.init();
  tft.setRotation(rot);
  tft.fillScreen(TFT_BLACK);
  frame.createSprite(scenes::W, scenes::H);
  tft.initDMA();
  scenes::begin();
  ledcSetup(0, 5000, 8);
  ledcAttachPin(TFT_BL, 0);
  backlight(255);

  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  esp_wifi_set_channel(CHANNEL, WIFI_SECOND_CHAN_NONE);
  esp_now_init();
  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BROADCAST, 6);
  peer.channel = CHANNEL;
  esp_now_add_peer(&peer);
  esp_now_register_recv_cb(onReceive);

  mv = readBattery();
  Serial.printf("lantern firmware, id=%u\n", myId);
}

void loop() {
  uint32_t now = millis();
  static uint32_t lastSecond = 0, leftDown = 0;
  static bool leftWas = true, rightWas = true, leftUsed = false;

  readSerial();

  bool left = digitalRead(BTN_LEFT), right = digitalRead(BTN_RIGHT);
  if (!left && leftWas) leftDown = now, leftUsed = false;
  if (!left && !leftUsed && now - leftDown > 1000) { setId((myId + 1) % (MAX_ID + 1)); leftUsed = true; }
  leftWas = left;
  bool identify = !right;
  if (identify || rightWas != right) show(identify);
  rightWas = right;

  // the strip is rewritten every few ms whether or not a frame came: a frame garbled on the wire to the LEDs
  // is gone before it can be seen
  static uint32_t lastShow = 0;
  if (localFade) {
    float v = 0.5f - 0.5f * cosf(now / 8000.0f * 2 * PI);  // dark to full and back in 8 s
    portENTER_CRITICAL(&lock);
    for (int i = 0; i < NUM_LEDS; i++)
      pixels[i * 3] = 255 * v, pixels[i * 3 + 1] = 140 * v, pixels[i * 3 + 2] = 40 * v;
    lastRx = now;
    dirty = true;
    portEXIT_CRITICAL(&lock);
  }
  if (!identify) {
    if (since(lastRx, now) > TIMEOUT_MS && !dark) {
      portENTER_CRITICAL(&lock);
      memset(pixels, 0, sizeof pixels);
      portEXIT_CRITICAL(&lock);
      dark = true;
    } else if (dirty) {
      dark = false;
    }
    if (dirty || now - lastShow >= 4) {
      show(false);
      lastShow = now;
    }
  }

  if (now - lastSecond >= 1000) {
    lastSecond = now;
    portENTER_CRITICAL(&lock);
    rxRate = rxCount, lostRate = lostCount, rxCount = 0, lostCount = 0;
    portEXIT_CRITICAL(&lock);
    hostRate = hostSent, hostSent = 0;
    mv = (mv * 3 + readBattery()) / 4;
    if (myId) sendStatus(now);
  }
  screen(now);
}
