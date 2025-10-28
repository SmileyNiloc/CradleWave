/**
 * The bare minimum code example for using Realtime Database service.
 *
 * The steps which are generally required are explained below.
 *
 * Step 1. Include the network, SSL client and Firebase libraries.
 * ===============================================================
 *
 * Step 2. Define the user functions that are required for library usage.
 * =====================================================================
 *
 * Step 3. Define the authentication config (identifier) class.
 * ============================================================
 * In the Firebase/Google Cloud services REST APIs, the auth tokens are used for authentication/authorization.
 *
 * The auth token is a short-lived token that will be expired in 60 minutes and need to be refreshed or re-created when it expired.
 *
 * There can be some special use case that some services provided the non-authentication usages e.g. using database secret
 * in Realtime Database, setting the security rules in Realtime Database, Firestore and Firebase Storage to allow public read/write access.
 *
 * The UserAuth (user authentication with email/password) is the basic authentication for Realtime Database,
 * Firebase Storage and Firestore services except for some Firestore services that involved with the Google Cloud services.
 *
 * It stores the email, password and API keys for authentication process.
 *
 * In Google Cloud services e.g. Cloud Storage and Cloud Functions, the higest authentication level is required and
 * the ServiceAuth class (OAuth2.0 authen) and AccessToken class will be use for this case.
 *
 * While the CustomAuth provides the same authentication level as user authentication unless it allows the custom UID and claims.
 *
 * Step 4. Define the authentication handler class.
 * ================================================
 * The FirebaseApp actually works as authentication handler.
 * It also maintains the authentication or re-authentication when you place the FirebaseApp::loop() inside the main loop.
 *
 * Step 5. Define the SSL client.
 * ==============================
 * It handles server connection and data transfer works.
 *
 * In this beare minimum example we use only one SSL client for all processes.
 * In some use cases e.g. Realtime Database Stream connection, you may have to define the SSL client for it separately.
 *
 * Step 6. Define the Async Client.
 * ================================
 * This is the class that is used with the functions where the server data transfer is involved.
 * It stores all sync/async taks in its queue.
 *
 * It requires the SSL client and network config (identifier) data for its class constructor for its network re-connection
 * (e.g. WiFi and GSM), network connection status checking, server connection, and data transfer processes.
 *
 * This makes this library reliable and operates precisely under various server and network conditions.
 *
 * Step 7. Define the class that provides the Firebase/Google Cloud services.
 * ==========================================================================
 * The Firebase/Google Cloud services classes provide the member functions that works with AsyncClient.
 *
 * Step 8. Start the authenticate process.
 * ========================================
 * At this step, the authentication credential will be used to generate the auth tokens for authentication by
 * calling initializeApp.
 *
 * This allows us to use different authentications for each Firebase/Google Cloud services with different
 * FirebaseApps (authentication handler)s.
 *
 * When calling initializeApp with timeout, the authenication process will begin immediately and wait at this process
 * until it finished or timed out. It works in sync mode.
 *
 * If no timeout was assigned, it will work in async mode. The authentication task will be added to async client queue
 * to process later e.g. in the loop by calling FirebaseApp::loop.
 *
 * The workflow of authentication process.
 *
 * -----------------------------------------------------------------------------------------------------------------
 *  Setup   |    FirebaseApp [account credentials/tokens] ───> InitializeApp (w/wo timeout) ───> FirebaseApp::getApp
 * -----------------------------------------------------------------------------------------------------------------
 *  Loop    |    FirebaseApp::loop  ───> FirebaseApp::ready ───> Firebase Service API [auth token]
 * ---------------------------------------------------------------------------------------------------
 *
 * Step 9. Bind the FirebaseApp (authentication handler) with your Firebase/Google Cloud services classes.
 * ========================================================================================================
 * This allows us to use different authentications for each Firebase/Google Cloud services.
 *
 * It is easy to bind/unbind/change the authentication method for different Firebase/Google Cloud services APIs.
 *
 * Step 10. Set the Realtime Database URL (for Realtime Database only)
 * ===================================================================
 *
 * Step 11. Maintain the authentication and async tasks in the loop.
 * ==============================================================
 * This is required for authentication/re-authentication process and keeping the async task running.
 *
 * Step 12. Checking the authentication status before use.
 * =======================================================
 * Before calling the Firebase/Google Cloud services functions, the FirebaseApp::ready() of authentication handler that bined to it
 * should return true.
 *
 * Step 13. Process the results of async tasks at the end of the loop.
 * ============================================================================
 * This requires only when async result was assigned to the Firebase/Google Cloud services functions.
 */

// Step 1

#define ENABLE_USER_AUTH
#define ENABLE_DATABASE
#define ENABLE_SERVICE_AUTH

// For ESP32
#include <WiFi.h>
#include <FirebaseClient.h>
#include "../include/secrets.h"
#include <NTPClient.h>


// Step 2
void asyncCB(AsyncResult &aResult);
void processData(AsyncResult &aResult);
unsigned long getUnixTime();

// Step 3
UserAuth user_auth(FIREBASE_API_KEY, "USER_EMAIL", "USER_PASSWORD");

ServiceAuth sa_auth(FIREBASE_CLIENT_EMAIL, FIREBASE_PROJECT_ID, FIREBASE_PRIVATE_KEY, 3000 /* expire period in seconds (<3600) */);


WiFiUDP ntpUDP;
NTPClient timeClient(ntpUDP, "pool.ntp.org", 0, 60000); 

int status = WL_IDLE_STATUS;     // the WiFi radio's status

file_config_data saFileCfg;

// Step 4
FirebaseApp app;

// Step 5
// Use two SSL clients for sync and async tasks for demonstation only.
WiFiClient ssl_client1, ssl_client2;

// Step 6
// Use two AsyncClients for sync and async tasks for demonstation only.
using AsyncClient = AsyncClientClass;
AsyncClient async_client1(ssl_client1), async_client2(ssl_client2);

// Step 7
RealtimeDatabase Database;

bool onetimeTest = false;

// The Optional proxy object that provides the data/information
//  when used in async mode without callback.
AsyncResult dbResult;

void setup()
{
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
    Serial.println(WIFI_SSID);
    status = WiFi.begin(WIFI_SSID);

    // wait 10 seconds for connection:
    delay(1000);
  }

  // you're connected now, so print out the data:
  Serial.print("You're connected to the network");
  Serial.println();
  
    // The SSL client options depend on the SSL client used.

    // Skip certificate verification (Optional)
    // ssl_client1.setInsecure();
    // ssl_client2.setInsecure();

    // Set timeout for ESP32 core sdk v3.x. (Optional)
    // ssl_client1.setConnectionTimeout(1000);
    // ssl_client1.setHandshakeTimeout(5);
    // ssl_client2.setConnectionTimeout(1000);
    // ssl_client2.setHandshakeTimeout(5);

    // ESP8266 Set buffer size (Optional)
    // ssl_client1.setBufferSizes(4096, 1024);
    // ssl_client2.setBufferSizes(4096, 1024);

    //Setup Service Account
  Firebase.printf("Firebase Client v%s\n", FIREBASE_CLIENT_VERSION);

  // uint32_t wifiTime = 0;

  // while(wifiTime < 100000)
  // {
  //     Serial.println("Syncing time with NTP server...");
  //     Serial.println("Current time is: " + String(wifiTime));
  //     wifiTime = WiFi.getTime();
  //     delay(500);
  // }

  // Initialize and sync NTP
  timeClient.begin();
  timeClient.update();

// while(true){
//   Serial.print("UNIX time: ");
//   timeClient.update();
//   Serial.println(timeClient.getEpochTime());
//   delay(500);
// }
  app.setTime(getUnixTime());

    // Step 8
    initializeApp(async_client1, app, getAuth(sa_auth), processData, "🔐 authTask");

    // Step 9
    // app.getApp<RealtimeDatabase>(Database);

    // Step 10
    Database.url("DATABASE_URL");
}

void loop()
{
    // Step 11
    app.loop();

    // Step 12
    if (app.ready() && !onetimeTest)
    {
        onetimeTest = true;

        // The following code shows how to call the Firebase functions in both async and await modes
        
        // for demonstation only. You can choose async or await mode or use both modes in the same application. 
        // For await mode, no callback and AsyncResult object are assigned to the function, the function will
        // return the value or payload immediately.

        // For async mode, the value or payload will be returned later to the AsyncResult object 
        // or when the callback was called.
        // If AsyncResult was assigned to the function, please don't forget to check it before 
        // exiting the loop as in step 13.

        // For elaborate usage, plese see other examples.

        // Realtime Database set value.
        // ============================

        // Async call with callback function
        Database.set<String>(async_client1, "/examples/BareMinimum/data/set1", "abc", processData, "RealtimeDatabase_SetTask");

        // Async call with AsyncResult for returning result.
        Database.set<bool>(async_client1, "/examples/BareMinimum/data/set2", true, dbResult);

        // Realtime Database get value.
        // ============================

        // Async call with callback function
        Database.get(async_client1, "/examples/BareMinimum/data/set1", processData, false, "RealtimeDatabase_GetTask");

        // Async call with AsyncResult for returning result.
        Database.get(async_client1, "/examples/BareMinimum/data/set2", dbResult, false);

        // Await call which waits until the result was received.
        String value = Database.get<String>(async_client2, "/examples/BareMinimum/data/set3");
        if (async_client2.lastError().code() == 0)
        {
            Serial.println("Value get complete.");
            Serial.println(value);
        }
        else
            Firebase.printf("Error, msg: %s, code: %d\n", async_client2.lastError().message().c_str(), async_client2.lastError().code());
    }

    // Step 13
    processData(dbResult);
}

void processData(AsyncResult &aResult)
{
    // Exits when no result is available when calling from the loop.
    if (!aResult.isResult())
        return;

    if (aResult.isEvent())
        Firebase.printf("Event task: %s, msg: %s, code: %d\n", aResult.uid().c_str(), aResult.eventLog().message().c_str(), aResult.eventLog().code());

    if (aResult.isDebug())
        Firebase.printf("Debug task: %s, msg: %s\n", aResult.uid().c_str(), aResult.debug().c_str());

    if (aResult.isError())
        Firebase.printf("Error task: %s, msg: %s, code: %d\n", aResult.uid().c_str(), aResult.error().message().c_str(), aResult.error().code());

    if (aResult.available())
        Firebase.printf("task: %s, payload: %s\n", aResult.uid().c_str(), aResult.c_str());
}

unsigned long getUnixTime() {
  timeClient.update();
  return timeClient.getEpochTime();
}