import streamlit as st
import streamlit.components.v1 as components
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import threading
import re
import json
import time
import io
import base64
from pathlib import Path

from full_sensitivity_analysis import (
    fetch_component_selenium,
    run_full_sensitivity_analysis_selenium,
    run_parameter_explorer_selenium,
    run_additivity_check_selenium,
    run_robustness_analysis_selenium,
    run_full_nonlinearity_scan_selenium,
    _selenium_login,
    parse_elca_url,
    AnalysisStopped,
)


# Element/module names on eLCA are free text with no built-in translation.
# Used by _translate_element_name() / _display_label() for display only;
# never affects the underlying cache/lookup key. Unlisted names stay German.
_ELEMENT_NAME_TRANSLATIONS = {
    "Bekleidung Holz": "Wood cladding",
    "Brettschichtholz": "Glued laminated timber (glulam)",
    "Dämmung / Zementestrich / Linolium": "Insulation / cement screed / linoleum",
    "Zementestrich - IWM": "Cement screed - IWM",
    "Estrich - Dämmung": "Screed - insulation",
    "Extensivbegrünung": "Extensive green roof",
    "Fassadenfarbe_2-fach_G": "Facade paint, 2-coat",
    "Flachdach unbelüftet / Stb.": "Unventilated flat roof / reinforced concrete",
    "Fundamentplatte Stb. / unterseitig gedämmt / Foamglas": "Foundation slab, reinforced concrete / insulated underside / Foamglas",
    "GK Platte doppelt / Anstrich / Folie": "Double-layer gypsum board / paint / vapour barrier",
    "GK_12,5mm_doppelt_beplankt_Anstrich_gespachtelt": "12.5 mm double-layer gypsum board, painted, joint-filled",
    "G_Bodenplatte_Stahlbeton-Ortbauweise_C25/30_250mm_2%": "Cast-in-place reinforced concrete foundation slab, C25/30, 250 mm",
    "G_Voranstrich_Kunstharz_5mm": "Synthetic resin primer, 5mm",
    "Gipskarton abgehangen": "Suspended gypsum board",
    "Gipskarton verspachtelt": "Joint-filled gypsum board",
    "Gipskartonplatte_12,5mm_Kleber_g": "Gypsum board 12.5mm, adhesive-fixed",
    "Holzkasten mit Schüttung": "Timber box element with loose fill",
    "Holzrahmen - Dämmung": "Timber frame - insulation",
    "Holzrahmen belüftet - Blech": "Timber frame, ventilated - sheet metal",
    "Holzschalung_Lattung_Konstruktionsvollholz_je 24mm_Unterspannbahn_Mineralwolle_120mm_g":
        "Timber cladding, battens, structural timber, underlay membrane, 120 mm mineral wool",
    "Kalksandstein 240mm": "Sand-lime brick, 240mm",
    "Kalksandstein - Bundesverband Kalksandstein": "Sand-lime brick - Bundesverband Kalksandstein",
    "Massivholz": "Solid timber",
    "Mauerziegel_270mm_E": "Clay brick, 270mm",
    "Mauerziegel_340mm_E": "Clay brick, 340mm",
    "Mauerziegel Durchschnitt - Poroton": "Clay brick, average - Poroton",
    "Metallständer_75mm mit Dämmung": "Metal stud, 75mm, with insulation",
    "Metallständer_100mm mit Dämmung": "Metal stud, 100mm, with insulation",
    "Parkett - Estrich": "Parquet - screed",
    "Porenbeton-Dämmplatte_25mm_geklebt_Kalkputz_E": "Aerated-concrete insulation board 25mm, glued, lime plaster",
    "Putz Gips / 20mm": "Gypsum plaster / 20mm",
    "Schiefer_E": "Slate",
    "Schwimmender Estrich": "Floating screed",
    "Sparrendach / Dämmung / Dampfbremse": "Pitched roof with rafters / insulation / vapour barrier",
    "Stahlbeton": "Reinforced concrete",
    "Steinzeugfliesen_unglasiert_inkl. Kleber_g": "Unglazed stoneware tiles, incl. adhesive",
    "WDVS_Mineralwolle_120mm_Dekorputz_G": "ETICS, mineral wool 120mm, decorative render",
    "Ziegeldeckung / Lattung": "Roof tiling / battens",
    "Innenwand / Holzständerwerk / OSB, GK": "Interior wall / timber stud frame / OSB, gypsum board",
    "Außenwand Gaube / Holzrahmenbau / Schieferverkleidung": "Exterior wall, dormer / timber frame construction / slate cladding",
    "Geschossdecke Holzrahmen/Holztafel, mit Abhängung, nass, ohne Schüttung":
        "Intermediate floor, timber frame/timber panel, with suspended ceiling, wet, without loose fill",
    "Innenwand / Kalksandstein / Gipsputz": "Interior wall / sand-lime brick / gypsum plaster",
    "Innenwand / Gipskarton / doppelbeplankt": "Interior wall / gypsum board / double-layered",
    "Sichtbalken": "Exposed beam",
    "Geschossdecke Sichtbalken, nass, mit Schüttung": "Intermediate floor, exposed beam, wet, with loose fill",
    "Sparrendach unbelüftet / Zwischensparrendämmung / Ziegel": "Unventilated rafter roof / between-rafter insulation / roof tiles",
    "Schilfrohrdämmung - Lehmputz": "Reed insulation - clay plaster",
    "Außenwand / Stampflehm / Lehmputz": "Exterior wall / rammed earth / clay plaster",
    "Geschossdecke / Stb. / schw. Estrich": "Intermediate floor / reinforced concrete / floating screed",
    "Stahlbetondecke 18cm": "Reinforced concrete slab, 18cm",
    "m²_Fenster / Isoglas 2-Scheiben / Alurahmen": "Window / double-glazing / aluminum frame (per m²)",
    "G_Stahlbeton-Ortbauweise_C25/30_100mm_1%": "Cast-in-place reinforced concrete, C25/30, 100mm",
    "Heizkörper Typ 22 h=300mm": "Radiator, type 22, height 300mm",
    "Fernwärme Übergabestation (Roe)": "District heating transfer station",
    "Gründach extensiv / Holzmassivbau": "Extensive green roof / solid timber construction",
    "Bodenplatte / unterseitig gedämmt / Perlite / Estrich": "Ground slab / insulated underside / perlite / screed",
    "Bodenplatte / oberseitig gedämmt / Sand / schw. Estrich": "Ground slab / insulated topside / sand / floating screed",
    "Außenwand / Holzrahmenbau / verputzt": "Exterior wall / timber frame construction / plastered",
    "Gründach extensiv / Stb.": "Extensive green roof / reinforced concrete",
    "G_Natursteinplatte_inkl. Kleber": "Natural stone slab, incl. adhesive",
    "Gasbrennwertkessel (Roe)": "Gas condensing boiler",
    "Geschossdecke Holzmassivbau, mit Abhängung, nass, mit Schüttung":
        "Intermediate floor, solid timber construction, with suspended ceiling, wet, with loose fill",
    "Außenwand / einschaliges Mauerwerk / WDVS / Innenfliesen": "Exterior wall / single-leaf masonry / ETICS / interior tiling",
    "Bodenplatte / unterseitig gedämmt / Estrich / Linolium": "Ground slab / insulated underside / screed / linoleum",
    "Flachdach / Stb.": "Flat roof / reinforced concrete",
    "Terrassenausbau": "Terrace construction",
    "Terrassendach / Stb.": "Terrace roof / reinforced concrete",
    "Erzeuger /Verteilung / Übergabe": "Generation / distribution / transfer",
    "Hohlkastendecke / Konstruktionsvollholz / Splittfüllung / Parkett":
        "Hollow box floor / structural solid timber / chippings fill / parquet",
    "Außenwand / einschaliges Mauerwerk / Innendämmung": "Exterior wall / single-leaf masonry / interior insulation",
    "Bodenplatte / unterseitig gedämmt / schw. Estrich": "Ground slab / insulated underside / floating screed",
    "Bodenplatte / oberseitig gedämmt / Estrich / Linolium": "Ground slab / insulated topside / screed / linoleum",
    "Bodenplatte / unterseitig gedämmt / Holzfußboden": "Ground slab / insulated underside / wood flooring",
    "Außenwand / einschaliges Mauerwerk / erdberührt": "Exterior wall / single-leaf masonry / in ground contact",
    "Außenwand / zweischaliges Mauerwerk / hinterlüftet": "Exterior wall / double-leaf masonry / ventilated cavity",
    "Außenwand / zweischaliges Mauerwerk / Kerndämmung": "Exterior wall / double-leaf masonry / core insulation",
    "Innenwand / Massivholzbau / GK": "Interior wall / solid timber construction / gypsum board",
    "Außenwand / Holzrahmenbau / Holzverkleidung": "Exterior wall / timber frame construction / wood cladding",
    "Außenwand / Stb. / Außendämmung / verputzt": "Exterior wall / reinforced concrete / external insulation / plastered",
    "Außenwand / Stb. / Außendämmung / erdberührt": "Exterior wall / reinforced concrete / external insulation / in ground contact",
    "Außenwand / einschaliges Mauerwerk / WDVS / verputzt": "Exterior wall / single-leaf masonry / ETICS / plastered",
    "Außenwand / einschaliges Mauerwerk / WDVS mit Fenster": "Exterior wall / single-leaf masonry / ETICS with window",
    "Außenwand / Holzmassivbau / Holzverkleidung": "Exterior wall / solid timber construction / wood cladding",
    "Außenwand / Holzrahmenbau / Baustroh / Lehmputz": "Exterior wall / timber frame construction / straw bale / clay plaster",
    "Geschossdecke / Holzrahmenbau / schw. Estrich": "Intermediate floor / timber frame construction / floating screed",
    "Kellerdecke / Stb. / unterseitig gedämmt / schw. Estrich": "Basement ceiling / reinforced concrete / insulated underside / floating screed",
    "Kellerdecke Stb. / oberseitig gedämmt / schw. Estrich": "Basement ceiling, reinforced concrete / insulated topside / floating screed",
    "Kellerdecke / Stb. / oberseitig gedämmt / schw. Estrich": "Basement ceiling / reinforced concrete / insulated topside / floating screed",
    "Flachdach unbelüftet, begehbar / Stb.": "Unventilated flat roof, walkable / reinforced concrete",
    "Flachdach unbelüftet / Holzrahmenbau": "Unventilated flat roof / timber frame construction",
    "Stb. / Warmdach": "Reinforced concrete / warm roof",
    "Wärmeerzeugungsanlage Gasbrennwertkessel": "Heat generation system, gas condensing boiler",
    "Lufttechnische Anlage / RLT- Anlage": "Ventilation system / air handling unit",
    "Starkstromanlagen / Elektroinstallation Steckdosen": "High-voltage systems / electrical wiring, power outlets",
    "Starkstromanlagen / Elektroinstallation Beleuchtung": "High-voltage systems / electrical wiring, lighting",
    "Lüfter WRG 1000m³/h": "Fan with heat recovery, 1000m³/h",
    "Lüftungskanal_1m b:800 h:400 d: 1mm": "Ventilation duct, 1m, w:800 h:400 t:1mm",
    "Kabel 3x 1m (Roe)": "Cable, 3x, 1m",
    "1 Stück Steckdose (Roe)": "Power outlet, 1 piece",
    "Leuchtstofflampe 1Stück 2x18Watt EVG(Roe)": "Fluorescent lamp, 1 piece, 2x18W electronic ballast",
    "Lichtschalter 1Stück (Roe)": "Light switch, 1 piece",
    "Verkabelung Beleuchtung 1m (Roe)": "Lighting wiring, 1m",
    "E_Zementestrich_60mm_EPS_20mm_30mm": "Cement screed 60mm, EPS 20mm/30mm",
    "Bodenplatte_Stb-Ortbauweise_C20/25_400mm_2%": "Ground slab, cast-in-place reinforced concrete, C20/25, 400mm",
    "G_XPS_300mm_Beton_20/25_150mm": "XPS 300mm, concrete C20/25, 150mm",
    "oberseitige Dämmung / Estrich / Linolium": "Topside insulation / screed / linoleum",
    "Fundamentplatte Stb. / Dränschicht": "Foundation slab, reinforced concrete / drainage layer",
    "Holzfußboden / Linolium": "Wood flooring / linoleum",
    "Fundamentplatte / unterseitige Dämmung / Dränschicht": "Foundation slab / underside insulation / drainage layer",
    "G_XPS_260mm": "XPS 260mm",
    "Gips-Putz/Anstrich": "Gypsum plaster / paint",
    "IBO_AWm_01_Stb 18cm 2% Armierung": "IBO_AWm_01, reinforced concrete 18cm, 2% reinforcement",
    "IBO_AWM_01_Dämmung EPS /035/ 32cm": "IBO_AWM_01, EPS insulation /035/, 32cm",
    "Kalk Innenputz": "Lime interior plaster",
    "Kalksandstein": "Sand-lime brick",
    "Dämmung - Abdichtung": "Insulation - sealing",
    "Kalksandstein 24cm": "Sand-lime brick, 24cm",
    "MW / Kerndämmung": "Mineral wool / core insulation",
    "WDVS (Roe)": "ETICS (Roe)",
    "Stück_Fenster_1,6m² / Isoglas 2-Scheiben / Alurahmen": "Window, 1.6m² / double-glazing / aluminum frame",
    "Gipskarton - Dämmung": "Gypsum board - insulation",
    "Massivholz - Dämmung": "Solid timber - insulation",
    "Vollschalung hinterlüftet": "Solid boarding, ventilated",
    "Gipskartonplatte gespachtelt - Dampfsperre": "Gypsum board, joint-filled - vapour barrier",
    "Strohballen - Holz": "Straw bale - timber",
    "Putz": "Plaster",
    "Heizungsrohr 1 m + Dämmung (Roe)": "Heating pipe, 1m + insulation",
    "Heizkörper Typ 22 h=600mm (Roe)": "Radiator, type 22, height 600mm",
}


def _loaded_element_text(name):
    """For the 'Loaded: ...' message specifically: shows the English
    translation with the original German name alongside in parentheses (so
    it's still identifiable against eLCA itself)"""
    translated = _translate_element_name(name)
    if translated != name.strip():
        return f"{translated} ({name.strip()})"
    return translated

# Matches "<name> (<n>)" at the start of a parameter label, same pattern
# used to build the label in fetch_component_selenium
_ELEMENT_NAME_RE = re.compile(r"^(.*?)(\s*\(\d+\))(\s*-.*)?$")


_MATERIAL_NAME_TRANSLATIONS = {
    "eLCA Luftschicht": "eLCA air gap",
    "Blanke Kupfer-Hausinstallationsrohre": "Bare copper plumbing pipes",
    "Heizkörper Typ 22 h=600mm": "Radiator, type 22, height 600mm",
    "Aluminium Blech (2005)": "Aluminium sheet metal (2005)",
    "Linoleum-Bodenbelag": "Linoleum flooring",
    "Holzfaserdämmplatte Mix (Trockenverfahren)": "Wood fibre insulation board, mixed (dry process)",
    "Organische Armierung - VDL": "Organic reinforcement mesh - VDL",
    "Armierungsputzmörtel - IWM": "Reinforcement render mortar - IWM",
    "Armiermasse Armatop AKS - Alsecco": "Reinforcement compound Armatop AKS - Alsecco",
    "Silikatputz - VDL": "Silicate render - VDL",
    "EPS-Hartschaum (Styropor ®) für Decken/Böden und als Perimeterdämmung B/P-035": "EPS rigid foam (Styropor®) for ceilings/floors and as perimeter insulation B/P-035",
    "EPS-Hartschaum (Styropor ®) für Decken/Böden und als Perimeterdämmung B/P-040": "EPS rigid foam (Styropor®) for ceilings/floors and as perimeter insulation B/P-040",
    "Kunstharzputz - VDL": "Synthetic resin render - VDL",
    "Glasarmierungsgitter - Vitrulan": "Glass reinforcement mesh - Vitrulan",
    "Gipskartonplatte": "Gypsum board",
    "Porenbeton-Dämmplatte - Multipor": "Aerated-concrete insulation board - Multipor",
    "Gipskarton verspachtelt - Dispersionsfarbe": "Joint-filled gypsum board - dispersion paint",
    "Estrichmörtel-Calciumsulfatestrich": "Calcium sulfate screed mortar",
    "Zementestrich - IWM": "Cement screed - IWM",
    "Mauerziegel": "Clay brick",
    "Durchschnitt": "average",
    "Kupferrohr blank": "Bare copper pipe",
}


def _translate_material_names(text):
    for de, en in _MATERIAL_NAME_TRANSLATIONS.items():
        text = text.replace(de, en)
    return text


def _translate_element_name(name):
    return _ELEMENT_NAME_TRANSLATIONS.get(name.strip(), name)


def _display_label(label):
    if not isinstance(label, str):
        return label
    m = _ELEMENT_NAME_RE.match(label)
    if m:
        name, num_suffix, rest = m.group(1).strip(), m.group(2) or "", m.group(3) or ""
        return f"{_translate_element_name(name)}{num_suffix}{_translate_material_names(rest)}"
    if " - " in label:
        name, rest = label.split(" - ", 1)
        return f"{_translate_element_name(name.strip())} - {_translate_material_names(rest)}"
    return _translate_element_name(label)


def analyze_shape(detail_df, linearity_threshold_pct_of_range=5.0):
    """Computes relative range, linearity, and whether the response is a discrete
    step rather than a gradual trend.

    Fit quality is measured against the curve's own range (gwp_range), not the
    component's baseline GWP, so small-effect parameters are not misclassified
    as linear. max_residual_pct remains baseline-relative for interpretation.

    Returns: relative_range, is_linear, is_stepwise, max_residual_pct,
    max_residual_pct_of_range, gwp_range, baseline_gwp. None if insufficient data.
    """
    df = detail_df.dropna(subset=["GWP"]).sort_values("Parameter Value")
    if len(df) < 2:
        return None

    x = df["Parameter Value"].values
    y = df["GWP"].values

    baseline_row = df.iloc[(df["Parameter Value"] - 1.0).abs().argsort()[:1]]
    baseline_gwp = baseline_row["GWP"].values[0]

    gwp_range = y.max() - y.min()
    relative_range = (gwp_range / baseline_gwp) * 100 if baseline_gwp else 0.0

    if len(x) >= 2:
        coeffs = np.polyfit(x, y, 1)
        y_linear = np.polyval(coeffs, x)
        residuals = np.abs(y - y_linear)
        max_residual_pct = (residuals.max() / baseline_gwp) * 100 if baseline_gwp else 0.0
        max_residual_pct_of_range = (residuals.max() / gwp_range * 100) if gwp_range else 0.0
    else:
        max_residual_pct = 0.0
        max_residual_pct_of_range = 0.0
    is_linear = max_residual_pct_of_range < linearity_threshold_pct_of_range

    step_jumps = np.abs(np.diff(y)) if len(y) > 1 else np.array([0.0])
    max_jump = step_jumps.max() if len(step_jumps) else 0.0
    if gwp_range > 0 and len(step_jumps):
        # Stepwise also covers staircases: check if a small minority of
        # jumps accounts for most of the movement, not just one big jump.
        sorted_jumps = np.sort(step_jumps)[::-1]
        cum_jumps = np.cumsum(sorted_jumps)
        n_dominant = int(np.searchsorted(cum_jumps, 0.8 * gwp_range)) + 1
        is_stepwise = (max_jump / gwp_range > 0.6) or (n_dominant <= max(1, len(step_jumps) * 0.3))
    else:
        is_stepwise = False

    return {
        "relative_range": relative_range,
        "is_linear": is_linear,
        "is_stepwise": is_stepwise,
        "max_residual_pct": max_residual_pct,
        "max_residual_pct_of_range": max_residual_pct_of_range,
        "gwp_range": gwp_range,
        "baseline_gwp": baseline_gwp,
    }


def oat_relative_change(detail_df, variation_pct):
    """Classic OAT sensitivity: how much GWP changes when this
    parameter is increased/decreased by X% from baseline.

    Interpolated from the Full Analysis wide-range curve (0.5x-1.5x baseline),
    not from a separate Selenium sweep.

    Returns: baseline_gwp, pct_increase/pct_decrease, gwp_at_increase/
    gwp_at_decrease, and rel_change_increase/rel_change_decrease. None if
    insufficient data.
    """
    df = detail_df.dropna(subset=["GWP"]).sort_values("Parameter Value")
    if len(df) < 2:
        return None
    x = df["Parameter Value"].values
    y = df["GWP"].values

    baseline_row = df.iloc[(df["Parameter Value"] - 1.0).abs().argsort()[:1]]
    baseline_gwp = baseline_row["GWP"].values[0]
    if not baseline_gwp:
        return None

    factor_up = 1 + variation_pct / 100
    factor_down = 1 - variation_pct / 100
    # Clip to the actually-tested range (0.5x-1.5x) so a variation request
    # right at the edge doesn't extrapolate past real data
    factor_up = min(factor_up, x.max())
    factor_down = max(factor_down, x.min())

    gwp_up = np.interp(factor_up, x, y)
    gwp_down = np.interp(factor_down, x, y)

    return {
        "baseline_gwp": baseline_gwp,
        "gwp_at_increase": gwp_up,
        "gwp_at_decrease": gwp_down,
        "rel_change_increase": (gwp_up - baseline_gwp) / baseline_gwp * 100,
        "rel_change_decrease": (gwp_down - baseline_gwp) / baseline_gwp * 100,
    }


def short_interpretation(param_type, shape):
    """One-line, coarse-grained interpretation for the summary table."""
    if shape is None:
        return "Not enough data"
    rr, is_linear, is_stepwise = shape["relative_range"], shape["is_linear"], shape["is_stepwise"]
    if is_stepwise and rr <= 15:
        cause = "replacement cycles" if param_type == "lifetime" else "a threshold"
        return f"Small impact, but stepwise (likely {cause})"
    if is_linear:
        if rr > 30:
            return "High impact, linear"
        elif rr > 15:
            return "Moderate impact, linear"
        else:
            return "Low impact, stable"
    else:
        if rr > 30:
            return "High impact, non-linear (threshold effect)"
        else:
            return "Non-linear, limited magnitude"


def shape_thumbnail(detail_df, is_non_linear):
    """Small preview chart of one parameter's GWP curve for the summary
    table's "Shape" column, colored by category (amber non-linear/stepwise,
    green linear) with minimal axis ticks for real coordinates.
    Returns a base64 PNG data URI, or None if not enough data.
    """
    d = detail_df.dropna(subset=["GWP"]).sort_values("Parameter Value")
    if len(d) < 2:
        return None
    x = d["Parameter Value"].values
    y = d["GWP"].values
    color = "#e67e22" if is_non_linear else "#2e7d32"

    fig, ax = plt.subplots(figsize=(1.7, 0.75), dpi=110)
    ax.plot(x, y, color=color, linewidth=1.8)
    ax.set_xticks([x.min(), x.max()])
    ax.set_xticklabels([f"{x.min():.2g}x", f"{x.max():.2g}x"], fontsize=5.5)
    ax.set_yticks([y.min(), y.max()])
    ax.set_yticklabels([f"{y.min():.1f}", f"{y.max():.1f}"], fontsize=5.5)
    ax.tick_params(length=2, pad=1, colors="#888888")
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for spine in ["left", "bottom"]:
        ax.spines[spine].set_color("#cccccc")
    fig.patch.set_alpha(0.0)
    ax.patch.set_alpha(0.0)
    plt.tight_layout(pad=0.3)

    buf = io.BytesIO()
    fig.savefig(buf, format="png", transparent=True)
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


# EN 15804 module letter -> short stage description. Applied when a tag
# looks like a module code (e.g. "A1-A3", "B4"); plain-English rows like
# "Manufacture" use the word lookup below instead.
_STAGE_MODULE_CODE_RE = re.compile(r"^[A-D]\d")
_STAGE_MEANING = {
    "A": "material production/manufacturing",
    "B": "the use stage: things like replacement or maintenance over the building's life",
    "C": "end-of-life: deconstruction, transport and disposal of the material",
    "D": "benefits or loads outside the building's own system boundary, e.g. recycling potential",
}
_STAGE_PLAIN_WORD_LETTER = {
    "manufacture": "A", "manufacturing": "A", "production": "A",
    "replacement": "B", "maintenance": "B",
    "disposal": "C", "end of life": "C", "deconstruction": "C",
    "recycling": "D",
}
# Explains an already-computed dominant module (A/B/C/D per EN 15804);
# never used to guess a cause the numbers don't support.
_STAGE_SHORT_GIST = {
    "A": "the material itself",
    "B": "how often it's replaced or maintained",
    "C": "how it's disposed of at end of life",
    "D": "credits or burdens outside the building's own system boundary",
}
_STAGE_IMPLICATION = {
    "A": "what mainly drives this parameter's GWP is the material/quantity itself, not "
         "how long it lasts or how it's disposed of. A lower-impact material or a "
         "smaller amount of it would matter more here than extending its service life.",
    "B": "how often this needs replacing or maintaining over the building's life matters "
         "more here than the material itself, so extending its service life would likely "
         "have the biggest effect on lowering GWP.",
    "C": "how this material is deconstructed and disposed of at end of life matters more "
         "here than how it was produced. The disposal or recycling route is worth a "
         "closer look.",
    "D": "this parameter's effect mainly shows up as a credit or burden outside the "
         "building's own system boundary (e.g. recycling potential), rather than during "
         "construction or use.",
}
# Area ratio (split-layer share) has no service-life counterpart
# Override only these two entries for param_type == "area_ratio"; C/D use
# the shared dict above.
_STAGE_IMPLICATION_AREA_RATIO = {
    "A": "what mainly drives this parameter's GWP is the manufacturing footprint of "
         "whichever material gains area share, so shifting share toward the lower-impact "
         "material would matter more here than anything about disposal or replacement.",
    "B": "how often the material gaining area share needs replacing or maintaining "
         "matters more here than which material it is: worth comparing the replacement "
         "profile of both materials sharing this layer.",
}


def _stage_tag_to_letter(tag):
    """Resolves a scraped stage tag (e.g. "A1-A3", "B4", "D") to its EN 15804
    module letter, or None if unrecognized.
    """
    bare = re.sub(r"(?i)^stage\s+", "", tag).strip().upper()
    if _STAGE_MODULE_CODE_RE.match(bare) or bare == "D":
        return bare[0]
    return _STAGE_PLAIN_WORD_LETTER.get(bare.lower())


def _dominant_stage_for_df(df, baseline_gwp_val):
    """
    Returns (tag, letter, rel_pct) for the life-cycle stage with the largest
    change (% of baseline GWP) across the tested parameter range, or None if
    there is no stage data or all effects are negligible (<0.5% of baseline).
    """
    stage_cols = [c for c in df.columns if c.endswith(" GWP") and c != "GWP"]
    if not stage_cols or not baseline_gwp_val or len(df) < 2:
        return None
    dominant = None
    for col in stage_cols:
        vals = df[col].values
        if pd.isna(vals[0]) or pd.isna(vals[-1]):
            continue
        delta = float(vals[-1]) - float(vals[0])
        tag = col[:-4].strip()
        rel_pct = abs(delta) / abs(baseline_gwp_val) * 100
        if rel_pct < 0.5:
            continue
        letter = _stage_tag_to_letter(tag)
        if dominant is None or rel_pct > dominant[2]:
            dominant = (tag, letter, rel_pct)
    return dominant


def _stage_breakdown_commentary(df, baseline_gwp_val, param_type=None):
    """
    Short interpretation of how each captured life-cycle stage moved across this
    parameter's tested range, vs. the total GWP change over that range.
    """
    stage_cols = [c for c in df.columns if c.endswith(" GWP") and c != "GWP"]
    if not stage_cols or not baseline_gwp_val or len(df) < 2:
        return ""

    gwp_vals = df["GWP"].values
    total_delta = gwp_vals[-1] - gwp_vals[0]

    sentences = []
    for col in stage_cols:
        vals = df[col].values
        if pd.isna(vals[0]) or pd.isna(vals[-1]):
            continue
        v_from, v_to = float(vals[0]), float(vals[-1])
        delta = v_to - v_from
        tag = col[:-4].strip()
        rel_pct = abs(delta) / abs(baseline_gwp_val) * 100
        letter = _stage_tag_to_letter(tag)
        if rel_pct < 0.5:
            sentences.append(
                f"<b>{tag}</b> stays essentially flat. This parameter's value doesn't "
                f"meaningfully change it."
            )
            continue
        meaning = _STAGE_MEANING.get(letter, "")
        direction = "up" if delta > 0 else "down"
        # share_pct compares this stage's delta to the total GWP delta, not gwp_range,
        # so it can exceed 100% or go negative when stages offset each other. A large
        # negative share means this stage opposes the net change.
        share_text = ""
        if total_delta and abs(total_delta) > 1e-9:
            share_pct = delta / total_delta * 100
            if share_pct >= 120:
                share_text = (
                    ". On its own this stage would move GWP by more than the observed net "
                    "change; other stages partially offset it"
                )
            elif share_pct >= 80:
                share_text = ". This alone accounts for essentially all of the total GWP change"
            elif share_pct <= -120:
                share_text = (
                    ". This stage actually swings harder than the total does, in the "
                    "opposite direction; other stages pulling the other way are what keeps "
                    "the net change this size"
                )
            elif share_pct <= -20:
                share_text = ". This partially offsets the change driven by the other stages"
            elif share_pct <= 20:
                share_text = ". This is only a minor slice of the total GWP change, mostly driven elsewhere"
        meaning_clause = f" ({meaning})" if meaning else ""
        sentences.append(
            f"<b>{tag}</b>{meaning_clause} moves {direction} by {abs(delta):.2f} kg CO₂-eq/m² "
            f"({rel_pct:.1f}% of baseline total GWP) across the tested range{share_text}."
        )

    if not sentences:
        return ""

    # Closing sentence, only added when one stage clearly stands out and
    # its module letter is recognized.
    closing = ""
    dominant = _dominant_stage_for_df(df, baseline_gwp_val)
    if dominant is not None:
        dom_tag, dom_letter, dom_pct = dominant
        implication = None
        if param_type == "area_ratio":
            implication = _STAGE_IMPLICATION_AREA_RATIO.get(dom_letter)
        if implication is None:
            implication = _STAGE_IMPLICATION.get(dom_letter)
        if implication:
            closing = (
                f" In short, this parameter's GWP impact is concentrated in <b>{dom_tag}</b> "
                f"({dom_pct:.1f}% of baseline total GWP): {implication}"
            )

    list_items = "".join(f"<li style='margin-bottom: 4px;'>{s}</li>" for s in sentences)
    result = (
        "<b>Life-cycle stage breakdown:</b>"
        f"<ul style='margin: 6px 0 4px 20px; padding: 0;'>{list_items}</ul>"
    )
    if closing:
        result += closing.strip()
    return result


_MATERIAL_FAMILY_RE = re.compile(r"^(.*?)\s\((\d+)\)\s-\s(.*)$")


def _cross_parameter_material_comparison(label, param_type, all_summary_rows, all_detail_dfs,
                                          baseline_gwp_val):
    """Resolves an apparent contradiction when the same material has both a
    thickness and lifetime parameter analyzed, compares their Relative Range % and states which deserves more attention.
    """
    if param_type not in ("size", "lifetime") or not all_summary_rows or not all_detail_dfs:
        return ""
    m = _MATERIAL_FAMILY_RE.match(label)
    if not m:
        return ""
    comp_text, instance_num, rest = m.groups()
    suffix = " - thickness (mm)" if param_type == "size" else " - lifetime (yr)"
    if not rest.endswith(suffix):
        return ""
    material = rest[: -len(suffix)].strip()
    material_display = _translate_material_names(material)
    other_type = "lifetime" if param_type == "size" else "size"
    other_suffix = " - lifetime (yr)" if param_type == "size" else " - thickness (mm)"
    other_label = f"{comp_text} ({instance_num}) - {material}{other_suffix}"

    my_row = all_summary_rows.get(label)
    other_row = all_summary_rows.get(other_label)
    other_df = all_detail_dfs.get(other_label)
    my_df_for_dom = all_detail_dfs.get(label)
    if my_row is None or other_row is None or other_df is None or my_df_for_dom is None:
        return ""

    my_rr = abs(my_row.get("Relative Range (%)", 0))
    other_rr = abs(other_row.get("Relative Range (%)", 0))
    if my_rr < 1e-9 and other_rr < 1e-9:
        return ""
    # Only worth a verdict when there's a real gap. A close call could
    # just be noise between two similarly-influential properties.
    smaller, larger = sorted((my_rr, other_rr))
    if larger < 1.3 * max(smaller, 1e-9):
        return ""

    my_dom = _dominant_stage_for_df(my_df_for_dom, baseline_gwp_val)
    other_dom = _dominant_stage_for_df(other_df, baseline_gwp_val)
    if not my_dom or not other_dom:
        return ""
    my_meaning = _STAGE_MEANING.get(my_dom[1])
    other_meaning = _STAGE_MEANING.get(other_dom[1])
    if not my_meaning or not other_meaning:
        return ""

    my_kind = "thickness" if param_type == "size" else "lifetime"
    other_kind = "thickness" if other_type == "size" else "lifetime"
    winner_is_me = my_rr > other_rr
    winner_kind, loser_kind = (my_kind, other_kind) if winner_is_me else (other_kind, my_kind)
    winner_meaning, loser_meaning = (my_meaning, other_meaning) if winner_is_me else (other_meaning, my_meaning)
    winner_rr, loser_rr = (my_rr, other_rr) if winner_is_me else (other_rr, my_rr)

    # The "X says A, even though Y says B" framing only applies when they
    # disagree; if both share the same dominant module, use a shorter statement.
    if my_dom[1] == other_dom[1]:
        variants = [
            f"<b>{material_display}: thickness vs. lifetime.</b> Both are dominated by the same "
            f"life-cycle stage here ({my_meaning}), so there's no real disagreement to resolve between "
            f"the two readings. {winner_kind.capitalize()} still has the larger overall effect "
            f"on this material ({winner_rr:.1f}% relative range vs. {loser_rr:.1f}% for "
            f"{loser_kind}).",

            f"<b>{material_display}: thickness vs. lifetime.</b> These two readings agree rather than "
            f"conflict. Both trace back to the same stage ({my_meaning}), so there's nothing to "
            f"reconcile between them. The gap between them is in size, not direction. "
            f"{winner_kind} moves total GWP more ({winner_rr:.1f}% relative range vs. "
            f"{loser_rr:.1f}% for {loser_kind}).",

            f"For <b>{material_display}</b>, thickness and lifetime aren't pulling in different "
            f"directions. Both come down to the same underlying stage ({my_meaning}), so "
            f"picking one explanation over the other isn't necessary here. What differs is the "
            f"scale, since {winner_kind} accounts for the bigger share of this material's GWP swing "
            f"({winner_rr:.1f}% relative range against {loser_rr:.1f}% for {loser_kind}).",
        ]
        return variants[_variant_index(label + "|xcmp", len(variants))]

    # Name whatever the loser's own dominant stage actually points to
    my_letter, other_letter = my_dom[1], other_dom[1]
    loser_letter = other_letter if winner_is_me else my_letter
    loser_gist = _STAGE_SHORT_GIST.get(loser_letter, "a different factor")

    # Framed as "alone" vs. "compared together" rather than "X says A, even
    # though Y says B instead".
    variants = [
        f"<b>{material_display}: thickness vs. lifetime.</b> Looked at alone, {loser_kind} points to "
        f"{loser_gist} as what matters most. Compared together, though, {winner_kind} moves "
        f"total GWP more ({winner_rr:.1f}% relative range vs. {loser_rr:.1f}% for {loser_kind}), "
        f"driven mainly by {winner_meaning}, so for <b>{material_display}</b>, {winner_kind} deserves "
        f"the closer attention.",

        f"<b>{material_display}: thickness vs. lifetime.</b> These two tell different stories read on "
        f"their own. {loser_kind.capitalize()} alone highlights {loser_gist}. Side by side, though, it's "
        f"{winner_kind} that actually moves total GWP more ({winner_rr:.1f}% vs. {loser_rr:.1f}% "
        f"for {loser_kind}), through {winner_meaning}, which is the one worth prioritizing for "
        f"<b>{material_display}</b>.",

        f"On <b>{material_display}</b>, thickness and lifetime don't agree on what matters most when "
        f"looked at individually. {loser_kind.capitalize()} alone would point to {loser_gist}. Compared "
        f"directly, though, {winner_kind} is the bigger driver of total GWP ({winner_rr:.1f}% "
        f"relative range against {loser_rr:.1f}% for {loser_kind}), via {winner_meaning}, which is "
        f"where to focus for this material.",
    ]
    return variants[_variant_index(label + "|xcmp", len(variants))]


_PARAM_KIND_PHRASE = {
    "quantity": "how many units of it are installed",
    "size": "how thick this layer is",
    "area_ratio": "how the area is split between the two materials here",
}


def _kind_phrase(param_type):
    return _PARAM_KIND_PHRASE.get(param_type, "this input")


def _variant_index(label, n):
    """Deterministic 0..n-1 pick based on the label, so the same parameter
    always reads the same way across reruns, while different parameters in the
    same tier don't all get identical text. This avoids repetitive copy for
    components with many similar linear parameters (e.g. quantity/thickness).
    """
    return sum(ord(c) for c in label) % n


def render_full_interpretation(label, param_type, detail_df, shape, reference_period=None,
                                all_summary_rows=None, all_detail_dfs=None, all_param_types=None,
                                additivity_notes=None):
    """Fine-grained interpretation for one parameter's full curve. Skips chart
    numbers (min/max GWP, relative range %) and focuses on whether intermediate
    values can be skipped, where thresholds occur, and which direction to push.

    reference_period: study period in years; used for lifetime parameters to
    convert jumps into exact replacement counts.
    all_summary_rows / all_detail_dfs / all_param_types: all analyzed parameters,
    used for cross-parameter insights.
    additivity_notes: populated if Additivity Check was run with this parameter.
    """
    # Display-only English version of `label`
    display_label = _display_label(label)

    if param_type == "area_ratio":
        # Split layers get one explanatory note naming the paired material
        own_material = "this material"
        m = re.match(r"^(.*?)\s\((\d+)\)\s-\s(.*)$", label)
        if m:
            rest = m.group(3)
            suffix = " - area ratio (%)"
            own_material = rest[: -len(suffix)].strip() if rest.endswith(suffix) else own_material
        partner_material = "its paired material"
        ep_match = next((ep for ep in explorer_params if ep[0] == label), None)
        if ep_match is not None and len(ep_match) > 9:
            partner_material = ep_match[9]
        note_box(
            f"This is a split layer shared between <b>{own_material}</b> and "
            f"<b>{partner_material}</b>. Changing this value shifts area from one to "
            f"the other. The paired material's share is adjusted automatically so "
            f"the two always sum to 100%, so the layer's total area stays the same; "
            f"only which material fills how much of it changes."
        )
    df = detail_df.dropna(subset=["GWP"]).sort_values("Parameter Value")
    rr, is_linear, is_stepwise = shape["relative_range"], shape["is_linear"], shape["is_stepwise"]
    baseline_gwp_val = shape["baseline_gwp"]

    x = df["Parameter Value"].values
    y = df["GWP"].values

    baseline_actual_val = None
    if "Actual Value" in df.columns and len(df):
        baseline_actual_row = df.iloc[(df["Parameter Value"] - 1.0).abs().argsort()[:1]]
        baseline_actual_val = baseline_actual_row["Actual Value"].values[0]

    below_baseline = df[df["Parameter Value"] < 1.0]["GWP"]
    above_baseline = df[df["Parameter Value"] > 1.0]["GWP"]
    gwp_drop = (baseline_gwp_val - below_baseline.min()) if len(below_baseline) else 0.0
    gwp_rise = (above_baseline.max() - baseline_gwp_val) if len(above_baseline) else 0.0
    asymmetric = baseline_gwp_val and abs(gwp_rise - gwp_drop) / baseline_gwp_val > 0.02

    # Locate the jump closest to baseline (not just the biggest one)
    jump_from_x = jump_to_x = jump_size = None
    jump_from_actual = jump_to_actual = None
    jump_from_a1a3 = jump_to_a1a3 = jump_from_b4 = jump_to_b4 = None
    num_jumps = 0
    if len(y) > 1:
        diffs = np.abs(np.diff(y))
        noise_floor = max(baseline_gwp_val * 0.001, 1e-9) if baseline_gwp_val else 1e-9
        jump_idxs = [i for i, d in enumerate(diffs) if d > noise_floor]
        num_jumps = len(jump_idxs)
        if jump_idxs:
            if param_type == "lifetime" and len(jump_idxs) > 1:
                j = min(jump_idxs, key=lambda i: min(abs(x[i] - 1.0), abs(x[i + 1] - 1.0)))
            else:
                j = max(jump_idxs, key=lambda i: diffs[i])
            jump_from_x, jump_to_x, jump_size = x[j], x[j + 1], diffs[j]
            if "Actual Value" in df.columns:
                actual = df["Actual Value"].values
                jump_from_actual, jump_to_actual = actual[j], actual[j + 1]
            if "A1-A3 GWP" in df.columns and "B4 GWP" in df.columns:
                a1a3_vals = df["A1-A3 GWP"].values
                b4_vals = df["B4 GWP"].values
                # Best-effort scrape may miss a point. Missing values can appear as NaN in
                # pandas, so check for both NaN and None.
                candidates = (a1a3_vals[j], a1a3_vals[j + 1], b4_vals[j], b4_vals[j + 1])
                if not any(v is None or (isinstance(v, float) and np.isnan(v)) for v in candidates):
                    jump_from_a1a3, jump_to_a1a3 = a1a3_vals[j], a1a3_vals[j + 1]
                    jump_from_b4, jump_to_b4 = b4_vals[j], b4_vals[j + 1]

    def _describe_jump_location():
        """Human-readable "between A and B" description of where the jump
        occurs. Prefers real units over baseline-relative x factors."""
        if jump_from_actual is not None and jump_to_actual is not None:
            unit = " years" if param_type == "lifetime" else ""
            decimals = 1
            while (
                round(jump_from_actual, decimals) == round(jump_to_actual, decimals)
                and decimals < 6
            ):
                decimals += 1
            return f"{jump_from_actual:.{decimals}f}{unit} and {jump_to_actual:.{decimals}f}{unit}"
        decimals = 2
        while (
            round(jump_from_x, decimals) == round(jump_to_x, decimals)
            and decimals < 6
        ):
            decimals += 1
        return f"{jump_from_x:.{decimals}f}x and {jump_to_x:.{decimals}f}x baseline"

    def _stage_proof_text():
        if None in (jump_from_a1a3, jump_to_a1a3, jump_from_b4, jump_to_b4):
            return ""
        a1a3_stable = abs(jump_to_a1a3 - jump_from_a1a3) < max(0.01, abs(jump_from_a1a3) * 0.01)
        b4_delta = abs(jump_to_b4 - jump_from_b4)
        if a1a3_stable:
            return (
                f" Product stage (A1-A3) barely moves, and this is the replacement stage (B4) "
                f"alone, shifting by {b4_delta:.1f} kg CO₂-eq/m²."
            )
        return f" B4 (replacement) shifts by {b4_delta:.1f} kg CO₂-eq/m² here too."

    if is_stepwise and rr <= 15:
        # For lifetime, name the exact mechanism: replacement count is
        # ceil(reference_period / lifetime) - 1, and this integer flips at the jump.
        mechanism_text = None
        if (
            param_type == "lifetime" and reference_period
            and jump_from_actual is not None and jump_from_actual > 0 and jump_to_actual > 0
        ):
            reps_from = int(np.ceil(reference_period / jump_from_actual)) - 1
            reps_to = int(np.ceil(reference_period / jump_to_actual)) - 1
            if reps_from != reps_to:
                mechanism_text = (
                    f"At a service life of {jump_from_actual:.1f} years, the material must be "
                    f"replaced {reps_from} time{'s' if reps_from != 1 else ''} over the "
                    f"building's {reference_period:.0f}-year reference period; stretch it to "
                    f"{jump_to_actual:.1f} years and that drops to {reps_to} replacement"
                    f"{'s' if reps_to != 1 else ''}. That's the entire mechanism, one fewer "
                    f"manufacturing-and-disposal cycle and nothing more subtle."
                    f"{_stage_proof_text()}"
                )
        cause = (
            "the number of replacement cycles required over the building's reference study "
            "period changing by one"
            if param_type == "lifetime" else "a threshold being crossed"
        )
        lead = (
            f"Don't read <b>{display_label}</b> as \"doesn't matter\" just because its overall GWP swing "
            f"is small relative to baseline ({rr:.1f}%, or {shape['gwp_range']:.2f} kg "
            f"CO₂-eq/m² across the full tested range). The real story is that GWP only moves at "
            f"ONE specific point, caused by {cause}. Everywhere else in the tested range, changing "
            f"this value has essentially no effect at all, so refining your estimate of it is "
            f"wasted effort unless your real value sits close to {_describe_jump_location()}."
        ) if jump_size else (
            f"Don't read <b>{display_label}</b> as \"doesn't matter\": its response is stepwise rather "
            f"than gradual, likely due to {cause}, meaning most of the tested range gives an "
            f"identical result and only a narrow band around the real jump is worth pinning down."
        )
        insight_box(f"{lead} {mechanism_text}" if mechanism_text else lead)
    elif is_linear:
        # More material doesn't always mean more GWP, so direction is
        # measured (slope sign)
        slope = np.polyfit(x, y, 1)[0] if len(x) >= 2 else 0.0
        risk_direction = "increasing" if slope >= 0 else "decreasing"

        # Three impact tiers with a few paraphrased write-ups so parameters in the
        # same tier don't print identical text. _variant_index selects phrasing
        # deterministically from the label.
        kind = _kind_phrase(param_type)
        mrp = shape["max_residual_pct"]
        xmin, xmax = x.min(), x.max()
        gwp_range_val = shape["gwp_range"]

        # rr is relative to this element's baseline, which can hide a large absolute
        # swing on big assemblies. Comparing absolute GWP Range with analyzed peers
        # for the same element gives a more honest "large compared to what" view.
        peer_ranges = [
            abs(row.get("GWP Range", 0)) for lbl, row in (all_summary_rows or {}).items()
            if lbl != label and row.get("GWP Range") is not None
        ]
        large_vs_peers = len(peer_ranges) >= 3 and gwp_range_val >= sorted(peer_ranges)[len(peer_ranges) // 2]

        if rr > 30:
            variants = [
                f"<b>{display_label}</b> is one of the parameters where getting the input value right "
                f"actually matters. A {rr:.1f}% GWP swing across the tested range "
                f"({gwp_range_val:.2f} kg CO₂-eq/m²) means a rough guess or an optimistic "
                f"supplier figure here can meaningfully shift the whole result, particularly when "
                f"{risk_direction} it. The upside is that the response is a straight line (fit "
                f"residuals under {mrp:.2f}% of baseline), so once you have a real value you "
                f"trust, you can interpolate the GWP at nearby values instead of re-running eLCA. "
                f"That trust only extends to the {xmin:.2f}x-{xmax:.2f}x range actually tested. "
                f"Past {xmax:.2f}x baseline, re-test directly rather than extending the "
                f"line by eye.",

                f"Getting {kind} right is genuinely worth the effort for <b>{display_label}</b>, since a "
                f"{rr:.1f}% GWP swing ({gwp_range_val:.2f} kg CO₂-eq/m²) sits on this one number, "
                f"so a careless estimate (especially one that ends up {risk_direction} it) can "
                f"throw the whole result off by a meaningful margin. Since the curve is a "
                f"straight line here (residuals under {mrp:.2f}% of baseline), a value you "
                f"actually trust can just be interpolated rather than re-tested in eLCA every "
                f"time, as long as it stays inside the {xmin:.2f}x-{xmax:.2f}x range this was "
                f"tested over. Anything past {xmax:.2f}x baseline should be checked directly "
                f"instead of extrapolated.",

                f"<b>{display_label}</b> carries real weight: {rr:.1f}% of baseline GWP "
                f"({gwp_range_val:.2f} kg CO₂-eq/m²) moves with this input alone, which makes it "
                f"one of the few parameters here where a sloppy number actually costs you "
                f"accuracy, particularly if you end up {risk_direction} it without a good source. "
                f"It's at least linear (residuals under {mrp:.2f}% of baseline across the "
                f"{xmin:.2f}x-{xmax:.2f}x tested range), so once the real value is known, GWP at "
                f"nearby points can be read off the line instead of re-running eLCA, just not "
                f"past {xmax:.2f}x baseline, where the line hasn't actually been tested.",
            ]
            warning_box(variants[_variant_index(label, len(variants))])
        elif rr > 15:
            variants = [
                f"<b>{display_label}</b> sits in the middle of the pack. A {rr:.1f}% GWP swing across the "
                f"tested range ({gwp_range_val:.2f} kg CO₂-eq/m²) is worth keeping an eye on "
                f"(especially before {risk_direction} it by a large amount), but it's not where "
                f"your biggest wins or risks are. The response is linear, so a reasonable "
                f"estimate combined with interpolation (rather than repeated eLCA runs) is good "
                f"enough here; save your precision effort for the higher-impact parameters "
                f"instead.",

                f"<b>{display_label}</b> is a mid-tier parameter. {rr:.1f}% of baseline GWP "
                f"({gwp_range_val:.2f} kg CO₂-eq/m²) rides on {kind}, enough to be worth a "
                f"reasonable estimate, especially before {risk_direction} it substantially, but "
                f"not enough to chase down an exact figure. Since the response is a straight "
                f"line, interpolating from one trusted estimate works fine here. Put your "
                f"precision budget toward the higher-impact parameters instead.",

                f"Moderate stakes for <b>{display_label}</b>. The measured {rr:.1f}% GWP swing "
                f"({gwp_range_val:.2f} kg CO₂-eq/m²) means it's not a parameter to guess wildly "
                f"on, particularly if {risk_direction} it by a lot, but it's also not one of the "
                f"ones driving this element's result. Linear response, so one decent estimate "
                f"plus interpolation covers it, with no need for repeated eLCA runs and no need to "
                f"prioritize this one over higher-impact parameters.",
            ]
            note_box(variants[_variant_index(label, len(variants))])
        else:
            # A low % here means small relative to this element's baseline,
            # not small in absolute terms; large_vs_peers tells the two apart.
            if large_vs_peers:
                caveat = (
                    f" One caveat: that's still {gwp_range_val:.2f} kg CO₂-eq/m² in absolute "
                    f"terms, more than half the other parameters analyzed for this element move "
                    f"it by less, so don't fully write this one off if the raw amount matters "
                    f"more to you than the percentage does."
                )
            else:
                caveat = (
                    f" In absolute terms that's {gwp_range_val:.2f} kg CO₂-eq/m² too, genuinely "
                    f"small both relative to baseline and next to the other parameters analyzed "
                    f"for this element."
                )
            variants = [
                f"<b>{display_label}</b> is one you can stop worrying about, with only a {rr:.1f}% GWP swing "
                f"across the entire tested range, moving gradually and by small amounts either "
                f"way. A rough estimate is genuinely fine here. It's not worth the time to source "
                f"a more precise value or a \"greener\" alternative for this one, since even a "
                f"generous margin of error in your input barely moves the result.{caveat}",

                f"<b>{display_label}</b> barely matters for this element's own GWP percentage. The full "
                f"tested range only produces a {rr:.1f}% swing, moving gradually with no sharp "
                f"jumps anywhere. A rough guess for {kind} is genuinely good enough, and chasing a "
                f"more precise number or a lower-impact alternative here wouldn't be worth the "
                f"effort, since even a generous margin of error barely changes the "
                f"result.{caveat}",

                f"Low relative stakes here: <b>{display_label}</b> only moves GWP by {rr:.1f}% of "
                f"baseline across the whole tested range, and does so smoothly rather than at any "
                f"one point. There's little reason to spend time refining {kind} or hunting for a "
                f"\"greener\" option for this specific input.{caveat}",
            ]
            insight_box(variants[_variant_index(label, len(variants))])
    else:
        # Three cases: (1) lifetime with a known replacement-count mechanism,
        # (2) a clean single step with no known cause, (3) a genuinely curved response.
        jump_pct = (jump_size / baseline_gwp_val * 100) if (jump_size and baseline_gwp_val) else 0.0

        mechanism_text = None
        if (
            jump_size and param_type == "lifetime" and reference_period
            and jump_from_actual is not None and jump_to_actual is not None
            and jump_from_actual > 0 and jump_to_actual > 0
        ):
            reps_from = int(np.ceil(reference_period / jump_from_actual)) - 1
            reps_to = int(np.ceil(reference_period / jump_to_actual)) - 1
            if reps_from != reps_to:
                # "Entire swing" only applies when this is the only threshold;
                # with several, it's just one slice of the total rr%.
                swing_clause = (
                    f"that's the entire {rr:.0f}% swing here."
                    if num_jumps <= 1 else
                    f"one of {num_jumps} such thresholds in the tested range, which together "
                    f"add up to the full {rr:.0f}% swing."
                )
                mechanism_text = (
                    f"At {jump_from_actual:.1f} years the material needs "
                    f"{reps_from} replacement{'s' if reps_from != 1 else ''} over the "
                    f"{reference_period:.0f}-year reference period; at {jump_to_actual:.1f} "
                    f"years that drops to {reps_to}. Each avoided replacement skips a full "
                    f"manufacturing-and-disposal cycle: {swing_clause}"
                    f"{_stage_proof_text()}"
                )

        if mechanism_text:
            severity = (
                "could flip which design option looks more sustainable if you guess wrong "
                "here"
                if rr > 200 else
                "worth getting the input right"
            )
            warning_box(
                f"<b>{display_label}</b>'s big swing here isn't from more or less material. It's "
                f"driven entirely by how many times it gets replaced over the building's "
                f"lifetime, and {severity}. {mechanism_text} Test your real value directly in "
                f"eLCA if it's anywhere near {_describe_jump_location()}, since being off by even a "
                f"little there can land you on the wrong side of the jump."
            )
        elif is_stepwise and jump_size:
            warning_box(
                f"<b>{display_label}</b> behaves like an on/off switch, not a dial: GWP sits essentially "
                f"flat across most of the tested range and moves almost entirely in one place, "
                f"between {_describe_jump_location()} ({jump_size:.2f} kg CO₂-eq/m², "
                f"{jump_pct:.1f}% of baseline). Everywhere else, a rough estimate barely matters; "
                f"right at that line, it's the only thing that does. Test your real value "
                f"directly in eLCA if it falls anywhere close."
            )
        elif jump_size:
            warning_box(
                f"<b>{display_label}</b> doesn't have one danger zone to watch for. It curves across "
                f"the tested range rather than jumping at a single point ({rr:.0f}% total swing, "
                f"steepest single move {jump_pct:.1f}% near {_describe_jump_location()}), so "
                f"proportional math from any one nearby value will be off by a different amount "
                f"depending on where on the curve your real value sits. Test it directly in eLCA "
                f"rather than interpolating from a neighboring point."
            )
        else:
            warning_box(
                f"<b>{display_label}</b> should not be reasoned about with simple proportional math. The "
                f"response doesn't move at a steady rate, so test the exact value you care about "
                f"directly in eLCA rather than estimating from nearby points."
            )

    if asymmetric:
        # Picks between a few paraphrased write-ups, same as the linear
        # tiers above. Uses a different label suffix so the variant index
        # doesn't always match the one picked above for the same parameter.
        asym_kind = _kind_phrase(param_type)
        if gwp_rise > gwp_drop:
            variants = [
                f"<b>{display_label}</b> is a one-way risk. Pushing it up to the highest tested value "
                f"costs more GWP ({gwp_rise:.2f} kg CO₂-eq/m²) than dropping to the lowest tested "
                f"value saves ({gwp_drop:.2f} kg CO₂-eq/m²). If your estimate of {asym_kind} is uncertain or "
                f"likely to creep up during construction, that matters more in this direction, so "
                f"it's better to err on the side of underestimating it than overestimating it.",

                f"The risk on <b>{display_label}</b> isn't symmetric. Going up to the highest tested "
                f"value adds {gwp_rise:.2f} kg CO₂-eq/m², while dropping to the lowest tested value "
                f"only saves {gwp_drop:.2f}. So if there's any real doubt about {asym_kind}, a "
                f"cautious (lower) number is the safer guess to work with, since overshooting costs "
                f"more than undershooting saves.",

                f"Worth flagging for <b>{display_label}</b>: overshooting to the highest tested value "
                f"is the expensive direction here ({gwp_rise:.2f} kg CO₂-eq/m² added), while "
                f"undershooting to the lowest tested value only gives back {gwp_drop:.2f}. If {asym_kind} tends to run higher "
                f"than planned once construction actually starts, that's exactly the direction "
                f"that hurts most, so plan around the lower end of your estimate, not the higher "
                f"one.",
            ]
            warning_box(variants[_variant_index(label + "|asym", len(variants))])
        else:
            variants = [
                f"<b>{display_label}</b> is a one-way opportunity: reducing it to the lowest tested "
                f"value saves more GWP ({gwp_drop:.2f} kg CO₂-eq/m²) than raising it to the highest "
                f"tested value costs ({gwp_rise:.2f} kg CO₂-eq/m²). If you're looking for where to focus "
                f"reduction efforts, this asymmetry means the payoff here is bigger than the "
                f"symmetric numbers alone would suggest.",

                f"<b>{display_label}</b> rewards going low: trimming {asym_kind} to the lowest tested "
                f"value saves {gwp_drop:.2f} kg CO₂-eq/m², more than the {gwp_rise:.2f} kg CO₂-eq/m² "
                f"raising it to the highest tested value would cost. If this element is a candidate for reduction "
                f"efforts, this is one of the parameters where pushing the value down pays off "
                f"disproportionately.",

                f"There's an asymmetric upside on <b>{display_label}</b>: cutting it to the lowest "
                f"tested value saves {gwp_drop:.2f} kg CO₂-eq/m², while raising it to the highest "
                f"tested value only costs {gwp_rise:.2f}. Worth keeping in mind if you're hunting for reduction "
                f"opportunities: {asym_kind} gives back more than it takes.",
            ]
            insight_box(variants[_variant_index(label + "|asym", len(variants))])

    # How does this parameter rank against everything else analyzed?
    # Only answerable once more than one parameter has been tested.
    if all_summary_rows and len(all_summary_rows) > 1 and label in all_summary_rows:
        ranked = sorted(
            all_summary_rows.items(),
            key=lambda kv: abs(kv[1].get("Relative Range (%)", 0)),
            reverse=True,
        )
        ranked_labels = [l for l, _ in ranked]
        rank = ranked_labels.index(label) + 1
        total = len(ranked_labels)
        top_label, top_row = ranked[0]
        top_rr = abs(top_row.get("Relative Range (%)", 0))
        if rank == 1 and total > 1:
            note_box(
                f"Of the {total} parameters analyzed so far for this element, <b>{display_label}</b> has "
                f"the largest measured effect on GWP. If you can only get one input right, this "
                f"is it."
            )
        elif top_label != label and top_rr > 0:
            share = min(rr / top_rr * 100, 999)
            note_box(
                f"Of the {total} parameters analyzed so far, <b>{display_label}</b> ranks #{rank} by "
                f"measured effect, about {share:.0f}% the size of the most influential one, "
                f"<b>{_display_label(top_label)}</b> ({top_rr:.1f}% relative range). "
                + ("Your attention is better spent there than here."
                   if rank > max(total // 2, 1) else
                   "Still one of the more influential inputs for this element.")
            )

    # Trade-off against the most influential comparable parameter
    if is_linear and all_detail_dfs and all_summary_rows and all_param_types:
        my_slope = np.polyfit(x, y, 1)[0] if len(x) >= 2 else None
        best = None  # (other_label, other_slope, other_rr)
        for other_label in all_param_types:
            if other_label == label:
                continue
            other_row = all_summary_rows.get(other_label)
            other_df = all_detail_dfs.get(other_label)
            if other_row is None or other_df is None:
                continue
            if other_row.get("Max Deviation from Linear (%)", 999) >= 1.0:
                continue  # only compare against other confirmed-linear parameters
            od = other_df.dropna(subset=["GWP"]).sort_values("Parameter Value")
            if len(od) < 2:
                continue
            other_slope = np.polyfit(od["Parameter Value"].values, od["GWP"].values, 1)[0]
            other_rr = abs(other_row.get("Relative Range (%)", 0))
            if best is None or other_rr > best[2]:
                best = (other_label, other_slope, other_rr)
        if best and my_slope is not None and best[1] != 0:
            other_label, other_slope, _ = best
            example_pct = 10.0
            needed_pct = -(my_slope / other_slope) * example_pct
            if 0.5 <= abs(needed_pct) <= 200:
                verb = "reducing" if needed_pct < 0 else "increasing"
                note_box(
                    f"Trade-off: a {example_pct:.0f}% increase in <b>{display_label}</b> could be offset, "
                    f"in terms of total GWP, by {verb} <b>{_display_label(other_label)}</b> by roughly "
                    f"{abs(needed_pct):.1f}%."
                )

    # Interaction/independence, if this parameter has been through an
    # Additivity Check in Parameter Explorer
    if additivity_notes and label in additivity_notes:
        info = additivity_notes[label]
        others = ", ".join(f"<b>{_display_label(o)}</b>" for o in info.get("other_labels", [])) or "the other changed parameters"
        if info.get("is_additive"):
            note_box(
                f"When you tested <b>{display_label}</b> together with {others} in Parameter Explorer, "
                f"their effects on GWP added up independently. You can reason about "
                f"<b>{display_label}</b> on its own without worrying it behaves differently in "
                f"combination with those."
            )
        else:
            warning_box(
                f"When you tested <b>{display_label}</b> together with {others} in Parameter Explorer, "
                f"their combined effect on GWP was NOT simply the sum of each one alone. "
                f"<b>{display_label}</b>'s real-world impact depends somewhat on what else changes at "
                f"the same time, so reasoning about it in isolation can be misleading."
            )

    #  Per-stage breakdown (A1-A3, B4, C, D, ...), if captured: adds context to above
    stage_text = _stage_breakdown_commentary(df, baseline_gwp_val, param_type)
    if stage_text:
        note_box(stage_text)

    #  If the other property (thickness <-> lifetime) was also analyzed, resolve
    # apparent stage-breakdown contradictions.
    comparison_text = _cross_parameter_material_comparison(
        label, param_type, all_summary_rows, all_detail_dfs, baseline_gwp_val
    )
    if comparison_text:
        insight_box(comparison_text)


def note_box(text):
    """Purple: neutral, middle-tier information, green: insight, amber: warning.
    Background uses a translucent accent tint, which is too close to the page background
    in Streamlit dark mode to keep the card distinct in both themes.
    """
    st.markdown(
        f"""<div class="note-box" style="border-left: 3px solid #7b52ab;
                        border: 1px solid rgba(123, 82, 171, 0.4); border-left-width: 3px;
                        padding: 8px 14px; background: rgba(123, 82, 171, 0.16); border-radius: 8px;
                        color: var(--text-color); font-size: 0.95rem; margin: 6px 0;">
            {text}
        </div>""",
        unsafe_allow_html=True
    )


def insight_box(text):
    #Green: genuinely good news
    st.markdown(
        f"""<div class="insight-box" style="border-left: 3px solid #2ca02c;
                        border: 1px solid rgba(44, 160, 44, 0.4); border-left-width: 3px;
                        padding: 8px 14px; background: rgba(44, 160, 44, 0.16); border-radius: 8px;
                        color: var(--text-color); font-size: 0.95rem; margin: 6px 0;">
            {text}
        </div>""",
        unsafe_allow_html=True
    )


def warning_box(text):
    #Amber: caution /risk
    st.markdown(
        f"""<div class="warning-box" style="border-left: 3px solid #e67e22;
                        border: 1px solid rgba(230, 126, 34, 0.4); border-left-width: 3px;
                        padding: 8px 14px; background: rgba(230, 126, 34, 0.16); border-radius: 8px;
                        color: var(--text-color); font-size: 0.95rem; margin: 6px 0;">
            {text}
        </div>""",
        unsafe_allow_html=True
    )


def hint_box(text):
    st.markdown(
        f"""<div style="border: 1px dashed rgba(128, 128, 128, 0.5); padding: 6px 12px;
                        border-radius: 8px; color: var(--text-color); opacity: 0.85;
                        font-size: 0.85rem; margin: 6px 0;">
            {text}
        </div>""",
        unsafe_allow_html=True
    )


def success_box_with_tooltip(text, tooltip):
    # Green insight row with an inline "?" tooltip
    style = (
        ".elca-tt-wrap { position: relative; display: inline-flex; } "
        ".elca-tt-wrap .elca-tt-bubble { visibility: hidden; opacity: 0; "
        "transition: opacity 0.12s ease; position: absolute; top: 130%; right: 0; "
        "width: 230px; background: var(--background-color, #fff); "
        "color: var(--text-color, #262730); border: 1px solid rgba(128, 132, 149, 0.4); "
        "border-radius: 6px; padding: 8px 10px; font-size: 0.78rem; line-height: 1.3; "
        "box-shadow: 0 2px 10px rgba(0, 0, 0, 0.18); z-index: 999; text-align: left; } "
        ".elca-tt-wrap:hover .elca-tt-bubble { visibility: visible; opacity: 1; }"
    )
    box = (
        f'<div style="border-left: 3px solid #2ca02c; border: 1px solid rgba(44, 160, 44, 0.4); '
        f'border-left-width: 3px; padding: 8px 14px; background: rgba(44, 160, 44, 0.16); '
        f'border-radius: 8px; color: var(--text-color); font-size: 0.95rem; margin: 6px 0; '
        f'display: flex; align-items: center; justify-content: space-between;">'
        f'<span>{text}</span>'
        f'<span class="elca-tt-wrap" style="flex-shrink: 0; margin-left: 12px;">'
        f'<span style="display: inline-flex; align-items: center; justify-content: center; '
        f'width: 15px; height: 15px; border-radius: 50%; border: 1px solid #808495; '
        f'color: #808495; font-size: 0.65rem; cursor: help;">?</span>'
        f'<span class="elca-tt-bubble">{tooltip}</span>'
        f'</span>'
        f'</div>'
    )
    st.markdown(f"<style>{style}</style>{box}", unsafe_allow_html=True)


# Full Analysis runs persist after tab closure via a server-owned background
# thread. _ACTIVE_RUNS uses @st.cache_resource so reconnecting sessions find
# the same run, while completed parameters are checkpointed to CACHE_DIR.
@st.cache_resource
def _get_active_runs_registry():
    return {}


@st.cache_resource
def _get_active_runs_lock():
    # guards check-then-write access to _ACTIVE_RUNS
    return threading.Lock()


_ACTIVE_RUNS = _get_active_runs_registry()
_ACTIVE_RUNS_LOCK = _get_active_runs_lock()

CACHE_DIR = Path.home() / ".elca_sensitivity_cache"
CACHE_DIR.mkdir(exist_ok=True)


def _run_key(comp):
    return f"{comp['project_id']}_{comp['rel_id']}"


def _cache_path(comp):
    return CACHE_DIR / f"{_run_key(comp)}.json"


def _load_disk_cache(comp):
    """Returns (summary_rows, detail_dfs, param_types) previously checkpointed
    for this exact component, or empty dicts if there's no cache yet."""
    path = _cache_path(comp)
    if not path.exists():
        return {}, {}, {}
    try:
        with open(path) as f:
            raw = json.load(f)
        detail_dfs = {
            label: pd.DataFrame(rows)
            for label, rows in raw.get("detail_dfs", {}).items()
        }
        return raw.get("summary_rows", {}), detail_dfs, raw.get("param_types", {})
    except Exception:
        # A corrupted/partial cache file should never block the app from
        # loading the component: just treat it as no cache.
        return {}, {}, {}


def _save_disk_cache(comp, summary_rows, detail_dfs, param_types):
    path = _cache_path(comp)
    raw = {
        "summary_rows": summary_rows,
        "detail_dfs": {label: df.to_dict("records") for label, df in detail_dfs.items()},
        "param_types": param_types,
    }
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w") as f:
        json.dump(raw, f)
    tmp_path.replace(path)  # avoids a half-written file if interrupted mid-save


def _driver_is_alive(driver):
    """True if the Selenium session still controls an open browser window.
    Closing Chrome externally doesn't clear st.session_state["driver"], so
    detect this early instead of reporting per-parameter failures.
    """
    if driver is None:
        return False
    try:
        _ = driver.title
        return True
    except Exception:
        return False


def _clean_error_text(error):
    """Strips Selenium's multi-line dump, leaving
    only the useful first-line error message.
    """
    return str(error or "").split("Stacktrace:")[0].strip()


def _is_transient_network_error(exc):
    """True if `exc` looks like a brief network failure rather than an
    expired login session, waiting and retrying works better here."""
    text = str(exc)
    network_signatures = (
        "ERR_CONNECTION_REFUSED", "ERR_CONNECTION_RESET", "ERR_CONNECTION_TIMED_OUT",
        "ERR_CONNECTION_CLOSED", "ERR_NETWORK_CHANGED", "ERR_INTERNET_DISCONNECTED",
        "ERR_NAME_NOT_RESOLVED", "ERR_EMPTY_RESPONSE", "ERR_ADDRESS_UNREACHABLE",
        "ERR_SOCKET_NOT_CONNECTED", "ERR_NETWORK_ACCESS_DENIED",
    )
    return any(sig in text for sig in network_signatures)


def _call_selenium_with_relogin(fn, driver, username, password, max_relogin_attempts=2):
    """Runs the Selenium action `fn`; on failure, relogins and retries, like
    _run_full_analysis_background, to handle expired eLCA sessions gracefully.

    max_relogin_attempts=2: Additivity Check makes multiple round-trips, so a
    session may expire again during retry.
    Returns (result, None) on success, or (None, error) if all attempts fail.
    """
    first_error = None
    for attempt in range(max_relogin_attempts + 1):
        try:
            return fn(), None
        except AnalysisStopped:
            # A deliberate Stop, not a failure, eLCA is already clean
            raise
        except Exception as e:
            if first_error is None:
                first_error = e
            if attempt == max_relogin_attempts:
                break
            if _is_transient_network_error(e):
                time.sleep(8)
            else:
                try:
                    _selenium_login(driver, username, password)
                except Exception:
                    break
    return None, first_error


def _session_expired_warning(error=None):
    """Replaces Streamlit's raw traceback when a Parameter Explorer action still
    fails after _call_selenium_with_relogin, suggests Disconnect + Connect
    """
    warning_box(
        "This didn't go through: most likely the eLCA session timed out after sitting idle "
        "for a while (an automatic re-login was already tried and didn't fix it). Go to "
        "<b>Connection &amp; Component Settings</b> above, click <b>Disconnect</b>, then "
        "<b>Connect &amp; Load Component</b> again (your cached Full Analysis results won't "
        "be lost) and try this action again."
        + (f"<br><br><i>Underlying error: {_clean_error_text(error)[:300]}</i>" if error is not None else "")
    )


def _test_one_parameter_with_retries(driver, comp, ep, username, password, max_attempts=5):
    """Runs the non-linearity scan for one parameter with retries. Expired eLCA
    sessions trigger relogin; transient network errors use increasing waits.

    Returns (summary_df, detail_dfs, cleanup_warnings, last_error,
    was_network_error). last_error is None on success.
    """
    network_backoff = [10, 30, 60, 120]  # seconds; grows with each retry
    network_retries_used = 0
    last_error = None
    was_network_error = False
    for attempt in range(1, max_attempts + 1):
        try:
            summary_df, detail_dfs, cleanup_warnings = run_full_nonlinearity_scan_selenium(
                driver, comp, parameters=[ep]
            )
            return summary_df, detail_dfs, cleanup_warnings, None, False
        except Exception as e:
            last_error = e
            was_network_error = _is_transient_network_error(e)
            if attempt == max_attempts:
                break
            if was_network_error:
                wait = network_backoff[min(network_retries_used, len(network_backoff) - 1)]
                network_retries_used += 1
                time.sleep(wait)
            else:
                try:
                    _selenium_login(driver, username, password)
                except Exception:
                    break  # re-login itself failed; record the original error
    return None, None, [], last_error, was_network_error


def _run_full_analysis_background(driver, comp, params_to_run, run_state, username, password):
    """Runs on a background thread using only run_state and disk, never st.*.
    Tests one parameter at a time and checkpoints progress after each.
    Credentials stay in local variables and are never logged or persisted.
    Stop requests are checked only between parameters to avoid interrupting writes.
    """
    lock = run_state["lock"]
    total = len(params_to_run)
    network_retry_queue = []
    try:
        for idx, ep in enumerate(params_to_run, start=1):
            with lock:
                if run_state["stop_requested"]:
                    run_state["stopped"] = True
                    return
            label = ep[0]
            with lock:
                # Display-only; run_state keys still use the original `label`.
                run_state["current_label"] = _display_label(label)
                run_state["done"] = idx - 1
                run_state["total"] = total

            summary_df, detail_dfs, cleanup_warnings, last_error, was_network_error = _test_one_parameter_with_retries(
                driver, comp, ep, username, password
            )
            if summary_df is None:
                with lock:
                    run_state["errors"].append(f"{_display_label(label)}: {_clean_error_text(last_error)}")
                if was_network_error:
                    # Queue for one more try after the rest of the list
                    network_retry_queue.append(ep)
                continue

            with lock:
                run_state["param_types"][label] = ep[1]
                if label in detail_dfs:
                    run_state["detail_dfs"][label] = detail_dfs[label]
                for _, row in summary_df.iterrows():
                    run_state["summary_rows"][row["Parameter"]] = row.to_dict()
                run_state["done"] = idx
                for w in cleanup_warnings:
                    run_state["errors"].append(w)
                # Checkpoint after every single parameter, not just at the
                # end, so an interrupted run keeps whatever finished so far
                _save_disk_cache(
                    comp, run_state["summary_rows"], run_state["detail_dfs"], run_state["param_types"]
                )

        with lock:
            already_stopped = run_state["stop_requested"]
        if network_retry_queue and not already_stopped:
            with lock:
                run_state["current_label"] = (
                    f"Network hiccup earlier: retrying {len(network_retry_queue)} "
                    "parameter(s) now that the rest of the run is done..."
                )
            time.sleep(30)
            for ep in network_retry_queue:
                with lock:
                    if run_state["stop_requested"]:
                        run_state["stopped"] = True
                        return
                label = ep[0]
                with lock:
                    run_state["current_label"] = f"Retrying (earlier network hiccup): {_display_label(label)}"
                summary_df, detail_dfs, cleanup_warnings, last_error, _ = _test_one_parameter_with_retries(
                    driver, comp, ep, username, password
                )
                if summary_df is None:
                    continue  # still down, the earlier failure message stands
                with lock:
                    run_state["param_types"][label] = ep[1]
                    if label in detail_dfs:
                        run_state["detail_dfs"][label] = detail_dfs[label]
                    for _, row in summary_df.iterrows():
                        run_state["summary_rows"][row["Parameter"]] = row.to_dict()
                    # Went through this time; drop the earlier failure message for this label.
                    run_state["errors"] = [
                        e for e in run_state["errors"] if e.split(":", 1)[0] != _display_label(label)
                    ]
                    for w in cleanup_warnings:
                        run_state["errors"].append(w)
                    _save_disk_cache(
                        comp, run_state["summary_rows"], run_state["detail_dfs"], run_state["param_types"]
                    )
    finally:
        with lock:
            run_state["status"] = "done"


# Same pattern as the Full Analysis registry above, keyed by component +
# action name so explorer and additivity check could run concurrently.
@st.cache_resource
def _get_active_actions_registry():
    return {}


_ACTIVE_ACTIONS = _get_active_actions_registry()


def _action_key(comp, action):
    return f"{_run_key(comp)}:{action}"


def _run_stoppable_action_background(fn, action_state):
    """Runs fn(should_stop) in a background thread and stores the result in
    action_state.
    """
    def should_stop():
        with action_state["lock"]:
            return action_state["stop_requested"]

    try:
        result = fn(should_stop)
        with action_state["lock"]:
            action_state["result"] = result
    except AnalysisStopped:
        with action_state["lock"]:
            action_state["stopped"] = True
    except Exception as e:
        with action_state["lock"]:
            action_state["error"] = e
    finally:
        with action_state["lock"]:
            action_state["status"] = "done"


@st.fragment(run_every=1)
def _render_connect_status():
    # A fragment auto-refreshes on a timer without st.rerun(), so it won't block the outer run.
    _connect_bg = st.session_state.get("_connect_bg")
    if _connect_bg is not None:
        with _connect_bg["lock"]:
            status = _connect_bg["status"]
            error = _connect_bg.get("error")
            comp = _connect_bg.get("comp")
            bg_driver = _connect_bg.get("driver")

        if status == "running":
            st.info("⏳ Connecting to eLCA and loading component...")
            return
        elif status == "done":
            st.session_state["driver"] = bg_driver
            st.session_state["loaded_component"] = comp
            # Reset the parameter-picker expander open for the newly-loaded
            # component; otherwise it stays collapsed from a previous run.
            st.session_state["params_expander_expanded"] = True
            st.session_state.pop("_collapse_params_after_summary", None)
            for key in ["sensitivity_df", "parameter_result", "parameter_inputs",
                        "additivity_result", "robustness_df", "comparison_df"]:
                st.session_state[key] = None
            for key in ["selected_param_labels", "scan_summary_rows", "scan_detail_dfs", "scan_param_types",
                        "param_additivity_notes"]:
                st.session_state.pop(key, None)
            # Clear the Yes/No "answered" flag on reconnect; it's keyed only by parameter
            # label, so otherwise a same-named label on another component could be skipped.
            for key in ["summary_jump_handled_for", "selected_detail_label_widget", "scroll_to_inspect"]:
                st.session_state.pop(key, None)

            # Restore results checkpointed to disk for this component.
            disk_summary, disk_details, disk_types = _load_disk_cache(comp)
            if disk_details:
                # Cached baselines are frozen at test time; direct eLCA edits can make the
                # sweep stale. Drop entries that no longer match the freshly fetched value.
                fresh_baseline_by_label = {ep[0]: ep[4] for ep in comp["explorer_parameters"]}
                stale = []  # [(label, cached_val, fresh_val), ...]
                for label, df in disk_details.items():
                    fresh_val = fresh_baseline_by_label.get(label)
                    if fresh_val is None or df.empty or "Actual Value" not in df.columns:
                        continue
                    baseline_row = df.iloc[(df["Parameter Value"] - 1.0).abs().argsort()[:1]]
                    cached_val = baseline_row["Actual Value"].values[0]
                    tolerance = max(abs(fresh_val) * 0.01, 0.01)
                    if abs(cached_val - fresh_val) > tolerance:
                        stale.append((label, cached_val, fresh_val))
                for label, _, _ in stale:
                    disk_details.pop(label, None)
                    disk_summary.pop(label, None)
                    disk_types.pop(label, None)

                st.session_state["scan_summary_rows"] = disk_summary
                st.session_state["scan_detail_dfs"] = disk_details
                st.session_state["scan_param_types"] = disk_types
                if stale:
                    # Includes old and new value per parameter to make the storing
                    # of eLCA's field manually possible without hunting for the numbers.
                    lines = "<br>".join(
                        f"&bull; <b>{_display_label(l)}</b>: was {c:.3g}, now {f:.3g}"
                        for l, c, f in stale
                    )
                    st.session_state["last_connect_stale_msg"] = (
                        f"Dropped {len(stale)} cached parameter(s) whose eLCA value no longer "
                        "matches what was last tested here, most likely edited directly in "
                        f"eLCA since:<br>{lines}<br>Restore eLCA's value back to the old one if "
                        "you want the previous result to stand without waiting for a fresh "
                        "sweep, or run/re-analyze below to measure the new one instead."
                    )
                # If everything is cached, don't collapse the picker before it's ever shown;
                # flag it to collapse on the next rerun instead.
                all_labels = [ep[0] for ep in comp["explorer_parameters"]]
                if all_labels and all(lbl in disk_details for lbl in all_labels):
                    st.session_state["_collapse_params_after_summary"] = True

            st.session_state["_connect_bg"] = None
            st.session_state["last_connect_success_msg"] = f"Loaded: {_loaded_element_text(comp['name'])}"
            # just refreshes the rest of the page with the newly loaded component.
            st.rerun()
        else:
            st.session_state["driver"] = bg_driver
            st.session_state["_connect_bg"] = None
            # Match common failure patterns by message text (no dedicated
            # exception types for most of these) for a plain explanation.
            err_text = (error or "").lower()
            if "no such window" in err_text or "target window already closed" in err_text or "web view not found" in err_text:
                # The Chrome window got closed (by hand, or via the
                # confirmation popup's Cancel/X) before it finished
                # connecting. Not a real eLCA/network problem.
                msg = (
                    "The Chrome window closed before connecting finished: most likely it (or "
                    "the confirmation popup) got closed too early. Click **Connect & Load "
                    "Component** again, confirm the popup, and leave the Chrome window open "
                    "and untouched until the component loads."
                )
            elif "session not created" in err_text or "cannot find chrome binary" in err_text or "chrome not reachable" in err_text or "chrome failed to start" in err_text:
                # Chrome itself never launched: nothing was reached on
                # eLCA at all.
                msg = (
                    "Chrome couldn't be started on this computer. Make sure Google Chrome is "
                    "installed and closed in any conflicting state, then try **Connect & Load "
                    "Component** again. If this keeps happening, restarting the computer "
                    "usually clears it."
                )
            elif "login failed" in err_text:
                msg = "Login failed: please double-check your eLCA username and password."
            else:
                # Unrecognized error: show the real message, dropping
                # Selenium's Stacktrace dump.
                msg = f"Could not connect / load component: {_clean_error_text(error)}"
            # Stash and hand off to a full rerun instead of st.error() here:
            # this fragment reruns every second and would wipe the message immediately.
            st.session_state["last_connect_error_msg"] = msg
            st.rerun()


def _render_connect_messages():
    # Rendered outside the polling fragment, so the message stays on
    # screen instead of being cleared by its 1-second auto-refresh.
    if st.session_state.get("last_connect_success_msg"):
        st.success(st.session_state.pop("last_connect_success_msg"))
    if st.session_state.get("last_connect_stale_msg"):
        warning_box(st.session_state.pop("last_connect_stale_msg"))
    if st.session_state.get("last_connect_error_msg"):
        st.error(st.session_state.pop("last_connect_error_msg"))


st.set_page_config(page_title="eLCA Sensitivity Analysis", layout="wide", page_icon="🌿")

# Visual theme
st.markdown(
    """
    <style>
    .stButton > button {
        border-radius: 10px;
        border: 1.5px solid #2e7d32;
        color: #2e7d32;
        background: var(--background-color);
        font-weight: 600;
        transition: transform 0.15s ease, box-shadow 0.15s ease, background 0.15s ease, color 0.15s ease;
    }
    .stButton > button:hover {
        background: #2e7d32;
        color: #ffffff;
        transform: scale(1.035);
        box-shadow: 0 6px 16px rgba(46, 125, 50, 0.25);
    }
    .stButton > button:active {
        transform: scale(0.97);
    }
    [data-testid="stMetric"] {
        background: var(--secondary-background-color);
        border: 1px solid rgba(128, 128, 128, 0.25);
        border-radius: 12px;
        padding: 14px 16px;
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-3px);
        box-shadow: 0 8px 18px rgba(46, 125, 50, 0.12);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
    }
    /* var(--secondary-background-color) sits almost on top of the page's
       own background in dark mode (same issue the note/insight/warning
       boxes work around), so a translucent tint plus a real border is used
       instead, which reads as a distinct pill in both themes. */
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 18px;
        background: rgba(128, 128, 128, 0.14);
        border: 1px solid rgba(128, 128, 128, 0.4);
        border-bottom: none;
        transition: transform 0.15s ease, background 0.15s ease;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: rgba(46, 125, 50, 0.22);
        border-color: rgba(46, 125, 50, 0.5);
        transform: translateY(-2px);
    }
    .stTabs [aria-selected="true"] {
        background: #2e7d32 !important;
        border-color: #2e7d32 !important;
        color: #ffffff !important;
    }
    /* Streamlit's default pill width clips text even when already short;
       widen it here to avoid double-truncating. */
    [data-baseweb="tag"] {
        max-width: none !important;
    }
    [data-baseweb="tag"] span[title] {
        max-width: none !important;
        overflow: visible !important;
        text-overflow: unset !important;
        white-space: nowrap !important;
    }
    [data-testid="stExpander"] {
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.25);
        transition: box-shadow 0.15s ease;
    }
    [data-testid="stExpander"]:hover {
        box-shadow: 0 6px 16px rgba(46, 125, 50, 0.10);
    }
    [data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #2e7d32, #66bb6a);
    }
    .note-box, .insight-box, .warning-box {
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    .note-box:hover, .insight-box:hover, .warning-box:hover {
        transform: scale(1.01);
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
    }
    .page-title {
        text-align: center;
        font-size: 2.6rem;
        font-weight: 800;
        color: var(--text-color);
        margin: 0.3rem 0 0.2rem 0;
    }
    .page-subtitle {
        text-align: center;
        color: var(--text-color);
        opacity: 0.7;
        font-size: 1.05rem;
        margin-bottom: 1.2rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="page-title">eLCA Parameter Sensitivity Analysis</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="page-subtitle">This tool analyzes how different component parameters '
    'influence the total GWP result and allows users to explore alternative parameter configurations.</div>',
    unsafe_allow_html=True,
)

# Connection: everything runs through one persistent browser session
with st.expander("Connection & Component Settings",
                 expanded=not bool(st.session_state.get("loaded_component"))):

    note_box(
        "This app drives the real eLCA website through an automated browser (Chrome will "
        "open). Because every calculation is a real page interaction, analyses take "
        "noticeably longer than a plain web request would: a few seconds per parameter "
        "value tested."
    )

    col_u, col_p = st.columns(2)
    with col_u:
        username_input = st.text_input("eLCA Username", key="username_input")
    with col_p:
        password_input = st.text_input("eLCA Password", type="password", key="password_input")

    url_input = st.text_input(
        "eLCA Element Link",
        placeholder="https://www.bauteileditor.de/projects/12345/#!/project-elements/9999999/",
        help="Open the building element in eLCA and paste its full URL here: the Project ID "
             "and Element ID are read from it automatically.",
        key="url_input"
    )

    # Disconnecting & reconnecting locked
    _loaded_comp_for_guard = st.session_state.get("loaded_component")
    _connect_running_guard = (st.session_state.get("_connect_bg") or {}).get("status") == "running"
    _bg_blocks_disconnect = _connect_running_guard or (
        _loaded_comp_for_guard is not None
        and _ACTIVE_RUNS.get(_run_key(_loaded_comp_for_guard), {}).get("status") == "running"
    )
    if _connect_running_guard:
        st.info("**Connect** and **Disconnect** are locked while connecting. Wait for it to finish.")
    elif _bg_blocks_disconnect:
        st.warning("**Connect** and **Disconnect** are locked while Full Analysis is running in the background. Wait for it to finish first.")

    @st.dialog("Before the browser opens")
    def _connect_warning_dialog():
        st.write(
            "This opens a real Chrome window the tool drives itself: please don't click, "
            "type, or scroll in it. Recommended: minimize it once it appears and let the "
            "tool work."
        )
        st.caption(
            "FYI: your eLCA username and password are only used to sign in; they're never "
            "saved, and are cleared the moment you close the tool."
        )
        col_cancel, col_btn = st.columns([1, 2])
        with col_cancel:
            if st.button("Cancel"):
                st.session_state["_pending_connect"] = False
                st.rerun()
        with col_btn:
            if st.button("I've read and accept - Connect", use_container_width=True):
                st.session_state["_pending_connect"] = False
                st.session_state["_do_connect"] = True
                st.rerun()

    col_connect, col_disconnect = st.columns(2)
    with col_connect:
        connect_button = st.button("Connect & Load Component", disabled=_bg_blocks_disconnect)
    with col_disconnect:
        disconnect_button = st.button("Disconnect", disabled=_bg_blocks_disconnect)

    if connect_button and not _bg_blocks_disconnect:
        if username_input and password_input and url_input:
            st.session_state["_pending_connect"] = True
        else:
            st.warning("Enter your username, password and the element link first.")

    if st.session_state.get("_pending_connect"):
        _connect_warning_dialog()

    if disconnect_button and not _bg_blocks_disconnect:
        driver = st.session_state.get("driver")
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
        for key in ["driver", "loaded_component", "sensitivity_df", "parameter_result",
                    "parameter_inputs", "additivity_result", "robustness_df", "comparison_df"]:
            st.session_state[key] = None
        for key in ["selected_param_labels", "scan_summary_rows", "scan_detail_dfs", "scan_param_types",
                    "param_additivity_notes"]:
            st.session_state.pop(key, None)
        for key in ["summary_jump_handled_for", "selected_detail_label_widget", "scroll_to_inspect"]:
            st.session_state.pop(key, None)
        st.session_state.pop("_collapse_params_after_summary", None)
        st.success("Disconnected. Browser closed.")

    # Runs the actual connecting on a background thread instead of inline,
    # the popup closes on the accept click
    def _connect_in_background(state, existing_driver, project_id_input, element_id_input, username, password):
        lock = state["lock"]
        try:
            if not _driver_is_alive(existing_driver):
                if existing_driver is not None:
                    try:
                        existing_driver.quit()
                    except Exception:
                        pass
                from selenium import webdriver
                from selenium.webdriver.chrome.options import Options as ChromeOptions
                chrome_options = ChromeOptions()
                chrome_options.add_argument("--start-maximized")
                # Selenium Manager auto-downloads the matching chromedriver
                driver = webdriver.Chrome(options=chrome_options)
            else:
                driver = existing_driver
            with lock:
                state["driver"] = driver
            _selenium_login(driver, username, password)
            comp = fetch_component_selenium(driver, project_id_input, element_id_input)
            with lock:
                state["comp"] = comp
                state["status"] = "done"
        except Exception as e:
            with lock:
                state["error"] = str(e)
                state["status"] = "error"

    if st.session_state.pop("_do_connect", False):
        existing_driver = st.session_state.get("driver")
        conn_state = {
            "lock": threading.Lock(), "status": "running",
            "driver": existing_driver, "comp": None, "error": None,
        }
        try:
            project_id_input, element_id_input = parse_elca_url(url_input)
        except Exception as e:
            conn_state["status"] = "error"
            conn_state["error"] = str(e)
        else:
            threading.Thread(
                target=_connect_in_background,
                args=(conn_state, existing_driver, project_id_input, element_id_input,
                      username_input, password_input),
                daemon=True,
            ).start()
        st.session_state["_connect_bg"] = conn_state

    _render_connect_status()
    _render_connect_messages()

if not st.session_state.get("loaded_component"):
    # Skip this reminder while a connect is in progress
    _connecting_now = (st.session_state.get("_connect_bg") or {}).get("status") == "running"
    if not _connecting_now:
        st.info("Enter your eLCA username, password and the element link above, then click **Connect & Load Component**.")
    st.stop()

driver = st.session_state["driver"]
comp = st.session_state["loaded_component"]
explorer_params = comp["explorer_parameters"]
known_sensitivity = comp["known_sensitivity"]
project_id = comp["project_id"]
ALL_PARAM_LABELS = [ep[0] for ep in explorer_params]

_PARAM_TYPE_BY_LABEL = {ep[0]: ep[1] for ep in explorer_params}
_PARAM_LABEL_RE = re.compile(r"^(.*?)\s\((\d+)\)\s-\s(.*)$")


def _truncate_keep_disambiguator(name, max_len):
    """Truncates a material name to max_len while preserving a trailing "(n)"
    disambiguator, so distinct layers don't render with identical pill text.
    """
    m = re.match(r"^(.*)\s(\([0-9]+\))$", name)
    if not m:
        return (name[:max_len] + "…") if len(name) > max_len else name
    base, disambiguator = m.group(1), m.group(2)
    budget = max_len - len(disambiguator) - 1
    base = (base[:budget] + "…") if len(base) > budget else base
    return f"{base} {disambiguator}"


def _short_param_label(l, style="pill"):
    """Shortens parameter labels for fixed-width UI elements, keeping only the
    distinguishing component tag, material name, and changed property. Legend
    style is tighter for narrow chart columns.
    """
    ptype = _PARAM_TYPE_BY_LABEL.get(l)
    max_len = 16 if style == "pill" else 13
    m = _PARAM_LABEL_RE.match(l) if ptype in ("size", "lifetime", "quantity", "area_ratio") else None
    if not m:
        return (l[: max_len + 4] + "…") if len(l) > max_len + 4 else l
    comp_text, instance_num, rest = m.groups()
    # Uses the translated name's first letter, so e.g. "Gipskarton
    # verspachtelt" (-> "Joint-filled gypsum board") tags as J(1), not G(1).
    tag = f"{_translate_element_name(comp_text)[:1].upper()}({instance_num})"
    if ptype == "quantity":
        # "quantity" covers composite "Number installed" and material "Other Materials"
        # Amount; split them so both don't render as "{tag} Quantity".
        if rest.strip() == "quantity":
            return f"{tag} Quantity" if style == "pill" else f"{tag} Qty"
        suffix = " - amount"
        layer_name = rest[: -len(suffix)] if rest.endswith(suffix) else rest
        layer_name = _translate_material_names(layer_name.strip())
        layer_name = _truncate_keep_disambiguator(layer_name, max_len)
        return f"{tag} {layer_name} (amount)" if style == "pill" else f"{tag} {layer_name} (amt)"
    if ptype == "area_ratio":
        suffix = " - area ratio (%)"
        unit_label = "%"
    else:
        suffix = " - thickness (mm)" if ptype == "size" else " - lifetime (yr)"
        unit_label = "mm" if ptype == "size" else "yr"
    layer_name = rest[: -len(suffix)] if rest.endswith(suffix) else rest
    layer_name = _translate_material_names(layer_name.strip())
    layer_name = _truncate_keep_disambiguator(layer_name, max_len)
    return f"{tag} {layer_name} ({unit_label})"


success_box_with_tooltip(
    f"Loaded: <b>{_loaded_element_text(comp['name'])}</b> (Element ID: {comp['rel_id']})",
    "Element/module names are translated to English where recognized (eLCA itself "
    "doesn't translate these, only the materials inside them). It is expected that a "
    "name never seen before shows up in German instead."
)

# Parameter selection, chosen once up front for Full Analysis, starts empty
if "selected_param_labels" not in st.session_state:
    st.session_state["selected_param_labels"] = []

if "oat_variation_pct" not in st.session_state:
    st.session_state["oat_variation_pct"] = 10

with st.expander(
    "Which parameters should be analyzed?",
    # stays open until a run starts, then collapses so the results
    # are the obvious next thing to look at.
    expanded=st.session_state.get("params_expander_expanded", True),
):
    note_box(
        "Recommended: select and run every parameter here first (or click <b>Select all</b>). "
        "In the <b>Parameter Explorer</b> tab, you can only change the value of a parameter "
        "that's already been analyzed here, to guarantee every scenario's interpretation "
        "there is backed by a real measured curve."
    )
    hint_box(
        "Names can look similar and picks sometimes need a second click: please double-check "
        "your selection."
    )
    if st.button("Select all"):
        st.session_state["selected_param_labels"] = list(ALL_PARAM_LABELS)
    st.session_state["selected_param_labels"] = st.multiselect(
        "Parameters to include in the Full Analysis",
        ALL_PARAM_LABELS,
        default=st.session_state["selected_param_labels"],
        format_func=_short_param_label,
        help="Pick the parameters to test, or click Select all. Already-analyzed "
             "parameters are cached and won't be re-run. Names are shortened here "
             "to fit: the full name for each one shows up once results are in, "
             "in the summary table below."
    )
    st.session_state["oat_variation_pct"] = st.slider(
        "Variation % for the quick sensitivity ranking below",
        min_value=1, max_value=50, value=st.session_state["oat_variation_pct"],
        help="Only affects the quick ranking chart below: change it any time, no need to "
             "re-run the analysis."
    )

selected_param_labels = st.session_state["selected_param_labels"]

# Result caches, keyed by parameter label, so re-running after adding new
# parameters to the selection only computes the new ones.
if "scan_summary_rows" not in st.session_state:
    st.session_state["scan_summary_rows"] = {}   # label -> summary dict
if "scan_detail_dfs" not in st.session_state:
    st.session_state["scan_detail_dfs"] = {}      # label -> detail DataFrame
if "scan_param_types" not in st.session_state:
    st.session_state["scan_param_types"] = {}     # label -> param_type

tab1, tab2 = st.tabs([
    "Full Sensitivity Analysis",
    "Parameter Explorer"
])


with tab1:
    st.subheader("Full Sensitivity Analysis")
    st.write(
        "One run tests every selected parameter automatically. Start it and come back later: "
        "no need to pick parameters or press a button one at a time."
    )
    if not selected_param_labels:
        st.info("Select at least one parameter above (or click Select all) to run an analysis.")

    to_run_labels = [
        label for label in selected_param_labels
        if label not in st.session_state["scan_detail_dfs"]
    ]
    already_done = len(selected_param_labels) - len(to_run_labels)

    if already_done and to_run_labels:
        note_box(
            f"{already_done} of {len(selected_param_labels)} selected parameters are already "
            f"analyzed (cached). Only the remaining {len(to_run_labels)} will be run."
        )
    elif already_done and not to_run_labels:
        warning_box(
            "All selected parameters are already analyzed and cached: no need to run anything. "
            "The button below now says <b>Re-analyze</b>: clicking it discards the cached results "
            "for these parameters and tests them all again from scratch through eLCA (slow). To "
            "analyze new parameters instead, add them in the parameter picker above. Changed "
            "something directly in eLCA instead? Re-analyze the whole component here, not just "
            "the parameter you touched, since one change can make every cached baseline stale. "
            "To try a value without touching the cache, use <b>Parameter Explorer</b>'s scenario "
            "feature instead: it always measures live against eLCA's current state."
        )

    run_key = _run_key(comp)
    bg_run = _ACTIVE_RUNS.get(run_key)
    bg_running = bg_run is not None and bg_run["status"] == "running"

    if bg_running:
        note_box(
            "Running in the background: safe to close this tab or switch away. Just keep "
            "the computer awake and the terminal running Streamlit open."
        )

    run_full_button = st.button(
        "Run Full Analysis" if (to_run_labels or not selected_param_labels) else "Re-analyze selected parameters",
        disabled=bg_running or not selected_param_labels,
    )

    if run_full_button and not bg_running and not _driver_is_alive(driver):
        st.error(
            "The browser window this app was controlling is no longer open "
            "(closed outside the app, or the Mac slept through it), so no "
            "analysis can run right now. Go to **Connection & Component "
            "Settings** above and click **Connect & Load Component** again "
            "to open a fresh browser window: your cached results won't be "
            "lost."
        )
    elif run_full_button and not bg_running:
        # Re-check and set under one lock: `bg_running` may be stale if another tab
        # started a run meanwhile. Otherwise both tabs could start threads on one component.
        with _ACTIVE_RUNS_LOCK:
            already_running = _ACTIVE_RUNS.get(run_key, {}).get("status") == "running"
            if not already_running:
                params_to_run = [ep for ep in explorer_params if ep[0] in (to_run_labels or selected_param_labels)]
                # "Re-analyze" (nothing left to run) clears the cache for the
                # selected parameters and redoes them.
                if not to_run_labels:
                    for ep in params_to_run:
                        st.session_state["scan_detail_dfs"].pop(ep[0], None)
                        st.session_state["scan_summary_rows"].pop(ep[0], None)

                # Runs on a background thread tied to the Streamlit server process, not this tab
                new_run_state = {
                    "lock": threading.Lock(),
                    "status": "running",
                    "done": 0,
                    "total": len(params_to_run),
                    "current_label": "",
                    "summary_rows": dict(st.session_state["scan_summary_rows"]),
                    "detail_dfs": dict(st.session_state["scan_detail_dfs"]),
                    "param_types": dict(st.session_state["scan_param_types"]),
                    "errors": [],
                    "stop_requested": False,
                    "stopped": False,
                }
                _ACTIVE_RUNS[run_key] = new_run_state
                threading.Thread(
                    target=_run_full_analysis_background,
                    args=(driver, comp, params_to_run, new_run_state, username_input, password_input),
                    daemon=True,
                ).start()
        # Collapse the parameter picker after a run has started
        st.session_state["params_expander_expanded"] = False
        if already_running:
            st.warning("A background run for this component was just started from another tab. Refresh to see its progress.")
        else:
            st.rerun()

    if bg_running:
        with bg_run["lock"]:
            done, total = bg_run["done"], bg_run["total"]
            current_label = bg_run["current_label"]
            n_errors = len(bg_run["errors"])
            stop_requested = bg_run["stop_requested"]
        st.progress(done / total if total else 0)
        st.info(f"⏳ {done}/{total}: {current_label}")
        if n_errors:
            st.warning(f"{n_errors} item(s) need a look so far. Check back at the end for details.")
        if stop_requested:
            st.info(
                "Stopping after the parameter currently being tested finishes its own "
                "read/write/reset cycle on eLCA, so nothing is left half-changed there. "
                "This can still take a few minutes if that parameter is mid-retry."
            )
        elif st.button("⏹ Stop analysis", key="stop_full_analysis"):
            # Only sets a flag: the background thread itself decides when it's safe to actually stop
            # Nothing already written to eLCA is touched by this click.
            with bg_run["lock"]:
                bg_run["stop_requested"] = True
            st.rerun()
        # Auto-refresh
        time.sleep(2)
        st.rerun()
    elif bg_run is not None and bg_run["status"] == "done":
        # Background run finished (completed or stopped): merge completed results
        # into the session cache and retire the entry to prevent re-running.
        was_stopped = bg_run.get("stopped", False)
        with bg_run["lock"]:
            st.session_state["scan_summary_rows"].update(bg_run["summary_rows"])
            st.session_state["scan_detail_dfs"].update(bg_run["detail_dfs"])
            st.session_state["scan_param_types"].update(bg_run["param_types"])
            errors = list(bg_run["errors"])
        del _ACTIVE_RUNS[run_key]
        st.session_state["last_run_success_msg"] = (
            "Analysis stopped. Results for every parameter tested before Stop was clicked "
            "were kept; the rest were skipped, and nothing on eLCA was left mid-change."
            if was_stopped else "Full Analysis finished."
        )
        st.session_state["last_run_errors"] = errors
        # No st.rerun(): it would clear st.success() before display. Continuing lets
        # the summary below use the fresh results in the same page load.

    if st.session_state.get("last_run_success_msg"):
        st.success(st.session_state["last_run_success_msg"])
        if st.session_state.get("last_run_errors"):
            st.warning(
                "Some items need a second look (a failed parameter, or a lifetime marker "
                "that may not have fully cleaned up in eLCA): "
                + "; ".join(st.session_state["last_run_errors"])
            )
        if st.button("Dismiss", key="dismiss_run_result"):
            st.session_state["last_run_success_msg"] = None
            st.session_state["last_run_errors"] = []
            st.rerun()

    # Coarse-grained summary
    analyzed_labels = [l for l in selected_param_labels if l in st.session_state["scan_detail_dfs"]]

    if analyzed_labels:
        st.divider()
        st.subheader("Summary")

        # Deferred collapse
        if st.session_state.pop("_collapse_params_after_summary", False):
            st.session_state["params_expander_expanded"] = False

        rows = []
        baseline_points = []  # [(label, baseline_gwp), ...], grouped by closeness below
        for label in analyzed_labels:
            detail_df = st.session_state["scan_detail_dfs"][label]
            param_type = st.session_state["scan_param_types"].get(label, "")
            shape = analyze_shape(detail_df)
            if shape is None:
                continue
            is_nl = (not shape["is_linear"]) or shape["is_stepwise"]
            # Small preview chart, colored by shape category
            rows.append({
                "Parameter": _display_label(label),
                "_raw_label": label,
                "GWP Range": round(shape["gwp_range"], 4),
                "Relative Range (%)": round(shape["relative_range"], 2),
                "Non-linear": is_nl,
                "Interpretation": short_interpretation(param_type, shape),
                "Shape": shape_thumbnail(detail_df, is_nl),
            })
            # Each baseline_gwp is read fresh right before its own sweep
            # then grouped below with a small tolerance so floating-point noise doesn't look
            # like a real difference between parameters.
            b_gwp = shape.get("baseline_gwp")
            if b_gwp:
                baseline_points.append((label, b_gwp))

        summary_table = pd.DataFrame(rows).sort_values(
            by="Relative Range (%)", ascending=False
        ).reset_index(drop=True)
        summary_table.index = summary_table.index + 1

        # Group by closeness to the sorted neighbor rather than a fixed grid
        TOL = 1.001  # 0.1% relative tolerance between neighboring baselines
        groups = []
        for label, b_gwp in sorted(baseline_points, key=lambda p: p[1]):
            if groups and abs(b_gwp) <= abs(groups[-1][-1][1]) * TOL:
                groups[-1].append((label, b_gwp))
            else:
                groups.append([(label, b_gwp)])

        if len(groups) > 1:
            # Multiple baseline groups suggest eLCA was edited between tests. GWP Range
            # remains valid, but Relative Range (%) isn't comparable. Warn only; full
            # re-analysis is the only consistent fix. Show each group's own baseline
            # instead of guessing which one is outdated.
            group_summaries = []
            overflow_groups = []
            max_labels_shown = 5
            for group in groups:
                group_baseline = group[0][1]
                group_labels = [label for label, _ in group]
                shown = group_labels[:max_labels_shown]
                label_text = ", ".join(_display_label(l) for l in shown)
                if len(group_labels) > max_labels_shown:
                    label_text += f", +{len(group_labels) - max_labels_shown} more (see below)"
                    overflow_groups.append((group_baseline, group_labels))
                group_summaries.append(
                    f"baseline {group_baseline:.2f} kg CO₂-eq/m² "
                    f"({len(group_labels)} parameter{'s' if len(group_labels) != 1 else ''}): "
                    + label_text
                )
            warning_box(
                "The cached parameters below don't share the same baseline GWP "
                "(eLCA's state likely changed between some of these tests), so "
                "the Relative Range (%) and ranking may not be directly "
                "comparable across all rows. To check which is correct: open "
                "this component in eLCA directly, compare its current total "
                "GWP to the baselines below, then re-analyze the group that "
                "doesn't match (or select all and click Re-analyze above for "
                "a fully consistent set). Groups found: "
                + " | ".join(group_summaries) + "."
            )
            for group_baseline, group_labels in overflow_groups:
                with st.expander(
                    f"Show all {len(group_labels)} parameters at baseline "
                    f"{group_baseline:.2f} kg CO₂-eq/m²"
                ):
                    for l in group_labels:
                        st.write(f"- {_display_label(l)}")

        note_box(
            "Shape color: <b style='color:#2e7d32'>green</b> = linear, "
            "<b style='color:#e67e22'>amber</b> = non-linear/stepwise. "
            "Click a row to jump to it below."
        )
        summary_event = st.dataframe(
            summary_table,
            use_container_width=True,
            column_order=("Parameter", "GWP Range", "Relative Range (%)", "Non-linear", "Interpretation", "Shape"),
            column_config={
                "GWP Range": st.column_config.NumberColumn(
                    "GWP Range",
                    help="The gap between the highest and lowest GWP seen while testing this "
                    "parameter across its full range, in kg CO₂-eq/m². A raw amount, not a "
                    "percentage.",
                ),
                "Relative Range (%)": st.column_config.NumberColumn(
                    "Relative Range (%)",
                    help="That same GWP gap, shown as a percentage of the baseline GWP, i.e. "
                    "how much this parameter alone can move the result. Rows are sorted by this "
                    "column, highest first.",
                ),
                "Shape": st.column_config.ImageColumn(
                    "Shape",
                    help="Green = linear, amber = non-linear/stepwise. Axis ticks show the tested range (x) and GWP range (y).",
                ),
            },
            on_select="rerun",
            selection_mode="single-row",
            key="summary_table_select",
        )
        st.caption(
            "* GWP Range = highest minus lowest GWP for that parameter. Relative Range (%) = "
            "that gap vs. baseline GWP: rows are sorted by this."
        )

        # Clicking a row jumps to inspection. Track whether the exact row was already
        # selected to avoid re-popping the prompt on unrelated reruns.
        try:
            selected_rows = summary_event.selection["rows"]
        except Exception:
            selected_rows = []

        if selected_rows:
            # Original (untranslated) label: session_state and cache lookups
            # key off this. Only the note_box text below uses the translated version.
            clicked_label = summary_table.iloc[selected_rows[0]]["_raw_label"]
            if st.session_state.get("summary_jump_handled_for") != clicked_label:
                # Flag is only set inside the Yes/No handlers below
                note_box(
                    f"Inspect <b>{_display_label(clicked_label)}</b>? Click Yes to jump to it below."
                )
                col_yes, col_no, _ = st.columns([1, 1, 4])
                with col_yes:
                    if st.button("Yes", key="jump_yes"):
                        st.session_state["selected_detail_label_widget"] = clicked_label
                        st.session_state["summary_jump_handled_for"] = clicked_label
                        st.session_state["scroll_to_inspect"] = True
                        st.rerun()
                with col_no:
                    if st.button("No", key="jump_no"):
                        st.session_state["summary_jump_handled_for"] = clicked_label
                        st.rerun()
        else:
            # Row unchecked: clear the "already answered" memory so
            # re-checking the same row later counts as a fresh ask.
            st.session_state.pop("summary_jump_handled_for", None)

        non_linear_count = int(summary_table["Non-linear"].sum())
        if non_linear_count:
            nl_names = summary_table[summary_table["Non-linear"]]["Parameter"].tolist()
            warning_box(
                f"{non_linear_count} of {len(summary_table)} analyzed parameters show non-linear "
                f"or stepwise GWP response: " + ", ".join(f"<b>{n}</b>" for n in nl_names) + ". "
                f"A simple percentage-based sensitivity result is not reliable for these. "
                f"Inspect their full curves below."
            )
        if len(summary_table) > 0:
            top_row = summary_table.iloc[0]
            note_box(
                f"<b>{top_row['Parameter']}</b> has the largest GWP range across the analyzed "
                f"parameters. Select it below to see its full curve and a more "
                f"detailed explanation."
            )

        # Compare element GWP to building average (not shown in eLCA UI).
        # project_gwp_per_m2 is cached at load time.
        project_gwp_per_m2 = comp.get("project_gwp_per_m2")
        if project_gwp_per_m2:
            any_shape = analyze_shape(st.session_state["scan_detail_dfs"][analyzed_labels[0]])
            element_gwp = any_shape.get("baseline_gwp") if any_shape else None
            if element_gwp and project_gwp_per_m2:
                ratio = element_gwp / project_gwp_per_m2
                extra = (
                    " Worth checking whether that's expected for this type of component, or a "
                    "sign it deserves closer attention."
                    if ratio > 1.5 else ""
                )
                note_box(
                    f"For context: <b>{_translate_element_name(comp['name'])}</b>'s own baseline GWP is {element_gwp:.3f} "
                    f"kg CO₂-eq/m², while the whole building averages {project_gwp_per_m2:.3f} "
                    f"kg CO₂-eq/m² (NGF) over the same reference period. So, per square meter, "
                    f"this element is currently about {ratio:.1f}x "
                    f"{'more' if ratio > 1 else 'less'} carbon-intensive than the building's "
                    f"overall average.{extra}"
                )

        # Quick ±X% sensitivity ranking (classic OAT)
        variation_pct = st.session_state["oat_variation_pct"]
        oat_rows = []
        for label in analyzed_labels:
            oat = oat_relative_change(st.session_state["scan_detail_dfs"][label], variation_pct)
            if oat is None:
                continue
            oat_rows.append({
                "Parameter": label,
                "up": oat["rel_change_increase"],
                "down": oat["rel_change_decrease"],
            })

        if oat_rows:
            st.divider()
            st.subheader(f"Quick sensitivity ranking (±{variation_pct}% change per parameter)")
            st.write(
                f"If only this ONE parameter is changed by {variation_pct}% (all others stay at "
                f"baseline), how much does GWP move? Ranked by whichever direction has the "
                f"bigger effect."
            )

            # oat_df_all keeps every analyzed parameter's OAT value; oat_df
            # is the chart-only top-15 subset used below for bar-specific warnings.
            oat_df_all = pd.DataFrame(oat_rows)
            oat_df_all["biggest_abs"] = oat_df_all[["up", "down"]].abs().max(axis=1)
            oat_df = oat_df_all.sort_values("biggest_abs", ascending=False).head(15)

            max_change = oat_df["biggest_abs"].max() or 1
            colors = []
            for val in oat_df["biggest_abs"]:
                ratio = val / max_change
                colors.append("#d62728" if ratio >= 0.66 else "#ff7f0e" if ratio >= 0.33 else "#2ca02c")

            # Bar design
            fig_height = max(4, len(oat_df) * 0.6)
            fig, ax = plt.subplots(figsize=(14, fig_height))
            y_pos = np.arange(len(oat_df))
            ax.barh(y_pos - 0.18, oat_df["up"], height=0.32, color=colors)
            ax.barh(y_pos + 0.18, oat_df["down"], height=0.32, color=colors, hatch="///", edgecolor="white", linewidth=0)
            ax.set_yticks(y_pos)
            ax.set_yticklabels([_display_label(p) for p in oat_df["Parameter"]])
            ax.axvline(x=0, color="#888888", linewidth=1)
            ax.set_xlabel("GWP change from baseline (%)", fontsize=10)
            ax.invert_yaxis()
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.grid(axis="x", alpha=0.25, linestyle="--")
            span = max(max_change * 1.25, 1.0)
            ax.set_xlim(-span, span)

            from matplotlib.patches import Patch
            plt.tight_layout()
            reserved_inches = 0.7
            fig.subplots_adjust(top=1 - reserved_inches / fig_height)
            # Legends pinned to fixed figure corners
            magnitude_handles = [
                Patch(facecolor="#d62728", label="High impact"),
                Patch(facecolor="#ff7f0e", label="Medium impact"),
                Patch(facecolor="#2ca02c", label="Low impact"),
            ]
            direction_handles = [
                Patch(facecolor="#888888", label=f"+{variation_pct}% change"),
                Patch(facecolor="#888888", hatch="///", edgecolor="white", label=f"-{variation_pct}% change"),
            ]
            fig.legend(
                handles=magnitude_handles, title="Magnitude", loc="upper left",
                bbox_to_anchor=(0.01, 0.97), fontsize=8, title_fontsize=8, frameon=False,
                handlelength=1.4, handletextpad=0.5,
            )
            fig.legend(
                handles=direction_handles, title="Direction", loc="upper right",
                bbox_to_anchor=(0.99, 0.97), fontsize=8, title_fontsize=8, frameon=False,
                handlelength=1.4, handletextpad=0.5,
            )
            fig.suptitle(
                "Parameter Sensitivity: Quick OAT Ranking", x=0.5,
                fontsize=12, fontweight="bold", y=0.99,
            )
            st.pyplot(fig)

            # Small variations may miss non-linear thresholds and show ~0%.
            # Flag explicitly using raw labels to avoid translation mismatch.
            nl_lookup = summary_table.set_index("_raw_label")["Non-linear"].to_dict()
            # Limit to top-15 (oat_df) to match chart bars.
            # Threshold is relative to max_change so flat bars scale with x-axis.
            hidden = [
                row["Parameter"] for _, row in oat_df.iterrows()
                if nl_lookup.get(row["Parameter"]) and row["biggest_abs"] < max_change * 0.02
            ]
            if hidden:
                names = ", ".join(f"<b>{_display_label(n)}</b>" for n in hidden)
                warning_box(
                    f"{names} "
                    + ("have" if len(hidden) > 1 else "has")
                    + f" almost no measured effect at this ±{variation_pct}% check, but "
                    + ("they're" if len(hidden) > 1 else "it's")
                    + f" flagged non-linear, since a ±{variation_pct}% wiggle around baseline "
                    f"doesn't happen to cross their real threshold. That threshold is real "
                    f"and can be large; it just sits further out than this quick check "
                    f"looks. Select it below to see the actual jump."
                )

            # Count excluded non-linear parameters outside top-15.
            # Kept as a simple count to show extra sensitive inputs exist.
            n_not_shown = len(oat_df_all) - len(oat_df)
            if n_not_shown > 0:
                not_shown_labels = set(oat_df_all["Parameter"]) - set(oat_df["Parameter"])
                n_not_shown_nl = sum(1 for n in not_shown_labels if nl_lookup.get(n))
                note_box(
                    f"Only the top 15 parameters by effect are plotted above: "
                    f"{n_not_shown} more {'were' if n_not_shown > 1 else 'was'} analyzed "
                    f"but didn't make the cut."
                    + (
                        f" {n_not_shown_nl} of {'those' if n_not_shown > 1 else 'it'} "
                        f"{'are' if n_not_shown_nl > 1 else 'is'} flagged non-linear, so not "
                        f"necessarily flat, just not among the biggest movers here, and "
                        f"being non-linear means even a small change to them could still "
                        f"cause a big GWP jump. Check Inspect if any of them matter to you."
                        if n_not_shown_nl else ""
                    )
                )

        # Inspect a single parameter
        # a summary-table row click can jump straight to it: uses only cached results, no new eLCA calls.
        st.divider()
        st.markdown('<div id="inspect-anchor"></div>', unsafe_allow_html=True)
        if st.session_state.pop("scroll_to_inspect", False):
            components.html(
                """
                <script>
                setTimeout(function() {
                    var el = window.parent.document.getElementById('inspect-anchor');
                    if (el) { el.scrollIntoView({behavior: 'smooth', block: 'start'}); }
                }, 150);
                </script>
                """,
                height=0,
            )
        st.subheader("Inspect a parameter")
        st.write(
            "Pick a parameter below (or click a row in the summary table above) to see "
            "its full curve and detailed interpretation."
        )

        if (
            "selected_detail_label_widget" in st.session_state
            and st.session_state["selected_detail_label_widget"] not in analyzed_labels
        ):
            del st.session_state["selected_detail_label_widget"]
        selected_detail_label = st.selectbox(
            "Select parameter to inspect",
            analyzed_labels,
            key="selected_detail_label_widget",
            format_func=_display_label,
        )

        detail_df = st.session_state["scan_detail_dfs"][selected_detail_label]
        param_type = st.session_state["scan_param_types"].get(selected_detail_label, "")
        detail_shape = analyze_shape(detail_df)

        if detail_shape is None:
            st.warning("Not enough data points were captured for this parameter.")
        else:
            df_plot = detail_df.dropna(subset=["GWP"]).sort_values("Parameter Value")

            fig_detail, ax_detail = plt.subplots(figsize=(10, 5))
            ax_detail.plot(
                df_plot["Parameter Value"], df_plot["GWP"],
                marker="o", linewidth=2, markersize=6, color="#1f77b4"
            )
            ax_detail.axvline(x=1.0, color="#888888", linestyle="--", linewidth=1, alpha=0.6)
            ax_detail.set_xlabel("Parameter value relative to baseline", fontsize=10)
            ax_detail.set_ylabel("GWP (kg CO₂-eq / m²)", fontsize=10)
            ax_detail.set_title(f"GWP Response: {_display_label(selected_detail_label)}", fontsize=12, fontweight="bold", pad=12)
            ax_detail.spines["top"].set_visible(False)
            ax_detail.spines["right"].set_visible(False)
            ax_detail.grid(True, alpha=0.25, linestyle="--")
            plt.tight_layout()
            st.pyplot(fig_detail)

            col1, col2, col3 = st.columns(3)
            col1.metric("GWP Range", f"{detail_shape['gwp_range']:.4f}")
            col2.metric("Relative Range", f"{detail_shape['relative_range']:.2f}%")
            col3.metric("Shape", "Non-linear" if (not detail_shape["is_linear"] or detail_shape["is_stepwise"]) else "Linear")

            st.subheader("What do these results mean?")
            render_full_interpretation(
                selected_detail_label, param_type, detail_df, detail_shape,
                reference_period=comp.get("reference_period"),
                all_summary_rows=st.session_state.get("scan_summary_rows"),
                all_detail_dfs=st.session_state.get("scan_detail_dfs"),
                all_param_types=st.session_state.get("scan_param_types"),
                additivity_notes=st.session_state.get("param_additivity_notes"),
            )

            with st.expander("Raw data"):
                st.caption(
                    "* \"Total GWP\" belongs to the element you connected to, not to one of its "
                    "layers. Want a sub-element's own GWP instead? Paste **that sub-element's "
                    "own link** in the eLCA Element Link field above and connect directly to it. "
                    "Extra columns (A1-A3, B4, etc.) break the total down by life-cycle stage. "
                    "The highlighted row is the baseline value (Parameter Value = 1.0x)."
                )

                def _highlight_baseline_row(row):
                    # use tolerance instead of exact equality for 1.0 (avoids float drift).
                    # matches the baseline-finding logic used across the app.
                    is_baseline = abs(row["Parameter Value"] - 1.0) < 1e-6
                    return ["background-color: rgba(255, 213, 79, 0.18)" if is_baseline else "" for _ in row]

                st.dataframe(
                    df_plot.rename(columns={"GWP": "Total GWP"}).style.apply(
                        _highlight_baseline_row, axis=1
                    ),
                    use_container_width=True,
                )

        # Compare multiple parameters on one chart; reuses cached curves, no new calls.
        st.divider()
        with st.expander("Compare multiple parameters", expanded=True):
            st.write(
                "Overlay several parameters' curves on one chart to compare their shape and "
                "magnitude directly."
            )

            # Short labels for the pills/legend
            compare_labels = st.multiselect(
                "Parameters to compare",
                analyzed_labels,
                default=analyzed_labels[: min(3, len(analyzed_labels))],
                max_selections=8,
                format_func=_short_param_label,
                key="compare_labels_widget",
            )
            st.caption(
                "* Up to 8 at once: remove one (**×**) to add a different one. Full names "
                "are in the table above."
            )
            hint_box(
                "Names can look similar and picks sometimes need a second click: please double-check "
                "your selection."
            )
            if len(compare_labels) >= 2:
                fig_cmp, ax_cmp = plt.subplots(figsize=(13, 5.5))
                palette = plt.cm.tab10.colors
                for i, lbl in enumerate(compare_labels):
                    d_cmp = (
                        st.session_state["scan_detail_dfs"][lbl]
                        .dropna(subset=["GWP"])
                        .sort_values("Parameter Value")
                    )
                    if len(d_cmp) < 2:
                        continue
                    ax_cmp.plot(
                        d_cmp["Parameter Value"], d_cmp["GWP"],
                        marker="o", markersize=4, linewidth=1.8,
                        color=palette[i % len(palette)], label=_short_param_label(lbl, style="legend"),
                    )
                ax_cmp.axvline(x=1.0, color="#888888", linestyle="--", linewidth=1, alpha=0.6)
                ax_cmp.set_xlabel("Parameter value relative to baseline", fontsize=10)
                ax_cmp.set_ylabel("GWP (kg CO₂-eq / m²)", fontsize=10)
                ax_cmp.set_title("Parameter comparison", fontsize=12, fontweight="bold", pad=12)
                ax_cmp.spines["top"].set_visible(False)
                ax_cmp.spines["right"].set_visible(False)
                ax_cmp.grid(True, alpha=0.25, linestyle="--")
                # Place legend outside plot area to avoid overlap with data lines.
                # Extra figure width gives the legend room without squeezing the plot.
                ax_cmp.legend(
                    fontsize=8, loc="upper left", bbox_to_anchor=(1.01, 1),
                    borderaxespad=0, frameon=False,
                )
                fig_cmp.tight_layout(rect=[0, 0, 0.8, 1])
                st.pyplot(fig_cmp)
            elif len(compare_labels) == 1:
                st.caption("Pick at least one more parameter to compare against.")


with tab2:
    if "parameter_result" not in st.session_state:
        st.session_state["parameter_result"] = None

    if "additivity_result" not in st.session_state:
        st.session_state["additivity_result"] = None

    st.subheader("Parameter Explorer")
    st.write(
        "Adjust the parameters below and click **Calculate New GWP** to see how your "
        "changes affect the environmental impact. The additivity check reveals whether "
        "combined parameter changes behave independently or interact with each other."
    )

    if not st.session_state["scan_detail_dfs"]:
        st.warning(
            "Run the **Full Analysis** tab first to get the most out of this tool. "
            "It identifies which parameters have the strongest influence on GWP, "
            "so you know where to focus your changes here."
        )

    # Dynamically build inputs from component definition.
    # Split "quantity" params: whole-component to Component Quantities, material-level amounts to layer parameters.
    quantity_params = [
        ep for ep in explorer_params if ep[1] == "quantity" and not ep[0].endswith(" - amount")
    ]
    material_amount_params = [
        ep for ep in explorer_params if ep[1] == "quantity" and ep[0].endswith(" - amount")
    ]
    size_params = [ep for ep in explorer_params if ep[1] != "quantity"]
    size_only = [ep for ep in size_params if ep[1] == "size"]
    lifetime_only = [ep for ep in size_params if ep[1] == "lifetime"]
    area_ratio_only = [ep for ep in size_params if ep[1] == "area_ratio"]

    # stable key per parameter so the reset button can clear the exact number_input.
    widget_key_for = {}
    for i, ep in enumerate(quantity_params):
        widget_key_for[ep[3]] = f"exp_qty_{i}"
    for i, ep in enumerate(material_amount_params):
        widget_key_for[ep[3]] = f"exp_matqty_{i}"
    for i, ep in enumerate(size_only):
        widget_key_for[ep[3]] = f"exp_size_{i}"
    for i, ep in enumerate(lifetime_only):
        widget_key_for[ep[3]] = f"exp_life_{i}"
    for i, ep in enumerate(area_ratio_only):
        widget_key_for[ep[3]] = f"exp_area_{i}"

    if st.button("↺ Reset to baseline values"):
        # Overwrite session_state before creating widgets.
        # Streamlit requires modifying widget keys before instantiation to handle reset properly.
        for ep in explorer_params:
            param_key, baseline_val = ep[3], ep[4]
            wkey = widget_key_for.get(param_key)
            if wkey is not None:
                st.session_state[wkey] = baseline_val
        st.session_state["area_ratio_synced_keys"] = set()

    col1, col2 = st.columns(2)
    user_values = {}

    with col1:
        st.markdown("### Component Quantities")
        for ep in quantity_params:
            label, _, _, param_key, baseline_val, step, min_val, max_val = ep
            user_values[param_key] = st.number_input(
                _display_label(label), min_value=min_val, value=baseline_val, step=step, key=widget_key_for[param_key]
            )

    with col2:
        st.markdown("### Layer Parameters")

        if size_only:
            st.markdown("**Thickness (mm)**")
            for ep in size_only:
                label, _, _, param_key, baseline_val, step, min_val, max_val = ep
                user_values[param_key] = st.number_input(
                    _display_label(label), min_value=min_val, value=baseline_val, step=step, key=widget_key_for[param_key]
                )

        if material_amount_params:
            st.markdown("**Amount**")
            for ep in material_amount_params:
                label, _, _, param_key, baseline_val, step, min_val, max_val = ep
                user_values[param_key] = st.number_input(
                    _display_label(label), min_value=min_val, value=baseline_val, step=step, key=widget_key_for[param_key]
                )

        if lifetime_only:
            st.markdown("**Lifetime (yr)**")
            for ep in lifetime_only:
                label, _, _, param_key, baseline_val, step, min_val, max_val = ep
                user_values[param_key] = st.number_input(
                    _display_label(label), min_value=min_val, value=baseline_val, step=step, key=widget_key_for[param_key]
                )

        if area_ratio_only:
            st.markdown("**Area ratio / Share (%)**")
            st.caption(
                "Each of these belongs to a split layer shared with one other material: "
                "its paired partner is adjusted automatically to keep the two summing to 100%, "
                "including in the field below (it updates live as you type)."
            )
            # Track directly edited side vs mirrored side to prevent double-counting
            if "area_ratio_synced_keys" not in st.session_state:
                st.session_state["area_ratio_synced_keys"] = set()

            for ep in area_ratio_only:
                label, param_key, baseline_val, step, min_val, max_val = ep[0], ep[3], ep[4], ep[5], ep[6], ep[7]
                partner_key = ep[8] if len(ep) > 8 else None
                own_wkey = widget_key_for[param_key]

                def _sync_partner_share(own_wkey=own_wkey, param_key=param_key, partner_key=partner_key):
                    # Sync partner value before widget rerun.
                    # Updates the paired number_input instantly without waiting for Calculate New GWP.
                    partner_wkey = widget_key_for.get(partner_key) if partner_key else None
                    if partner_wkey is not None and own_wkey in st.session_state:
                        st.session_state[partner_wkey] = round(100.0 - st.session_state[own_wkey], 4)
                    st.session_state["area_ratio_synced_keys"].discard(param_key)
                    if partner_key:
                        st.session_state["area_ratio_synced_keys"].add(partner_key)

                user_values[param_key] = st.number_input(
                    _display_label(label), min_value=min_val, max_value=max_val, value=baseline_val, step=step,
                    key=own_wkey, on_change=_sync_partner_share
                )

            # The mirrored side of a pair is pinned back to its baseline
            for synced_key in st.session_state.get("area_ratio_synced_keys", set()):
                if synced_key in user_values:
                    for ep in area_ratio_only:
                        if ep[3] == synced_key:
                            user_values[synced_key] = ep[4]
                            break

    # Which currently-changed parameters haven't been analyzed yet?
    # Scenario Interpretation needs Full Analysis's measured sensitivity to
    # give a reliable read, so the button is locked until they're covered.
    key_to_label = {ep[3]: ep[0] for ep in explorer_params}
    key_to_baseline = {ep[3]: ep[4] for ep in explorer_params}
    unanalyzed_changed = sorted({
        key_to_label[key] for key, val in user_values.items()
        if abs(val - key_to_baseline[key]) > 0.001
        and key_to_label[key] not in st.session_state["scan_detail_dfs"]
    })

    if unanalyzed_changed:
        st.warning(
            "**Calculate New GWP** is locked because " +
            ", ".join(f"**{_display_label(l)}**" for l in unanalyzed_changed) +
            (" hasn't" if len(unanalyzed_changed) == 1 else " haven't") +
            " been analyzed in **Full Analysis** yet. Either run Full Analysis for "
            + ("it" if len(unanalyzed_changed) == 1 else "them") +
            " first, or reset the value(s) back to baseline."
        )

    bg_run_here = _ACTIVE_RUNS.get(_run_key(comp))
    bg_running_here = bg_run_here is not None and bg_run_here["status"] == "running"
    if bg_running_here:
        st.warning("**Calculate New GWP** is locked while Full Analysis is running in the background.")

    explorer_action_key = _action_key(comp, "explorer")
    additivity_action_key = _action_key(comp, "additivity")
    explorer_action = _ACTIVE_ACTIONS.get(explorer_action_key)
    explorer_running = explorer_action is not None and explorer_action["status"] == "running"
    additivity_action = _ACTIVE_ACTIONS.get(additivity_action_key)
    additivity_running = additivity_action is not None and additivity_action["status"] == "running"
    if additivity_running:
        st.warning("**Calculate New GWP** is locked while **Run Additivity Check** is in progress.")

    calculate_button = st.button(
        "Calculate New GWP",
        disabled=bool(unanalyzed_changed) or bg_running_here or explorer_running or additivity_running,
    )

    if calculate_button:
        # Clear previous scenario before the slow Selenium call.
        # Prevents Streamlit from showing stale metrics/charts while waiting.
        st.session_state["parameter_result"] = None
        st.session_state["additivity_result"] = None
        captured_values = dict(user_values)
        new_action_state = {
            "lock": threading.Lock(), "status": "running",
            "result": None, "error": None,
            "stop_requested": False, "stopped": False,
        }
        _ACTIVE_ACTIONS[explorer_action_key] = new_action_state
        threading.Thread(
            target=_run_stoppable_action_background,
            args=(
                lambda should_stop: _call_selenium_with_relogin(
                    lambda: run_parameter_explorer_selenium(
                        driver, comp, user_values=captured_values, should_stop=should_stop
                    ),
                    driver, username_input, password_input,
                ),
                new_action_state,
            ),
            daemon=True,
        ).start()
        st.rerun()

    if explorer_running:
        with explorer_action["lock"]:
            stop_requested = explorer_action["stop_requested"]
        st.info("⏳ Calculating new scenario...")
        if stop_requested:
            st.info(
                "Stopping as soon as the parameter currently being changed is reset back to "
                "baseline, so nothing is left half-changed on eLCA."
            )
        elif st.button("⏹ Stop", key="stop_explorer_calc"):
            with explorer_action["lock"]:
                explorer_action["stop_requested"] = True
            st.rerun()
        time.sleep(1)
        st.rerun()
    elif explorer_action is not None and explorer_action["status"] == "done":
        with explorer_action["lock"]:
            stopped = explorer_action["stopped"]
            outcome = explorer_action["result"]
            bg_error = explorer_action["error"]
        del _ACTIVE_ACTIONS[explorer_action_key]
        if stopped:
            st.session_state["parameter_result"] = None
            st.info("Scenario calculation stopped. Every value it had changed was reset back to baseline first.")
        elif bg_error is not None:
            st.session_state["parameter_result"] = None
            _session_expired_warning(bg_error)
        else:
            result, error = outcome
            if error is not None:
                # Most likely an idle eLCA session: a re-login was already
                # tried automatically inside _call_selenium_with_relogin and
                # still failed.
                st.session_state["parameter_result"] = None
                _session_expired_warning(error)
            else:
                st.session_state["parameter_result"] = result
                # Build parameter_inputs for interpretation
                parameter_inputs = {}
                for ep in explorer_params:
                    label, param_key, baseline_val = ep[0], ep[3], ep[4]
                    parameter_inputs[label] = (user_values.get(param_key, baseline_val), baseline_val)
                st.session_state["parameter_inputs"] = parameter_inputs

    if st.session_state["parameter_result"] is not None:
        result = st.session_state["parameter_result"]

        st.success("Scenario calculated.")

        col_a, col_b, col_c = st.columns(3)

        col_a.metric("Baseline GWP", f"{result['baseline_gwp']:.2f}")
        col_b.metric("New GWP", f"{result['new_gwp']:.2f}")
        col_c.metric(
            "Change",
            f"{result['relative_change']:.2f}%",
            delta=f"{result['absolute_change']:.2f}"
        )

        if result.get("cleanup_warnings"):
            warning_box(
                "This result is correct, but eLCA may still show a leftover custom "
                "lifetime setting from this calculation: "
                + "; ".join(result["cleanup_warnings"])
            )

        st.subheader("Scenario Interpretation")

        inputs = st.session_state.get("parameter_inputs", {})
        changed = []
        for label, (new_val, baseline_val) in inputs.items():
            if abs(new_val - baseline_val) > 0.001:
                pct = ((new_val - baseline_val) / baseline_val) * 100
                if abs(pct) < 0.05:
                    continue
                direction = "increased" if pct > 0 else "decreased"
                changed.append((label, pct, direction))

        changed_sorted = sorted(changed, key=lambda x: abs(x[1]), reverse=True)

        def _fmt(label, pct):
            return f"<b>{_display_label(label)}</b> ({pct:+.1f}%)"

        def _param_direction_sign(label):
            """Return +1 if increasing param increases GWP (e.g. thickness/amount),
            -1 if it decreases GWP (e.g. longer lifetime means fewer replacements).
            Calculated directly from the parameter curve.
            """
            df = st.session_state["scan_detail_dfs"].get(label)
            if df is None:
                return 1
            d = df.dropna(subset=["GWP"]).sort_values("Parameter Value")
            if len(d) < 2:
                return 1
            slope = np.polyfit(d["Parameter Value"].values, d["GWP"].values, 1)[0]
            return 1 if slope >= 0 else -1

        def _toward_baseline(pct):
            return "Increasing" if pct < 0 else "Decreasing"

        # GWP sensitivity per parameter, from Full Analysis's measured relative range
        sens_map = {
            label: abs(row.get("Relative Range (%)", 0))
            for label, row in st.session_state.get("scan_summary_rows", {}).items()
        }

        if result["relative_change"] > 0:
            st.warning(
                f"This scenario **increases** the GWP by **{result['relative_change']:.2f}%** "
                f"({result['absolute_change']:+.2f} kg CO₂-eq / m²)."
            )
        elif result["relative_change"] < 0:
            st.success(
                f"This scenario **reduces** the GWP by **{abs(result['relative_change']):.2f}%** "
                f"({result['absolute_change']:+.2f} kg CO₂-eq / m²)."
            )
        else:
            st.info("The parameter changes in this scenario do not affect the GWP.")

        if changed_sorted:

            # All changed parameters are guaranteed in sens_map (button is locked until Full Analysis completes).
            # Waterfall: interpolates individual parameter impact using OAT curves.
            # The final bar shows the actual eLCA combined result, highlighting parameter interactions.
            def _individual_gwp_delta(label):
                new_val, baseline_val = inputs[label]
                if not baseline_val:
                    return 0.0
                factor = new_val / baseline_val
                d = st.session_state["scan_detail_dfs"][label].dropna(subset=["GWP"]).sort_values("Parameter Value")
                xv, yv = d["Parameter Value"].values, d["GWP"].values
                factor_clipped = min(max(factor, xv.min()), xv.max())
                gwp_at_factor = np.interp(factor_clipped, xv, yv)
                own_baseline_row = d.iloc[(d["Parameter Value"] - 1.0).abs().argsort()[:1]]
                own_baseline = own_baseline_row["GWP"].values[0]
                return gwp_at_factor - own_baseline

            baseline_gwp_val = result["baseline_gwp"]
            actual_total = result["new_gwp"]

            segments = []
            running = baseline_gwp_val
            for label, pct, direction in changed_sorted:
                delta = _individual_gwp_delta(label)
                segments.append((label, pct, delta))
                running += delta
            expected_total = running
            # Reuses each parameter's waterfall-bar contribution so the
            # driving/offsetting narrative below can't contradict the chart.
            segment_delta = {l: d for l, p, d in segments}

            # Sort by actual GWP impact (segment_delta), not input change size.
            # Ensures "main driver" text matches the largest waterfall bars.
            changed_by_impact = sorted(
                changed_sorted, key=lambda x: abs(segment_delta.get(x[0], 0.0)), reverse=True
            )

            def short(l, max_len=18):
                # Trim at the last word boundary, not mid-word
                if len(l) <= max_len:
                    return l
                cut = l[:max_len]
                if " " in cut:
                    cut = cut[: cut.rfind(" ")]
                return cut.rstrip() + "…"

            label_to_type = {ep[0]: ep[1] for ep in explorer_params}
            _label_re = re.compile(r"^(.*?)\s\((\d+)\)\s-\s(.*)$")

            def _split_label(l):
                m = _label_re.match(l)
                if not m:
                    return None
                comp_text, instance_num, rest = m.groups()
                return comp_text.strip(), instance_num, rest

            # Group parameters beyond GROUP_THRESHOLD into "N others".
            # Keeps the chart readable while preserving the correct total sum.
            MAX_WF_BARS = 5
            GROUP_THRESHOLD = 6
            segments_by_impact = sorted(segments, key=lambda t: abs(t[2]), reverse=True)
            if len(segments_by_impact) > GROUP_THRESHOLD:
                wf_segments = list(segments_by_impact[:MAX_WF_BARS])
                grouped = segments_by_impact[MAX_WF_BARS:]
                grouped_delta = sum(d for _, _, d in grouped)
                grouped_label = f"{len(grouped)} others"
                wf_segments.append((grouped_label, None, grouped_delta))
            else:
                wf_segments = list(segments_by_impact)
                grouped = []

            parsed_labels = {l: _split_label(l) for l, p, d in wf_segments if p is not None}
            # Abbreviate element name to keep tag initials consistent across charts
            comp_names = sorted({_translate_element_name(v[0]) for v in parsed_labels.values() if v})

            def _abbrev_map(names):
                # Shortest unique prefix per component in the chart, extended only if needed to resolve conflicts.
                length = 1
                while length <= 6:
                    candidate = {n: n[:length] for n in names}
                    if len(set(candidate.values())) == len(candidate):
                        return candidate
                    length += 1
                return {n: n[:6] for n in names}

            comp_abbrev = _abbrev_map(comp_names)

            def _wf_short_label(l):
                parts = parsed_labels.get(l)
                ptype = label_to_type.get(l)
                if not parts:
                    return short(l)
                comp_text, instance_num, rest = parts
                comp_text_display = _translate_element_name(comp_text)
                tag = f"{comp_abbrev.get(comp_text_display, comp_text_display[:1])}({instance_num})"
                if ptype == "quantity":
                    if rest.strip() == "quantity":
                        return f"{tag} Quantity"
                    suffix = " - amount"
                    layer_name = rest[: -len(suffix)] if rest.endswith(suffix) else rest
                    layer_name = layer_name.strip()
                    if len(layer_name) > 20:
                        layer_name = layer_name[:20] + "…"
                    return f"{tag} {layer_name}\n(Amount)"
                if ptype == "area_ratio":
                    type_word = "Area ratio"
                    suffix = " - area ratio (%)"
                else:
                    type_word = "Thickness" if ptype == "size" else "Lifetime"
                    suffix = " - thickness (mm)" if ptype == "size" else " - lifetime (yr)"
                layer_name = rest[: -len(suffix)] if rest.endswith(suffix) else rest
                layer_name = layer_name.strip()
                if len(layer_name) > 20:
                    layer_name = layer_name[:20] + "…"
                return f"{tag} {layer_name}\n({type_word})"

            wf_labels = (
                ["Baseline"]
                + [
                    f"{_wf_short_label(l)}\n({p:+.1f}%)" if p is not None else short(l)
                    for l, p, d in wf_segments
                ]
                + ["Actual result"]
            )
            wf_values = [baseline_gwp_val] + [d for l, p, d in wf_segments] + [actual_total]
            wf_kinds = ["base"] + ["up" if d >= 0 else "down" for l, p, d in wf_segments] + ["total"]

            fig_wf, ax_wf = plt.subplots(figsize=(max(6.5, 1.7 * len(wf_labels)), 4.2))
            cum = 0.0
            for i, (val, kind) in enumerate(zip(wf_values, wf_kinds)):
                if kind in ("base", "total"):
                    bottom, height = 0.0, val
                    color = "#4a4a4a" if kind == "base" else "#1f77b4"
                    cum = val
                    label_text = f"{val:.2f}"
                else:
                    bottom = cum if val >= 0 else cum + val
                    height = abs(val)
                    color = "#d62728" if val >= 0 else "#2ca02c"
                    cum += val
                    label_text = f"{val:+.2f}"
                ax_wf.bar(i, height, bottom=bottom, color=color, width=0.6)
                ax_wf.text(
                    i, bottom + height + (max(baseline_gwp_val, actual_total, 1) * 0.02),
                    label_text, ha="center", va="bottom", fontsize=9, color="#333"
                )
            ax_wf.set_xticks(range(len(wf_labels)))
            ax_wf.set_xticklabels(wf_labels, fontsize=8.5, rotation=25, ha="right")
            ax_wf.set_ylabel("GWP (kg CO₂-eq / m²)", fontsize=10)
            ax_wf.spines["top"].set_visible(False)
            ax_wf.spines["right"].set_visible(False)
            ax_wf.grid(True, axis="y", alpha=0.25, linestyle="--")

            from matplotlib.patches import Patch
            # Placed above the axes, not inside the plot area
            ax_wf.legend(
                handles=[
                    Patch(facecolor="#d62728", label="Increases GWP"),
                    Patch(facecolor="#2ca02c", label="Reduces GWP"),
                    Patch(facecolor="#1f77b4", label="Actual combined result"),
                ],
                loc="lower center", bbox_to_anchor=(0.5, 1.02), ncol=3,
                fontsize=8, frameon=False,
            )
            plt.tight_layout()
            st.pyplot(fig_wf)

            if grouped:
                st.caption(
                    f"* Showing the {MAX_WF_BARS} biggest-impact parameters; the other "
                    f"{len(grouped)} are grouped into \"combined\": full list below the chart."
                )

            gap = actual_total - expected_total
            if baseline_gwp_val and abs(gap) / baseline_gwp_val * 100 > 3:
                # Bars are interpolated from single-parameter curves, not live recalculations.
                # Small gaps might stem from interpolation error; Additivity Check validates real interactions.
                warning_box(
                    f"The bars above (each estimated from its own previously-measured curve) predict "
                    f"{expected_total:.2f} kg CO₂-eq/m² combined. eLCA's actual result is "
                    f"{actual_total:.2f}, a {abs(gap):.2f} kg CO₂-eq/m² gap. That's a signal "
                    f"to check: run <b>Additivity Check</b> below to confirm it."
                )

            # Small change, big effect: flags changed params with a high measured sensitivity
            small_high_impact = [
                (l, p, d) for l, p, d in changed_sorted
                if abs(p) <= 10 and sens_map.get(l, 0) >= 5
            ]
            if len(small_high_impact) == 1:
                l, p, _ = small_high_impact[0]
                warning_box(
                    f"{_fmt(l, p)} is only a small change, but this parameter has a high measured "
                    f"GWP sensitivity ({sens_map[l]:.1f}% relative range in Full Analysis). Even small "
                    f"adjustments here can noticeably shift the GWP, so it's worth watching closely."
                )
            elif len(small_high_impact) >= 2:
                labels = " and ".join(_fmt(l, p) for l, p, _ in small_high_impact[:2])
                warning_box(
                    f"{labels} are only small changes, but both have a high measured GWP sensitivity. "
                    f"Even minor adjustments to either can noticeably shift the GWP, so both are worth watching closely."
                )

            gwp_went_up = result["relative_change"] > 0
            # GWP change is near zero, so avoid claiming any parameter drove or offset changes.
            # Use small epsilon to handle eLCA's display rounding (e.g. 0.00%).
            gwp_change_negligible = abs(result["relative_change"]) < 0.01

            # Group by actual effect (input % change * slope sign), not raw input direction.
            # Uses segment_delta to capture exact impact at current value, avoiding zero-contribution step parameters.
            effective_direction = {l: p * _param_direction_sign(l) for l, p, _ in changed_sorted}
            def _meaningful_contribution(l):
                if not baseline_gwp_val:
                    return False
                return abs(segment_delta.get(l, 0.0)) / baseline_gwp_val * 100 >= 0.5
            high_sens_up = [
                (l, p, d) for l, p, d in changed_by_impact
                if effective_direction[l] > 0 and sens_map.get(l, 0) >= 5 and _meaningful_contribution(l)
            ]
            high_sens_down = [
                (l, p, d) for l, p, d in changed_by_impact
                if effective_direction[l] < 0 and sens_map.get(l, 0) >= 5 and _meaningful_contribution(l)
            ]
            low_sens_changed = [(l, p, d) for l, p, d in changed_sorted if l in sens_map and sens_map[l] < 2]

            if gwp_change_negligible:
                # Combined GWP barely changed despite modified inputs.
                # Highlight parameters that hit a flat region locally, even if sensitive elsewhere on their curves.
                flat_high_sens = [
                    (l, p) for l, p, _ in changed_sorted
                    if sens_map.get(l, 0) >= 5 and not _meaningful_contribution(l)
                ]
                if flat_high_sens:
                    plural = len(flat_high_sens) > 1
                    labels = " and ".join(_fmt(l, p) for l, p in flat_high_sens[:2])
                    note_box(
                        f"{labels} {'have' if plural else 'has'} a high measured GWP sensitivity "
                        f"overall, but at the value{'s' if plural else ''} you set here, "
                        f"{'they land' if plural else 'it lands'} on a flat stretch of "
                        f"{'their' if plural else 'its'} curve, typical for step-like parameters "
                        f"like lifetime, which only move the GWP right at a replacement-count "
                        f"threshold. This particular change did not shift the GWP, even though other "
                        f"values of the same parameter can have a large effect."
                    )
                else:
                    st.caption(
                        "None of the changed parameters had a measurable individual effect on GWP "
                        "at these specific values."
                    )
            elif gwp_went_up:
                if high_sens_up:
                    l, p, _ = high_sens_up[0]
                    warning_box(
                        f"{_fmt(l, p)} is the main driver of this increase, with a high measured "
                        f"GWP sensitivity ({sens_map[l]:.1f}%). {_toward_baseline(p)} it back toward "
                        f"baseline will have the strongest effect on lowering the GWP."
                    )
                if high_sens_down:
                    l, p, _ = high_sens_down[0]
                    note_box(
                        f"{_fmt(l, p)} is working in the right direction, but was not enough on its "
                        f"own to offset the other changes."
                    )
                if not high_sens_up and not high_sens_down:
                    l, p, d = changed_by_impact[0]
                    if l in sens_map:
                        note_box(
                            f"{_fmt(l, p)} had the largest measured effect in this scenario, though its "
                            f"measured GWP sensitivity here is low ({sens_map[l]:.1f}%). {_toward_baseline(p)} "
                            f"it back toward baseline will help somewhat, but do not expect a large effect."
                        )
                    else:
                        note_box(
                            f"{_fmt(l, p)} had the largest measured effect in this scenario. Moving it "
                            f"back toward baseline would likely lower the GWP most, but this is not yet "
                            f"confirmed by measured data."
                        )
            else:
                if high_sens_down:
                    l, p, _ = high_sens_down[0]
                    insight_box(
                        f"{_fmt(l, p)} is driving this reduction, with a high measured GWP "
                        f"sensitivity ({sens_map[l]:.1f}%). It is the most effective parameter to keep "
                        f"optimizing in this direction."
                    )
                if high_sens_up:
                    l, p, _ = high_sens_up[0]
                    warning_box(
                        f"{_fmt(l, p)} is partially offsetting the gain. Keeping it closer to baseline "
                        f"would strengthen the reduction."
                    )

            if low_sens_changed:
                labels = " and ".join(_fmt(l, p) for l, p, _ in low_sens_changed[:2])
                note_box(
                    f"{labels} had little measured effect on GWP in Full Analysis "
                    f"(< 2% relative range). Changing these further is unlikely to matter much."
                )

            note_box(
                "Changed in this scenario: " +
                ", ".join(_fmt(l, p) for l, p, _ in changed_sorted) + "."
            )
        else:
            st.caption("No parameters were changed from their baseline values.")

        # Additivity Check
        if changed_sorted:
            st.divider()
            st.subheader("Do parameters interact?")
            st.write(
                "When multiple parameters are changed at once, do their effects simply add up, "
                "or do they interact with each other? This check compares the sum of individual "
                "effects to the combined result."
            )

            if bg_running_here:
                st.warning("**Run Additivity Check** is locked while Full Analysis is running in the background.")
            if explorer_running:
                st.warning("**Run Additivity Check** is locked while **Calculate New GWP** is in progress.")
            run_additivity = st.button(
                "Run Additivity Check",
                disabled=bg_running_here or explorer_running or additivity_running,
            )

            if run_additivity:
                captured_values = dict(user_values)
                new_additivity_state = {
                    "lock": threading.Lock(), "status": "running",
                    "result": None, "error": None,
                    "stop_requested": False, "stopped": False,
                }
                _ACTIVE_ACTIONS[additivity_action_key] = new_additivity_state
                threading.Thread(
                    target=_run_stoppable_action_background,
                    args=(
                        lambda should_stop: _call_selenium_with_relogin(
                            lambda: run_additivity_check_selenium(
                                driver, comp, user_values=captured_values, should_stop=should_stop
                            ),
                            driver, username_input, password_input,
                        ),
                        new_additivity_state,
                    ),
                    daemon=True,
                ).start()
                st.rerun()

            if additivity_running:
                with additivity_action["lock"]:
                    stop_requested = additivity_action["stop_requested"]
                st.info("⏳ Calculating additivity check...")
                if stop_requested:
                    st.info(
                        "Stopping as soon as the parameter currently being changed is reset back "
                        "to baseline, so nothing is left half-changed on eLCA."
                    )
                elif st.button("⏹ Stop", key="stop_additivity_calc"):
                    with additivity_action["lock"]:
                        additivity_action["stop_requested"] = True
                    st.rerun()
                time.sleep(1)
                st.rerun()
            elif additivity_action is not None and additivity_action["status"] == "done":
                with additivity_action["lock"]:
                    stopped = additivity_action["stopped"]
                    outcome = additivity_action["result"]
                    bg_error = additivity_action["error"]
                del _ACTIVE_ACTIONS[additivity_action_key]
                if stopped:
                    st.session_state["additivity_result"] = None
                    st.info("Additivity check stopped. Every value it had changed was reset back to baseline first.")
                elif bg_error is not None:
                    st.session_state["additivity_result"] = None
                    _session_expired_warning(bg_error)
                else:
                    add_result, error = outcome
                    if error is not None:
                        # same idle-session recovery as Calculate New GWP above
                        st.session_state["additivity_result"] = None
                        _session_expired_warning(error)
                    else:
                        st.session_state["additivity_result"] = add_result
                        # Save per-parameter notes so inspection views can access them across scenario changes.
                        if "param_additivity_notes" not in st.session_state:
                            st.session_state["param_additivity_notes"] = {}
                        checked_labels = [l for l, _, _ in changed_sorted]
                        for l in checked_labels:
                            st.session_state["param_additivity_notes"][l] = {
                                "is_additive": bool(add_result.get("is_additive")),
                                "other_labels": [o for o in checked_labels if o != l],
                            }

            if "additivity_result" in st.session_state and st.session_state["additivity_result"] is not None:
                add = st.session_state["additivity_result"]

                # Show baseline explicitly to compare distances from baseline instead of raw expected vs. actual values.
                col_base, col_a, col_b, col_c = st.columns(4)
                col_base.metric("Baseline GWP", f"{add['baseline_gwp']:.4f}")
                col_a.metric("Expected GWP (additive)", f"{add['expected_gwp']:.4f}")
                col_b.metric("Actual GWP (combined)", f"{add['actual_gwp']:.4f}")
                col_c.metric("Interaction effect", f"{add['interaction']:+.4f}")

                if add.get("cleanup_warnings"):
                    warning_box(
                        "These results are correct, but eLCA may still show a leftover "
                        "custom lifetime setting from this check: "
                        + "; ".join(add["cleanup_warnings"])
                    )

                if add["individual_results"]:
                    ind_df = pd.DataFrame(add["individual_results"])
                    ind_df.index = range(1, len(ind_df) + 1)
                    if "Parameter" in ind_df.columns:
                        ind_df = ind_df.assign(Parameter=ind_df["Parameter"].apply(_display_label))
                    st.dataframe(ind_df, use_container_width=True)

                    # Flag exactly 0.0000 change on modified inputs as a warning (indicates possible
                    # silent eLCA write failure or true zero-effect).
                    zero_labels = [
                        r["Parameter"] for r in add["individual_results"]
                        if abs(r["Individual GWP change (kg CO2-eq)"]) < 1e-9
                    ]
                    if zero_labels:
                        st.caption(
                            "⚠️ Parameters showing exactly 0.0000 rarely reflect a "
                            "silently failed write: if that looks surprising, re-run "
                            "to confirm."
                        )

                # Dynamic interpretation based on interaction magnitude and direction (avoids static templates).
                # interaction_pct is normalized against baseline GWP to stay consistent with the app.
                interaction = add["interaction"]
                interaction_pct = add.get("interaction_pct", 0.0)
                # Compare change magnitudes from baseline for sub-/super-additivity, not just raw interaction sign.
                # Raw sign fails for negative changes
                expected_change = add["expected_gwp"] - add["baseline_gwp"]
                actual_change = add["actual_gwp"] - add["baseline_gwp"]
                sub_additive = abs(actual_change) < abs(expected_change)

                if interaction_pct < 1.0:
                    insight_box(
                        f"These parameters behave essentially <b>additively</b> here. The gap between "
                        f"predicted and actual combined GWP is only {interaction_pct:.2f}% of baseline, "
                        f"close enough to zero to be measurement noise rather than a real interaction. "
                        f"The table above is a reliable, independent read of each parameter's own "
                        f"contribution, safe to reason about them one at a time."
                    )
                elif interaction_pct < 5.0:
                    insight_box(
                        f"These parameters are additive in practice. Changing them all together "
                        f"landed only {interaction_pct:.2f}% of baseline GWP away from simply adding "
                        f"up each one's own individually-measured effect ({interaction:+.4f} kg "
                        f"CO₂-eq/m² difference), close enough that you can trust each parameter's "
                        f"number in the table above on its own, even when changing several of them "
                        f"at the same time."
                    )
                elif sub_additive:
                    # |actual_change| < |expected_change|, the combined
                    # effect is SMALLER in magnitude than the sum predicts:
                    # the parameters partially cancel each other out.
                    severity = "substantially" if interaction_pct >= 15 else "noticeably"
                    warning_box(
                        f"These parameters do <b>not</b> act independently. Combined, they move GWP "
                        f"{severity} less than adding their individual effects would predict: "
                        f"{add['expected_gwp']:.2f} expected vs. {add['actual_gwp']:.2f} actual "
                        f"kg CO₂-eq/m² ({interaction:+.4f}, {interaction_pct:.1f}% of baseline GWP). "
                        f"Some of what each parameter does on its own overlaps with what the other is "
                        f"doing. The table above <b>overstates</b> each one's real contribution when "
                        f"they're changed together like this."
                    )
                else:
                    # |actual_change| > |expected_change|, combined effect
                    # is LARGER in magnitude than the sum predicts: the
                    # parameters compound each other.
                    severity = "substantially" if interaction_pct >= 15 else "noticeably"
                    warning_box(
                        f"These parameters do <b>not</b> act independently. Combined, they move GWP "
                        f"{severity} more than adding their individual effects would predict: "
                        f"{add['expected_gwp']:.2f} expected vs. {add['actual_gwp']:.2f} actual "
                        f"kg CO₂-eq/m² ({interaction:+.4f}, {interaction_pct:.1f}% of baseline GWP). "
                        f"Changing these together compounds their effect beyond what either one alone "
                        f"would suggest. The table above <b>understates</b> their real combined "
                        f"contribution when they're changed together like this."
                    )

                if len(add["individual_results"]) >= 2:
                    biggest = max(
                        add["individual_results"],
                        key=lambda r: abs(r.get("Individual GWP change (kg CO2-eq)", 0.0)),
                    )
                    st.caption(
                        f"* **{_display_label(biggest['Parameter'])}** had the largest individual effect "
                        f"({biggest['Individual GWP change (kg CO2-eq)']:+.4f} kg CO₂-eq/m²)."
                    )

        st.divider()