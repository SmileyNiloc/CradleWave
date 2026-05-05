/*
 * Connects to WiFi, reads raw FMCW chirp data from BGT60TR13C over SPI,
 * and publishes binary frames to AWS IoT Core over MQTT/TLS.
 *
 * SPI protocol based on BGT60TR13C Datasheet V2.4.9, Section 5.
 */

#include <string.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/event_groups.h"
#include "esp_system.h"
#include "esp_mac.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "esp_log.h"
#include "nvs_flash.h"
#include "lwip/sockets.h"
#include "driver/gpio.h"
#include "mqtt_client.h"
#include "esp_netif_sntp.h"
#include "driver/spi_master.h"
#include "esp_heap_caps.h"

#include "lwip/err.h"
#include "lwip/sys.h"

// WiFi credentials
#define EXAMPLE_ESP_WIFI_SSID "UD Devices"
#define EXAMPLE_ESP_WIFI_PASS ""
#define EXAMPLE_ESP_MAXIMUM_RETRY  CONFIG_ESP_MAXIMUM_RETRY

// AWS IoT config
#define AWS_IOT_ENDPOINT "a1py3mdrrjrz1-ats.iot.us-east-1.amazonaws.com"
#define AWS_IOT_PORT 8883
#define MQTT_TOPIC "raw_sensor_data"
#define MQTT_CLIENT_ID "esp32s3-cradlewave-001"

// TLS certificates
extern const uint8_t aws_root_ca_pem_start[] asm("_binary_AmazonRootCA1_cer_start");
extern const uint8_t aws_root_ca_pem_end[] asm("_binary_AmazonRootCA1_cer_end");
extern const uint8_t certificate_pem_crt_start[] asm("_binary_CradleWave_ES32_cert_pem_start");
extern const uint8_t certificate_pem_crt_end[] asm("_binary_CradleWave_ES32_cert_pem_end");
extern const uint8_t private_pem_key_start[] asm("_binary_CradleWave_ES32_private_key_start");
extern const uint8_t private_pem_key_end[] asm("_binary_CradleWave_ES32_private_key_end");

// WiFi auth mode threshold
#if CONFIG_ESP_STATION_EXAMPLE_WPA3_SAE_PWE_HUNT_AND_PECK
#define ESP_WIFI_SAE_MODE WPA3_SAE_PWE_HUNT_AND_PECK
#define EXAMPLE_H2E_IDENTIFIER ""
#elif CONFIG_ESP_STATION_EXAMPLE_WPA3_SAE_PWE_HASH_TO_ELEMENT
#define ESP_WIFI_SAE_MODE WPA3_SAE_PWE_HASH_TO_ELEMENT
#define EXAMPLE_H2E_IDENTIFIER CONFIG_ESP_WIFI_PW_ID
#elif CONFIG_ESP_STATION_EXAMPLE_WPA3_SAE_PWE_BOTH
#define ESP_WIFI_SAE_MODE WPA3_SAE_PWE_BOTH
#define EXAMPLE_H2E_IDENTIFIER CONFIG_ESP_WIFI_PW_ID
#endif

#if CONFIG_ESP_WIFI_AUTH_OPEN
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_OPEN
#elif CONFIG_ESP_WIFI_AUTH_WEP
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WEP
#elif CONFIG_ESP_WIFI_AUTH_WPA_PSK
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WPA_PSK
#elif CONFIG_ESP_WIFI_AUTH_WPA2_PSK
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WPA2_PSK
#elif CONFIG_ESP_WIFI_AUTH_WPA_WPA2_PSK
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WPA_WPA2_PSK
#elif CONFIG_ESP_WIFI_AUTH_WPA3_PSK
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WPA3_PSK
#elif CONFIG_ESP_WIFI_AUTH_WPA2_WPA3_PSK
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WPA2_WPA3_PSK
#elif CONFIG_ESP_WIFI_AUTH_WAPI_PSK
#define ESP_WIFI_SCAN_AUTH_MODE_THRESHOLD WIFI_AUTH_WAPI_PSK
#endif

// GPIO pin assignments
#define LED_ENABLE  GPIO_NUM_37
#define LDO_ENABLE  GPIO_NUM_35
#define LED_GND     GPIO_NUM_15
#define PIN_MISO    GPIO_NUM_13 // S1_SPI_MISO
#define PIN_MOSI    GPIO_NUM_11 // S1_SPI_MOSI
#define PIN_CLK     GPIO_NUM_12 // S1_SPI_CLK
#define PIN_CS      GPIO_NUM_10 // S1_SPI_CSN
#define PIN_RST     GPIO_NUM_9  // S1_RST
#define PIN_IRQ     GPIO_NUM_14 // S1_IRQ
#define PIN_SPI_En  GPIO_NUM_8

// SPI host
#define BGT_SPI_HOST  SPI2_HOST

// BGT60TR13C register addresses (7-bit, per datasheet Section 4)
#define BGT60_REG_MAIN      0x00 // main control, FRAME_START lives here
#define BGT60_REG_ADC0      0x01 // MADC control
#define BGT60_REG_CHIP_ID   0x02 // chip ID, should read 0x000303
#define BGT60_REG_STAT1     0x03 // status register 1
#define BGT60_REG_PACR1     0x04 // PLL analog control 1
#define BGT60_REG_PACR2     0x05 // PLL analog control 2
#define BGT60_REG_SFCTL     0x06 // SPI & FIFO control, PREFIX_EN, FIFO_CREF
#define BGT60_REG_SADC_CTRL 0x07 // sensor ADC control
#define BGT60_REG_CSI_0     0x08
#define BGT60_REG_CSI_1     0x09
#define BGT60_REG_CSI_2     0x0A
#define BGT60_REG_CSCI      0x0B
#define BGT60_REG_CSDS_0    0x0C
#define BGT60_REG_CSDS_1    0x0D
#define BGT60_REG_CSDS_2    0x0E
#define BGT60_REG_CSCDS     0x0F
#define BGT60_REG_CSU1_0    0x10
#define BGT60_REG_CSU1_1    0x11
#define BGT60_REG_CSU1_2    0x12
#define BGT60_REG_CSC1      0x16
#define BGT60_REG_CSC2      0x1D
#define BGT60_REG_CSC3      0x24
#define BGT60_REG_CSC4      0x2B
#define BGT60_REG_CCR0      0x2C
#define BGT60_REG_CCR1      0x2D
#define BGT60_REG_CCR2      0x2E
#define BGT60_REG_CCR3      0x2F
#define BGT60_REG_PLL1_0    0x30
#define BGT60_REG_PLL1_1    0x31
#define BGT60_REG_PLL1_2    0x32
#define BGT60_REG_PLL1_3    0x33
#define BGT60_REG_PLL1_4    0x34
#define BGT60_REG_PLL1_5    0x35
#define BGT60_REG_PLL1_6    0x36
#define BGT60_REG_PLL1_7    0x37
#define BGT60_REG_PLL2_7    0x3F
#define BGT60_REG_PLL3_7    0x47
#define BGT60_REG_PLL4_7    0x4F
#define BGT60_REG_RFT1      0x56
#define BGT60_REG_UNK_0x5B  0x5B

/* BGT60TR13C init register table
    - FMCW chirp configuration for BGT60TR13C
    - contain both target register value and encoded address/RW header in high byte
    - bgt60_write_reg() masks data to bits 23-0 before transmitting
    - applied in sequence via bgt60_write_register_list() after MISO_HS_RD is cleared
    - list does not set FRAME_START, that's last step of bgt60_configure()
 */
typedef struct {
    uint8_t  addr;
    uint32_t data; //lower 24 bits are the real register value
} bgt60_reg_init_t;

static const bgt60_reg_init_t bgt60_init_list[] = {
    {BGT60_REG_MAIN     , 0x011e8270},
    {BGT60_REG_ADC0     , 0x03140210},
    {BGT60_REG_PACR1    , 0x09e967fd},
    {BGT60_REG_PACR2    , 0x0b0805b4},
    {BGT60_REG_SFCTL    , 0x0d1023ff},
    {BGT60_REG_SADC_CTRL, 0x0f010700},
    {BGT60_REG_CSI_0    , 0x11000000},
    {BGT60_REG_CSI_1    , 0x13000000},
    {BGT60_REG_CSI_2    , 0x15000000},
    {BGT60_REG_CSCI     , 0x17000be0},
    {BGT60_REG_CSDS_0   , 0x19000000},
    {BGT60_REG_CSDS_1   , 0x1b000000},
    {BGT60_REG_CSDS_2   , 0x1d000000},
    {BGT60_REG_CSCDS    , 0x1f000b60},
    {BGT60_REG_CSU1_0   , 0x21103c51},
    {BGT60_REG_CSU1_1   , 0x231ff41f},
    {BGT60_REG_CSU1_2   , 0x25700c63},
    {BGT60_REG_CSC1     , 0x2d000490},
    {BGT60_REG_CSC2     , 0x3b000480},
    {BGT60_REG_CSC3     , 0x49000480},
    {BGT60_REG_CSC4     , 0x57000480},
    {BGT60_REG_CCR0     , 0x5911be0e},
    {BGT60_REG_CCR1     , 0x5b5a3c0a},
    {BGT60_REG_CCR2     , 0x5d01f000},
    {BGT60_REG_CCR3     , 0x5f787e1e},
    {BGT60_REG_PLL1_0   , 0x61c72e83},
    {BGT60_REG_PLL1_1   , 0x63000393},
    {BGT60_REG_PLL1_2   , 0x650002b2},
    {BGT60_REG_PLL1_3   , 0x67000040},
    {BGT60_REG_PLL1_4   , 0x69000000},
    {BGT60_REG_PLL1_5   , 0x6b000000},
    {BGT60_REG_PLL1_6   , 0x6d000000},
    {BGT60_REG_PLL1_7   , 0x6f2d1d10},
    {BGT60_REG_PLL2_7   , 0x7f000100},
    {BGT60_REG_PLL3_7   , 0x8f000100},
    {BGT60_REG_PLL4_7   , 0x9f000100},
    {BGT60_REG_RFT1     , 0xad000000},
    {BGT60_REG_UNK_0x5B , 0xb7000000},
};

#define BGT60_INIT_LIST_LEN  (sizeof(bgt60_init_list) / sizeof(bgt60_init_list[0]))

// Frame dimensions
#define BGT60_NUM_CHIRPS     32
#define BGT60_NUM_SAMPLES    64
#define BGT60_TOTAL_SAMPLES  (BGT60_NUM_CHIRPS * BGT60_NUM_SAMPLES) // 2048

// 2 12-bit samples in every 24-bit FIFO word
// 2048 samples / 2 = 1024 FIFO words to read
#define BGT60_FIFO_WORDS     (BGT60_TOTAL_SAMPLES / 2) // 1024

// burst read transfer layout
// 4 + 4 + (1024 * 3) = 3080 bytes
#define BGT60_BURST_CMD_BYTES   4
#define BGT60_BURST_HDR_BYTES   4 // GSR0 (1) + DC padding (3)
#define BGT60_BURST_DATA_BYTES  (BGT60_FIFO_WORDS * 3) // 3072
#define BGT60_BURST_TOTAL_BYTES (BGT60_BURST_CMD_BYTES + BGT60_BURST_HDR_BYTES + BGT60_BURST_DATA_BYTES) // 3080

/* MQTT binary payload:
    - bytes(0 to 7) = uint64_t timestamp_ms (little-endian)
    - bytes(8 to end) = uint16_t samples, 1024 * 2 bytes = 2048 bytes
    - Total = 8200 bytes
 */
#define BGT60_FRAME_BYTES    (BGT60_TOTAL_SAMPLES * sizeof(uint16_t)) // 8192
#define MQTT_PAYLOAD_SIZE    (8 + BGT60_FRAME_BYTES) // 8200

//WiFi MQTT state
static EventGroupHandle_t s_wifi_event_group;
#define WIFI_CONNECTED_BIT  BIT0
#define WIFI_FAIL_BIT       BIT1
static int s_retry_num = 0;

static const char *TAG = "cradlewave";

static esp_mqtt_client_handle_t mqtt_client = NULL;
static bool mqtt_connected = false;

// SPI IRQ handles
static spi_device_handle_t bgt_spi;
static SemaphoreHandle_t   bgt_irq_sem;

/* BGT60TR13C SPI low-level register access:
    - matches Infineon's reference driver sensor-xensiv-bgt60trxx transaction
    - wire format (32 bits MSB first on SCLK):
        - bit(31 downto 25) = register address
        - bit(24) = RW (1 = write, 0 = read)
        - bit(23 downto 0) = data (write data on MOSI; MISO returns [GSR0(4b)][data(20b)]
*/

#define BGT60_SPI_WR_OP_MSK      0x01000000UL // bit 24 = RW
#define BGT60_SPI_REGADR_POS     25U
#define BGT60_SPI_REGADR_MSK     0xFE000000UL // bits 31..25 = addr
#define BGT60_SPI_DATA_MSK       0x00FFFFFFUL // bits 23..0  = data
#define BGT60_SPI_GSR0_MSK       0x0F000000UL // bits 27..24 = GSR0

// Reverse byte order of a 32-bit word, xensiv_bgt60trxx_platform_word_reverse()
static inline uint32_t bgt60_word_reverse(uint32_t x)
{
    return __builtin_bswap32(x);
}

// Low-level full-duplex transfer of 4 bytes, xensiv_bgt60trxx_platform_spi_transfer()
static esp_err_t bgt60_spi_xfer4(const void *tx, void *rx)
{
    spi_transaction_t t = {
        .length    = 32, // 4 bytes * 8 bits
        .tx_buffer = tx,
        .rx_buffer = rx,
    };
    return spi_device_transmit(bgt_spi, &t);
}

// Write a 24-bit value to a register, xensiv_bgt60trxx_set_reg()
static esp_err_t bgt60_write_reg(uint8_t addr, uint32_t data)
{
    WORD_ALIGNED_ATTR uint32_t w;
    w = ((uint32_t)addr << BGT60_SPI_REGADR_POS) & BGT60_SPI_REGADR_MSK;
    w |= BGT60_SPI_WR_OP_MSK;
    w |= (data & BGT60_SPI_DATA_MSK);
    w = bgt60_word_reverse(w);
    return bgt60_spi_xfer4(&w, NULL);
}

// Read a 24-bit register value, xensiv_bgt60trxx_get_reg()
static esp_err_t bgt60_read_reg(uint8_t addr, uint32_t *data_out)
{
    WORD_ALIGNED_ATTR uint32_t tx_w;
    WORD_ALIGNED_ATTR uint32_t rx_w = 0;

    tx_w = ((uint32_t)addr << BGT60_SPI_REGADR_POS) & BGT60_SPI_REGADR_MSK;
    // RW bit = 0 for read, data bits = don't care
    tx_w = bgt60_word_reverse(tx_w);

    esp_err_t ret = bgt60_spi_xfer4(&tx_w, &rx_w);
    if (ret != ESP_OK) {
        return ret;
    }

    rx_w = bgt60_word_reverse(rx_w);

    // Byte-swapped host-endian view:
    // bits(27 downto 24) = GSR0 error flags
    // bits(23 downto 0) = register data (per reference driver, mask with
    uint8_t gsr0 = (uint8_t)((rx_w & BGT60_SPI_GSR0_MSK) >> 24);
    // ignored errors
    if ((gsr0 & 0x0F) != 0x00 && (gsr0 & 0x0F) != 0x04 && (gsr0 & 0x0F) != 0x01 && (gsr0 & 0x0F) != 0x09) {
        ESP_LOGW(TAG, "read_reg addr=0x%02X GSR0 error flags: 0x%02X", addr, gsr0);
    }

    *data_out = rx_w & BGT60_SPI_DATA_MSK;
    return ESP_OK;
}

/* BGT60TR13C SPI burst FIFO read, xensiv_bgt60trxx_get_fifo_data()
    - 4-byte burst command + data payload, all under one CSn assertion
    - burst command encoding:
        - bits(31 downto 25) = 0x7F (burst command opcode)
        - bit(24) = 1 (RW: burst read uses command bit 24 = 1)
        - bits(23 downto 17) = SADDR (start address, FIFO register)
        - bit(16) = 0 (RWB: burst read data direction, 0 = read)
        - bits(15 downto 9) = NBURSTS (0 = unbounded, master stops by deasserting CS)
        - bits(8 downto 0) = reserved
    - FIFO register is at 0x60 (XENSIV_BGT60TRXX_REG_FIFO_TR13C)
        - resulting command word = 0xFFC0_0000.
*/

#define BGT60_SPI_BURST_MODE_CMD         0xFF000000UL
#define BGT60_SPI_BURST_MODE_SADR_POS    17U
#define BGT60_REG_FIFO_TR13C             0x60U

static esp_err_t bgt60_burst_read_fifo(uint16_t *samples_out)
{
    uint8_t *tx = heap_caps_calloc(BGT60_BURST_TOTAL_BYTES, 1, MALLOC_CAP_DMA);
    uint8_t *rx = heap_caps_calloc(BGT60_BURST_TOTAL_BYTES, 1, MALLOC_CAP_DMA);
    if (!tx || !rx) {
        free(tx);
        free(rx);
        return ESP_ERR_NO_MEM;
    }

    // FIFO register for BGT60TR13C = 0x60
    uint8_t fifo_reg = BGT60_REG_FIFO_TR13C;

    // build burst command in host-endian, then byte-swap into first 4 bytes of TX buffer
    uint32_t cmd = BGT60_SPI_BURST_MODE_CMD | ((uint32_t)fifo_reg << BGT60_SPI_BURST_MODE_SADR_POS);
    cmd = bgt60_word_reverse(cmd);
    memcpy(tx, &cmd, 4);
    // tx[4..end] stays 0x00, any value on MOSI is valid during data phase

    spi_transaction_t t = {
        .length = BGT60_BURST_TOTAL_BYTES * 8,
        .tx_buffer = tx,
        .rx_buffer = rx,
    };
    esp_err_t ret = spi_device_transmit(bgt_spi, &t);

    if (ret == ESP_OK) {
        // rx(0) = GSR0 (clocked out during command byte 0)
        // rx(1 to 3) = don't-care bytes from command phase
        // rx(4 to end) = FIFO data, 3 bytes per 24-bit word, MSB first
        uint8_t gsr0 = rx[0];
        if ((gsr0 & 0x0F) != 0x00 && (gsr0 & 0x0F) != 0x04 && (gsr0 & 0x0F) != 0x01 && (gsr0 & 0x0F) != 0x09) {
            ESP_LOGW(TAG, "Burst read GSR0 error flags: 0x%02X", gsr0);
        }

        int out_idx = 0;
        for (int i = 0; i < BGT60_FIFO_WORDS && out_idx < BGT60_TOTAL_SAMPLES; i++) {
            int base = BGT60_BURST_HDR_BYTES + (i * 3);
            uint32_t word = ((uint32_t)rx[base] << 16)
                          | ((uint32_t)rx[base + 1] << 8)
                          |  (uint32_t)rx[base + 2];
            // upper 12 bits = first sample
            // lower 12 bits = second sample
            samples_out[out_idx++] = (uint16_t)((word >> 12) & 0xFFF);
            samples_out[out_idx++] = (uint16_t)( word & 0xFFF);
        }
    }

    free(tx);
    free(rx);
    return ret;
}

/* BGT60TR13C hardware reset, xensiv_bgt60trxx_hard_reset():
    - Sequence:
        1. RST high, CSn high (idle state)
        2. T_CS_BRES > 100 ns before RST low (wait)
        3. RST low (reset asserted)
        4. T_RES > 1000 ns held low (wait)
        5. RST high (reset released)
        6. T_CS_ARES > 100 ns before SPI (wait)
*/
static void bgt60_hw_reset(void)
{
    gpio_set_direction(PIN_RST, GPIO_MODE_OUTPUT);

    // RST high, CSn high (idle)
    gpio_set_level(PIN_RST, 1);
    gpio_set_level(PIN_CS,  1);
    vTaskDelay(pdMS_TO_TICKS(1));

    // RST low (assert reset)
    gpio_set_level(PIN_RST, 0);
    vTaskDelay(pdMS_TO_TICKS(1));

    // RST high (release reset)
    gpio_set_level(PIN_RST, 1);
    vTaskDelay(pdMS_TO_TICKS(1));
    // Chip is now in Deep Sleep, ready to accept SPI commands
}

/* BGT60TR13C chip ID layout & soft reset, xensiv_bgt60trxx_soft_reset():
    - CHIP_ID (24-bit register 0x02) layout:
        - bits(23 downto 8) = DIGITAL_ID (0xFFFF00)
        - bits(7 downto 0) = RF_ID (0x0000FF)
    - For BGT60TR13C DIGITAL_ID = 3, RF_ID = 3 -> CHIP_ID = 0x000303
    - SFCTL (0x06) layout:
        - bits(23 downto 19) = RSVD (reset = 14B)
        - bit(18) = PREFIX_EN
        - bit(17) = LFSR_EN
        - bit(16) = MISO_HS_RD (reset = 1B)
        - bits(15 downto 14) = RSVD
        - bit(13) = FIFO_LP_MODE
        - bits(12 downto 0 = FIFO_CREF (max 8191)
    - CRITICAL: MISO_HS_RD = 1 at reset means  chip drives MISO on rising edge of SCLK, 
      which is incompatible with standard SPI mode 0 sampling. Must write SFCTL with 
      MISO_HS_RD = 0 as first SPI transaction (before any read attempt) if running at 
      SPI clock < 25 MHz with ESP32 in mode 0. Writes work fine even with bad MISO 
      timing because they don't depend on MISO.
*/

#define BGT60_REG_CHIP_ID_DIGITAL_ID_MSK   0x00FFFF00UL
#define BGT60_REG_CHIP_ID_DIGITAL_ID_POS   8U
#define BGT60_REG_CHIP_ID_RF_ID_MSK        0x000000FFUL
#define BGT60_REG_CHIP_ID_RF_ID_POS        0U
#define BGT60_CHIP_ID_TR13C                0x000303UL

#define BGT60_REG_MAIN_FRAME_START_MSK     0x00000001UL
#define BGT60_RESET_SW                     0x00000002UL // SW reset in MAIN
#define BGT60_RESET_FSM                    0x00000004UL // FSM reset in MAIN
#define BGT60_RESET_TIMEOUT                1000U

// SFCTL bit field positions/masks (datasheet Section 4.8)
#define BGT60_SFCTL_FIFO_CREF_POS          0U
#define BGT60_SFCTL_FIFO_CREF_MSK          0x00001FFFUL // bits(12 downto 0)
#define BGT60_SFCTL_FIFO_LP_MODE_MSK       0x00002000UL // bit(13)
#define BGT60_SFCTL_MISO_HS_RD_MSK         0x00010000UL // bit(16)
#define BGT60_SFCTL_LFSR_EN_MSK            0x00020000UL // bit(17)
#define BGT60_SFCTL_PREFIX_EN_MSK          0x00040000UL // bit(18)
#define BGT60_SFCTL_RSVD_DEFAULT           0x00700000UL // bits(22 downto 19) reset to 14B = 1110b; bit 23 reset unknown

__attribute__((unused))
static esp_err_t bgt60_soft_reset(uint32_t reset_type)
{
    uint32_t tmp;
    esp_err_t err = bgt60_read_reg(BGT60_REG_MAIN, &tmp);
    if (err != ESP_OK) return err;

    tmp |= reset_type;
    err = bgt60_write_reg(BGT60_REG_MAIN, tmp);
    if (err != ESP_OK) return err;

    // poll reset bit until chip clears it
    for (uint32_t timeout = BGT60_RESET_TIMEOUT; timeout > 0; --timeout) {
        err = bgt60_read_reg(BGT60_REG_MAIN, &tmp);
        if (err == ESP_OK && (tmp & reset_type) == 0U) {
            vTaskDelay(pdMS_TO_TICKS(1));
            return ESP_OK;
        }
    }
    ESP_LOGE(TAG, "Soft reset (type 0x%08lX) timed out", (unsigned long)reset_type);
    return ESP_ERR_TIMEOUT;
}

/* Write SFCTL with known-good value, MUST be first SPI operation
    - MISO_HS_RD = 0 (low-speed MISO, falling-edge output)
    - PREFIX_EN = 0 (no metadata header in FIFO)
    - FIFO_CREF = fifo_cref (IRQ when FIFO level exceeds this)
    - RSVD bits = preserved at their reset value 
*/
static esp_err_t bgt60_write_sfctl(uint32_t fifo_cref, bool prefix_en)
{
    uint32_t val = BGT60_SFCTL_RSVD_DEFAULT;
    val |= (fifo_cref << BGT60_SFCTL_FIFO_CREF_POS) & BGT60_SFCTL_FIFO_CREF_MSK;
    if (prefix_en) val |= BGT60_SFCTL_PREFIX_EN_MSK;
    // MISO_HS_RD left at 0
    return bgt60_write_reg(BGT60_REG_SFCTL, val);
}

// apply full init register list (bgt60_init_list[])
static esp_err_t bgt60_write_register_list(void)
{
    for (size_t i = 0; i < BGT60_INIT_LIST_LEN; i++) {
        esp_err_t err = bgt60_write_reg(bgt60_init_list[i].addr,
                                        bgt60_init_list[i].data);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "Register list write failed at index %u "
                          "(addr=0x%02X): %d",
                     (unsigned)i, bgt60_init_list[i].addr, err);
            return err;
        }
    }
    return ESP_OK;
}

/* BGT60TR13C chip configuration
    - order of operations:
        1. write SFCTL with MISO_HS_RD=0 FIRST (blind), chip powers up with
           MISO_HS_RD = 1 which breaks SPI mode 0 reads
        2. diagnostic: read CHIP_ID a few times, should read 0x000303
        3. apply full register list
        4. start frame generation by writing FRAME_START=1 to MAIN
*/
static void bgt60_configure(void)
{
    uint32_t chipid = 0;
    esp_err_t err;

    // step 1 - blind write: clear MISO_HS_RD so MISO outputs on falling edge
    // placeholder SFCTL value, register list overwrites this with full working config later
    ESP_LOGI(TAG, "Writing SFCTL with MISO_HS_RD=0 (blind - fixes MISO timing)");
    err = bgt60_write_sfctl(BGT60_FIFO_WORDS, false);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Initial SFCTL write failed: %d", err);
    }

    // step 2 - diagnostic: read CHIP_ID a few times
    ESP_LOGI(TAG, "CHIP_ID diagnostic (expect 0x000303 for TR13C):");
    for (int i = 0; i < 4; i++) {
        uint32_t v = 0;
        err = bgt60_read_reg(BGT60_REG_CHIP_ID, &v);
        ESP_LOGI(TAG, "  read %d: 0x%06lX (err=%d)", i, (unsigned long)v, err);
        if (i == 0) chipid = v;
    }

    if (chipid != BGT60_CHIP_ID_TR13C) {
        ESP_LOGE(TAG, "CHIP_ID mismatch (expected 0x000303). SPI is returning ");
        return;
    }
    ESP_LOGI(TAG, "CHIP_ID OK (BGT60TR13C)");

    // step 3 - apply full register list (FMCW chirp configuration)
    ESP_LOGI(TAG, "Applying %u-entry register configuration...", (unsigned)BGT60_INIT_LIST_LEN);
    err = bgt60_write_register_list();
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Register list application failed");
        return;
    }
    ESP_LOGI(TAG, "Register list applied successfully.");

    // step 4 - start frame generation
    uint32_t main_val = 0;
    err = bgt60_read_reg(BGT60_REG_MAIN, &main_val);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Could not read MAIN to start frames");
        return;
    }
    main_val |= BGT60_REG_MAIN_FRAME_START_MSK;
    err = bgt60_write_reg(BGT60_REG_MAIN, main_val);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "FRAME_START write failed");
        return;
    }

    ESP_LOGI(TAG, "BGT60 configured and frame generation started.");
}

// BGT60TR13C SPI bus + device init
#define BGT_SPI_CLOCK_HZ         (25 * 1000 * 1000) // 25 MHz bring-up
#define BGT_SPI_MODE             0 // CPOL=0, CPHA=0
#define BGT_SPI_INPUT_DELAY_NS   0

static void bgt60_spi_init(void)
{
    // SPI bus config, max_transfer_sz must exceed full burst frame
    spi_bus_config_t bus_cfg = {
        .miso_io_num     = PIN_MISO,
        .mosi_io_num     = PIN_MOSI,
        .sclk_io_num     = PIN_CLK,
        .quadwp_io_num   = -1,
        .quadhd_io_num   = -1,
        .max_transfer_sz = 6200, // > BGT60_BURST_TOTAL_BYTES
    };
    ESP_ERROR_CHECK(spi_bus_initialize(BGT_SPI_HOST, &bus_cfg, SPI_DMA_CH_AUTO));

    // standard SPI mode 0 (CPOL=0, CPHA=0), up to 50 MHz
    // cs_ena_pretrans/posttrans: hold CSn low for extra SPI-clock cycles
    spi_device_interface_config_t dev_cfg = {
        .clock_speed_hz   = BGT_SPI_CLOCK_HZ,
        .mode             = BGT_SPI_MODE,
        .spics_io_num     = PIN_CS,
        .queue_size       = 1,
        .input_delay_ns   = BGT_SPI_INPUT_DELAY_NS,
        .cs_ena_pretrans  = 2, // 2 SPI-clock cycles of CSn-low before SCLK
        .cs_ena_posttrans = 2, // 2 SPI-clock cycles of CSn-low after last SCLK
        .flags            = 0,
    };
    ESP_ERROR_CHECK(spi_bus_add_device(BGT_SPI_HOST, &dev_cfg, &bgt_spi));

    ESP_LOGI(TAG, "SPI bus up: %d Hz, mode %d, input_delay_ns=%d", BGT_SPI_CLOCK_HZ, BGT_SPI_MODE, BGT_SPI_INPUT_DELAY_NS);
}

// BGT60TR13C IRQ interrupt handler and init
static void IRAM_ATTR bgt_irq_handler(void *arg)
{
    BaseType_t higher_prio_woken = pdFALSE;
    xSemaphoreGiveFromISR(bgt_irq_sem, &higher_prio_woken);
    portYIELD_FROM_ISR(higher_prio_woken);
}

static void bgt60_irq_init(void)
{
    bgt_irq_sem = xSemaphoreCreateBinary();

    gpio_config_t io_conf = {
        .pin_bit_mask = (1ULL << PIN_IRQ),
        .mode         = GPIO_MODE_INPUT,
        .pull_up_en   = GPIO_PULLUP_DISABLE, // chip has internal pull-up
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type    = GPIO_INTR_POSEDGE, // IRQ fires on rising edge
    };
    gpio_config(&io_conf);
    gpio_install_isr_service(0);
    gpio_isr_handler_add(PIN_IRQ, bgt_irq_handler, NULL);
}

/* BGT60TR13C per-frame FIFO reset + frame restart
    - after reading one frame's worth of data via burst read:
        1. set FIFO_RESET in MAIN - clears FIFO and returns to 0
        2. set FRAME_START in MAIN - kicks off next frame's chirps
*/
static esp_err_t bgt60_restart_frame(void)
{
    uint32_t main_val = 0;
    esp_err_t err = bgt60_read_reg(BGT60_REG_MAIN, &main_val);
    if (err != ESP_OK) return err;

    // clear FRAME_START first, then pulse FIFO_RESET
    main_val &= ~BGT60_REG_MAIN_FRAME_START_MSK;
    err = bgt60_write_reg(BGT60_REG_MAIN, main_val | (1UL << 3));
    if (err != ESP_OK) return err;

    esp_rom_delay_us(10); // FIFO_RESET should self-clears in << 1 us
    main_val &= ~(1UL << 3); // mark it cleared in our local copy

    // start next frame
    return bgt60_write_reg(BGT60_REG_MAIN, main_val | BGT60_REG_MAIN_FRAME_START_MSK);
}

/* frame logging - prints frame contents to esp_log
    - set BGT60_LOG_FRAME_MODE to control what gets logged per frame:
        - 0 = off (minimal log noise)
        - 1 = stats only (sample count, min, max, mean)
        - 2 = stats + head (stats, plus first BGT60_LOG_HEAD_SAMPLES values)
        - 3 = full dump (stats + every sample, 16 per line)
*/
#define BGT60_LOG_FRAME_MODE     0
#define BGT60_LOG_HEAD_SAMPLES   64 // how many samples to print in mode 2
 
static void bgt60_log_frame(const uint16_t *frame, uint64_t timestamp_ms)
{
#if BGT60_LOG_FRAME_MODE == 0
    (void)frame;
    (void)timestamp_ms;
    return;
#else
    // compute summary statistics over the whole frame
    // samples are 12-bit unsigned (0 to 4095)
    uint32_t sum = 0;
    uint16_t vmin = UINT16_MAX;
    uint16_t vmax = 0;
    for (int i = 0; i < BGT60_TOTAL_SAMPLES; i++) {
        uint16_t v = frame[i];
        sum += v;
        if (v < vmin) vmin = v;
        if (v > vmax) vmax = v;
    }
    uint32_t mean_x100 = (sum * 100u) / BGT60_TOTAL_SAMPLES;
 
    ESP_LOGI(TAG, "Frame stats: ts=%llu n=%d min=%u max=%u mean=%lu.%02lu",
             (unsigned long long)timestamp_ms,
             BGT60_TOTAL_SAMPLES,
             vmin, vmax,
             (unsigned long)(mean_x100 / 100u),
             (unsigned long)(mean_x100 % 100u));
 
#if BGT60_LOG_FRAME_MODE >= 2
    // print first N samples, 16 per line, as hex
    int head = BGT60_LOG_HEAD_SAMPLES;
    if (head > BGT60_TOTAL_SAMPLES) head = BGT60_TOTAL_SAMPLES;
 
    char line[128];
    for (int i = 0; i < head; i += 16) {
        int n = 0;
        n += snprintf(line + n, sizeof(line) - n, "  [%4d]", i);
        int end = (i + 16 < head) ? i + 16 : head;
        for (int j = i; j < end; j++) {
            n += snprintf(line + n, sizeof(line) - n, " %03X", frame[j]);
            if (n >= (int)sizeof(line)) break;
        }
        ESP_LOGI(TAG, "%s", line);
    }
#endif
 
#if BGT60_LOG_FRAME_MODE >= 3
    // full dump
    char line2[128];
    for (int i = BGT60_LOG_HEAD_SAMPLES; i < BGT60_TOTAL_SAMPLES; i += 16) {
        int n = 0;
        n += snprintf(line2 + n, sizeof(line2) - n, "  [%4d]", i);
        int end = (i + 16 < BGT60_TOTAL_SAMPLES) ? i + 16 : BGT60_TOTAL_SAMPLES;
        for (int j = i; j < end; j++) {
            n += snprintf(line2 + n, sizeof(line2) - n, " %03X", frame[j]);
            if (n >= (int)sizeof(line2)) break;
        }
        ESP_LOGI(TAG, "%s", line2);
    }
#endif
#endif
}
 
/* Radar publish task:
    - waits for IRQ (one full frame ready), burst-reads the FIFO, then publishes binary MQTT message:
        - bytes(0 to 7) = uint64_t timestamp_ms, little-endian
        - bytes(8 to end) = uint16_t samples[4096], little-endian (12-bit ADC values)
*/
static void radar_publish_task(void *pvParameters)
{
    // allocate sample buffer, uint16_t holds 12-bit ADC values (0 to 2047)
    uint16_t *frame = heap_caps_malloc(BGT60_TOTAL_SAMPLES * sizeof(uint16_t), MALLOC_CAP_DMA);
    uint8_t  *payload = malloc(MQTT_PAYLOAD_SIZE);
 
    if (!frame || !payload) {
        ESP_LOGE(TAG, "Failed to allocate radar buffers (%d + %d bytes)", (int)(BGT60_TOTAL_SAMPLES * sizeof(uint16_t)), (int)MQTT_PAYLOAD_SIZE);
        vTaskDelete(NULL);
        return;
    }
 
    ESP_LOGI(TAG, "Radar publish task started — waiting for IRQ...");
 
    while (1) {
        // wait for MQTT connection
        if (!mqtt_connected) {
            vTaskDelay(pdMS_TO_TICKS(500));
            continue;
        }
 
        // block until BGT60 asserts IRQ (frame ready)
        if (xSemaphoreTake(bgt_irq_sem, pdMS_TO_TICKS(500)) != pdTRUE) {
            ESP_LOGW(TAG, "IRQ timeout — no frame received");
            continue;
        }
 
        // capture timestamp immediately when IRQ fires
        struct timeval tv;
        gettimeofday(&tv, NULL);
        uint64_t timestamp_ms = (uint64_t)tv.tv_sec * 1000ULL + (uint64_t)tv.tv_usec / 1000ULL;
 
        // burst-read full frame from FIFO
        esp_err_t err = bgt60_burst_read_fifo(frame);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "FIFO burst read failed: %d", err);
            continue;
        }

        // flashes led
        gpio_set_level(LED_ENABLE, 1);
 
        // log frame contents
        bgt60_log_frame(frame, timestamp_ms);
 
        // build binary payload
        memcpy(payload,     &timestamp_ms, 8);
        memcpy(payload + 8, frame, BGT60_TOTAL_SAMPLES * sizeof(uint16_t));
 
        // publish at QoS 0 (fire-and-forget)
        // QoS 1 with 8KB payloads at 15 Hz will saturate MQTT queue
        int msg_id = esp_mqtt_client_publish(
            mqtt_client,
            MQTT_TOPIC,
            (const char *)payload,
            MQTT_PAYLOAD_SIZE,
            0, // QoS 0
            0 // no retain
        );
 
        if (msg_id < 0) {
            ESP_LOGW(TAG, "MQTT publish failed (queue full?)");
        } else {
            ESP_LOGI(TAG, "Frame published: ts=%llu  %d bytes", (unsigned long long)timestamp_ms, MQTT_PAYLOAD_SIZE);
        }
 
        // reset FIFO and kick off next frame
        // without this, chip overflows after 2-3 frames and stops generating IRQs
        esp_err_t rerr = bgt60_restart_frame();
        if (rerr != ESP_OK) {
            ESP_LOGE(TAG, "Frame restart failed: %d", rerr);
        }

        xSemaphoreTake(bgt_irq_sem, 0);
        gpio_set_level(LED_ENABLE, 0);

        // print delta times to console
        static uint64_t last_irq_ms = 0;
        uint64_t now_ms = (uint64_t)tv.tv_sec * 1000ULL + (uint64_t)tv.tv_usec / 1000ULL;
        uint64_t since_last = (last_irq_ms == 0) ? 0 : (now_ms - last_irq_ms);
        last_irq_ms = now_ms;
        ESP_LOGI(TAG, "IRQ delta: %llu ms", (unsigned long long)since_last);
    }
 
    free(frame);
    free(payload);
}

// Wifi setup, from esp-idf examples
static void event_handler(void *arg, esp_event_base_t event_base, int32_t event_id, void *event_data)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        if (s_retry_num < EXAMPLE_ESP_MAXIMUM_RETRY) {
            esp_wifi_connect();
            s_retry_num++;
            ESP_LOGI(TAG, "retry to connect to the AP");
        } else {
            xEventGroupSetBits(s_wifi_event_group, WIFI_FAIL_BIT);
        }
        ESP_LOGI(TAG, "connect to the AP fail");
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        ip_event_got_ip_t *event = (ip_event_got_ip_t *)event_data;
        ESP_LOGI(TAG, "got ip:" IPSTR, IP2STR(&event->ip_info.ip));
        s_retry_num = 0;
        xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    }
}

static void wifi_init_sta(void)
{
    s_wifi_event_group = xEventGroupCreate();

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));

    esp_event_handler_instance_t instance_any_id;
    esp_event_handler_instance_t instance_got_ip;
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT, ESP_EVENT_ANY_ID, &event_handler, NULL, &instance_any_id));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT, IP_EVENT_STA_GOT_IP, &event_handler, NULL, &instance_got_ip));

    wifi_config_t wifi_config = {
        .sta = {
            .password         = EXAMPLE_ESP_WIFI_PASS,
            .threshold.authmode = WIFI_AUTH_OPEN,
            .sae_pwe_h2e      = ESP_WIFI_SAE_MODE,
            .sae_h2e_identifier = EXAMPLE_H2E_IDENTIFIER,
#ifdef CONFIG_ESP_WIFI_WPA3_COMPATIBLE_SUPPORT
            .disable_wpa3_compatible_mode = 0,
#endif
        },
    };
    memset(wifi_config.sta.ssid, 0, sizeof(wifi_config.sta.ssid));
    size_t ssid_len = strlen(EXAMPLE_ESP_WIFI_SSID);
    if (ssid_len > sizeof(wifi_config.sta.ssid)) {
        ssid_len = sizeof(wifi_config.sta.ssid);
    }
    memcpy(wifi_config.sta.ssid, EXAMPLE_ESP_WIFI_SSID, ssid_len);

    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "wifi_init_sta finished.");

    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
                                            WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
                                            pdFALSE, pdFALSE, portMAX_DELAY);
    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "connected to AP: %s", EXAMPLE_ESP_WIFI_SSID);
    } else if (bits & WIFI_FAIL_BIT) {
        ESP_LOGI(TAG, "failed to connect to AP: %s", EXAMPLE_ESP_WIFI_SSID);
    } else {
        ESP_LOGE(TAG, "UNEXPECTED EVENT");
    }
}

// MQTT functionality
static void mqtt_event_handler(void *arg, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = (esp_mqtt_event_handle_t)event_data;
    switch (event->event_id) {
        case MQTT_EVENT_CONNECTED:
            ESP_LOGI(TAG, "MQTT connected to AWS IoT");
            mqtt_connected = true;
            break;
        case MQTT_EVENT_DISCONNECTED:
            ESP_LOGW(TAG, "MQTT disconnected");
            mqtt_connected = false;
            break;
        case MQTT_EVENT_ERROR:
            ESP_LOGE(TAG, "MQTT error");
            break;
        default:
            break;
    }
}

static void mqtt_start(void)
{
    esp_mqtt_client_config_t mqtt_cfg = {
        .broker = {
            .address = {
                .hostname  = AWS_IOT_ENDPOINT,
                .port      = AWS_IOT_PORT,
                .transport = MQTT_TRANSPORT_OVER_SSL,
            },
            .verification = {
                .certificate = (const char *)aws_root_ca_pem_start,
            },
        },
        .credentials = {
            .client_id = MQTT_CLIENT_ID,
            .authentication = {
                .certificate = (const char *)certificate_pem_crt_start,
                .key         = (const char *)private_pem_key_start,
            },
        },
    };

    mqtt_client = esp_mqtt_client_init(&mqtt_cfg);
    esp_mqtt_client_register_event(mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL);
    esp_mqtt_client_start(mqtt_client);
}

// SNTP time sync
static void sync_time(void)
{
    ESP_LOGI(TAG, "Syncing time via SNTP...");
    esp_sntp_config_t config = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_netif_sntp_init(&config);
    esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000));
    ESP_LOGI(TAG, "Time synced.");
}

// main
void app_main(void)
{
    // NVS init (required by WiFi driver)
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);

    if (CONFIG_LOG_MAXIMUM_LEVEL > CONFIG_LOG_DEFAULT_LEVEL) {
        esp_log_level_set("wifi", CONFIG_LOG_MAXIMUM_LEVEL);
    }

    uint8_t mac[6];
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    ESP_LOGI(TAG, "MAC: %02x:%02x:%02x:%02x:%02x:%02x",
             mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]);

    // 1. connect to WiFi
    wifi_init_sta();

    // 2. sync real-world time (needed for valid MQTT timestamps)
    sync_time();

    // 3. start MQTT connection to AWS IoT Core
    mqtt_start();

    // 4. power on the BGT60TR13C shield
    //    LDO_ENABLE must be asserted before SPI init so chip has power
    gpio_set_direction(LDO_ENABLE, GPIO_MODE_OUTPUT);
    gpio_set_level(LDO_ENABLE, 1);
    vTaskDelay(pdMS_TO_TICKS(10)); // allow LDO to stabilise

    gpio_set_direction(PIN_SPI_En, GPIO_MODE_OUTPUT);
    gpio_set_level(PIN_SPI_En, 0);

    gpio_set_direction(LED_ENABLE, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_ENABLE, 1);
    gpio_set_direction(LED_GND, GPIO_MODE_OUTPUT);
    gpio_set_level(LED_GND, 0);

    // 5. init SPI bus and device
    bgt60_spi_init();

    // 6. hardware reset
    bgt60_hw_reset();

    // 7. verify SPI comms, software-reset chip, configure FIFO, start frames
    bgt60_configure();

    // 8. configure IRQ input
    bgt60_irq_init();

    // 9. start radar read + publish task
    xTaskCreate(radar_publish_task, "radar_pub", 8192, NULL, 5, NULL);

    ESP_LOGI(TAG, "Returned from app_main()");
}
