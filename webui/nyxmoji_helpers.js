(function attachNyxmojiHelpers(root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.NyxmojiHelpers = api;
})(typeof globalThis !== "undefined" ? globalThis : null, function createNyxmojiHelpers() {
  function normalisedColor(color) {
    return typeof color === "string" ? color.trim().toLowerCase() : "";
  }

  function findOption(feature, optionId) {
    if (!feature || !Array.isArray(feature.options)) return null;
    const expected = String(optionId == null ? "" : optionId);
    return feature.options.find(option => option && String(option.id) === expected) || null;
  }

  function optionColorsAreVerified(feature, optionId) {
    const option = findOption(feature, optionId);
    return !!option && option.colors_verified === true;
  }

  function verifiedColorsForOption(feature, optionId) {
    const option = findOption(feature, optionId);
    if (!option || option.colors_verified !== true || !Array.isArray(option.colors)) return [];
    const seen = new Set();
    return option.colors.filter(color => {
      const key = normalisedColor(color);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      return true;
    }).map(color => String(color).trim());
  }

  function verifiedColorUnion(feature, optionIds) {
    const seen = new Set();
    const colors = [];
    (Array.isArray(optionIds) ? optionIds : []).forEach(optionId => {
      verifiedColorsForOption(feature, optionId).forEach(color => {
        const key = normalisedColor(color);
        if (!seen.has(key)) {
          seen.add(key);
          colors.push(color);
        }
      });
    });
    return colors;
  }

  function filterConfiguredColors(configuredColors, availableColors) {
    const requested = new Set((Array.isArray(configuredColors) ? configuredColors : [])
      .map(normalisedColor)
      .filter(Boolean));
    const seen = new Set();
    return (Array.isArray(availableColors) ? availableColors : []).filter(color => {
      const key = normalisedColor(color);
      if (!key || !requested.has(key) || seen.has(key)) return false;
      seen.add(key);
      return true;
    }).map(color => String(color).trim());
  }

  function hasSelectableColors(feature, optionIds) {
    return verifiedColorUnion(feature, optionIds).length > 0;
  }

  function cleanParams(params) {
    if (!params || typeof params !== "object" || Array.isArray(params)) return {};
    const clean = {};
    Object.entries(params).forEach(([key, value]) => {
      if (!key || value == null || typeof value === "object") return;
      clean[String(key)] = String(value);
    });
    return clean;
  }

  function resolveOptionRender(feature, optionId, selectedColor) {
    const option = findOption(feature, optionId);
    const render = option && option.render && typeof option.render === "object" ? option.render : null;
    if (!render) return {};
    const params = cleanParams(render.params);
    const target = normalisedColor(selectedColor);
    if (!target) return params;
    for (const variantKey of ["colour_variants", "color_variants"]) {
      const variants = render[variantKey];
      if (!variants || typeof variants !== "object" || Array.isArray(variants)) continue;
      const matchingColor = Object.keys(variants).find(color => normalisedColor(color) === target);
      if (matchingColor) Object.assign(params, cleanParams(variants[matchingColor]));
    }
    return params;
  }

  function applyAvatarParams(baseUrl, params) {
    let url;
    try { url = new URL(baseUrl); } catch (error) { return ""; }
    Object.entries(cleanParams(params)).forEach(([key, value]) => url.searchParams.set(key, value));
    return url.toString();
  }

  return {
    findOption,
    optionColorsAreVerified,
    verifiedColorsForOption,
    verifiedColorUnion,
    filterConfiguredColors,
    hasSelectableColors,
    resolveOptionRender,
    applyAvatarParams,
  };
});
