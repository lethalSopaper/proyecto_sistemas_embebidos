#include "gps_neo6m_oled_mqtt.h"

#include <stdbool.h>
#include <stddef.h>
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

#define GPS_UART_NUM UART_NUM_1
#define GPS_UART_BAUD_RATE 9600
#define GPS_UART_RX_PIN GPIO_NUM_2
#define GPS_UART_TX_PIN GPIO_NUM_3
#define GPS_UART_BUFFER_SIZE 1024
#define GPS_LINE_BUFFER_SIZE 128
#ifndef GPS_MQTT_NO_DISPLAY
#define OLED_SDA_PIN GPIO_NUM_7
#define OLED_SCL_PIN GPIO_NUM_44
#define OLED_I2C_ADDRESS 0x78
#include "u8g2.h"
#include "u8g2_esp32_hal.h"
#else
#define RED_LED_PIN GPIO_NUM_9
#define GREEN_LED_PIN GPIO_NUM_8
#endif
#define MODE_BUTTON_PIN GPIO_NUM_1
#define MAX_MEASUREMENTS 256
#define MEASUREMENT_CHUNK_SIZE 8
#define WIFI_CONNECTED BIT0
#define MQTT_CONNECTED BIT1
#define MQTT_PUBLISHED BIT2
#define WIFI_PROFILE_COUNT 5
#define WIFI_SSID_LENGTH 32
#define WIFI_PASSWORD_LENGTH 64

static const char *TAG = "gps_oled_mqtt";
static EventGroupHandle_t wifi_events;
static esp_mqtt_client_handle_t mqtt_client;
#ifndef GPS_MQTT_NO_DISPLAY
static u8g2_t display;
#endif
static bool upload_mode;
static bool wifi_initialized;
static bool wifi_started;
static nvs_handle_t storage;
static char active_wifi_ssid[WIFI_SSID_LENGTH];
static size_t last_uploaded_count;

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
static char measurement_key[16];
static char mqtt_status_topic[128];
static char mqtt_payload[192];

typedef struct {
    char ssid[WIFI_SSID_LENGTH];
    char password[WIFI_PASSWORD_LENGTH];
} wifi_profile_t;

typedef struct {
    uint32_t count;
    wifi_profile_t profiles[WIFI_PROFILE_COUNT];
} wifi_profile_store_t;

static wifi_profile_store_t wifi_profiles;

static void persist_measurements(void)
{
    uint32_t count = (uint32_t)measurement_count;
    if (measurement_count == 0) return;
    size_t chunk = (measurement_count - 1) / MEASUREMENT_CHUNK_SIZE;
    size_t offset = chunk * MEASUREMENT_CHUNK_SIZE;
    size_t items = measurement_count - offset;
    snprintf(measurement_key, sizeof(measurement_key), "m%02u", (unsigned)chunk);
    esp_err_t error = nvs_set_blob(storage, measurement_key, &measurements[offset],
                                   items * sizeof(measurements[0]));
    if (error == ESP_OK) {
        error = nvs_set_u32(storage, "m_count", count);
    }
    if (error == ESP_OK) error = nvs_commit(storage);
    if (error != ESP_OK) {
        ESP_LOGE(TAG, "No se pudieron guardar %d mediciones en NVS: %s",
                 (int)measurement_count, esp_err_to_name(error));
    }
}

static void load_measurements(void)
{
    uint32_t stored_count = 0;
    esp_err_t error = nvs_get_u32(storage, "m_count", &stored_count);
    if (error == ESP_OK && stored_count <= MAX_MEASUREMENTS) {
        measurement_count = 0;
        for (size_t chunk = 0; measurement_count < stored_count; chunk++) {
            size_t items = stored_count - measurement_count;
            if (items > MEASUREMENT_CHUNK_SIZE) items = MEASUREMENT_CHUNK_SIZE;
            size_t size = items * sizeof(measurements[0]);
            snprintf(measurement_key, sizeof(measurement_key), "m%02u",
                     (unsigned)chunk);
            error = nvs_get_blob(storage, measurement_key,
                                 &measurements[measurement_count], &size);
            if (error != ESP_OK || size != items * sizeof(measurements[0])) {
                measurement_count = 0;
                ESP_LOGW(TAG, "No se pudo cargar el bloque %u de mediciones: %s",
                         (unsigned)chunk, esp_err_to_name(error));
                return;
            }
            measurement_count += items;
        }
        return;
    }

    /* Compatibility with the single-blob format used by older firmware. */
    size_t size = sizeof(measurement_store);
    error = nvs_get_blob(storage, "measurements", &measurement_store, &size);
    size_t data_offset = offsetof(measurement_store_t, data);
    size_t expected_size = data_offset +
                           measurement_store.count * sizeof(measurements[0]);
    if (error == ESP_OK && measurement_store.count <= MAX_MEASUREMENTS &&
        size >= expected_size) {
        measurement_count = measurement_store.count;
        memcpy(measurements, measurement_store.data,
               measurement_count * sizeof(measurements[0]));
    } else if (error != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "No se pudieron cargar las mediciones de NVS: %s",
                 esp_err_to_name(error));
    }
}

static void persist_wifi_profiles(void)
{
    ESP_ERROR_CHECK(nvs_set_blob(
        storage, "wifi_profiles", &wifi_profiles, sizeof(wifi_profiles)
    ));
    ESP_ERROR_CHECK(nvs_commit(storage));
}

static void load_wifi_profiles(void)
{
    size_t size = sizeof(wifi_profiles);
    esp_err_t error = nvs_get_blob(storage, "wifi_profiles", &wifi_profiles, &size);
    if (error != ESP_OK || wifi_profiles.count > WIFI_PROFILE_COUNT) {
        memset(&wifi_profiles, 0, sizeof(wifi_profiles));
    }
}

static void add_configured_wifi_profile(const char *ssid, const char *password)
{
    if (ssid == NULL || ssid[0] == '\0') return;
    for (uint32_t i = 0; i < wifi_profiles.count; i++) {
        if (strcmp(wifi_profiles.profiles[i].ssid, ssid) == 0) {
            snprintf(wifi_profiles.profiles[i].password, WIFI_PASSWORD_LENGTH,
                     "%s", password != NULL ? password : "");
            return;
        }
    }
    if (wifi_profiles.count == WIFI_PROFILE_COUNT) {
        ESP_LOGW(TAG, "Lista WiFi llena; no se agrego SSID=%s", ssid);
        return;
    }
    snprintf(wifi_profiles.profiles[wifi_profiles.count].ssid,
             WIFI_SSID_LENGTH, "%s", ssid);
    snprintf(wifi_profiles.profiles[wifi_profiles.count].password,
             WIFI_PASSWORD_LENGTH, "%s", password != NULL ? password : "");
    wifi_profiles.count++;
    ESP_LOGI(TAG, "Red WiFi agregada a NVS: %s", ssid);
}

static void sync_configured_wifi_profiles(void)
{
    add_configured_wifi_profile(CONFIG_GPS_WIFI_SSID, CONFIG_GPS_WIFI_PASSWORD);
    add_configured_wifi_profile(CONFIG_GPS_WIFI_SSID_2, CONFIG_GPS_WIFI_PASSWORD_2);
    add_configured_wifi_profile(CONFIG_GPS_WIFI_SSID_3, CONFIG_GPS_WIFI_PASSWORD_3);
    add_configured_wifi_profile(CONFIG_GPS_WIFI_SSID_4, CONFIG_GPS_WIFI_PASSWORD_4);
    add_configured_wifi_profile(CONFIG_GPS_WIFI_SSID_5, CONFIG_GPS_WIFI_PASSWORD_5);
    persist_wifi_profiles();
}

#ifndef GPS_MQTT_NO_DISPLAY
static void oled_message(const char *title, const char *message)
{
    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_6x10_tf);
    u8g2_DrawStr(&display, 0, 14, title);
    u8g2_DrawStr(&display, 0, 32, message);
    u8g2_SendBuffer(&display);
}
#endif

#ifdef GPS_MQTT_NO_DISPLAY
static void leds_init(void)
{
    gpio_config_t leds = {
        .pin_bit_mask = (1ULL << RED_LED_PIN) | (1ULL << GREEN_LED_PIN),
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    ESP_ERROR_CHECK(gpio_config(&leds));
    gpio_set_level(RED_LED_PIN, 0);
    gpio_set_level(GREEN_LED_PIN, 0);
}

static void led_green_set(bool on)
{
    gpio_set_level(GREEN_LED_PIN, on ? 1 : 0);
}

static void led_red_set(bool on)
{
    gpio_set_level(RED_LED_PIN, on ? 1 : 0);
}

static void led_red_measurement(void)
{
    led_red_set(true);
    vTaskDelay(pdMS_TO_TICKS(100));
    if (measurement_count < MAX_MEASUREMENTS) led_red_set(false);
}
#endif

#ifndef GPS_MQTT_NO_DISPLAY
static void oled_measurement(const gps_measurement_t *m)
{
    char line[32];
    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_5x7_tf);
    snprintf(line, sizeof(line), "Mediciones: %d", (int)measurement_count);
    u8g2_DrawStr(&display, 0, 8, line);
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

static void oled_upload_complete(void)
{
    char line[32];
    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_5x7_tf);
    u8g2_DrawStr(&display, 0, 10, "CARGA COMPLETA");
    snprintf(line, sizeof(line), "WiFi: %.20s", active_wifi_ssid);
    u8g2_DrawStr(&display, 0, 28, line);
    snprintf(line, sizeof(line), "Enviadas: %d", (int)last_uploaded_count);
    u8g2_DrawStr(&display, 0, 42, line);
    u8g2_DrawStr(&display, 0, 60, "Pulsa: GPS MONITOR");
    u8g2_SendBuffer(&display);
}
#else
static void oled_message(const char *title, const char *message)
{
    (void)title;
    (void)message;
}

static void oled_measurement(const gps_measurement_t *m)
{
    (void)m;
}

static void oled_upload_complete(void)
{
}
#endif

static void wifi_event_handler(
    void *arg,
    esp_event_base_t event_base,
    int32_t event_id,
    void *event_data
)
{
    if (event_base == WIFI_EVENT && event_id == WIFI_EVENT_STA_DISCONNECTED) {
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
    if ((xEventGroupGetBits(wifi_events) & WIFI_CONNECTED) != 0) {
        ESP_LOGI(TAG, "WiFi ya conectado; se reutilizara la conexion existente");
        return true;
    }

    for (uint32_t i = 0; i < wifi_profiles.count; i++) {
        wifi_profile_t *profile = &wifi_profiles.profiles[i];
        wifi_config_t config = {0};
        snprintf((char *)config.sta.ssid, sizeof(config.sta.ssid), "%s", profile->ssid);
        snprintf((char *)config.sta.password, sizeof(config.sta.password),
                 "%s", profile->password);
        snprintf(active_wifi_ssid, sizeof(active_wifi_ssid), "%s", profile->ssid);
        oled_message("WiFi intentando", active_wifi_ssid);
        ESP_LOGI(TAG, "Conectando a WiFi SSID=%s (%s)", profile->ssid,
                 profile->password[0] == '\0' ? "sin contraseña" : "con contraseña");
        xEventGroupClearBits(wifi_events, WIFI_CONNECTED);
        esp_err_t error = esp_wifi_set_config(WIFI_IF_STA, &config);
        if (error != ESP_OK) {
            ESP_LOGE(TAG, "No se pudo configurar WiFi %s: %s",
                     profile->ssid, esp_err_to_name(error));
            continue;
        }
        if (!wifi_started) {
            error = esp_wifi_start();
            if (error != ESP_OK) {
                ESP_LOGE(TAG, "No se pudo iniciar WiFi: %s", esp_err_to_name(error));
                continue;
            }
            wifi_started = true;
        } else {
            esp_wifi_disconnect();
        }
        error = esp_wifi_connect();
        if (error != ESP_OK && error != ESP_ERR_WIFI_CONN) {
            ESP_LOGE(TAG, "No se pudo conectar a WiFi %s: %s",
                     profile->ssid, esp_err_to_name(error));
            continue;
        }
        EventBits_t bits = xEventGroupWaitBits(
            wifi_events, WIFI_CONNECTED, pdFALSE, pdFALSE, pdMS_TO_TICKS(8000)
        );
        if ((bits & WIFI_CONNECTED) != 0) {
            oled_message("WiFi conectado", active_wifi_ssid);
            return true;
        }
    }
    oled_message("WiFi sin conexion", "Revise perfiles");
    return false;
}

static void mqtt_event_handler(void *handler_args, esp_event_base_t base, int32_t event_id, void *event_data)
{
    if (event_id == MQTT_EVENT_CONNECTED) {
        ESP_LOGI(TAG, "Conectado al broker MQTT");
        xEventGroupSetBits(wifi_events, MQTT_CONNECTED);
    } else if (event_id == MQTT_EVENT_PUBLISHED) {
        xEventGroupSetBits(wifi_events, MQTT_PUBLISHED);
    } else if (event_id == MQTT_EVENT_DISCONNECTED) {
        xEventGroupClearBits(wifi_events, MQTT_CONNECTED);
    }
}

static bool publish_and_wait(const char *topic, const char *payload)
{
    xEventGroupClearBits(wifi_events, MQTT_PUBLISHED);
    if (esp_mqtt_client_publish(mqtt_client, topic, payload, 0, 1, 0) < 0) {
        ESP_LOGE(TAG, "No se pudo encolar el mensaje MQTT en %s", topic);
        return false;
    }
    EventBits_t bits = xEventGroupWaitBits(
        wifi_events, MQTT_PUBLISHED, pdTRUE, pdFALSE, pdMS_TO_TICKS(5000)
    );
    if ((bits & MQTT_PUBLISHED) == 0) {
        ESP_LOGE(TAG, "Tiempo agotado esperando confirmacion MQTT en %s", topic);
        return false;
    }
    return true;
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
    if (!publish_and_wait(mqtt_status_topic, "uploading")) {
        goto upload_failed;
    }

    for (size_t i = 0; i < measurement_count; i++) {
        gps_measurement_t *m = &measurements[i];
        snprintf(
            mqtt_payload, sizeof(mqtt_payload),
            "{\"latitude\":%.6f,\"longitude\":%.6f,\"altitude\":%.2f,\"satellites\":%d,\"hdop\":%.2f}",
            m->latitude, m->longitude, m->altitude_m, m->satellites, m->hdop
        );
        if (!publish_and_wait(CONFIG_GPS_MQTT_TOPIC, mqtt_payload)) {
            goto upload_failed;
        }
    }
    last_uploaded_count = measurement_count;
    ESP_LOGI(TAG, "Mediciones publicadas: %d", (int)last_uploaded_count);
    if (!publish_and_wait(mqtt_status_topic, "complete")) {
        goto upload_failed;
    }
    measurement_count = 0;
    esp_err_t erase_error = nvs_erase_key(storage, "m_count");
    if (erase_error != ESP_OK && erase_error != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "No se pudo borrar el contador NVS: %s",
                 esp_err_to_name(erase_error));
    }
    erase_error = nvs_erase_key(storage, "measurements");
    if (erase_error != ESP_OK && erase_error != ESP_ERR_NVS_NOT_FOUND) {
        ESP_LOGW(TAG, "No se pudo borrar el registro anterior: %s",
                 esp_err_to_name(erase_error));
    }
    for (size_t chunk = 0; chunk < MAX_MEASUREMENTS / MEASUREMENT_CHUNK_SIZE; chunk++) {
        snprintf(measurement_key, sizeof(measurement_key), "m%02u", (unsigned)chunk);
        erase_error = nvs_erase_key(storage, measurement_key);
        if (erase_error != ESP_OK && erase_error != ESP_ERR_NVS_NOT_FOUND) {
            ESP_LOGW(TAG, "No se pudo borrar el bloque %s: %s",
                     measurement_key, esp_err_to_name(erase_error));
        }
    }
    ESP_ERROR_CHECK(nvs_commit(storage));
    esp_mqtt_client_stop(mqtt_client);
    esp_mqtt_client_destroy(mqtt_client);
    mqtt_client = NULL;
    return true;

upload_failed:
    esp_mqtt_client_stop(mqtt_client);
    esp_mqtt_client_destroy(mqtt_client);
    mqtt_client = NULL;
    return false;
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

#ifndef GPS_MQTT_NO_DISPLAY
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
#endif

static bool nmea_coordinate_to_decimal(
    const char *value, double *coordinate
)
{
    if (value == NULL || value[0] == '\0') return false;
    double nmea_value = atof(value);
    int degrees = (int)(nmea_value / 100.0);
    double minutes = nmea_value - (degrees * 100.0);
    if (minutes < 0.0 || minutes >= 60.0) return false;
    *coordinate = degrees + (minutes / 60.0);
    return true;
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
    if (!nmea_coordinate_to_decimal(fields[2], &m->latitude) ||
        !nmea_coordinate_to_decimal(fields[4], &m->longitude)) {
        m->valid = false;
        return false;
    }
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
    if (upload_mode) return;
    if (measurement_count < MAX_MEASUREMENTS) {
        measurements[measurement_count++] = m;
#ifdef GPS_MQTT_NO_DISPLAY
        led_green_set(true);
        led_red_measurement();
#endif
    } else {
        ESP_LOGW(TAG, "Limite de mediciones alcanzado: %d", MAX_MEASUREMENTS);
#ifdef GPS_MQTT_NO_DISPLAY
        led_red_set(true);
#endif
    }
    if (measurement_count % 10 == 0) persist_measurements();
    oled_measurement(&m);
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
    load_wifi_profiles();
    sync_configured_wifi_profiles();
#ifndef GPS_MQTT_NO_DISPLAY
    oled_init();
#else
    leds_init();
    if (measurement_count >= MAX_MEASUREMENTS) led_red_set(true);
#endif
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
#ifdef GPS_MQTT_NO_DISPLAY
                led_green_set(false);
#endif
                oled_message("Modo", "CARGA WIFI");
                bool connected = wifi_initialized && wifi_connect();
                if (!connected || !upload_measurements()) {
                    ESP_LOGW(TAG, "Fallo de WiFi/MQTT con %s", CONFIG_GPS_WIFI_SSID);
                    oled_message("CARGA FALLIDA", "Sin WiFi/MQTT");
                } else {
#ifdef GPS_MQTT_NO_DISPLAY
                    led_green_set(true);
                    led_red_set(false);
#endif
                    oled_upload_complete();
                }
            } else {
#ifdef GPS_MQTT_NO_DISPLAY
                led_green_set(true);
                if (measurement_count < MAX_MEASUREMENTS) led_red_set(false);
#endif
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
