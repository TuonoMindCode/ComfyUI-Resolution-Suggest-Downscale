# tuono_resolution_suggest_downscale.py
#
# Resolution Suggest & Downscale
#
# - Chooses multiple_of from a model profile (8 / 16 / 32 / 64).
# - Either:
#     * Downscales image by a percentage preset, OR
#     * Uses "Resolution suggestion 1/2/3/4" based on:
#         - static table (1–3)
#         - dynamic very low VRAM (4)
# - Preserves aspect ratio.
# - Snaps width/height to the chosen multiple_of.
# - Info output shows:
#     * multiple_of: N (Profile name)
#     * scale_preset + reduction/scale
#     * input image: WxH
#     * result: raw WxH -> snapped WxH
#     * suggested/common resolutions + less common lower resolution
#
# Typical flow:
#   Load Image ─────────────┐
#                            │
#                   (image)  ▼
#   Resolution Suggest & Downscale ─► width/height ─► Resize Image (V2)
#                             │
#                             └─► info (STRING)


class TuonoResolutionSuggestDownscale:
    """
    Resolution Suggest & Downscale
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "model_profile": (
                    [
                        "multiple_of: 8 (SD / General (8))",
                        "multiple_of: 16 (WAN 2.2 / Strict (16))",
                        "multiple_of: 32 (Video / Advanced (32))",
                        "multiple_of: 64 (Legacy / Extra Safe (64))",
                    ],
                    {
                        "default": "multiple_of: 16 (WAN 2.2 / Strict (16))",
                    },
                ),
                "scale_preset": (
                    [
                        "0% smaller (keep original) (1920x1080→1920x1080, 1280x720→1280x720)",
                        "10% smaller (1920x1080→1728x972, 1280x720→1152x648)",
                        "20% smaller (1920x1080→1536x864, 1280x720→1024x576)",
                        "30% smaller (1920x1080→1344x756, 1280x720→896x504)",
                        "40% smaller (1920x1080→1152x648, 1280x720→768x432)",
                        "50% smaller (1920x1080→960x540, 1280x720→640x360)",
                        "60% smaller (1920x1080→768x432, 1280x720→512x288)",
                        "Resolution suggestion 1 (highest from table)",
                        "Resolution suggestion 2 (lower from table)",
                        "Resolution suggestion 3 (lowest from table)",
                        "Resolution suggestion 4 (very low VRAM)",
                    ],
                    {
                        "default": "30% smaller (1920x1080→1344x756, 1280x720→896x504)",
                    },
                ),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("image", "width", "height", "info")
    FUNCTION = "calc"
    CATEGORY = "Resolution/Utilities"

    # --- Helpers: core ---

    def _snap_dim(self, value, multiple):
        if value <= 0:
            return multiple
        v = int(value)
        snapped = (v // multiple) * multiple
        if snapped < multiple:
            snapped = multiple
        return snapped

    def _profile_to_multiple(self, model_profile: str):
        """
        Map dropdown string to (multiple_of, profile_label)
        profile_label används bara i info-texten.
        """
        if model_profile.startswith("multiple_of: 8"):
            return 8, "SD / General (8)"
        if model_profile.startswith("multiple_of: 16"):
            return 16, "WAN 2.2 / Strict (16)"
        if model_profile.startswith("multiple_of: 32"):
            return 32, "Video / Advanced (32)"
        if model_profile.startswith("multiple_of: 64"):
            return 64, "Legacy / Extra Safe (64)"
        # fallback
        return 8, "SD / General (8)"

    # --- Helpers: percentage presets ---

    def _scale_from_percentage_preset(self, scale_preset: str):
        """
        Convert percentage scale presets to (reduction_percent, scale).
        """
        if scale_preset.startswith("0%"):
            reduction = 0.0
        elif scale_preset.startswith("10%"):
            reduction = 10.0
        elif scale_preset.startswith("20%"):
            reduction = 20.0
        elif scale_preset.startswith("30%"):
            reduction = 30.0
        elif scale_preset.startswith("40%"):
            reduction = 40.0
        elif scale_preset.startswith("50%"):
            reduction = 50.0
        elif scale_preset.startswith("60%"):
            reduction = 60.0
        else:
            reduction = 0.0

        scale = 1.0 - (reduction / 100.0)
        if scale < 0.1:
            scale = 0.1
        return reduction, scale

    def _scale_and_snap(self, w, h, scale, multiple_of):
        raw_w = w * scale
        raw_h = h * scale
        snapped_w = self._snap_dim(round(raw_w), multiple_of)
        snapped_h = self._snap_dim(round(raw_h), multiple_of)
        if snapped_w > w:
            snapped_w = self._snap_dim(w, multiple_of)
        if snapped_h > h:
            snapped_h = self._snap_dim(h, multiple_of)
        return int(snapped_w), int(snapped_h), int(round(raw_w)), int(round(raw_h))

    # --- Helpers: common resolutions table ---

    def _get_common_resolution_table(self):
        return {
            # 4K and high resolutions
            (3840, 2160): "2560x1440, 1920x1080, 1280x720, 960x540, 854x480",
            (3440, 1440): "2560x1080, 2560x1440, 1920x810, 1600x720, 1280x540",
            (2560, 1440): "1920x1080, 1600x900, 1280x720, 1024x576, 960x540",
            (2560, 1080): "1920x810, 1920x800, 1600x900, 1280x720, 1024x576",
            (2048, 1152): "1920x1080, 1600x900, 1280x720, 1024x576, 960x540",

            # SDXL / Civitai-style portrait & landscape
            (1024, 1024): "896x896, 768x768, 640x640",
            (1152, 896):  "1024x800, 960x768, 896x736",
            (896, 1152):  "768x992, 672x864, 576x736",
            (1216, 832):  "1152x768, 1024x704, 896x640",
            (832, 1216):  "768x1120, 704x1024, 640x928",
            (1344, 768):  "1216x704, 1152x672, 1024x576",
            (768, 1344):  "704x1216, 672x1152, 576x1024",
            (1536, 640):  "1344x576, 1216x512, 1024x448",
            (640, 1536):  "576x1344, 512x1216, 448x1024",
            (640, 960):   "576x864, 512x768, 480x720",
            (768, 1152):  "704x1056, 640x960, 576x864",
            (800, 1200):  "704x1056, 640x960, 576x864",
            (832, 1216):  "768x1120, 704x1024, 640x928",

            # Classic 16:9 landscape
            (1920, 1080): "1600x900, 1536x864, 1280x720, 1024x576, 960x540",
            (1720, 720):  "1600x720, 1280x720, 1024x576, 960x540, 854x480",
            (1680, 1050): "1600x900, 1440x900, 1280x800, 1280x720, 1024x640",
            (1600, 900):  "1440x810, 1280x720, 1024x576",
            (1536, 864):  "1440x810, 1280x720, 1024x576",
            (1366, 768):  "1280x720, 1152x648, 1024x576",
            (1360, 768):  "1280x720, 1152x648, 1024x576",
            (1280, 720):  "1152x648, 1024x576, 960x540",
            (1270, 720):  "1152x648, 1024x576, 960x540",
            (1024, 576):  "960x540, 854x480, 768x432",
            (960, 540):   "854x480, 848x480, 800x450",
            (854, 480):   "800x450, 768x432, 640x360",
            (848, 480):   "800x450, 768x432, 640x360",
            (800, 450):   "768x432, 720x405, 640x360",
            (720, 405):   "640x360, 576x324, 512x288",
            (640, 360):   "576x324, 512x288, 426x240",
            (426, 240):   "400x225, 384x216, 320x180",

            # Square / near-square
            (2048, 2048): "1536x1536, 1024x1024, 768x768",
            (1536, 1536): "1280x1280, 1024x1024, 768x768",
            (1280, 1280): "1024x1024, 896x896, 768x768",
            (1024, 1024): "896x896, 768x768, 640x640",
            (896, 896):   "768x768, 704x704, 640x640",
            (768, 768):   "640x640, 576x576, 512x512",
            (640, 640):   "576x576, 512x512, 480x480",
            (512, 512):   "448x448, 384x384, 320x320",

            # Portrait
            (1080, 1920): "900x1600, 720x1280, 540x960",
            (720, 1280):  "640x1138, 540x960, 480x853",
            (640, 1136):  "576x1024, 540x960, 480x853",

            # 1152x896 variant
            (1152, 896):  "1024x800, 960x768, 896x672",
        }

    def _parse_res_list(self, text):
        results = []
        parts = text.split(",")
        for p in parts:
            p = p.strip()
            if "x" not in p:
                continue
            w_str, h_str = p.split("x", 1)
            try:
                w = int(w_str.strip())
                h = int(h_str.strip())
                results.append((w, h))
            except Exception:
                continue
        return results

    def _static_resolution_suggestions(self, current_w, current_h, multiple_of):
        table = self._get_common_resolution_table()
        key = (current_w, current_h)
        if key in table:
            base = f"suggested/common resolutions: {table[key]}"
        else:
            base = "suggested/common resolutions: (no static entries for this input size)"
        low_w, low_h, _, _ = self._scale_and_snap(current_w, current_h, 0.5, multiple_of)
        low = f"less common lower resolution (same aspect ratio): {low_w}x{low_h}"
        return f"{base} | {low}"

    # --- Helpers: resolution suggestion presets ---

    def _get_suggestion_target(self, w, h, multiple_of, scale_preset: str):
        preset_lower = scale_preset.lower()

        # Suggestion 4: always dynamic low VRAM (~50%)
        if "suggestion 4" in preset_lower or "very low vram" in preset_lower:
            new_w, new_h, raw_w, raw_h = self._scale_and_snap(w, h, 0.5, multiple_of)
            return new_w, new_h, raw_w, raw_h

        # For suggestion 1/2/3 we try static table first
        table = self._get_common_resolution_table()
        key = (w, h)
        suggestions = []
        if key in table:
            suggestions = self._parse_res_list(table[key])

        if "suggestion 1" in preset_lower:
            idx = 0
        elif "suggestion 2" in preset_lower:
            idx = 1
        elif "suggestion 3" in preset_lower:
            idx = 2
        else:
            idx = None

        if suggestions and idx is not None:
            if 0 <= idx < len(suggestions):
                target_w, target_h = suggestions[idx]
            else:
                target_w, target_h = suggestions[-1]

            snapped_w = self._snap_dim(target_w, multiple_of)
            snapped_h = self._snap_dim(target_h, multiple_of)
            if snapped_w > w:
                snapped_w = self._snap_dim(w, multiple_of)
            if snapped_h > h:
                snapped_h = self._snap_dim(h, multiple_of)

            raw_w = target_w
            raw_h = target_h
            return snapped_w, snapped_h, raw_w, raw_h

        # No static suggestions: dynamic fallbacks
        if "suggestion 1" in preset_lower:
            scale = 0.8
        elif "suggestion 2" in preset_lower:
            scale = 0.7
        elif "suggestion 3" in preset_lower:
            scale = 0.6
        else:
            scale = 0.5

        new_w, new_h, raw_w, raw_h = self._scale_and_snap(w, h, scale, multiple_of)
        return new_w, new_h, raw_w, raw_h

    # --- main ---

    def calc(self, image, model_profile, scale_preset):
        h = image.shape[1]
        w = image.shape[2]

        if h <= 0 or w <= 0:
            info = "Invalid image size – cannot calculate."
            return (image, int(w), int(h), info)

        multiple_of, profile_label = self._profile_to_multiple(model_profile)
        is_suggestion = scale_preset.startswith("Resolution suggestion")

        if is_suggestion:
            new_w, new_h, raw_w, raw_h = self._get_suggestion_target(
                w, h, multiple_of, scale_preset
            )
            if w > 0:
                scale = new_w / float(w)
            else:
                scale = 1.0
            reduction_percent = (1.0 - scale) * 100.0
        else:
            reduction_percent, scale = self._scale_from_percentage_preset(scale_preset)
            new_w, new_h, raw_w, raw_h = self._scale_and_snap(w, h, scale, multiple_of)

        simple_preset = scale_preset.split(" (")[0]
        suggestions_info = self._static_resolution_suggestions(w, h, multiple_of)

        lines = []
        lines.append(f"multiple_of: {multiple_of} ({profile_label})")
        lines.append(
            f"scale_preset={simple_preset}, reduction≈{reduction_percent:.1f}% (scale≈{scale:.4f})"
        )
        lines.append(f"input image: {w}x{h}")
        lines.append(f"result: raw {raw_w}x{raw_h} -> snapped {new_w}x{new_h}")
        lines.append(suggestions_info)

        info = " | ".join(lines)

        return (image, int(new_w), int(new_h), info)


NODE_CLASS_MAPPINGS = {
    "TuonoResolutionSuggestDownscale": TuonoResolutionSuggestDownscale,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "TuonoResolutionSuggestDownscale": "Resolution Suggest & Downscale",
}
