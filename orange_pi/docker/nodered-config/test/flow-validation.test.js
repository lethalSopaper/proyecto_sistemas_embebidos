const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const root = path.join(__dirname, "..");

test("Node-RED flow nodes have unique IDs and valid wires", () => {
    const flows = JSON.parse(fs.readFileSync(path.join(root, "flows.json"), "utf8"));
    const ids = new Set(flows.map((node) => node.id));

    assert.equal(ids.size, flows.length);
    for (const node of flows) {
        for (const output of node.wires || []) {
            for (const target of output) assert.ok(ids.has(target), `${node.id} -> ${target}`);
        }
        if (node.type === "function") assert.doesNotThrow(() => new Function(node.func));
    }
});

test("route management page has syntactically valid client-side JavaScript", () => {
    const html = fs.readFileSync(path.join(root, "routes.html"), "utf8");
    const script = html.match(/<script>([\s\S]*?)<\/script>/);

    assert.ok(script, "routes.html includes a script element");
    assert.doesNotThrow(() => new Function(script[1]));
});
