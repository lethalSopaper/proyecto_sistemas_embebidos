#include "gps_neo6m_oled.h"

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "driver/gpio.h"
#include "driver/uart.h"
#include "esp_err.h"
#include "esp_log.h"
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

static const char *TAG = "gps_neo6m_oled";

typedef struct {
    bool valid;
    double latitude;
    double longitude;
    double altitude_m;
    double hdop;
    int satellites;
} gps_measurement_t;

static u8g2_t display;

static void oled_show_status(const char *status)
{
    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_6x10_tf);
    u8g2_DrawStr(&display, 0, 12, "GPS NEO-6M");
    u8g2_DrawStr(&display, 0, 28, status);
    u8g2_SendBuffer(&display);
}

static void oled_show_measurement(const gps_measurement_t *measurement)
{
    char line[32];

    u8g2_ClearBuffer(&display);
    u8g2_SetFont(&display, u8g2_font_5x7_tf);

    snprintf(line, sizeof(line), "Lat: %.6f", measurement->latitude);
    u8g2_DrawStr(&display, 0, 24, line);
    snprintf(line, sizeof(line), "Lon: %.6f", measurement->longitude);
    u8g2_DrawStr(&display, 0, 34, line);
    snprintf(line, sizeof(line), "Alt: %.1f m", measurement->altitude_m);
    u8g2_DrawStr(&display, 0, 44, line);
    snprintf(
        line,
        sizeof(line),
        "Sat: %d  HDOP: %.1f",
        measurement->satellites,
        measurement->hdop
    );
    u8g2_DrawStr(&display, 0, 54, line);
    u8g2_DrawStr(&display, 0, 63, "GPS FIX OK");
    u8g2_SendBuffer(&display);
}

static bool gps_has_valid_checksum(const char *sentence)
{
    if (sentence[0] != '$') {
        return false;
    }

    const char *checksum = strchr(sentence, '*');
    if (checksum == NULL || checksum[1] == '\0' || checksum[2] == '\0') {
        return false;
    }

    unsigned char calculated = 0;
    for (const char *current = sentence + 1; current < checksum; current++) {
        calculated ^= (unsigned char)*current;
    }

    unsigned int expected = 0;
    if (sscanf(checksum + 1, "%2x", &expected) != 1) {
        return false;
    }

    return calculated == expected;
}

static double gps_coordinate_to_decimal(const char *coordinate, char hemisphere)
{
    double raw = 0.0;
    if (sscanf(coordinate, "%lf", &raw) != 1) {
        return 0.0;
    }

    double degrees = (int)(raw / 100.0);
    double minutes = raw - (degrees * 100.0);
    double decimal = degrees + (minutes / 60.0);
    if (hemisphere == 'S' || hemisphere == 'W') {
        decimal = -decimal;
    }

    return decimal;
}

static bool gps_parse_gga(char *sentence, gps_measurement_t *measurement)
{
    char *fields[15] = {0};
    size_t field_count = 0;
    char *field = strtok(sentence, ",");

    while (field != NULL && field_count < 15) {
        fields[field_count++] = field;
        field = strtok(NULL, ",*");
    }

    if (field_count < 10 ||
        (strcmp(fields[0] + 1, "GPGGA") != 0 &&
         strcmp(fields[0] + 1, "GNGGA") != 0)) {
        return false;
    }

    if (fields[6][0] == '0' || fields[2][0] == '\0' || fields[4][0] == '\0') {
        measurement->valid = false;
        return true;
    }

    measurement->valid = true;
    measurement->latitude = gps_coordinate_to_decimal(fields[2], fields[3][0]);
    measurement->longitude = gps_coordinate_to_decimal(fields[4], fields[5][0]);
    measurement->satellites = atoi(fields[7]);
    measurement->hdop = atof(fields[8]);
    measurement->altitude_m = atof(fields[9]);
    return true;
}

static void gps_process_sentence(char *sentence)
{
    if (sentence[0] != '$' || !gps_has_valid_checksum(sentence)) {
        return;
    }

    gps_measurement_t measurement = {0};
    if (!gps_parse_gga(sentence, &measurement)) {
        return;
    }

    if (!measurement.valid) {
        ESP_LOGI(TAG, "Sin fix GPS; esperando satelites...");
        oled_show_status("Esperando fix...");
        return;
    }

    ESP_LOGI(
        TAG,
        "Fix valido | lat=%.6f lon=%.6f alt=%.2f m sat=%d hdop=%.2f",
        measurement.latitude,
        measurement.longitude,
        measurement.altitude_m,
        measurement.satellites,
        measurement.hdop
    );
    oled_show_measurement(&measurement);
}

static void gps_uart_init(void)
{
    const uart_config_t uart_config = {
        .baud_rate = GPS_UART_BAUD_RATE,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .source_clk = UART_SCLK_DEFAULT,
    };

    ESP_ERROR_CHECK(uart_driver_install(
        GPS_UART_NUM,
        GPS_UART_BUFFER_SIZE,
        0,
        0,
        NULL,
        0
    ));
    ESP_ERROR_CHECK(uart_param_config(GPS_UART_NUM, &uart_config));
    ESP_ERROR_CHECK(uart_set_pin(
        GPS_UART_NUM,
        GPS_UART_TX_PIN,
        GPS_UART_RX_PIN,
        UART_PIN_NO_CHANGE,
        UART_PIN_NO_CHANGE
    ));
}

static void oled_init(void)
{
    u8g2_esp32_hal_t hal = U8G2_ESP32_HAL_DEFAULT;
    hal.bus.i2c.sda = OLED_SDA_PIN;
    hal.bus.i2c.scl = OLED_SCL_PIN;
    u8g2_esp32_hal_init(hal);

    u8g2_Setup_ssd1306_i2c_128x64_noname_f(
        &display,
        U8G2_R0,
        u8g2_esp32_i2c_byte_cb,
        u8g2_esp32_gpio_and_delay_cb
    );
    u8x8_SetI2CAddress(&display.u8x8, OLED_I2C_ADDRESS);
    u8g2_InitDisplay(&display);
    u8g2_SetPowerSave(&display, 0);
    oled_show_status("Esperando GPS...");
}

void gps_neo6m_oled_app_main(void)
{
    oled_init();
    gps_uart_init();

    ESP_LOGI(TAG, "GPS + OLED iniciados");
    ESP_LOGI(TAG, "GPS TX GPIO%d, RX GPIO%d", GPS_UART_RX_PIN, GPS_UART_TX_PIN);
    ESP_LOGI(TAG, "OLED SDA GPIO%d, SCL GPIO%d", OLED_SDA_PIN, OLED_SCL_PIN);

    char line[GPS_LINE_BUFFER_SIZE];
    size_t line_length = 0;
    uint8_t byte = 0;

    while (true) {
        int bytes_read = uart_read_bytes(
            GPS_UART_NUM,
            &byte,
            1,
            pdMS_TO_TICKS(1000)
        );
        if (bytes_read <= 0) {
            continue;
        }

        if (byte == '$') {
            line_length = 0;
            line[line_length++] = (char)byte;
        } else if (byte == '\n') {
            line[line_length] = '\0';
            if (line_length > 0) {
                gps_process_sentence(line);
            }
            line_length = 0;
        } else if (byte != '\r' && line_length > 0) {
            if (line_length < sizeof(line) - 1) {
                line[line_length++] = (char)byte;
            } else {
                line_length = 0;
            }
        }
    }
}
