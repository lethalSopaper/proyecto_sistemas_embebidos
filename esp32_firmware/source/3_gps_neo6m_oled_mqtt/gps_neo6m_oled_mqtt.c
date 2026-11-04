#include "gps_neo6m_oled_mqtt.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_event.h"
#include "esp_log.h"
#include "mqtt_client.h"
#include "esp_netif.h"
#include "esp_wifi.h"
#include "freertos/event_groups.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "u8g2.h"
#include "u8g2_esp32_hal.h"

#define GPS_UART_NUM UART_NUM_1
#define GPS_UART_BAUD_RATE 9600
#define GPS_UART_RX_PIN GPIO_NUM_2
#define GPS_UART_TX_PIN GPIO_NUM_3
#define GPS_UART_BUFFER_SIZE 1024
#define GPS_LINE_BUFFER_SIZE 128
#define OLED_SDA_PIN GPIO_NUM_7
#define OLED_SCL_PIN GPIO_NUM_44
#define OLED_I2C_ADDRESS 0x78
#define MODE_BUTTON_PIN GPIO_NUM_1
#define MAX_MEASUREMENTS 64
#define WIFI_CONNECTED BIT0
#define MQTT_CONNECTED BIT1

static const char *TAG = "gps_oled_mqtt";
static EventGroupHandle_t wifi_events;
static esp_mqtt_client_handle_t mqtt_client;
static u8g2_t display;
static bool upload_mode;
static bool wifi_initialized;
static bool wifi_started;
static nvs_handle_t storage;

typedef struct {
    bool valid;
    double latitude;
    double longitude;
    double altitude_m;
    double hdop;
    int satellites;
} gps_measurement_t;

static gps_measurement_t measurements[MAX_MEASUREMENTS];
static size_t measurement_count;

typedef struct {
    uint32_t count;
    gps_measurement_t data[MAX_MEASUREMENTS];
} measurement_store_t;

static measurement_store_t measurement_store;
static char mqtt_status_topic[128];
static char mqtt_payload[192];

static void persist_measurements(void)
{
    measurement_store.count = measurement_count;
    memcpy(measurement_store.data, measurements, sizeof(measurements));
    ESP_ERROR_CHECK(nvs_set_blob(
        storage, "measurements", &measurement_store, sizeof(measurement_store)
    ));
    ESP_ERROR_CHECK(nvs_commit(storage));
}

static void load_measurements(void)
{
    size_t size = sizeof(measurement_store);
    esp_err_t error = nvs_get_blob(storage, "measurements", &measurement_store, &size);
    if (error == ESP_OK && measurement_store.count <= MAX_MEASUREMENTS) {
        measurement_count = measurement_store.count;
        memcpy(measurements, measurement_store.data, sizeof(measurements));
    }
}

static void oled_message(const char *title, const char *message)
{
    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_6x10_tf);
    u8g2_DrawStr(&display, 0, 14, title);
    u8g2_DrawStr(&display, 0, 32, message);
    u8g2_SendBuffer(&display);
}

static void oled_measurement(const gps_measurement_t *m)
{
    char line[32];
    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_5x7_tf);
    snprintf(line, sizeof(line), "Lat: %.6f", m->latitude);
    u8g2_DrawStr(&display, 0, 24, line);
    snprintf(line, sizeof(line), "Lon: %.6f", m->longitude);
    u8g2_DrawStr(&display, 0, 34, line);
    snprintf(line, sizeof(line), "Alt: %.1f m", m->altitude_m);
    u8g2_DrawStr(&display, 0, 44, line);
    snprintf(line, sizeof(line), "Sat: %d HDOP: %.1f", m->satellites, m->hdop);
    u8g2_DrawStr(&display, 0, 54, line);
    u8g2_DrawStr(&display, 0, 63, upload_mode ? "UPLOAD MODE" : "GPS MONITOR");
    u8g2_SendBuffer(&display);
}

static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data
)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_START) {
        esp_wifi_connect();
    } else if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
        xEventGroupClearBits(wifi_events, WIFI_CONNECTED);
        const wifi_event_sta_disconnected_t *disconnected = event_data;
        ESP_LOGW(TAG, "WiFi desconectado; razon=%d", disconnected->reason);
    } else if (event_base == IP_EVENT && event_id == IP_EVENT_STA_GOT_IP) {
        xEventGroupSetBits(wifi_events, WIFI_CONNECTED);
        const ip_event_got_ip_t *got_ip = event_data;
        ESP_LOGI(TAG, "WiFi conectado; IP=" IPSTR, IP2STR(&got_ip->ip_info.ip));
    }
}

static bool wifi_connect(void)
{
    wifi_config_t config = {0};
    snprintf((char *)config.sta.ssid, sizeof(config.sta.ssid), "%s", CONFIG_GPS_WIFI_SSID);
    snprintf((char *)config.sta.password, sizeof(config.sta.password), "%s", CONFIG_GPS_WIFI_PASSWORD);
    ESP_LOGI(TAG, "Conectando a WiFi SSID=%s (%s)", CONFIG_GPS_WIFI_SSID,
             CONFIG_GPS_WIFI_PASSWORD[0] == '\0' ? "sin contraseña" : "con contraseña");
    xEventGroupClearBits(wifi_events, WIFI_CONNECTED);
    esp_err_t error = esp_wifi_set_config(WIFI_IF_STA, &config);
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "No se pudo configurar WiFi: %s", esp_err_to_name(error));
        return false;
    }
    if (!wifi_started) {
        error = esp_wifi_start();
        if (error != ESP_OK) {
            ESP_LOGE(TAG, "No se pudo iniciar WiFi: %s", esp_err_to_name(error));
            return false;
        }
        wifi_started = true;
    } else {
        error = esp_wifi_connect();
        if (error != ESP_OK && error != ESP_ERR_WIFI_CONN) {
            ESP_LOGE(TAG, "No se pudo conectar a WiFi: %s", esp_err_to_name(error));
            return false;
        }
    }

    EventBits_t bits = xEventGroupWaitBits(
        wifi_events, WIFI_CONNECTED, pdFALSE, pdFALSE, pdMS_TO_TICKS(15000)
    );
    return (bits & WIFI_CONNECTED) != 0;
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    if (event_id == MQTT_EVENT_CONNECTED) {
        ESP_LOGI(TAG, "Conectado al broker MQTT");
        xEventGroupSetBits(wifi_events, MQTT_CONNECTED);
    } else if (event_id == MQTT_EVENT_DISCONNECTED) {
        xEventGroupClearBits(wifi_events, MQTT_CONNECTED);
    }
}

static bool upload_measurements(void)
{
    persist_measurements();
    snprintf(mqtt_status_topic, sizeof(mqtt_status_topic), "%s/status",
             CONFIG_GPS_MQTT_TOPIC);
    esp_mqtt_client_config_t config = {
        .broker.address.uri = CONFIG_GPS_MQTT_URI,
        .credentials.client_id = "esp32-gps",
    };
    mqtt_client = esp_mqtt_client_init(&config);
    if (mqtt_client == NULL) {
        return false;
    }
    esp_err_t error = esp_mqtt_client_register_event(
        mqtt_client, ESP_EVENT_ANY_ID, mqtt_event_handler, NULL
    );
    if (error != ESP_OK || esp_mqtt_client_start(mqtt_client) != ESP_OK) {
        ESP_LOGE(TAG, "No se pudo iniciar el cliente MQTT");
        esp_mqtt_client_destroy(mqtt_client);
        mqtt_client = NULL;
        return false;
    }

    EventBits_t bits = xEventGroupWaitBits(
        wifi_events, MQTT_CONNECTED, pdFALSE, pdFALSE, pdMS_TO_TICKS(10000)
    );
    if ((bits & MQTT_CONNECTED) == 0) {
        ESP_LOGE(TAG, "No se pudo conectar al broker MQTT: %s", CONFIG_GPS_MQTT_URI);
        esp_mqtt_client_stop(mqtt_client);
        esp_mqtt_client_destroy(mqtt_client);
        mqtt_client = NULL;
        return false;
    }

    ESP_LOGI(TAG, "Publicando %d mediciones en %s", (int)measurement_count,
             CONFIG_GPS_MQTT_TOPIC);
    esp_mqtt_client_publish(mqtt_client, mqtt_status_topic, "uploading", 0, 1, 0);

    for (size_t i = 0; i < measurement_count; i++) {
        gps_measurement_t *m = &measurements[i];
        snprintf(
            mqtt_payload, sizeof(mqtt_payload),
            "{\"latitude\":%.6f,\"longitude\":%.6f,\"altitude\":%.2f,\"satellites\":%d,\"hdop\":%.2f}",
            m->latitude, m->longitude, m->altitude_m, m->satellites, m->hdop
        );
        if (esp_mqtt_client_publish(
                mqtt_client, CONFIG_GPS_MQTT_TOPIC, mqtt_payload, 0, 1, 0) < 0) {
            return false;
        }
    }
    ESP_LOGI(TAG, "Mediciones publicadas: %d", (int)measurement_count);
    esp_mqtt_client_publish(mqtt_client, mqtt_status_topic, "complete", 0, 1, 0);
    measurement_count = 0;
    ESP_ERROR_CHECK(nvs_erase_key(storage, "measurements"));
    ESP_ERROR_CHECK(nvs_commit(storage));
    esp_mqtt_client_stop(mqtt_client);
    esp_mqtt_client_destroy(mqtt_client);
    mqtt_client = NULL;
    return true;
}

static void gps_uart_init(void)
{
    const uart_config_t config = {
        .baud_rate = GPS_UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };
    ESP_ERROR_CHECK(uart_driver_install(GPS_UART_NUM, GPS_UART_BUFFER_SIZE, 0, 0, NULL, 0));
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_NUM, &config));
    ESP_ERROR_CHECK(uart_set_pin(GPS_UART_NUM, GPS_UART_TX_PIN, GPS_UART_RX_PIN,
                                 UART_PIN_NO_CHANGE, UART_PIN_NO_CHANGE));
}

static void oled_init(void)
{
    u8g2_esp32_hal_t hal = U8G2_ESP32_HAL_DEFAULT;
    hal.bus.i2c.sda = OLED_SDA_PIN;
    hal.bus.i2c.scl = OLED_SCL_PIN;
    u8g2_esp32_hal_init(hal);

    gpio_config_t i2c_pins = {
        .pin_bit_mask = (1ULL << OLED_SDA_PIN) | (1ULL << OLED_SCL_PIN),
        .mode = GPIO_MODE_INPUT_OUTPUT_OD,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&i2c_pins));
    u8g2_Setup_ssd1306_i2c_128x64_noname_f(
        &display, U8G2_R0, u8x8_byte_sw_i2c, u8g2_esp32_gpio_and_delay_cb
    );
    u8x8_SetI2CAddress(&display.u8x8, OLED_I2C_ADDRESS);
    u8g2_InitDisplay(&display);
    u8g2_SetPowerSave(&display, 0);
    oled_message("GPS NEO-6M", "GPS MONITOR");
}

static bool parse_gga(char *sentence, gps_measurement_t *m)
{
    char *fields[15] = {0};
    size_t count = 0;
    char *field = strtok(sentence, ",");
    while (field != NULL && count < 15) {
        fields[count++] = field;
        field = strtok(NULL, ",*");
    }
    if (count < 10 || (strcmp(fields[0] + 1, "GPGGA") != 0 &&
                       strcmp(fields[0] + 1, "GNGGA") != 0)) {
        return false;
    }
    if (fields[6][0] == '0') {
        return true;
    }
    m->valid = true;
    m->latitude = atof(fields[2]) / 100.0;
    m->longitude = atof(fields[4]) / 100.0;
    if (fields[3][0] == 'S') m->latitude = -m->latitude;
    if (fields[5][0] == 'W') m->longitude = -m->longitude;
    m->satellites = atoi(fields[7]);
    m->hdop = atof(fields[8]);
    m->altitude_m = atof(fields[9]);
    return true;
}

static void process_sentence(char *sentence)
{
    const char *checksum = strchr(sentence, '*');
    if (sentence[0] != '$' || checksum == NULL) return;
    unsigned char calculated = 0;
    for (const char *p = sentence + 1; p < checksum; p++) calculated ^= (unsigned char)*p;
    unsigned int expected = 0;
    if (sscanf(checksum + 1, "%2x", &expected) != 1 || calculated != expected) return;
    gps_measurement_t m = {0};
    if (!parse_gga(sentence, &m) || !m.valid) return;
    if (measurement_count < MAX_MEASUREMENTS) measurements[measurement_count++] = m;
    if (measurement_count % 10 == 0) persist_measurements();
    if (!upload_mode) {
        oled_measurement(&m);
    }
    ESP_LOGI(TAG, "Fix valido | lat=%.6f lon=%.6f", m.latitude, m.longitude);
}

void gps_neo6m_oled_mqtt_app_main(void)
{
    gpio_config_t button = {
        .pin_bit_mask = 1ULL << MODE_BUTTON_PIN,
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&button));
    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(nvs_open("gps", NVS_READWRITE, &storage));
    load_measurements();
    oled_init();
    gps_uart_init();
    wifi_events = xEventGroupCreate();
    if (wifi_events == NULL) {
        ESP_LOGE(TAG, "No se pudo crear el grupo de eventos WiFi");
        return;
    }
    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    if (esp_netif_create_default_wifi_sta() == NULL) {
        ESP_LOGE(TAG, "No se pudo crear la interfaz WiFi");
        return;
    }
    wifi_init_config_t wifi_init = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&wifi_init));
    ESP_ERROR_CHECK(esp_event_handler_register(
        WIFI_EVENT, ESP_EVENT_ANY_ID, &wifi_event_handler, NULL
    ));
    ESP_ERROR_CHECK(esp_event_handler_register(
        IP_EVENT, IP_EVENT_STA_GOT_IP, &wifi_event_handler, NULL
    ));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    wifi_initialized = true;
    ESP_LOGI(TAG, "Boton de modo: D0/GPIO1 a GND");
    ESP_LOGI(TAG, "Mediciones pendientes: %d", (int)measurement_count);

    char line[GPS_LINE_BUFFER_SIZE];
    size_t line_length = 0;
    uint8_t byte = 0;
    bool button_was_pressed = false;
    while (true) {
        int current_button = gpio_get_level(MODE_BUTTON_PIN);
        if (current_button == 0 && !button_was_pressed) {
            button_was_pressed = true;
            upload_mode = !upload_mode;
            ESP_LOGI(TAG, "Modo cambiado a %s", upload_mode ? "UPLOAD" : "GPS");
            if (upload_mode) {
                oled_message("Modo", "CARGA WIFI");
                bool connected = wifi_initialized && wifi_connect();
                if (!connected || !upload_measurements()) {
                    ESP_LOGW(TAG, "Fallo de WiFi/MQTT con %s", CONFIG_GPS_WIFI_SSID);
                    oled_message("CARGA FALLIDA", "Sin WiFi/MQTT");
                } else {
                    oled_message("CARGA COMPLETA", "Orange Pi OK");
                }
            } else {
                oled_message("Modo", "GPS MONITOR");
            }
            vTaskDelay(pdMS_TO_TICKS(50));
        } else if (current_button == 1) {
            button_was_pressed = false;
        }
        if (uart_read_bytes(GPS_UART_NUM, &byte, 1, pdMS_TO_TICKS(100)) <= 0) continue;
        if (byte == '$') {
            line_length = 0;
            line[line_length++] = '$';
        } else if (byte == '\n') {
            line[line_length] = '\0';
            if (line_length > 0) process_sentence(line);
            line_length = 0;
        } else if (byte != '\r' && line_length > 0 && line_length < sizeof(line) - 1) {
            line[line_length++] = (char)byte;
        }
    }
}
