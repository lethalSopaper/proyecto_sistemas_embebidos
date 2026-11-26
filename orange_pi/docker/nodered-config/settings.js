const fs = require("node:fs");
const bcrypt = require("/opt/gps/node_modules/bcryptjs");
const mysql = require("/opt/gps/node_modules/mysql2/promise");

const existingSettingsPath = "/data/settings.js";
const existingSettings = fs.existsSync(existingSettingsPath)
    ? require(existingSettingsPath)
    : {};

const requiredEnvironment = [
    "NODERED_ADMIN_USER",
    "NODERED_ADMIN_PASSWORD",
    "NODERED_HTTP_USER",
    "NODERED_HTTP_PASSWORD",
    "MARIADB_PASSWORD",
];
for (const name of requiredEnvironment) {
    if (!process.env[name]) {
        throw new Error(`Missing required environment variable ${name}`);
    }
}

const pool = mysql.createPool({
    host: process.env.MARIADB_HOST || "mariadb",
    port: Number(process.env.MARIADB_PORT || 3306),
    database: process.env.MARIADB_DATABASE || "gps",
    user: process.env.MARIADB_USER || "gps_user",
    password: process.env.MARIADB_PASSWORD,
    connectionLimit: 5,
    waitForConnections: true,
    timezone: "Z",
});

module.exports = {
    ...existingSettings,
    flowFile: existingSettings.flowFile || "flows.json",
    adminAuth: {
        type: "credentials",
        users: [{
            username: process.env.NODERED_ADMIN_USER,
            password: bcrypt.hashSync(process.env.NODERED_ADMIN_PASSWORD, 10),
            permissions: "*",
        }],
    },
    httpNodeAuth: {
        user: process.env.NODERED_HTTP_USER,
        pass: bcrypt.hashSync(process.env.NODERED_HTTP_PASSWORD, 10),
    },
    functionGlobalContext: {
        ...(existingSettings.functionGlobalContext || {}),
        gpsRepository: require("/opt/gps/gps-repository.js")(pool),
        gpsRoutesHtml: fs.readFileSync("/opt/gps/routes.html", "utf8"),
    },
};
