/*
 Test for sending POST request to backend server for CradleWave
*/
#define NINA_DEBUG
#include <SPI.h>
#include <WiFiNINA.h>
#include "secrets.h"

///////please enter your sensitive data in the Secret tab/arduino_secrets.h
char ssid[] = "UD Devices";        // your network SSID (name)
// char ssid[] = "LAN of Milk and Honey";        // your network SSID (name)
// char pswd[] = "promiseLand";    // your network password (use for WPA, or use as key for WEP)
int status = WL_IDLE_STATUS;     // the WiFi radio's status
// char server[] = "httpbin.org";
char server[] = "cradlewave-351958736605.northamerica-northeast2.run.app";

WiFiSSLClient client;

void printCurrentNet();
void printWifiData();
void printMacAddress(byte mac[]);
String sendRequest(char *host, const char *path, const char *postData);

void setup() {
  //Initialize serial and wait for port to open:
  Serial.begin(9600);
  while (!Serial) {
    ; // wait for serial port to connect. Needed for native USB port only
  }
  // check for the WiFi module:
  if (WiFi.status() == WL_NO_MODULE) {
    Serial.println("Communication with WiFi module failed!");
    // don't continue
    while (true);
  }

  String fv = WiFi.firmwareVersion();
  if (fv < WIFI_FIRMWARE_LATEST_VERSION) {
    Serial.println("Please upgrade the firmware");
  }

  // attempt to connect to WiFi network:
  while (status != WL_CONNECTED) {
    Serial.print("Attempting to connect to open SSID: ");
    Serial.println(ssid);
    status = WiFi.begin(ssid);
    delay(1000);
    }

    char path[] = "/api/test";
    char body[] = "{\"test_key\":\"test_value\"}";

    String response = sendRequest(server,path,body);
    Serial.println("Response from server:");
    Serial.println(response);
  }


void loop() {
  
}

String sendRequest(char *host, const char *path, const char *postData) {
  Serial.print("Attempting to connect to ");
  Serial.println(host);

  if (!client.connect(host, 443)) {
    Serial.println("Connection failed.");
    return "ERROR_CONNECT";
  }

  Serial.println("Connected to server");

  // Prepare the HTTP request in a fixed-size buffer
  char request[512];
  int contentLength = strlen(postData);

  snprintf(request, sizeof(request),
           "POST %s HTTP/1.1\r\n"
           "Host: %s\r\n"
           "Content-Type: application/json\r\n"
           "Content-Length: %d\r\n"
           "Connection: close\r\n\r\n"
           "%s",
           path, host, contentLength, postData);

  // Send the request
  client.print(request);

  // Read the response headers
  while (client.connected()) {
    String line = client.readStringUntil('\n');
    if (line == "\r" || line.length() == 0) {
      Serial.println("Headers received\n");
      break;
    }
  }

  // Read the response body
  String response = client.readString();
  client.stop();

  return response;
}


void printWifiData() {
  // print your board's IP address:
  IPAddress ip = WiFi.localIP();
  Serial.print("IP Address: ");
  Serial.println(ip);
  Serial.println(ip);

  // print your MAC address:
  byte mac[6];
  WiFi.macAddress(mac);
  Serial.print("MAC address: ");
  printMacAddress(mac);

  // print your subnet mask:
  IPAddress subnet = WiFi.subnetMask();
  Serial.print("NetMask: ");
  Serial.println(subnet);

  // print your gateway address:
  IPAddress gateway = WiFi.gatewayIP();
  Serial.print("Gateway: ");
  Serial.println(gateway);
}

void printCurrentNet() {
  // print the SSID of the network you're attached to:
  Serial.print("SSID: ");
  Serial.println(WiFi.SSID());

  // print the MAC address of the router you're attached to:
  byte bssid[6];
  WiFi.BSSID(bssid);
  Serial.print("BSSID: ");
  printMacAddress(bssid);

  // print the received signal strength:
  long rssi = WiFi.RSSI();
  Serial.print("Signal strength (RSSI): ");
  Serial.println(rssi);

  // print the encryption type:
  Serial.print("Encryption Type: ");
  Serial.println(WiFi.encryptionType());
}

void printMacAddress(byte mac[]) {
  for (int i = 0; i < 6; i++) {
    if (mac[i] < 16) {
      Serial.print('0');
    }
    Serial.print(mac[i], HEX);
    if (i < 5) {
      Serial.print(':');
    }
  }
  Serial.println();
}

