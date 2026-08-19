import pandas as pd
import numpy as np
import re
from bs4 import BeautifulSoup

BASE_URL = "https://www.bauteileditor.de"

# Remembers each lifetime field's original value/reason before we touch it.
_LIFETIME_ORIGINAL_STATE = {}


class AnalysisStopped(Exception):
    """Raised by should_stop() to stop a run early, always between parameters, never mid-write, so try/finally still reverts everything changed so far."""


def parse_elca_url(url):
    # Extract project_id and element_id from eLCA URL
    project_match = re.search(r"/projects/(\d+)/", url)
    element_match = re.search(r"/project-elements/(\d+)/", url)
    if not project_match or not element_match:
        raise ValueError(
            "Could not parse eLCA URL. Expected format: "
            "https://www.bauteileditor.de/projects/XXXXX/#!/project-elements/YYYYY/"
        )
    return project_match.group(1), element_match.group(1)


def _extract_gwp_from_full_page(soup):
    """GWP value from the "Total use" table, matched by header text since
    column order isn't fixed."""
    total_row = soup.find("tr", class_="total")
    if total_row is None:
        return None
    table = total_row.find_parent("table")
    if table is None:
        return None
    thead = table.find("thead")
    header_row = thead.find("tr") if thead else table.find("tr")
    if header_row is None:
        return None
    headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]

    gwp_idx = None
    for i, h in enumerate(headers):
        if h.strip().lower() == "gwp total impact":
            gwp_idx = i
            break
    if gwp_idx is None:
        for i, h in enumerate(headers):
            hl = h.strip().lower()
            if hl.startswith("gwp") and "biogenic" not in hl:
                gwp_idx = i
                break
    if gwp_idx is None:
        return None

    cells = total_row.find_all("td")
    if gwp_idx >= len(cells):
        return None
    try:
        return float(cells[gwp_idx].text.replace(",", "."))
    except Exception:
        return None


def _extract_all_stage_values_from_page(soup):
    """Every lifecycle-stage row (A1-A3, B4, C3-C4, D, ...), not just the
    total. Best-effort: returns {} on any layout surprise."""
    import re
    result = {}
    try:
        total_row = soup.find("tr", class_="total")
        if total_row is None:
            return result
        table = total_row.find_parent("table")
        if table is None:
            return result
        thead = table.find("thead")
        header_row = thead.find("tr") if thead else table.find("tr")
        if header_row is None:
            return result
        headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])]

        gwp_idx = None
        for i, h in enumerate(headers):
            if h.strip().lower() == "gwp total impact":
                gwp_idx = i
                break
        if gwp_idx is None:
            for i, h in enumerate(headers):
                hl = h.strip().lower()
                if hl.startswith("gwp") and "biogenic" not in hl:
                    gwp_idx = i
                    break
        if gwp_idx is None:
            return result

        body = table.find("tbody") or table
        for row in body.find_all("tr"):
            if "total" in (row.get("class") or []):
                continue
            first_cell = row.find("td")
            if first_cell is None:
                continue
            label = first_cell.get_text(strip=True).strip()
            if not label:
                continue
            code_part = label.split("(")[0].strip()
            tag = re.sub(r"\s*-\s*", "-", code_part) if code_part else label
            if not tag:
                continue
            cells = row.find_all("td")
            if gwp_idx >= len(cells):
                continue
            try:
                value = float(cells[gwp_idx].text.replace(",", "."))
            except Exception:
                continue
            result[f"{tag} GWP"] = value
        return result
    except Exception:
        return {}


def _selenium_login(driver, username, password):
    """Logs into eLCA and forces the UI language to English (GWP column is
    matched by English header text)."""
    from selenium.webdriver.common.by import By
    import time

    driver.get("https://www.bauteileditor.de/login/lang/?lang=en")
    time.sleep(1)

    driver.get("https://www.bauteileditor.de/login/")
    time.sleep(2)

    auth_fields = driver.find_elements(By.NAME, "authName")
    if not auth_fields:
        # Already logged in.
        if "login" in driver.current_url.lower():
            raise RuntimeError(
                "Could not find the eLCA login form, and the browser is still "
                "on a login-related URL. The page structure may have changed."
            )
        return

    auth_fields[0].send_keys(username)
    driver.find_element(By.NAME, "authKey").send_keys(password)
    driver.find_element(By.NAME, "login").click()
    time.sleep(3)

    if "login" in driver.current_url.lower():
        raise RuntimeError("Login failed. Please check your username and password.")


def _selenium_navigate_fresh(driver, url):
    """Reloads a neutral URL first, so Angular doesn't keep showing the
    previous element when jumping between hash-URLs."""
    import re as _re
    import time

    m = _re.match(r"(https?://[^/]+/projects/\d+/)", url)
    neutral_url = m.group(1) if m else url
    driver.get(neutral_url)
    time.sleep(0.3)
    driver.get(url)
    time.sleep(0.5)


def _wait_for_element(driver, by, value, timeout=10):
    """Waits for an element instead of a fixed sleep. Raises a clear
    RuntimeError with the current URL on timeout."""
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.common.exceptions import TimeoutException

    try:
        return WebDriverWait(driver, timeout).until(EC.presence_of_element_located((by, value)))
    except TimeoutException:
        raise RuntimeError(
            f"Could not find element ({by}={value!r}) on {driver.current_url!r} after waiting "
            f"{timeout}s. Possible causes: the page hasn't finished loading, the eLCA session "
            f"expired, or this element doesn't have the expected fields (e.g. no 'Linked modules' "
            f"table for a quantity edit, or the layer/lifetime inputs use a different id here)."
        )


def _read_total_row_text(driver):
    """Text of the first tr.total row, used to detect whether a save took effect."""
    from selenium.webdriver.common.by import By
    try:
        return driver.find_element(By.CSS_SELECTOR, "tr.total").text
    except Exception:
        return None


def _wait_for_total_change(driver, old_total_text, timeout=20):
    """Waits for tr.total's text to actually change, not just be present,
    confirmed by three consecutive matching reads (composites made of
    several linked modules can take an extra read or two to fully settle)."""
    from selenium.webdriver.support.ui import WebDriverWait
    import time as _time

    def _changed(d):
        return _read_total_row_text(d) not in (None, old_total_text)

    deadline = _time.time() + timeout
    try:
        WebDriverWait(driver, timeout).until(_changed)
    except Exception:
        return

    matches = 0
    last_read = _read_total_row_text(driver)
    while _time.time() < deadline:
        _time.sleep(0.5)
        current_read = _read_total_row_text(driver)
        if current_read is not None and current_read == last_read:
            matches += 1
            if matches >= 2:  # this read plus the previous two = 3 in a row
                return  # settled
        else:
            matches = 0
        last_read = current_read


def _selenium_get_current_gwp(driver, project_id, parent_id):
    """Composite element's current GWP, waiting for three consecutive reads
    to agree (composites made of several linked modules can take an extra
    read or two to fully settle). Used as the baseline for every parameter
    in a scan."""
    from selenium.webdriver.common.by import By
    from bs4 import BeautifulSoup
    import time

    _selenium_navigate_fresh(
        driver, f"https://www.bauteileditor.de/projects/{project_id}/#!/project-elements/{parent_id}/?tab=general"
    )
    _wait_for_element(driver, By.CSS_SELECTOR, "tr.total", timeout=20)

    deadline = time.time() + 15
    matches = 0
    last_text = _read_total_row_text(driver)
    while time.time() < deadline:
        time.sleep(0.5)
        next_text = _read_total_row_text(driver)
        if next_text is not None and next_text == last_text:
            matches += 1
            if matches >= 2:  # this read plus the previous two = 3 in a row
                break
        else:
            matches = 0
        last_text = next_text

    soup = BeautifulSoup(driver.page_source, "html.parser")
    gwp = _extract_gwp_from_full_page(soup)
    if gwp is None:
        total_row = soup.find("tr", class_="total")
        table = total_row.find_parent("table") if total_row else None
        thead = table.find("thead") if table else None
        header_row = (thead.find("tr") if thead else table.find("tr")) if table else None
        headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])] if header_row else []
        raise RuntimeError(
            "Found the 'Total use' table on "
            f"{driver.current_url!r} but could not identify the GWP column. "
            f"Headers found: {headers!r}. This means the column-matching "
            "logic needs to be adjusted for this project's table layout."
        )
    return gwp


def _selenium_check_lifetime_reason_gaps(driver):
    """Finds layers with "Own" lifetime selected but no reason typed in,
    which silently blocks eLCA from saving the whole page."""
    return driver.execute_script("""
        var gaps = [];
        document.querySelectorAll('input[data-has-text-input="1"]').forEach(function(radio) {
            if (!radio.checked) return;
            var name = radio.getAttribute('name') || '';
            if (name.indexOf('altLifeTime') !== 0) return;
            var infoName = name.replace('altLifeTime', 'lifeTimeInfo');
            var info = document.querySelector('input[name="' + infoName + '"]');
            if (info && !info.value) { gaps.push(name); }
        });
        return gaps;
    """) or []


def _selenium_raise_if_lifetime_reason_gap(driver):
    """Raises RuntimeError if a lifetime reason gap is found. Called before every save."""
    gaps = _selenium_check_lifetime_reason_gaps(driver)
    if gaps:
        raise RuntimeError(
            f"eLCA won't save this page: {', '.join(gaps)} has 'Own' "
            f"selected for its useful life but no reason typed in. Open "
            f"{driver.current_url!r} in eLCA, type any reason under "
            f"'Useful lives', save, and re-run this parameter."
        )


def _find_lifetime_reason_gaps_in_soup(soup):
    """Static-HTML twin, used at discovery time to catch this before a Full
    Analysis starts."""
    gaps = []
    for radio in soup.find_all("input", attrs={"data-has-text-input": "1"}):
        name = (radio.get("name") or "").strip().strip('"')
        if not name.startswith("altLifeTime"):
            continue
        if not radio.has_attr("checked"):
            continue
        info_name = name.replace("altLifeTime", "lifeTimeInfo")
        info = soup.find("input", {"name": info_name})
        info_value = (info.get("value") or "").strip().strip('"') if info else ""
        if not info_value:
            gaps.append(name)
    return gaps


def _selenium_set_parameter_and_get_gwp(driver, comp, project_id, param_type, layer_id, param_key, value, partner_key=None):
    """Sets one parameter through the real eLCA UI and returns the
    resulting aggregate GWP of the whole composite element."""
    from selenium.webdriver.common.by import By
    from bs4 import BeautifulSoup
    import time

    parent_id = comp["rel_id"]

    # "quantity": composite's top-level amount vs a material's Amount in "Other Materials".
    if param_type == "quantity" and layer_id is None:
        _selenium_navigate_fresh(
            driver, f"https://www.bauteileditor.de/projects/{project_id}/#!/project-elements/{parent_id}/?tab=general"
        )
        _wait_for_element(driver, By.NAME, param_key)
        old_total_text = _read_total_row_text(driver)
        driver.execute_script(f"""
            var input = document.querySelector('input[name="{param_key}"]');
            if (!input) return;
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, '{value}');
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        """)
        time.sleep(0.3)

        # Verify the write took before saving.
        actual_value = driver.execute_script(f"""
            var input = document.querySelector('input[name="{param_key}"]');
            return input ? input.value : null;
        """)
        try:
            actual_float = float(str(actual_value).replace(",", "."))
            matches = abs(actual_float - float(value)) < 1e-6
        except (TypeError, ValueError):
            matches = False
        if not matches:
            raise RuntimeError(
                f"Wrote {value!r} to {param_key!r} but the field reads back "
                f"{actual_value!r} just before saving on "
                f"{driver.current_url!r}. Refusing to save a value that "
                f"doesn't match what was requested (the session may have "
                f"expired)."
            )

        _selenium_raise_if_lifetime_reason_gap(driver)

        save_btn = _wait_for_element(driver, By.NAME, "saveElements")
        driver.execute_script("arguments[0].click();", save_btn)
        _wait_for_total_change(driver, old_total_text, timeout=20)
        _wait_for_element(driver, By.CSS_SELECTOR, "tr.total", timeout=15)
        page = driver.page_source
    else:
        # Snapshot the parent's total to confirm the save later.
        _selenium_navigate_fresh(
            driver, f"https://www.bauteileditor.de/projects/{project_id}/#!/project-elements/{parent_id}/?tab=general"
        )
        _wait_for_element(driver, By.CSS_SELECTOR, "tr.total", timeout=20)
        old_total_text = _read_total_row_text(driver)

        _selenium_navigate_fresh(
            driver,
            f"https://www.bauteileditor.de/projects/{project_id}/#!/project-elements/{layer_id}/?rel={parent_id}&tab=general"
        )
        _wait_for_element(driver, By.NAME, param_key)

        if param_type == "lifetime":
            # Click the "custom lifetime" radio before writing the value (order matters).
            alt_key = param_key.replace("lifeTime", "altLifeTime")
            info_key = param_key.replace("lifeTime", "lifeTimeInfo")

            state_key = (layer_id, param_key)
            if state_key not in _LIFETIME_ORIGINAL_STATE:
                original_state = driver.execute_script(f"""
                    var own = document.querySelector(
                        'input[name="{alt_key}"][data-has-text-input="1"]');
                    var val = document.querySelector('input[name="{param_key}"]');
                    var info = document.querySelector('input[name="{info_key}"]');
                    return {{
                        wasOwn: own ? own.checked : false,
                        value: val ? val.value : null,
                        reason: info ? info.value : null,
                    }};
                """)
                if original_state:
                    _LIFETIME_ORIGINAL_STATE[state_key] = original_state

            driver.execute_script(f"""
                var eigene = document.querySelector(
                    'input[name="{alt_key}"][data-has-text-input="1"]');
                if (eigene) {{
                    eigene.click();
                    eigene.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            time.sleep(0.3)

            is_checked = driver.execute_script(f"""
                var eigene = document.querySelector(
                    'input[name="{alt_key}"][data-has-text-input="1"]');
                return eigene ? eigene.checked : null;
            """)
            if is_checked is not True:
                raise RuntimeError(
                    f"Could not switch {alt_key!r} to 'custom lifetime' "
                    f"(checked={is_checked!r}) on {driver.current_url!r}. "
                    f"Without this, eLCA ignores the new {param_key!r} value "
                    f"and keeps using the standard/reference lifetime, so the "
                    f"GWP would never change regardless of the value tested."
                )

        driver.execute_script(f"""
            var input = document.querySelector('input[name="{param_key}"]');
            if (!input) return;
            var setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value').set;
            setter.call(input, '{value}');
            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
        """)
        time.sleep(0.3)

        if param_type != "lifetime":
            actual_value = driver.execute_script(f"""
                var input = document.querySelector('input[name="{param_key}"]');
                return input ? input.value : null;
            """)
            try:
                actual_float = float(str(actual_value).replace(",", "."))
                matches = abs(actual_float - float(value)) < 1e-6
            except (TypeError, ValueError):
                matches = False
            if not matches:
                raise RuntimeError(
                    f"Wrote {value!r} to {param_key!r} but the field reads "
                    f"back {actual_value!r} just before saving on "
                    f"{driver.current_url!r}. Refusing to save a value that "
                    f"doesn't match what was requested (the session may have "
                    f"expired)."
                )

        if param_type == "area_ratio" and partner_key:
            # Write the paired value manually (eLCA doesn't balance it).
            partner_value = 100.0 - float(value)
            driver.execute_script(f"""
                var input = document.querySelector('input[name="{partner_key}"]');
                if (!input) return;
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(input, '{partner_value}');
                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
            """)
            time.sleep(0.3)

            actual_partner = driver.execute_script(f"""
                var input = document.querySelector('input[name="{partner_key}"]');
                return input ? input.value : null;
            """)
            try:
                actual_partner_float = float(str(actual_partner).replace(",", "."))
                partner_matches = abs(actual_partner_float - partner_value) < 1e-6
            except (TypeError, ValueError):
                partner_matches = False
            if not partner_matches:
                raise RuntimeError(
                    f"Wrote {partner_value!r} to paired field {partner_key!r} "
                    f"(balancing {param_key!r}={value!r}) but it reads back "
                    f"{actual_partner!r} just before saving on "
                    f"{driver.current_url!r}. Refusing to save a split layer "
                    f"whose shares wouldn't sum to 100% (the session may have "
                    f"expired)."
                )

        if param_type == "lifetime":
            info_key = param_key.replace("lifeTime", "lifeTimeInfo")
            driver.execute_script(f"""
                var reason = document.querySelector('input[name="{info_key}"]');
                if (reason) {{
                    var setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value').set;
                    setter.call(reason, 'sensitivity analysis');
                    reason.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    reason.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            time.sleep(0.3)

            actual_value = driver.execute_script(f"""
                var input = document.querySelector('input[name="{param_key}"]');
                return input ? input.value : null;
            """)
            try:
                actual_float = float(str(actual_value).replace(",", "."))
                matches = abs(actual_float - float(value)) < 1e-6
            except (TypeError, ValueError):
                matches = False
            if not matches:
                raise RuntimeError(
                    f"Wrote {value!r} to {param_key!r} but the field reads "
                    f"back {actual_value!r} just before saving on "
                    f"{driver.current_url!r}. Refusing to save a value that "
                    f"doesn't match what was requested."
                )

        _selenium_raise_if_lifetime_reason_gap(driver)

        # Two possible forms; find the one containing this field.
        save_btn_name = driver.execute_script(f"""
            var input = document.querySelector('input[name="{param_key}"]');
            if (!input) return null;
            var form = input.closest('form');
            if (!form) return null;
            var candidates = form.querySelectorAll(
                'button[type="submit"][name], input[type="submit"][name]');
            for (var i = 0; i < candidates.length; i++) {{
                if (candidates[i].name.indexOf('save') === 0) {{
                    return candidates[i].name;
                }}
            }}
            return null;
        """)
        if not save_btn_name:
            raise RuntimeError(
                f"Could not find a 'save...' submit button in {param_key!r}'s "
                f"enclosing form on {driver.current_url!r}. The page structure "
                f"may have changed."
            )
        save_btn = _wait_for_element(driver, By.NAME, save_btn_name)
        driver.execute_script("arguments[0].click();", save_btn)
        time.sleep(2)

        # Go back to the parent page for the real aggregate total.
        _selenium_navigate_fresh(
            driver, f"https://www.bauteileditor.de/projects/{project_id}/#!/project-elements/{parent_id}/?tab=general"
        )
        _wait_for_total_change(driver, old_total_text, timeout=20)
        _wait_for_element(driver, By.CSS_SELECTOR, "tr.total", timeout=15)
        page = driver.page_source

    soup = BeautifulSoup(page, "html.parser")
    gwp = _extract_gwp_from_full_page(soup)
    if gwp is None:
        total_row = soup.find("tr", class_="total")
        table = total_row.find_parent("table") if total_row else None
        thead = table.find("thead") if table else None
        header_row = (thead.find("tr") if thead else table.find("tr")) if table else None
        headers = [c.get_text(strip=True) for c in header_row.find_all(["th", "td"])] if header_row else []
        raise RuntimeError(
            f"Could not read the GWP value after setting {param_key!r} "
            f"(param_type={param_type!r}) to {value!r}, on "
            f"{driver.current_url!r}. tr.total found: {total_row is not None}. "
            f"Headers found: {headers!r}."
        )
    return gwp


def _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key):
    """Clears the "custom lifetime" marker left behind after a lifetime
    parameter is reset. Best-effort: returns True if clean, False if an
    attempt was made but didn't finish."""
    from selenium.webdriver.common.by import By
    import time
    import json

    info_key = param_key.replace("lifeTime", "lifeTimeInfo")
    alt_key = param_key.replace("lifeTime", "altLifeTime")
    state_key = (layer_id, param_key)
    original_state = _LIFETIME_ORIGINAL_STATE.get(state_key)

    try:
        _selenium_navigate_fresh(
            driver,
            f"https://www.bauteileditor.de/projects/{project_id}/#!/project-elements/{layer_id}/?rel={parent_id}&tab=general"
        )
        _wait_for_element(driver, By.NAME, param_key, timeout=10)

        info_value = driver.execute_script(f"""
            var input = document.querySelector('input[name="{info_key}"]');
            return input ? input.value : null;
        """)
        if info_value != "sensitivity analysis":
            return True  # not the tool's marker, already clean, or a genuine custom setting

        # Was it genuinely on "Own" before we touched it? Restore that instead.
        was_genuine_own = (
            original_state is not None
            and original_state.get("wasOwn")
            and original_state.get("reason")
            and original_state.get("reason") != "sensitivity analysis"
        )
        if was_genuine_own:
            restored = driver.execute_script(f"""
                var val = document.querySelector('input[name="{param_key}"]');
                var info = document.querySelector('input[name="{info_key}"]');
                if (!val || !info) return false;
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(val, {json.dumps(original_state["value"])});
                val.dispatchEvent(new Event('input', {{ bubbles: true }}));
                val.dispatchEvent(new Event('change', {{ bubbles: true }}));
                setter.call(info, {json.dumps(original_state["reason"])});
                info.dispatchEvent(new Event('input', {{ bubbles: true }}));
                info.dispatchEvent(new Event('change', {{ bubbles: true }}));
                return true;
            """)
            if not restored:
                return False
            save_btn_name = driver.execute_script(f"""
                var input = document.querySelector('input[name="{param_key}"]');
                if (!input) return null;
                var form = input.closest('form');
                if (!form) return null;
                var candidates = form.querySelectorAll(
                    'button[type="submit"][name], input[type="submit"][name]');
                for (var i = 0; i < candidates.length; i++) {{
                    if (candidates[i].name.indexOf('save') === 0) {{
                        return candidates[i].name;
                    }}
                }}
                return null;
            """)
            if not save_btn_name:
                return False
            save_btn = _wait_for_element(driver, By.NAME, save_btn_name, timeout=10)
            driver.execute_script("arguments[0].click();", save_btn)
            time.sleep(1.5)
            _LIFETIME_ORIGINAL_STATE.pop(state_key, None)
            return True

        standard_already = driver.execute_script(f"""
            var r = document.querySelector('input[name="{alt_key}"][data-has-text-input="0"]');
            return r ? r.checked : null;
        """)
        if not standard_already:
            clicked = driver.execute_script(f"""
                var r = document.querySelector('input[name="{alt_key}"][data-has-text-input="0"]');
                if (r) {{ r.click(); r.dispatchEvent(new Event('change', {{ bubbles: true }})); }}
                return !!r;
            """)
            if not clicked:
                return False  # standard radio not found, marker is still stuck
            time.sleep(0.3)
        # Reason can still be stuck even if standard was already checked.

        save_btn_name = driver.execute_script(f"""
            var input = document.querySelector('input[name="{param_key}"]');
            if (!input) return null;
            var form = input.closest('form');
            if (!form) return null;
            var candidates = form.querySelectorAll(
                'button[type="submit"][name], input[type="submit"][name]');
            for (var i = 0; i < candidates.length; i++) {{
                if (candidates[i].name.indexOf('save') === 0) {{
                    return candidates[i].name;
                }}
            }}
            return null;
        """)
        if not save_btn_name:
            return False  # save button not found, the click above never got saved
        driver.execute_script(f"""
            var info = document.querySelector('input[name="{info_key}"]');
            if (info) {{
                var setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value').set;
                setter.call(info, '');
                info.dispatchEvent(new Event('input', {{ bubbles: true }}));
                info.dispatchEvent(new Event('change', {{ bubbles: true }}));
            }}
        """)
        save_btn = _wait_for_element(driver, By.NAME, save_btn_name, timeout=10)
        driver.execute_script("arguments[0].click();", save_btn)
        time.sleep(1.5)
        _LIFETIME_ORIGINAL_STATE.pop(state_key, None)
        return True
    except Exception:
        return False  # best-effort, never raises; callers check this return value


def _find_stale_lifetime_markers_in_soup(soup):
    """Finds layers still marked with this tool's leftover "sensitivity
    analysis" reason, e.g. from a crashed run. Detection-only, doesn't revert."""
    gaps = []
    for radio in soup.find_all("input", attrs={"data-has-text-input": "1"}):
        name = (radio.get("name") or "").strip().strip('"')
        if not name.startswith("altLifeTime"):
            continue
        if not radio.has_attr("checked"):
            continue
        info_name = name.replace("altLifeTime", "lifeTimeInfo")
        info = soup.find("input", {"name": info_name})
        info_value = (info.get("value") or "").strip().strip('"') if info else ""
        if info_value == "sensitivity analysis":
            gaps.append(name)
    return gaps


def fetch_component_selenium(driver, project_id, element_id):
    """Loads a component and its layers via Selenium, discovering
    parameters from the rendered page's input fields."""
    def get_html(elem_id):
        from selenium.webdriver.common.by import By

        _selenium_navigate_fresh(
            driver, f"{BASE_URL}/projects/{project_id}/#!/project-elements/{elem_id}/?tab=general"
        )
        _wait_for_element(driver, By.NAME, "name", timeout=20)
        return driver.page_source

    html = get_html(element_id)
    soup = BeautifulSoup(html, "html.parser")

    if soup.find("input", {"name": "login"}):
        raise ValueError("Not logged into eLCA in this browser session.")

    name_input = soup.find("input", {"name": "name"})
    element_name = name_input.get("value", element_id) if name_input else element_id

    reason_gaps = []
    for gap_name in _find_lifetime_reason_gaps_in_soup(soup):
        reason_gaps.append(f"{element_name} - {gap_name}")

    stale_markers = []
    for gap_name in _find_stale_lifetime_markers_in_soup(soup):
        stale_markers.append(f"{element_name} - {gap_name}")

    all_inputs = soup.find_all("input")
    sub_elements = []
    quantities = {}
    i = 1
    while True:
        eid_input = None
        qty_input = None
        for inp in all_inputs:
            name = inp.get("name", "").strip().strip('"').strip('\\"')
            if name == f"elementId[{i}]":
                eid_input = inp
            if name == f"quantity[{i}]":
                qty_input = inp
        if not eid_input:
            break
        sub_id = eid_input.get("value", "").strip().strip('"')
        qty = qty_input.get("value", "1").strip().strip('"') if qty_input else "1"
        quantities[sub_id] = (i, qty)
        sub_elements.append(sub_id)
        i += 1

    if not sub_elements:
        # Plain leaf element, no "Linked modules" table.
        sub_elements.append(element_id)

    parameters = []
    explorer_parameters = []
    known_sensitivity = {}
    # Checked once discovery finishes, so problems block connecting instead of mid-run.

    def process_element(elem_id, elem_name, short_name, depth=0):
        elem_html = get_html(elem_id)
        elem_soup = BeautifulSoup(elem_html, "html.parser")

        all_inputs_e = elem_soup.find_all("input")
        sub_sub_elements = []
        j = 1
        while True:
            eid = None
            for inp in all_inputs_e:
                n = inp.get("name", "").strip().strip('"')
                if n == f"elementId[{j}]":
                    eid = inp.get("value", "").strip().strip('"')
                    break
            if not eid:
                break
            sub_sub_elements.append(eid)
            j += 1

        # Generous depth cap to avoid runaway recursion on unexpectedly deep nesting.
        if sub_sub_elements and depth < 6:
            for ssidx, ss_id in enumerate(sub_sub_elements, start=1):
                ss_name_val = ss_id
                for inp in elem_soup.find_all("input"):
                    n = inp.get("name", "").strip().strip('"')
                    if n == "name":
                        ss_name_val = inp.get("value", ss_id).strip().strip('"')
                        break
                ss_short = f"{ss_name_val.strip()} ({ssidx})"
                process_element(ss_id, ss_name_val, ss_short, depth + 1)
        else:
            layer_ids = set()
            layer_values = {}
            for inp in all_inputs_e:
                name = inp.get("name", "").strip().strip('"')
                value = inp.get("value", "").strip().strip('"')
                match = re.match(r"(size|areaRatio|lifeTime|quantity)\[(\d+)\]", name)
                if match:
                    layer_ids.add(match.group(2))
                    layer_values[name] = value

            # Real material names instead of generic "Layer N" labels.
            layer_material_names = {}
            for layer_id in layer_ids:
                container = elem_soup.find("li", id=f"component-group-{layer_id}")
                if container is None:
                    container = elem_soup.find("div", id=f"component-{layer_id}")
                if container is None:
                    continue
                name_link = next(
                    (a for a in container.find_all("a") if not a.get("class")),
                    None
                )
                if name_link and name_link.get_text(strip=True):
                    raw_name = name_link.get_text(strip=True)
                    layer_material_names[layer_id] = (
                        raw_name[:40].strip() + "…" if len(raw_name) > 40 else raw_name
                    )

            for gap_field in _find_lifetime_reason_gaps_in_soup(elem_soup):
                gap_match = re.search(r"\[(\d+)\]", gap_field)
                gap_layer_id = gap_match.group(1) if gap_match else "?"
                gap_material = layer_material_names.get(gap_layer_id, f"Layer {gap_layer_id}")
                reason_gaps.append(f"{short_name} - {gap_material}")

            for stale_field in _find_stale_lifetime_markers_in_soup(elem_soup):
                stale_match = re.search(r"\[(\d+)\]", stale_field)
                stale_layer_id = stale_match.group(1) if stale_match else "?"
                stale_material = layer_material_names.get(stale_layer_id, f"Layer {stale_layer_id}")
                stale_markers.append(f"{short_name} - {stale_material}")

            # Split/"Bay" layers: pair 2-member groups so their area ratio stays balanced.
            layer_partner = {}
            for group_li in elem_soup.find_all("li", id=re.compile(r"^component-group-\d+$")):
                if "siblings" not in (group_li.get("class") or []):
                    continue
                primary_id = group_li["id"].replace("component-group-", "")
                member_ids = [primary_id]
                for div in group_li.find_all("div", id=re.compile(r"^component-\d+$")):
                    if "sibling" in (div.get("class") or []):
                        member_ids.append(div["id"].replace("component-", ""))
                if len(member_ids) == 2:
                    a, b = member_ids
                    layer_partner[a] = b
                    layer_partner[b] = a

            # Disambiguate repeated material names so results don't collide.
            material_name_counts = {}
            for name in layer_material_names.values():
                material_name_counts[name] = material_name_counts.get(name, 0) + 1
            material_name_seen = {}

            layer_num = 1
            other_num = 1
            for layer_id in sorted(layer_ids):
                size_val = layer_values.get(f"size[{layer_id}]")
                area_val = layer_values.get(f"areaRatio[{layer_id}]", "100,0")
                life_val = layer_values.get(f"lifeTime[{layer_id}]", "50")
                material_name = layer_material_names.get(layer_id)
                if material_name is not None and material_name_counts[material_name] > 1:
                    material_name_seen[material_name] = material_name_seen.get(material_name, 0) + 1
                    material_name = f"{material_name} ({material_name_seen[material_name]})"

                if size_val is None:
                    other_label = material_name or f"Other {other_num}"
                    try:
                        life_float = float(life_val.replace(",", "."))
                        parameters.append((f"{short_name} - {other_label} - lifetime", "lifetime", elem_id, f"lifeTime[{layer_id}]", life_float))
                        explorer_parameters.append((f"{short_name} - {other_label} - lifetime (yr)", "lifetime", elem_id, f"lifeTime[{layer_id}]", life_float, 1.0, 1.0, 200.0))
                    except ValueError:
                        pass
                    # "Other Materials" has its own Amount field too.
                    other_qty_val = layer_values.get(f"quantity[{layer_id}]")
                    if other_qty_val is not None:
                        try:
                            other_qty_float = float(other_qty_val.replace(",", "."))
                            qty_max = max(other_qty_float * 10, 100.0) if other_qty_float > 0 else 100.0
                            qty_step = max(other_qty_float * 0.1, 0.1)
                            parameters.append((f"{short_name} - {other_label} - amount", "quantity", elem_id, f"quantity[{layer_id}]", other_qty_float))
                            explorer_parameters.append((f"{short_name} - {other_label} - amount", "quantity", elem_id, f"quantity[{layer_id}]", other_qty_float, qty_step, 0.0, qty_max))
                        except ValueError:
                            pass
                    other_num += 1
                    continue

                try:
                    size_float = float(size_val.replace(",", "."))
                    area_float = float(area_val.replace(",", "."))
                    life_float = float(life_val.replace(",", "."))
                except ValueError:
                    layer_num += 1
                    continue

                if material_name is None and size_float == 0:
                    # Empty/unused slot, skip.
                    layer_num += 1
                    continue

                layer_label = material_name or f"Layer {layer_num}"
                parameters.append((f"{short_name} - {layer_label} - thickness", "size", elem_id, f"size[{layer_id}]", size_float))
                parameters.append((f"{short_name} - {layer_label} - area ratio", "area_ratio", elem_id, f"areaRatio[{layer_id}]", area_float))
                parameters.append((f"{short_name} - {layer_label} - lifetime", "lifetime", elem_id, f"lifeTime[{layer_id}]", life_float))

                explorer_parameters.append((f"{short_name} - {layer_label} - thickness (mm)", "size", elem_id, f"size[{layer_id}]", size_float, 1.0, 0.0, 2000.0))
                explorer_parameters.append((f"{short_name} - {layer_label} - lifetime (yr)", "lifetime", elem_id, f"lifeTime[{layer_id}]", life_float, 1.0, 1.0, 200.0))
                if layer_id in layer_partner:
                    partner_key = f"areaRatio[{layer_partner[layer_id]}]"
                    partner_label = layer_material_names.get(layer_partner[layer_id], "the paired material")
                    explorer_parameters.append((f"{short_name} - {layer_label} - area ratio (%)", "area_ratio", elem_id, f"areaRatio[{layer_id}]", area_float, 1.0, 0.0, 100.0, partner_key, partner_label))
                layer_num += 1

    for sub_idx, sub_id in enumerate(sub_elements, start=1):
        sub_html = get_html(sub_id)
        sub_soup = BeautifulSoup(sub_html, "html.parser")

        sub_name = sub_id
        for inp in sub_soup.find_all("input"):
            n = inp.get("name", "").strip().strip('"')
            if n == "name":
                sub_name = inp.get("value", sub_id).strip().strip('"')
                break

        short_name = f"{sub_name.strip()} ({sub_idx})"
        process_element(sub_id, sub_name, short_name)

        if sub_id in quantities:
            idx, qty_val_str = quantities[sub_id]
            qty_key = f"quantity[{idx}]"
            if f"{short_name} - quantity" not in [p[0] for p in parameters]:
                qty_val = float(qty_val_str.replace(",", "."))
                parameters.insert(0, (f"{short_name} - quantity", "quantity", None, qty_key, qty_val))
                explorer_parameters.insert(0, (f"{short_name} - quantity", "quantity", None, qty_key, qty_val, 0.1, 0.0, 10.0))
                known_sensitivity[f"{short_name} - quantity"] = 6.0

    if not parameters:
        raise RuntimeError(
            f"Loaded '{element_name}' but found zero editable parameters "
            f"(no elementId[n]/size[n]/lifeTime[n]/quantity[n] fields on its "
            f"sub-element pages). Either this element has no linked modules/"
            f"layers, or the page didn't finish rendering before it was read. "
            f"Try reconnecting."
        )

    if reason_gaps:
        raise RuntimeError(
            f"Before analyzing: {'; '.join(reason_gaps)} has \"Own\" "
            "selected for its useful life but no reason typed in. eLCA "
            "won't save that page without one. Open it in eLCA, type any "
            "reason under \"Useful lives\", save, and reconnect."
        )

    if stale_markers:
        raise RuntimeError(
            f"Before analyzing: {'; '.join(stale_markers)} still has a "
            "custom (\"Own\") lifetime with the reason \"sensitivity "
            "analysis\". This is most likely left over from an earlier "
            "interrupted run of this tool, not a real value. Check it in "
            "eLCA: if it's leftover, switch it back to standard and save; "
            "if you set it on purpose, just change the reason text and "
            "save. Then reconnect."
        )

    return {
        "project_id": project_id,
        "rel_id": element_id,
        "name": element_name,
        "parameters": parameters,
        "explorer_parameters": explorer_parameters,
        "known_sensitivity": known_sensitivity,
        "reference_period": _selenium_get_reference_period(driver, project_id),
        "project_gwp_per_m2": _selenium_get_project_gwp_per_m2(driver, project_id),
    }


def _selenium_get_reference_period(driver, project_id):
    """Project's reference study period (years), used to explain lifetime
    jumps via replacement count. Returns None on failure."""
    from selenium.webdriver.common.by import By

    try:
        import time as _time
        _selenium_navigate_fresh(
            driver, f"{BASE_URL}/projects/{project_id}/#!/project-data/general/"
        )
        _wait_for_element(driver, By.NAME, "lifeTime", timeout=15)
        deadline = _time.time() + 6
        last = driver.find_element(By.NAME, "lifeTime").get_attribute("value")
        while _time.time() < deadline:
            _time.sleep(0.3)
            nxt = driver.find_element(By.NAME, "lifeTime").get_attribute("value")
            if nxt == last:
                break
            last = nxt
        return float(last.replace(",", "."))
    except Exception:
        return None


def _selenium_get_project_gwp_per_m2(driver, project_id):
    """Project's overall GWP intensity, for building-wide context next to
    element results. Returns None on failure."""
    from selenium.webdriver.common.by import By

    def _read_value():
        tables = driver.find_elements(By.CSS_SELECTOR, "table.report.report-effects")
        if not tables:
            return None
        rows = tables[0].find_elements(By.TAG_NAME, "tr")
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 3 and cells[0].text.strip() == "GWP total impact":
                return cells[-1].text.strip()
        return None

    try:
        import time as _time
        _selenium_navigate_fresh(
            driver, f"{BASE_URL}/projects/{project_id}/#!/project-reports/summary/"
        )
        _wait_for_element(driver, By.CSS_SELECTOR, "table.report.report-effects", timeout=15)
        deadline = _time.time() + 6
        last = _read_value()
        while _time.time() < deadline:
            _time.sleep(0.3)
            nxt = _read_value()
            if nxt == last:
                break
            last = nxt
        return float(last.replace(",", ".")) if last is not None else None
    except Exception:
        return None


def run_full_sensitivity_analysis_selenium(driver, comp, variation_percent=10, progress_callback=None, parameters=None):
    """One-at-a-Time sweep: each parameter changed by +variation_percent%,
    then reset. One row per parameter in the returned DataFrame."""
    project_id = comp["project_id"]
    parent_id = comp["rel_id"]
    delta = variation_percent / 100
    params_to_test = parameters if parameters is not None else comp["parameters"]
    total_params = len(params_to_test)

    baseline_gwp = _selenium_get_current_gwp(driver, project_id, parent_id)
    if baseline_gwp is None:
        raise RuntimeError(
            "Could not read the baseline GWP value from eLCA (no GWP column "
            "found on the composite element's page). Try reconnecting."
        )

    results = []
    for idx, (label, param_type, layer_id, param_key, original_value) in enumerate(params_to_test, start=1):
        if progress_callback:
            progress_callback(idx - 1, total_params, label)

        modified_value = original_value * (1 + delta)
        modified_gwp = None
        try:
            modified_gwp = _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, modified_value
            )
        finally:
            # Always reset, even on error.
            _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, original_value
            )
            if param_type == "lifetime":
                _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key)

        if progress_callback:
            progress_callback(idx, total_params, label)

        if modified_gwp is None or baseline_gwp is None:
            continue

        absolute_change = modified_gwp - baseline_gwp
        relative_change_percent = (absolute_change / baseline_gwp) * 100 if baseline_gwp else 0.0
        value_delta = modified_value - original_value
        finite_difference = (absolute_change / value_delta) if value_delta else 0.0
        normalized_sensitivity = (
            ((modified_gwp - baseline_gwp) / baseline_gwp) / (value_delta / original_value)
            if baseline_gwp and original_value and value_delta else 0.0
        )

        results.append({
            "Parameter": label,
            "Parameter Type": param_type,
            "Original Value": original_value,
            "Modified Value": modified_value,
            "Baseline GWP": baseline_gwp,
            "Modified GWP": modified_gwp,
            "Absolute Change": absolute_change,
            "Relative Change (%)": relative_change_percent,
            "Finite Difference": finite_difference,
            "Normalized Sensitivity": normalized_sensitivity,
        })

    if not results:
        raise RuntimeError(
            "No parameter could be read back with a valid GWP value, so no "
            "sensitivity results were produced. This usually means the GWP "
            "column couldn't be located on the eLCA page for any of the tested "
            "parameters (e.g. an unexpected UI language or layout change)."
        )

    df = pd.DataFrame(results)
    df["Absolute Sensitivity"] = df["Normalized Sensitivity"].abs()
    df = df.sort_values(by="Absolute Sensitivity", ascending=False)
    return df


def run_parameter_explorer_selenium(driver, comp, user_values, should_stop=None):
    """Applies every changed explorer parameter, reads the combined GWP,
    then resets everything touched."""
    project_id = comp["project_id"]
    parent_id = comp["rel_id"]

    baseline_gwp = _selenium_get_current_gwp(driver, project_id, parent_id)

    changed = []
    cleanup_warnings = []
    new_gwp = baseline_gwp
    try:
        for ep in comp["explorer_parameters"]:
            label, param_type, layer_id, param_key, baseline_val = ep[0], ep[1], ep[2], ep[3], ep[4]
            partner_key = ep[8] if len(ep) > 8 else None
            new_val = user_values.get(param_key, baseline_val)
            if abs(new_val - baseline_val) < 1e-9:
                continue
            if should_stop is not None and should_stop():
                raise AnalysisStopped("Stopped by user before this parameter was changed.")
            changed.append((label, param_type, layer_id, param_key, baseline_val, partner_key))
            new_gwp = _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, new_val, partner_key
            )
    finally:
        # Revert each param individually so one failed reset doesn't skip the rest.
        for label, param_type, layer_id, param_key, baseline_val, partner_key in changed:
            try:
                _selenium_set_parameter_and_get_gwp(
                    driver, comp, project_id, param_type, layer_id, param_key, baseline_val, partner_key
                )
            except Exception:
                cleanup_warnings.append(
                    f"{label}: could not confirm this was reset back to baseline after a "
                    f"failure mid-run; check its value in eLCA directly."
                )
                continue
            if param_type == "lifetime":
                cleaned = _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key)
                if not cleaned:
                    cleanup_warnings.append(
                        f"{label}: value restored, but eLCA may still show this layer as "
                        f"a custom (\"Own\") lifetime with reason \"sensitivity analysis\": "
                        f"check it in eLCA and switch back to standard if so."
                    )

    if baseline_gwp is None or new_gwp is None:
        raise RuntimeError("Could not read GWP from eLCA.")

    absolute_change = new_gwp - baseline_gwp
    relative_change = (absolute_change / baseline_gwp) * 100 if baseline_gwp else 0.0

    return {
        "baseline_gwp": baseline_gwp,
        "new_gwp": new_gwp,
        "absolute_change": absolute_change,
        "relative_change": relative_change,
        "cleanup_warnings": cleanup_warnings,
    }


def run_additivity_check_selenium(driver, comp, user_values, should_stop=None):
    """Measures each changed parameter's individual GWP effect, then the
    combined effect, and compares the two."""
    project_id = comp["project_id"]
    parent_id = comp["rel_id"]

    baseline_gwp = _selenium_get_current_gwp(driver, project_id, parent_id)

    changed_params = []
    for ep in comp["explorer_parameters"]:
        label, param_type, layer_id, param_key, baseline_val = ep[0], ep[1], ep[2], ep[3], ep[4]
        partner_key = ep[8] if len(ep) > 8 else None
        new_val = user_values.get(param_key, baseline_val)
        if abs(new_val - baseline_val) < 1e-9:
            continue
        changed_params.append((label, param_type, layer_id, param_key, baseline_val, new_val, partner_key))

    individual_results = []
    sum_of_individual_changes = 0.0
    cleanup_warnings = []
    for label, param_type, layer_id, param_key, baseline_val, new_val, partner_key in changed_params:
        if should_stop is not None and should_stop():
            raise AnalysisStopped("Stopped by user before this parameter was changed.")
        gwp = None
        try:
            gwp = _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, new_val, partner_key
            )
        finally:
            try:
                _selenium_set_parameter_and_get_gwp(
                    driver, comp, project_id, param_type, layer_id, param_key, baseline_val, partner_key
                )
            except Exception:
                cleanup_warnings.append(
                    f"{label}: could not confirm this was reset back to baseline after a "
                    f"failure mid-run; check its value in eLCA directly."
                )
            else:
                if param_type == "lifetime":
                    cleaned = _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key)
                    if not cleaned:
                        cleanup_warnings.append(
                            f"{label}: value restored, but eLCA may still show this layer as "
                            f"a custom (\"Own\") lifetime with reason \"sensitivity analysis\": "
                            f"check it in eLCA and switch back to standard if so."
                        )
        delta = (gwp - baseline_gwp) if (gwp is not None and baseline_gwp is not None) else 0.0
        sum_of_individual_changes += delta
        individual_results.append({
            "Parameter": label,
            "Individual GWP change (kg CO2-eq)": round(delta, 4),
        })

    expected_gwp = baseline_gwp + sum_of_individual_changes

    # Apply all changed parameters together, then reset them all.
    actual_gwp = baseline_gwp
    try:
        for label, param_type, layer_id, param_key, baseline_val, new_val, partner_key in changed_params:
            if should_stop is not None and should_stop():
                raise AnalysisStopped("Stopped by user before this parameter was changed.")
            actual_gwp = _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, new_val, partner_key
            )
    finally:
        for label, param_type, layer_id, param_key, baseline_val, new_val, partner_key in changed_params:
            try:
                _selenium_set_parameter_and_get_gwp(
                    driver, comp, project_id, param_type, layer_id, param_key, baseline_val, partner_key
                )
            except Exception:
                cleanup_warnings.append(
                    f"{label}: could not confirm this was reset back to baseline after a "
                    f"failure mid-run; check its value in eLCA directly."
                )
                continue
            if param_type == "lifetime":
                cleaned = _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key)
                if not cleaned:
                    cleanup_warnings.append(
                        f"{label}: value restored, but eLCA may still show this layer as "
                        f"a custom (\"Own\") lifetime with reason \"sensitivity analysis\": "
                        f"check it in eLCA and switch back to standard if so."
                    )

    interaction = actual_gwp - expected_gwp
    interaction_pct = (abs(interaction) / baseline_gwp) * 100 if baseline_gwp else 0.0
    is_additive = interaction_pct < 5.0

    return {
        "baseline_gwp": baseline_gwp,
        "expected_gwp": expected_gwp,
        "actual_gwp": actual_gwp,
        "interaction": interaction,
        "interaction_pct": interaction_pct,
        "is_additive": is_additive,
        "individual_results": individual_results,
        "cleanup_warnings": cleanup_warnings,
    }


def run_robustness_analysis_selenium(driver, comp, param_label, min_factor=0.5, max_factor=1.5, steps=11):
    """Sweeps a single parameter across [min_factor, max_factor] of
    baseline. Returns a DataFrame with columns Factor, Parameter Value,
    Actual Value, GWP."""
    import numpy as np

    project_id = comp["project_id"]
    parent_id = comp["rel_id"]
    factors = np.linspace(min_factor, max_factor, steps)

    param_def = None
    for ep in comp["explorer_parameters"]:
        if ep[0] == param_label:
            param_def = ep
            break
    if param_def is None:
        raise ValueError(f"Parameter not found: {param_label}")

    label, param_type, layer_id, param_key, baseline_val = param_def[0], param_def[1], param_def[2], param_def[3], param_def[4]
    min_bound = param_def[6] if len(param_def) > 6 else None
    max_bound = param_def[7] if len(param_def) > 7 else None
    partner_key = param_def[8] if len(param_def) > 8 else None

    results = []
    try:
        for factor in factors:
            modified_value = baseline_val * factor
            if min_bound is not None and modified_value < min_bound:
                continue
            if max_bound is not None and modified_value > max_bound:
                continue
            gwp = _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, modified_value, partner_key
            )
            results.append({"Factor": factor, "Parameter Value": factor, "Actual Value": modified_value, "GWP": gwp})
    finally:
        # Always reset to baseline.
        _selenium_set_parameter_and_get_gwp(
            driver, comp, project_id, param_type, layer_id, param_key, baseline_val, partner_key
        )
        if param_type == "lifetime":
            _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key)

    return pd.DataFrame(results).dropna(subset=["GWP"])


def run_full_nonlinearity_scan_selenium(driver, comp, min_factor=0.5, max_factor=1.5,
                                         steps=11, linearity_threshold=5.0, progress_callback=None,
                                         parameters=None):
    """Sweeps every explorer parameter across [min_factor, max_factor] of
    baseline. Returns (summary_df, detail_dfs, cleanup_warnings)."""
    import numpy as np

    project_id = comp["project_id"]
    parent_id = comp["rel_id"]
    reference_period = comp.get("reference_period")

    params_for_reset = parameters if parameters is not None else comp["explorer_parameters"]
    for ep in params_for_reset:
        r_layer_id, r_param_key, r_baseline_val = ep[2], ep[3], ep[4]
        r_partner_key = ep[8] if len(ep) > 8 else None
        try:
            # Defensive: force this parameter's own field back to its original
            # value before trusting the composite baseline, in case an earlier
            # interrupted attempt (crash, retry) left it not fully reverted.
            _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, ep[1], r_layer_id, r_param_key, r_baseline_val, r_partner_key
            )
            if ep[1] == "lifetime":
                _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, r_layer_id, r_param_key)
        except Exception:
            pass  # best-effort; the per-factor loop below verifies everything it writes anyway

    baseline_gwp = _selenium_get_current_gwp(driver, project_id, parent_id)
    if baseline_gwp is None:
        raise RuntimeError(
            "Could not read the baseline GWP value from eLCA (no GWP column "
            "found on the composite element's page). Try reconnecting."
        )

    # Stage breakdown for interpretation text later.
    baseline_stage_breakdown = {}
    try:
        from bs4 import BeautifulSoup
        baseline_stage_breakdown = _extract_all_stage_values_from_page(
            BeautifulSoup(driver.page_source, "html.parser")
        )
    except Exception:
        pass

    params = parameters if parameters is not None else comp["explorer_parameters"]
    total_params = len(params)

    def _lifetime_threshold_factors(baseline_val, rsp, hi_factor, lo_bound=None, max_thresholds=30):
        """Extra sample points at each replacement-count threshold
        (rsp / k), where the GWP curve actually jumps."""
        if not rsp or rsp <= 0 or not baseline_val or baseline_val <= 0:
            return []
        factors = []
        hi_val = baseline_val * hi_factor
        floor_val = lo_bound if (lo_bound is not None and lo_bound > 0) else 1.0
        thresholds_found = 0
        for k in range(1, 501):
            threshold_val = rsp / k
            if threshold_val > hi_val:
                continue
            if threshold_val < floor_val:
                break
            eps = max(threshold_val * 0.03, 0.25)
            for cand in (threshold_val - eps, threshold_val + eps):
                if cand >= floor_val:
                    factors.append(cand / baseline_val)
            thresholds_found += 1
            if thresholds_found >= max_thresholds:
                break
        return factors

    summary_rows = []
    detail_dfs = {}
    cleanup_warnings = []

    for idx, ep in enumerate(params, start=1):
        label, param_type, layer_id, param_key, baseline_val = ep[0], ep[1], ep[2], ep[3], ep[4]
        min_bound = ep[6] if len(ep) > 6 else None
        max_bound = ep[7] if len(ep) > 7 else None
        partner_key = ep[8] if len(ep) > 8 else None

        if progress_callback:
            progress_callback(idx - 1, total_params, label)

        candidate_factors = list(np.linspace(min_factor, max_factor, steps))
        if param_type == "lifetime":
            candidate_factors += _lifetime_threshold_factors(
                baseline_val, reference_period, max_factor, lo_bound=min_bound
            )
        else:
            candidate_factors += [0.25, 2.0]

        seen_values = []
        factors_to_test = []
        for f in sorted(candidate_factors):
            if abs(f - 1.0) < 1e-9:
                continue
            value = baseline_val * f
            if min_bound is not None and value < min_bound:
                continue
            if max_bound is not None and value > max_bound:
                continue
            if value <= 0:
                continue
            if seen_values and abs(value - seen_values[-1]) < 0.05:
                continue
            seen_values.append(value)
            factors_to_test.append(f)

        baseline_point = {"Parameter Value": 1.0, "Actual Value": baseline_val, "GWP": baseline_gwp}
        baseline_point.update(baseline_stage_breakdown)
        data_points = [baseline_point]
        try:
            for i, factor in enumerate(factors_to_test):
                modified_value = baseline_val * factor
                gwp = _selenium_set_parameter_and_get_gwp(
                    driver, comp, project_id, param_type, layer_id, param_key, modified_value, partner_key
                )
                point = {"Parameter Value": factor, "Actual Value": modified_value, "GWP": gwp}
                try:
                    from bs4 import BeautifulSoup
                    point.update(_extract_all_stage_values_from_page(
                        BeautifulSoup(driver.page_source, "html.parser")
                    ))
                except Exception:
                    pass
                data_points.append(point)
                if progress_callback:
                    progress_callback(idx - 1, total_params, f"{label} ({i + 1}/{len(factors_to_test)})")
        finally:
            _selenium_set_parameter_and_get_gwp(
                driver, comp, project_id, param_type, layer_id, param_key, baseline_val, partner_key
            )
            if param_type == "lifetime":
                cleaned = _selenium_cleanup_lifetime_marker(driver, project_id, parent_id, layer_id, param_key)
                if not cleaned:
                    cleanup_warnings.append(
                        f"{label}: value restored, but eLCA may still show this layer as "
                        f"a custom (\"Own\") lifetime with reason \"sensitivity analysis\": "
                        f"check it in eLCA and switch back to standard if so."
                    )

        df = pd.DataFrame(data_points).sort_values("Parameter Value").dropna(subset=["GWP"])
        detail_dfs[label] = df

        if len(df) >= 2:
            x = df["Parameter Value"].values
            y = df["GWP"].values
            baseline_row = df.iloc[(df["Parameter Value"] - 1.0).abs().argsort()[:1]]
            b_gwp = baseline_row["GWP"].values[0]

            coeffs = np.polyfit(x, y, 1)
            y_linear = np.polyval(coeffs, x)
            residuals = np.abs(y - y_linear)
            max_residual_pct = (residuals.max() / b_gwp) * 100 if b_gwp else 0.0
            gwp_range = y.max() - y.min()
            relative_range = (gwp_range / b_gwp) * 100 if b_gwp else 0.0
            # Judged against this parameter's own swing, not the total baseline.
            max_residual_pct_of_range = (residuals.max() / gwp_range * 100) if gwp_range else 0.0
            is_non_linear = max_residual_pct_of_range >= linearity_threshold
            if not is_non_linear and gwp_range > 0:
                # Catches a staircase that passes the residual check on average.
                step_jumps = np.abs(np.diff(y))
                if len(step_jumps):
                    sorted_jumps = np.sort(step_jumps)[::-1]
                    cum_jumps = np.cumsum(sorted_jumps)
                    n_dominant = int(np.searchsorted(cum_jumps, 0.8 * gwp_range)) + 1
                    is_non_linear = (step_jumps.max() / gwp_range > 0.6) or (
                        n_dominant <= max(1, len(step_jumps) * 0.3)
                    )
        else:
            gwp_range = relative_range = max_residual_pct = max_residual_pct_of_range = 0.0
            is_non_linear = False

        summary_rows.append({
            "Parameter": label,
            "GWP Range": round(gwp_range, 4),
            "Relative Range (%)": round(relative_range, 2),
            "Max Deviation from Linear (%)": round(max_residual_pct, 3),
            "Non-linear": is_non_linear,
            "Points sampled": len(df),
        })

        if progress_callback:
            progress_callback(idx, total_params, label)

    summary_df = pd.DataFrame(summary_rows).sort_values(
        by="Max Deviation from Linear (%)", ascending=False
    ).reset_index(drop=True)
    return summary_df, detail_dfs, cleanup_warnings
