const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const helpers = require("../webui/nyxmoji_helpers.js");

const garments = {
  type: "outfit",
  options: [
    {
      id: "red-shirt",
      preview: "https://preview.bitmoji.com/avatar/top?top=red-shirt",
      colors_verified: true,
      colors: ["#EC2020", "#010203"],
      render: {
        params: { top: "red-shirt" },
        colour_variants: {
          "#EC2020": { top_tone1: "16031775" },
          "#010203": { top_tone1: "66051" },
        },
      },
    },
    {
      id: "blue-shirt",
      preview: "https://preview.bitmoji.com/avatar/top?top=blue-shirt",
      colors_verified: true,
      colors: ["#010203", "#ABCDEF"],
      render: {
        params: { top: "blue-shirt" },
        color_variants: { "#ABCDEF": { top_tone1: "11259375" } },
      },
    },
    {
      id: "plain-shirt",
      preview: "https://preview.bitmoji.com/avatar/top?top=plain-shirt",
      colors_verified: true,
      colors: [],
      render: { params: { top: "plain-shirt" } },
    },
    {
      id: "legacy-shirt",
      colors: ["#FFFFFF"],
      render: { params: { top: "legacy-shirt" } },
    },
  ],
};

test("finds only the exact selected option and its verified colors", () => {
  assert.equal(helpers.findOption(garments, "red-shirt").id, "red-shirt");
  assert.equal(helpers.findOption(garments, "missing"), null);
  assert.deepEqual(helpers.verifiedColorsForOption(garments, "red-shirt"), ["#EC2020", "#010203"]);
  assert.deepEqual(helpers.verifiedColorsForOption(garments, "legacy-shirt"), []);
});

test("a verified colorless item has no selectable colors", () => {
  assert.deepEqual(helpers.verifiedColorsForOption(garments, "plain-shirt"), []);
  assert.equal(helpers.hasSelectableColors(garments, ["plain-shirt"]), false);
  assert.deepEqual(helpers.filterConfiguredColors(["#EC2020"], helpers.verifiedColorsForOption(garments, "plain-shirt")), []);
});

test("random pools use only the union from their exact verified options and prune stale colors", () => {
  const colors = helpers.verifiedColorUnion(garments, ["red-shirt", "blue-shirt"]);
  assert.deepEqual(colors, ["#EC2020", "#010203", "#ABCDEF"]);
  assert.deepEqual(helpers.filterConfiguredColors(["#ec2020", "#ABCDEF", "#FFFFFF"], colors), ["#EC2020", "#ABCDEF"]);
  assert.deepEqual(helpers.verifiedColorUnion(garments, ["plain-shirt"]), []);
});

test("merges only the selected option's exact color render variant without fabricating tones", () => {
  assert.deepEqual(helpers.resolveOptionRender(garments, "red-shirt", "#ec2020"), {
    top: "red-shirt", top_tone1: "16031775",
  });
  assert.deepEqual(helpers.resolveOptionRender(garments, "blue-shirt", "#EC2020"), {
    top: "blue-shirt",
  });
  assert.deepEqual(helpers.resolveOptionRender(garments, "blue-shirt", "#abcdef"), {
    top: "blue-shirt", top_tone1: "11259375",
  });
  assert.deepEqual(helpers.resolveOptionRender(garments, "plain-shirt", "#ec2020"), {
    top: "plain-shirt",
  });
});

test("applies only provided exact render params to an avatar URL", () => {
  const url = helpers.applyAvatarParams(
    "https://preview.bitmoji.com/bm-preview/v3/avatar/body?gender=1&top=base",
    { top: "red-shirt", top_tone1: "16031775", ignored: null },
  );
  const parsed = new URL(url);
  assert.equal(parsed.searchParams.get("gender"), "1");
  assert.equal(parsed.searchParams.get("top"), "red-shirt");
  assert.equal(parsed.searchParams.get("top_tone1"), "16031775");
  assert.equal(parsed.searchParams.has("ignored"), false);
  assert.equal(helpers.applyAvatarParams("not a valid url", { top: "red-shirt" }), "");
});

test("dashboard no longer declares a generic outfit palette or synthesizes tone params", () => {
  const dashboard = fs.readFileSync(path.join(__dirname, "../webui/dashboard.js"), "utf8");
  assert.equal(dashboard.includes("BM_OUTFIT_COLORS"), false);
  assert.equal(dashboard.includes('rp.param + "_tone1"'), false);
});
