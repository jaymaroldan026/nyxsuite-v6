MODEL_ALIASES = {
    "Debbie": "Debbie",
    "debbie": "Debbie",
    "Deborah": "Debbie",
    "deborah": "Debbie",
    "Debora": "Debbie",
    "debora": "Debbie",
}

BITMOJI_SELECTORS = {

    "entry": {
        "bitmoji_page": "https://www.bitmoji.com/home/",
        "login_with_snapchat": "button:has-text('Log In with Snapchat')",
        "oauth_continue": "button:has-text('Continue'), button:has-text('Agree')"
    },

    "gender": {
        "female": ".gender-select button:has(.gender-icon.female), .gender-select button:nth-of-type(2), button[aria-label='Female avatar'], button[aria-label='Female Avatar'], button:has(.gender-icon.female)"
    },

    "save": {
        "save_button": "div.save-button:has(span:has-text('Save'))",
        "confirm_button": "button[type='submit']:has-text('Save')"
    },

    "categories": {
        "icons": ".top-category-container, .category-item",
        "skin_tone": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M12.06 30.925')]]",
        "hair": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M56.08 47.49')]]",
        "eyes": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M62.744 34.37')]]",
        "eyebrows": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M21.33 33.337')]]",
        "nose": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M32.997 9')]]",
        "jaw": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M57.175 32.402')]]",
        "lips": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M7.16 38.42')]]",
        "body_type": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M32.994 4.29')]]",
        "earrings": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M2.054 7.728')]]",
        "makeup": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M57.7 18.21')]]",
        "tops": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M60.727 23.579')]]",
        "bottoms": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M35 8c-4.232')]]",
        "dresses": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M11.132 12.8')]]",
        "footwear": "xpath=//div[contains(@class,'category-item') and .//*[name()='path' and contains(@d,'M44.387 17.735')]]"
    },

    "subcategories": {
        "hair_color": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M33.44 7.88')]]",
        "hair_style": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M56.08 47.49')]]",
        "hair_treatment": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M33 12.43')]]",
        "eye_shape": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M62.744 34.37')]]",
        "eye_lashes": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M52.55 31')]]",
        "eye_color": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M33.44 7.88')]]",
        "chest_size": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M65.64 46.89')]]",
        "paired_earring": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M2.054 7.728')]]",
        "eyeshadow": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M57.7 18.21')]]",
        "blush": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M25.27 30.87')]]",
        "lipstick": "xpath=//div[contains(@class,'subcategory') and .//*[name()='path' and contains(@d,'M26.57 26.623')]]"
    },

    "items": {
        "skin_tone": ".swatch-trait-preview .container[tabindex='0']",
        "hair": ".swatch-trait-preview .container[tabindex='0'], .head-trait-container[tabindex='0']",
        "fallback": ".avatar-builder-category-container [tabindex='0'], .trait-preview [tabindex='0'], div[tabindex='0']",
        "random_earrings": [
            "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=6')] and .//img[contains(@src,'earringR_lobe1=6')]]",
            "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=14')] and .//img[contains(@src,'earringR_lobe1=14')]]",
            "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
            "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=4')] and .//img[contains(@src,'earringR_lobe1=4')]]",
            "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=7')] and .//img[contains(@src,'earringR_lobe1=7')]]",
            "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=3')] and .//img[contains(@src,'earringR_lobe1=3')]]"
        ]
    },

    "traits": {
        "clea_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f6b892']]",
        "clea_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=2039326')]]",
        "clea_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=1321')]]",
        "clea_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eye?') and contains(@src,'eye=1613')]]",
        "clea_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2280')]]",
        "clea_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "clea_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1494')]]",
        "clea_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1409')]]",
        "clea_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "clea_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "clea_paired_earring": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
        "clea_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fca087']]",
        "clea_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff94ab']]",
        "clea_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff713c']]",
        "olivia_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f6b892']]",
        "olivia_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=3613466')]]",
        "olivia_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=2945')]]",
        "olivia_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=5978405')]]",
        "olivia_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eye?') and contains(@src,'eye=1613')]]",
        "olivia_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2280')]]",
        "olivia_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "olivia_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1494')]]",
        "olivia_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1419')]]",
        "olivia_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "olivia_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "olivia_paired_earring": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
        "olivia_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fca087']]",
        "olivia_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff94ab']]",
        "olivia_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff713c']]",
        "emily_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f6b892']]",
        "emily_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8700')]]",
        "emily_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=2039326')]]",
        "emily_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1611') and contains(@src,'eyelash=-1')]]",
        "emily_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1611') and contains(@src,'eyelash=2280')]]",
        "emily_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "emily_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1574')]]",
        "emily_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1494')]]",
        "emily_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1410')]]",
        "emily_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "emily_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "emily_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=14')] and .//img[contains(@src,'earringR_lobe1=14')]]",
        "emily_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#292c2c']]",
        "emily_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff94ab']]",
        "emily_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff70a7']]",
        "debbie_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f1ac88']]",
        "debbie_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8750')]]",
        "debbie_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=3613466')]]",
        "debbie_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=5978405')]]",
        "debbie_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eye?') and contains(@src,'eye=1613')]]",
        "debbie_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eye?') and contains(@src,'eyelash=2281')]]",
        "debbie_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "debbie_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1575')]]",
        "debbie_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1492')]]",
        "debbie_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1411')]]",
        "debbie_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "debbie_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "debbie_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
        "debbie_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#dc5854']]",
        "debbie_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff94ab']]",
        "debbie_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#cf2c62']]",
        "alicia_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fab787']]",
        "alicia_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8700')]]",
        "alicia_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=6632737')]]",
        "alicia_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=5978405')]]",
        "alicia_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1613')]]",
        "alicia_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2281')]]",
        "alicia_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#5b341c']]",
        "alicia_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=3045')]]",
        "alicia_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1492')]]",
        "alicia_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1409')]]",
        "alicia_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "alicia_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "alicia_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=14')] and .//img[contains(@src,'earringR_lobe1=14')]]",
        "alicia_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#292c2c']]",
        "alicia_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fd438a']]",
        "alicia_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#cf2c62']]",
        "tessa_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f1ac88']]",
        "tessa_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8700')]]",
        "tessa_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=12688481')]]",
        "tessa_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=3545142')]]",
        "tessa_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1622')]]",
        "tessa_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2281')]]",
        "tessa_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "tessa_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1575')]]",
        "tessa_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1492')]]",
        "tessa_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1413')]]",
        "tessa_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "tessa_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "tessa_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
        "tessa_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#dc5854']]",
        "tessa_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fd438a']]",
        "tessa_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#e54f29' and @rx='50%' and @ry='50%']]",
        "chloe_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fab787']]",
        "chloe_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8701')]]",
        "chloe_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=6632737')]]",
        "chloe_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1619')]]",
        "chloe_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2281')]]",
        "chloe_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "chloe_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1575')]]",
        "chloe_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1492')]]",
        "chloe_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1410')]]",
        "chloe_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "chloe_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "chloe_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
        "chloe_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fca087']]",
        "chloe_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fd438a']]",
        "chloe_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff70a7' and @rx='50%' and @ry='50%']]",
        "willow_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f6b892']]",
        "willow_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8721')]]",
        "willow_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=7416175')]]",
        "willow_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=14361701')]]",
        "willow_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eye?') and contains(@src,'eye=1613')]]",
        "willow_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eye?') and contains(@src,'eyelash=2281')]]",
        "willow_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "willow_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1575')]]",
        "willow_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1491')]]",
        "willow_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1409')]]",
        "willow_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "willow_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "willow_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=5')] and .//img[contains(@src,'earringR_lobe1=5')]]",
        "willow_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fca087']]",
        "willow_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fd438a']]",
        "willow_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff713c' and @rx='50%' and @ry='50%']]",
        "jade_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f1ac88']]",
        "jade_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8701')]]",
        "jade_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=8672042')]]",
        "jade_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=13735731')]]",
        "jade_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1613')]]",
        "jade_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2281')]]",
        "jade_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#5b341c']]",
        "jade_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1575')]]",
        "jade_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1494')]]",
        "jade_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1409')]]",
        "jade_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "jade_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "jade_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=14')] and .//img[contains(@src,'earringR_lobe1=14')]]",
        "jade_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fca087']]",
        "jade_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ffa5a8']]",
        "jade_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff7292' and @rx='50%' and @ry='50%']]",
        "lizzie_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f6b892']]",
        "lizzie_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=1320')]]",
        "lizzie_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=15714429')]]",
        "lizzie_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=10513945')]]",
        "lizzie_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1619')]]",
        "lizzie_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2281')]]",
        "lizzie_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#465d6f']]",
        "lizzie_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1574')]]",
        "lizzie_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1494')]]",
        "lizzie_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1407')]]",
        "lizzie_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "lizzie_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "lizzie_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=6')] and .//img[contains(@src,'earringR_lobe1=6')]]",
        "lizzie_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#dc5854']]",
        "lizzie_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#c64e45']]",
        "lizzie_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff70a7' and @rx='50%' and @ry='50%']]",
        "nina_skin_tone": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f6b892']]",
        "nina_hair_style": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair=8700')]]",
        "nina_hair_color": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_tone=7677223')]]",
        "nina_hair_treatment": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'hair_treatment_tone=3545142')]]",
        "nina_eye_shape": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eye=1613')]]",
        "nina_eye_lashes": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'eyelash=2280')]]",
        "nina_eye_color": "xpath=//*[name()='svg' and contains(@class,'iris') and @tabindex='0' and .//*[name()='circle' and @fill='#111111']]",
        "nina_eyebrows": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/eyebrows?') and contains(@src,'brow=1574')]]",
        "nina_nose": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/nose?') and contains(@src,'nose=1493')]]",
        "nina_jaw": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/jaw?') and contains(@src,'jaw=1409')]]",
        "nina_lips": "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/mouth?') and contains(@src,'mouth=2341')]]",
        "nina_chest_size": "xpath=//div[@tabindex='0' and @value='1' and .//img[contains(@src,'breast=1')]]",
        "nina_earrings": "xpath=//div[contains(@class,'facial-feature-wrapper') and @tabindex='0' and .//img[contains(@src,'earringL_lobe1=6')] and .//img[contains(@src,'earringR_lobe1=6')]]",
        "nina_eyeshadow": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#fca087']]",
        "nina_blush": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#f8b6c6']]",
        "nina_lipstick": "xpath=//div[contains(@class,'container') and @tabindex='0' and .//*[name()='rect' and @fill='#ff713c' and @rx='50%' and @ry='50%']]"
    },

    "outfits": {
        "tops": [
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=699')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=964')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=698')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=183')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=949')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=532')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=92')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=429')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/top?') and contains(@src,'top=209')]]"
        ],
        "bottoms": [
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=948')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=922')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=911')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=240')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=356')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=965')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=287')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/bottom?') and contains(@src,'bottom=788')]]"
        ],
        "dresses": [
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/one_piece?') and contains(@src,'top=966') and contains(@src,'bottom=966')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/one_piece?') and contains(@src,'top=632') and contains(@src,'bottom=632')]]"
        ],
        "sandals": [
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=969')]]",
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=292')]]"
        ],
        "sneakers": [
            "xpath=//div[contains(@class,'mix-and-match-container') and @tabindex='0' and .//img[contains(@src,'/avatar/footwear?') and contains(@src,'footwear=470')]]"
        ]
    },

    "random_hair": {
        "Alicia": [
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=1321')]]",
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=1320')]]",
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=8700')]]",
        ],
        "Debbie": [
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=8750')]]",
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=8756')]]",
        ],
        "Jade": [
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=1320')]]",
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=8701')]]",
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=2945')]]",
            "xpath=//div[contains(@class,'head-trait-container') and @tabindex='0' and .//img[contains(@src,'/avatar/hair?') and contains(@src,'hair=3083')]]",
        ],
    },

    "models": {
        "Clea": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.clea_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.clea_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.clea_hair_color"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.clea_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.clea_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.clea_eye_color"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.clea_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.clea_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.clea_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.clea_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "paired_earring",
                    "selector": "traits.clea_paired_earring"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.clea_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.clea_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.clea_lipstick"
                }
            ]
        },
        "Olivia": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.olivia_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.olivia_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.olivia_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.olivia_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.olivia_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.olivia_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.olivia_eye_color"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.olivia_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.olivia_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.olivia_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.olivia_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "paired_earring",
                    "selector": "traits.olivia_paired_earring"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.olivia_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.olivia_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.olivia_lipstick"
                }
            ]
        },
        "Alicia": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.alicia_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.alicia_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.alicia_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.alicia_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.alicia_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.alicia_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.alicia_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.alicia_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.alicia_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.alicia_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.alicia_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.alicia_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.alicia_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.alicia_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.alicia_lipstick"
                }
            ]
        },
        "Willow": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.willow_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.willow_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.willow_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.willow_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.willow_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.willow_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.willow_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.willow_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.willow_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.willow_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.willow_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.willow_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.willow_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.willow_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.willow_lipstick"
                }
            ]
        },
        "Jade": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.jade_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.jade_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.jade_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.jade_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.jade_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.jade_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.jade_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.jade_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.jade_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.jade_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.jade_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.jade_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.jade_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.jade_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.jade_lipstick"
                }
            ]
        },
        "Nina": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.nina_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.nina_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.nina_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.nina_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.nina_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.nina_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.nina_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.nina_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.nina_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.nina_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.nina_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.nina_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.nina_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.nina_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.nina_lipstick"
                }
            ]
        },
        "Chloe": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.chloe_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.chloe_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.chloe_hair_color"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.chloe_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.chloe_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.chloe_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.chloe_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.chloe_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.chloe_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.chloe_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.chloe_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.chloe_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.chloe_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.chloe_lipstick"
                }
            ]
        },
        "Debbie": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.debbie_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.debbie_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.debbie_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.debbie_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.debbie_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.debbie_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.debbie_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.debbie_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.debbie_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.debbie_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.debbie_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.debbie_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.debbie_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.debbie_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.debbie_lipstick"
                }
            ]
        },
        "Lizzie": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.lizzie_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.lizzie_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.lizzie_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.lizzie_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.lizzie_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.lizzie_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.lizzie_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.lizzie_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.lizzie_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.lizzie_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.lizzie_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.lizzie_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.lizzie_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.lizzie_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.lizzie_lipstick"
                }
            ]
        },
        "Tessa": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.tessa_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.tessa_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.tessa_hair_color"
                },
                {
                    "step": "open_hair_treatment",
                    "selector": "subcategories.hair_treatment"
                },
                {
                    "step": "hair_treatment",
                    "selector": "traits.tessa_hair_treatment"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.tessa_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.tessa_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.tessa_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.tessa_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.tessa_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.tessa_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.tessa_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.tessa_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.tessa_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.tessa_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.tessa_lipstick"
                }
            ]
        },
        "Emily": {
            "face": [
                {
                    "step": "open_skin",
                    "selector": "categories.skin_tone"
                },
                {
                    "step": "skin_tone",
                    "selector": "traits.emily_skin_tone"
                },
                {
                    "step": "open_hair",
                    "selector": "categories.hair"
                },
                {
                    "step": "open_hair_style",
                    "selector": "subcategories.hair_style"
                },
                {
                    "step": "hair_style",
                    "selector": "traits.emily_hair_style"
                },
                {
                    "step": "open_hair_color",
                    "selector": "subcategories.hair_color"
                },
                {
                    "step": "hair_color",
                    "selector": "traits.emily_hair_color"
                },
                {
                    "step": "open_eyes",
                    "selector": "categories.eyes"
                },
                {
                    "step": "open_eye_shape",
                    "selector": "subcategories.eye_shape"
                },
                {
                    "step": "eye_shape",
                    "selector": "traits.emily_eye_shape"
                },
                {
                    "step": "open_eye_lashes",
                    "selector": "subcategories.eye_lashes"
                },
                {
                    "step": "eye_lashes",
                    "selector": "traits.emily_eye_lashes"
                },
                {
                    "step": "open_eye_color",
                    "selector": "subcategories.eye_color"
                },
                {
                    "step": "eye_color",
                    "selector": "traits.emily_eye_color"
                },
                {
                    "step": "open_eyebrows",
                    "selector": "categories.eyebrows"
                },
                {
                    "step": "eyebrows",
                    "selector": "traits.emily_eyebrows"
                },
                {
                    "step": "open_nose",
                    "selector": "categories.nose"
                },
                {
                    "step": "nose",
                    "selector": "traits.emily_nose"
                },
                {
                    "step": "open_jaw",
                    "selector": "categories.jaw"
                },
                {
                    "step": "jaw",
                    "selector": "traits.emily_jaw"
                },
                {
                    "step": "open_lips",
                    "selector": "categories.lips"
                },
                {
                    "step": "lips",
                    "selector": "traits.emily_lips"
                },
                {
                    "step": "open_body_type",
                    "selector": "categories.body_type"
                },
                {
                    "step": "open_chest_size",
                    "selector": "subcategories.chest_size"
                },
                {
                    "step": "chest_size",
                    "selector": "traits.emily_chest_size"
                },
                {
                    "step": "open_earrings",
                    "selector": "categories.earrings"
                },
                {
                    "step": "open_paired_earring",
                    "selector": "subcategories.paired_earring"
                },
                {
                    "step": "earrings",
                    "selector": "traits.random_earrings"
                },
                {
                    "step": "open_makeup",
                    "selector": "categories.makeup"
                },
                {
                    "step": "open_eyeshadow",
                    "selector": "subcategories.eyeshadow"
                },
                {
                    "step": "eyeshadow",
                    "selector": "traits.emily_eyeshadow"
                },
                {
                    "step": "open_blush",
                    "selector": "subcategories.blush"
                },
                {
                    "step": "blush",
                    "selector": "traits.emily_blush"
                },
                {
                    "step": "open_lipstick",
                    "selector": "subcategories.lipstick"
                },
                {
                    "step": "lipstick",
                    "selector": "traits.emily_lipstick"
                }
            ]
        },
    }
}
