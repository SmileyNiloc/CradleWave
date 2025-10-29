#include <WiFiNINA_Generic.h>
#include <WebSockets2_Generic.h>
using namespace websockets2_generic;

WebsocketsClient wsClient;

const char* ssid     = "Hothspot";
const char* pswd = "catenconnect";
const String ws_host  = "wss://cradlewave-351958736605.us-central1.run.app/ws";
String serialInputText = "";


void onMessage(WebsocketsMessage message) {
  Serial.print("[WS] Message: ");
  Serial.println(message.data());
}

void onEvent(WebsocketsEvent event, String data) {
  switch(event) {
    case WebsocketsEvent::ConnectionOpened:
      Serial.println("[WS] Connected!");
      wsClient.send("Hello from SAMD21 via WSS!");
      break;
    case WebsocketsEvent::ConnectionClosed:
      Serial.println("[WS] Disconnected!");
      break;
    case WebsocketsEvent::GotPing:
      Serial.println("[WS] Got ping!");
      break;
    case WebsocketsEvent::GotPong:
      Serial.println("[WS] Got pong!");
      break;
  }
}

// ====== WIFI CONNECT ======
void connectWiFi() {
  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("[WiFi] No WiFi module found!");
    while (true);
  }

  Serial.print("[WiFi] Connecting to ");
  Serial.println(ssid);
  WiFi.begin(ssid, pswd);

  uint8_t attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < 30) {
    delay(500);
    Serial.print(".");
    attempts++;
  }
  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("[WiFi] Connected! IP: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("[WiFi] Connection failed!");
  }
}

// ====== WEBSOCKET CONNECT ======
void connectWebSocket() {
  wsClient.onMessage(onMessage);
  wsClient.onEvent(onEvent);

  Serial.print("[WS] Connecting to ");
  Serial.println(ws_host);
  // Serial.print(ws_port);
  // Serial.println(ws_path);

  if (wsClient.connect(ws_host)) {
    Serial.println("[WS] Handshake OK");
  } else {
    Serial.println("[WS] Connection failed");
  }
}

// ====== SETUP ======
void setup() {
  Serial.begin(115200);
  while (!Serial);

  connectWiFi();
  connectWebSocket();
}

// ====== MAIN LOOP ======
void loop() {
  // Keep WiFi alive
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[WiFi] Lost connection, reconnecting...");
    connectWiFi();
  }

  // Keep WebSocket alive
  if (!wsClient.available()) {
    Serial.println("[WS] Reconnecting...");
    connectWebSocket();
  }

  wsClient.poll();
  // Check for serial input
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    //When user presses enter
    if (inChar == '\n') {
      Serial.print("[SERIAL] Sending: ");
      Serial.println(serialInputText);
      if(serialInputText.length() == 0) continue;
      if(serialInputText[0] == '0' && serialInputText[1] == 'b'){
        wsClient.sendBinary(serialInputText.c_str()+2);
      }
      //Send the serial input over WebSocket
      wsClient.send(serialInputText);
      serialInputText = "";
    } else {
      serialInputText += inChar;
    }
  }
}