const fs = require("node:fs");
const path = require("node:path");

const userDir = process.env.NODE_RED_USER_DIR || "/data";
const settingsPath = path.join(userDir, "settings.js");
const existingSettings = fs.existsSync(settingsPath)
    ? require(settingsPath)
    : {};
const flowFile = existingSettings.flowFile || "flows.json";
const existingFlowsPath = path.isAbsolute(flowFile)
    ? flowFile
    : path.join(userDir, flowFile);
const bundledFlowsPath = "/opt/gps/flows.json";

function readFlows(filePath) {
    if (!fs.existsSync(filePath)) {
        return [];
    }

    const flows = JSON.parse(fs.readFileSync(filePath, "utf8"));
    if (!Array.isArray(flows)) {
        throw new Error(`${filePath} must contain a Node-RED flow array`);
    }
    return flows;
}

const currentFlows = readFlows(existingFlowsPath);
const bundledFlows = readFlows(bundledFlowsPath);
const bundledIds = new Set(bundledFlows.map((node) => node.id));
const mergedFlows = [
    ...currentFlows.filter((node) => !bundledIds.has(node.id)),
    ...bundledFlows,
];

if (JSON.stringify(currentFlows) !== JSON.stringify(mergedFlows)) {
    if (fs.existsSync(existingFlowsPath)) {
        const backupPath = `${existingFlowsPath}.gps-backup-${Date.now()}`;
        fs.copyFileSync(existingFlowsPath, backupPath);
    }
    fs.writeFileSync(
        existingFlowsPath,
        `${JSON.stringify(mergedFlows, null, 2)}\n`,
        { mode: 0o600 },
    );
}
