# Nyxmoji Live Selector and Garment Colour Design

## Goal

Make each Nyxmoji option use the correct live Bitmoji editor selector and real
Bitmoji PNG preview, while making garment colours available only for the
specific selected garment that supports them.

## Scope

- Audit every supported feature against the live Bitmoji editor using AdsPower
  profile `k1f2la8v`; the audit must not save the avatar.
- Preserve the editor's actual preview PNG URL for each selectable option.
- Capture item-specific garment colour capability for Outfits, Tops, Bottoms,
  Dresses, Footwear, and Outerwear. A selected garment with no visible colour
  picker has an empty colour list.
- Correct the Nyxmoji stage preview so its query parameters match the selected
  option's live render data, including the appropriate colour parameter rather
  than assuming `<item>_tone1`.
- Show colour controls only when the selected fixed garment, or at least one
  option in a random garment pool, supports colours. Do not show unsupported
  colours for a fixed item.
- Sanitize saved model settings so an item cannot retain a colour that is not
  supported by that selected item; a random colour pool is restricted to the
  union of its selected items' supported colours.
- At runtime, apply a garment colour only after the exact garment tile was
  selected and a live colour picker is visible. If no picker exists, retain the
  selected item and skip colour selection without failing the profile.

## Non-goals

- Do not save or otherwise persist changes to the audit avatar.
- Do not introduce a synthetic full-spectrum colour palette.
- Do not change the existing model presets, random-selection semantics, or
  unrelated Bitmoji feature controls.

## Data Contract

Each catalog option continues to contain `id` and `preview`, where `preview` is
the live Bitmoji PNG URL. Garment options gain explicit live metadata:

```json
{
  "id": "1062",
  "preview": "https://preview.bitmoji.com/bm-preview/v3/avatar/footwear?...",
  "render": {
    "item_param": "footwear",
    "item_value": "1062",
    "colour_params": ["footwear_tone1", "footwear_tone2"]
  },
  "colors": ["#ec2020", "#f5bebc"]
}
```

For a colourless garment, `colors` and `render.colour_params` are empty. The
catalog stores live values rather than deriving them from hard-coded feature
rules. Legacy catalog entries remain readable: they may display their PNG and
select their item, but they expose no colour controls until a live scan supplies
the item metadata.

## Live Audit and Scanner

The scanner attaches to the AdsPower profile over CDP, opens the editor frame,
and visits every feature panel. It scrolls virtualized item grids to collect
every tile. For each garment tile it selects the tile without saving, waits for
the editor to settle, and records:

1. the exact item ID and PNG URL;
2. item and colour query parameters present in the live preview URL; and
3. the visible live colour picker swatches, if any.

The scanner uses a bounded wait and restores the panel state before proceeding.
It writes the catalog only after a complete successful scan; a partial or failed
audit leaves the current catalog unchanged.

## Nyxmoji UI and Preview

The option grid continues to render `option.preview` directly, so the thumbnail
is the real Bitmoji PNG. The stage preview starts from the selected option's
render metadata instead of constructing a generic clothing parameter. For a
colour selection, it updates only the recorded `colour_params` for that option.

In Fixed mode, colour controls are visible only if the chosen option has one or
more colours. Selecting a different garment immediately removes an unsupported
saved colour. In Random mode, colour controls are visible only if the selected
item pool has at least one supported colour; the available chips are the union
of those supported lists. The user selected the hide-controls treatment for
colourless garments.

## Runtime Application

The runner continues to use the catalog-derived item selector for configured
features. After it selects an outfit item, it requests the configured colour
only when that option supports colours. It then verifies that the live colour
picker is visible before matching the requested swatch. Absence of a picker is
a successful no-colour outcome, not a random-colour fallback or a profile error.

## Error Handling

- A stale or retired item still follows the existing same-pool fallback policy.
- If a configured colour is absent from the selected item's supported list, the
  setting is discarded during normalization and the item is applied unchanged.
- If the live picker differs from scanned metadata, the runner logs the mismatch
  and leaves the item unchanged rather than clicking an arbitrary swatch.
- The live audit never saves the Bitmoji; inability to attach to the supplied
  profile is reported as a test-environment blocker rather than treated as a
  selector mismatch.

## Verification

Automated coverage will prove selector generation, catalog normalization,
real-PNG preservation, item-specific colour visibility, saved-setting
normalization, preview query construction, and colourless runtime behavior.
The final smoke audit attaches to AdsPower profile `k1f2la8v`, records selector
counts and colour-picker capability without saving, and checks representative
Tops, Bottoms, Footwear, Dresses, and colourless options.
