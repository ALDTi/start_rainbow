import json
import re
import math
import numpy as np
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Farm Slot Planner", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Rajdhani', sans-serif;
    }
    .stApp {
        background: #0d0f14;
        color: #c9d1d9;
    }
    h1, h2, h3 {
        font-family: 'Share Tech Mono', monospace !important;
        color: #58a6ff !important;
        letter-spacing: 0.05em;
    }
    .block-container { padding-top: 2rem; }

    /* green button (no animals) */
    .btn-green a {
        background: #0d4429 !important;
        color: #3fb950 !important;
        border: 1px solid #238636 !important;
        font-family: 'Share Tech Mono', monospace !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        border-radius: 4px !important;
        padding: 6px 10px !important;
        transition: all 0.15s ease !important;
        width: 100% !important;
        display: inline-block;
        text-decoration: none !important;
        text-align: center;
    }
    .btn-green a:hover {
        background: #0f5132 !important;
        border-color: #3fb950 !important;
        box-shadow: 0 0 8px #3fb95044 !important;
        color: #3fb950 !important;
    }

    /* red button (has animals) */
    .btn-red a {
        background: #3d0f0f !important;
        color: #f85149 !important;
        border: 1px solid #da3633 !important;
        font-family: 'Share Tech Mono', monospace !important;
        font-size: 0.8rem !important;
        font-weight: 600 !important;
        border-radius: 4px !important;
        padding: 6px 10px !important;
        transition: all 0.15s ease !important;
        width: 100% !important;
        display: inline-block;
        text-decoration: none !important;
        text-align: center;
    }
    .btn-red a:hover {
        background: #5a1a1a !important;
        border-color: #f85149 !important;
        box-shadow: 0 0 8px #f8514944 !important;
        color: #f85149 !important;
    }

    /* row styling */
    .slot-row {
        display: grid;
        gap: 8px;
        align-items: center;
        padding: 5px 12px;
        border-left: 1px solid #30363d;
        border-right: 1px solid #30363d;
        border-bottom: 1px solid #21262d;
        background: #0d1117;
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.85rem;
    }
    .slot-row:hover { background: #161b22; }
    .slot-row:last-child { border-radius: 0 0 6px 6px; border-bottom: 1px solid #30363d; }

    .coord { color: #e6edf3; font-weight: 600; }
    .dist  { color: #8b949e; }
    .team  { color: #d2a679; }
    .team-zero { color: #3fb950; }
    .team-unclearable { color: #6e7681; font-style: italic; }
    .btn-disabled {
        background: #161b22;
        color: #484f58;
        border: 1px solid #30363d;
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.8rem;
        border-radius: 4px;
        padding: 6px 10px;
        text-align: center;
        width: 100%;
        display: inline-block;
    }

    .tribe-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 4px;
        font-family: 'Share Tech Mono', monospace;
        font-size: 0.8rem;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    .tribe-gaul   { background: #0d4429; color: #3fb950; border: 1px solid #238636; }
    .tribe-teuton { background: #3d2a00; color: #e3a840; border: 1px solid #a67820; }

    .stButton { margin: 0 !important; }
    div[data-testid="stHorizontalBlock"] { gap: 6px !important; align-items: center; }
</style>
""", unsafe_allow_html=True)

# ── constants ──────────────────────────────────────────────────────────────────
SERVER     = "ts12.x1.europe.travian.com"
SHEET_ID   = "1-9hAUMfgoehZ_ILgsVDwu2ib1j4LlXd4RwwUhvrMO-Y"
SHEET_NAME = "cookie"

animal_values  = [160, 160, 160, 160, 320, 320, 480, 480, 480, 800]
spawn_rates    = [5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
animal_cav_def = [20, 40, 60, 50, 33, 70, 200, 240, 250, 520]
animal_inf_def = [25, 35, 40, 66, 70, 80, 140, 380, 170, 440]

# Gaul constants
TT_ATK  = 100
TT_COST = 1050
TT_SPD  = 19

# Teuton constants
CLUB_ATK  = 40
TK_ATK    = 150
CLUB_COST = 250
TK_COST   = 1525
CLUB_SPD  = 7   # clubs are the slowest troop → dictates speed

# ── Gaul engine ───────────────────────────────────────────────────────────────
def gaul_hp_lost(animals, ntt):
    attacker_points = TT_ATK * ntt
    if attacker_points <= 0:
        return 1.0
    cav_def = np.sum([a * d for a, d in zip(animals, animal_cav_def)])
    nature_points = cav_def + 10
    atk_result = 100 * (nature_points / attacker_points) ** 1.5
    return atk_result / (atk_result + 100)

def gaul_cost(hp_lost, ntt):
    return round(ntt * hp_lost) * TT_COST

def gaul_get_best_team(animals, max_tt=500, profit_factor=0.8):
    for ntt in range(1, max_tt + 1):
        hp_lost = gaul_hp_lost(animals, ntt)
        cost    = gaul_cost(hp_lost, ntt)
        gain    = get_res_gained(animals, hp_lost)
        if total_animals_left(animals, hp_lost) <= 1 and gain >= profit_factor * cost:
            return ntt
    return None

def gaul_build_url(x, y, village_id, n):
    node_id = get_nodeid(x, y)
    return (
        f"https://{SERVER}/build.php?"
        f"newdid={village_id}&gid=16&"
        f"tt=2&troop%5Bt4%5D={n}&"
        f"targetMapId={node_id}&eventType=4&"
    )

# ── Teuton engine ─────────────────────────────────────────────────────────────
def teuton_hp_lost(animals, nclub, ntk):
    inf_atk   = CLUB_ATK * nclub
    cav_atk   = TK_ATK   * ntk
    total_atk = inf_atk + cav_atk
    if total_atk <= 0:
        return 1.0
    inf_def = np.sum([a * d for a, d in zip(animals, animal_inf_def)])
    cav_def = np.sum([a * d for a, d in zip(animals, animal_cav_def)])
    nature_points = (inf_def * (inf_atk / total_atk)) + (cav_def * (cav_atk / total_atk)) + 10
    atk_result = 100 * (nature_points / total_atk) ** 1.5
    return atk_result / (atk_result + 100)

def teuton_cost(hp_lost, nclub, ntk):
    return round(ntk * hp_lost) * TK_COST + round(nclub * hp_lost) * CLUB_COST

def teuton_get_best_team(animals, max_clubs=500, max_tk=20, profit_factor=0.8):
    """
    Full 2-D search over (nclub, ntk).
    Validity: ≤1 animal left AND gain ≥ profit_factor × cost.
    Returns the valid combo with the lowest team deployment cost (clubs*250 + tk*1525).
    """
    best_teamcost = np.inf
    best          = None

    for ntk in range(0, max_tk + 1):
        for nclub in range(1, max_clubs + 1):
            hp_lost   = teuton_hp_lost(animals, nclub, ntk)
            cost      = teuton_cost(hp_lost, nclub, ntk)
            gain      = get_res_gained(animals, hp_lost)
            left      = total_animals_left(animals, hp_lost)
            team_cost = CLUB_COST * nclub + TK_COST * ntk

            if left > 1 or gain < profit_factor * cost:
                continue

            if team_cost < best_teamcost:
                best_teamcost = team_cost
                best          = (nclub, ntk)

    return best  # (nclub, ntk) or None

def teuton_build_url(x, y, village_id, nclub, ntk):
    node_id = get_nodeid(x, y)
    tk_part = f"troop%5Bt6%5D={ntk}&" if ntk > 0 else ""
    return (
        f"https://{SERVER}/build.php?"
        f"newdid={village_id}&gid=16&"
        f"tt=2&troop%5Bt1%5D={nclub}&{tk_part}"
        f"targetMapId={node_id}&eventType=4&"
    )

# ── shared helpers ────────────────────────────────────────────────────────────
def get_res_gained(animals, hp_lost):
    return sum(round(c * (1 - hp_lost)) * v for c, v in zip(animals, animal_values))

def total_animals_left(animals, hp_lost):
    return sum(round(c * hp_lost) for c in animals)

def adapt_unit_counts(unit_counts, distance, speed):
    # find the highest animal type present
    last = next((i for i in range(9, -1, -1) if unit_counts[i] != 0), 0)
    spawn_rate = spawn_rates[last]
    if distance < 20:
        runtime = distance / speed
    else:
        runtime = (20 / speed) + ((distance - 20) / (speed * 4.2))
    units_spawned = round(int(runtime * 60) / spawn_rate)

    # cap: if multiple animal types present, highest type can't exceed count of second-highest
    nonzero_counts = sorted([c for c in unit_counts if c > 0])
    if len(nonzero_counts) >= 2:
        second_highest = nonzero_counts[-2]
        max_spawn = max(0, second_highest - unit_counts[last])
        units_spawned = min(units_spawned, max_spawn)

    unit_counts[last] += units_spawned
    return unit_counts

def get_nodeid(x, y):
    return (200 - y) * 401 + (x + 200) + 1

def build_map_url(x, y):
    return f"https://{SERVER}/karte.php?x={x}&y={y}"

def troops_needed(dist, speed):
    CYCLE_HR = 6 / 60
    return math.ceil((2 * dist / speed) / CYCLE_HR)

# ── sheet helpers ─────────────────────────────────────────────────────────────
def read_cookie_from_sheet(sheet_id, sheet_name):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    df  = pd.read_csv(url, header=None)
    return str(df.values[0][0])

def read_json_from_sheet(sheet_id, sheet_name="JSON"):
    url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&sheet={sheet_name}"
    df  = pd.read_csv(url, header=None)
    return json.loads(str(df.values[0][0]))

# ── map request helpers ───────────────────────────────────────────────────────
def post_request(server, x, y, cookie):
    url     = f"https://{server}/api/v1/map/position"
    headers = {
        "authority": server,
        "content-type": "application/json; charset=UTF-8",
        "cookie": cookie,
        "origin": f"https://{server}",
        "referer": f"https://{server}/karte.php",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "x-requested-with": "XMLHttpRequest",
        "x-version": "52.8",
    }
    r = requests.post(url, headers=headers,
                      json={"data": {"x": x, "y": y, "zoomLevel": 3, "ignorePositions": []}},
                      timeout=25)
    r.raise_for_status()
    return r.text

def parse_all_animal_positions(raw_text):
    cleaned      = raw_text.replace("\\", "")
    chunks       = cleaned.split('"position":{')
    position_map = {}
    seen_coords  = set()
    for chunk in chunks:
        xm = re.search(r'"x":\s*(-?\d+)', chunk)
        ym = re.search(r'"y":\s*(-?\d+)', chunk)
        if not (xm and ym):
            continue
        x, y = int(xm.group(1)), int(ym.group(1))
        seen_coords.add((x, y))
        if "animal" not in chunk:
            continue
        units = re.findall(r'class="unit u(3[1-9]|40)"><\/i><span class="value ">(\d+)<\/span>', chunk)
        counts = [0] * 10
        for uid, cnt in units:
            counts[int(uid) - 31] = int(cnt)
        position_map[(x, y)] = counts
    return position_map, seen_coords

# ── UI ────────────────────────────────────────────────────────────────────────
st.title("⚔ Farm Slot Planner")

with st.expander("Settings", expanded=True):
    t_col, c1, c2, c3, c4 = st.columns([1.2, 1, 1, 1, 1.5])
    tribe         = t_col.selectbox("Tribe", ["Gaul", "Teuton"], index=0)
    default_speed = TT_SPD if tribe == "Gaul" else CLUB_SPD
    speed         = c1.number_input("Hero speed", value=default_speed, min_value=1, step=1)
    max_teams     = c2.number_input("Max teams", value=500, min_value=1, max_value=500, step=1)
    profit_factor = c3.number_input(
        "Profit factor",
        value=0.80, min_value=0.0, max_value=2.0, step=0.05, format="%.2f",
        help="Minimum gain/cost ratio (gain ≥ factor × cost). Lower = more aggressive.",
    )
    sheet_id      = c4.text_input("Sheet ID", value=SHEET_ID)

    badge_cls = "tribe-gaul" if tribe == "Gaul" else "tribe-teuton"
    badge_lbl = "🛡 GAUL — Teutates Thunder" if tribe == "Gaul" else "🪓 TEUTON — Clubswinger + TK"
    st.markdown(f'<span class="tribe-badge {badge_cls}">{badge_lbl}</span>', unsafe_allow_html=True)

run_btn = st.button("🔍 Analyse slots", use_container_width=True)

if run_btn:
    with st.spinner("Reading sheet data..."):
        try:
            cookie   = read_cookie_from_sheet(sheet_id, SHEET_NAME)
            raw_data = read_json_from_sheet(sheet_id)
        except Exception as e:
            st.error(f"Failed to read Google Sheet: {e}")
            st.stop()

    village_id = raw_data["data"]["farmList"]["ownerVillage"]["id"]
    slots = raw_data["data"]["farmList"]["slots"]
    rows  = []
    for slot in slots:
        rows.append({
            "x":        slot["target"]["x"],
            "y":        slot["target"]["y"],
            "troop_sum": sum(slot["troop"].values()),
            "isActive": slot["isActive"],
            "distance": slot["distance"],
        })
    df = pd.DataFrame(rows)

    with st.spinner("Fetching map data..."):
        try:
            first        = df.iloc[0]
            raw_map      = post_request(SERVER, int(first["x"]), int(first["y"]), cookie)
            position_map, seen_coords = parse_all_animal_positions(raw_map)

            unknown_coords = [
                (int(r["x"]), int(r["y"])) for _, r in df.iterrows()
                if (int(r["x"]), int(r["y"])) not in seen_coords
            ]
            if unknown_coords:
                progress = st.progress(0.0, text=f"Fetching {len(unknown_coords)} out-of-range coords...")
                for i, (ux, uy) in enumerate(unknown_coords, 1):
                    progress.progress(i / len(unknown_coords), text=f"Fetching ({ux}, {uy})  {i}/{len(unknown_coords)}")
                    try:
                        raw_extra = post_request(SERVER, ux, uy, cookie)
                        extra_map, extra_seen = parse_all_animal_positions(raw_extra)
                        position_map.update(extra_map)
                        seen_coords.update(extra_seen)
                    except Exception:
                        pass
                progress.empty()
        except Exception as e:
            st.error(f"Map request failed: {e}")
            st.stop()

    df["has_animals"] = df.apply(lambda r: (r["x"], r["y"]) in position_map, axis=1)
    df["unknown"]     = df.apply(lambda r: (r["x"], r["y"]) not in seen_coords, axis=1)
    df["animals"]     = df.apply(lambda r: position_map.get((r["x"], r["y"]), [0] * 10), axis=1)

    # tribe-aware team calculation
    if tribe == "Gaul":
        def calc_team(row):
            if not row["has_animals"]:
                return 0
            animals = adapt_unit_counts(row["animals"][:], row["distance"], speed)
            result  = gaul_get_best_team(animals, max_tt=max_teams, profit_factor=profit_factor)
            return result if result is not None else 0
        df["n_teams"]  = df.apply(calc_team, axis=1)
        df["n_clubs"]  = 0
        df["n_tk"]     = 0
    else:
        def calc_team_teuton(row):
            if not row["has_animals"]:
                return (0, 0)
            animals = adapt_unit_counts(row["animals"][:], row["distance"], speed)
            result  = teuton_get_best_team(animals, max_clubs=max_teams, max_tk=20, profit_factor=profit_factor)
            return result if result is not None else (0, 0)
        teuton_results = df.apply(calc_team_teuton, axis=1)
        df["n_clubs"]  = teuton_results.apply(lambda t: t[0])
        df["n_tk"]     = teuton_results.apply(lambda t: t[1])
        df["n_teams"]  = df["n_clubs"]  # for clearable check (0 = unclearable)

    # troop cycling columns (based on tribe speed)
    troop_spd = TT_SPD if tribe == "Gaul" else CLUB_SPD
    df["troops_needed"] = df["distance"].apply(lambda d: troops_needed(d, troop_spd))
    # Gaul also tracks Hae separately; Teuton doesn't
    if tribe == "Gaul":
        df["hae_needed"] = df["distance"].apply(lambda d: troops_needed(d, 13))

    st.session_state["df"]         = df
    st.session_state["village_id"] = village_id
    st.session_state["tribe"]      = tribe

# ── render results ────────────────────────────────────────────────────────────
if "df" in st.session_state:
    df         = st.session_state["df"]
    village_id = st.session_state["village_id"]
    tribe      = st.session_state.get("tribe", "Gaul")

    active   = df[df["isActive"] == True]
    inactive = df[df["isActive"] == False].reset_index(drop=True)

    st.subheader("Active farm requirements")
    if tribe == "Gaul":
        total_tt_active  = int(active["troops_needed"].sum())
        total_hae_active = int(active[active["troop_sum"] == 2]["hae_needed"].sum())
        a1, a2 = st.columns(2)
        a1.metric("TT needed (all active farms)", total_tt_active)
        a2.metric("Hae needed (TT/hae active farms)", total_hae_active)
    else:
        total_clubs = int(active["troops_needed"].sum())
        a1, a2 = st.columns(2)
        a1.metric("Clubs needed (all active farms)", total_clubs)
        a2.metric("TK needed (all active farms)", total_clubs)

    st.markdown("---")

    if inactive.empty:
        st.info("All slots are currently active — nothing to send.")
    else:
        total     = len(inactive)
        n_animals = int(inactive["has_animals"].sum())
        n_empty   = total - n_animals

        clearable      = inactive[(inactive["has_animals"]) & (inactive["n_teams"] > 0)]
        total_to_clear = int(clearable["n_teams"].sum())
        n_clearable    = len(clearable)

        team_label = "TT" if tribe == "Gaul" else "Club+TK teams"

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Inactive slots", total)
        m2.metric("🔴 With animals", n_animals)
        m3.metric("🟢 Empty oases", n_empty)
        m4.metric(f"⚔ {team_label} to clear all", total_to_clear,
                  help=f"{n_clearable} clearable oases")

        only_animals = st.checkbox("Show only oases with animals", value=False)
        if only_animals:
            inactive = inactive[inactive["has_animals"]].reset_index(drop=True)

        # build attack URL list for open-all button
        attack_urls = []
        for _, row in inactive.iterrows():
            if bool(row["has_animals"]) and int(row["n_teams"]) > 0:
                x, y = int(row["x"]), int(row["y"])
                if tribe == "Gaul":
                    attack_urls.append(gaul_build_url(x, y, village_id, int(row["n_teams"])))
                else:
                    attack_urls.append(teuton_build_url(x, y, village_id, int(row["n_clubs"]), int(row["n_tk"])))

        if attack_urls:
            urls_json = json.dumps(attack_urls)
            components.html(
                f"""<button onclick="var urls={urls_json};urls.forEach(function(u){{window.open(u,'_blank');}});"
                    style="background:#3d0f0f;color:#f85149;border:1px solid #da3633;
                           font-family:'Share Tech Mono',monospace;font-size:0.85rem;
                           font-weight:700;border-radius:4px;padding:8px 18px;cursor:pointer;
                           letter-spacing:0.05em;">
                    ⚔ Open all {len(attack_urls)} attacks in new tabs
                </button>""",
                height=55,
            )

        # table header — Teuton has no Hae column
        if tribe == "Gaul":
            st.markdown(
                '<div style="display:grid;grid-template-columns:120px 70px 90px 80px 60px 80px 80px;'
                'gap:8px;padding:6px 12px;background:#161b22;border:1px solid #30363d;'
                'border-radius:6px 6px 0 0;font-family:\'Share Tech Mono\',monospace;'
                'font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin-top:1rem;">'
                '<span>Action</span><span>Troops</span><span>Team</span>'
                '<span>Coords</span><span>Dist.</span><span>TT needed</span><span>Hae needed</span>'
                '</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="display:grid;grid-template-columns:120px 120px 80px 60px 100px;'
                'gap:8px;padding:6px 12px;background:#161b22;border:1px solid #30363d;'
                'border-radius:6px 6px 0 0;font-family:\'Share Tech Mono\',monospace;'
                'font-size:0.75rem;color:#8b949e;text-transform:uppercase;letter-spacing:0.1em;margin-top:1rem;">'
                '<span>Action</span><span>Team</span>'
                '<span>Coords</span><span>Dist.</span><span>Clubs/TK needed</span>'
                '</div>',
                unsafe_allow_html=True,
            )

        for idx, row in inactive.iterrows():
            x, y    = int(row["x"]), int(row["y"])
            n_teams = int(row["n_teams"])   # for Gaul TT count; Teuton uses n_clubs/n_tk
            dist    = round(row["distance"], 1)
            has_an  = bool(row["has_animals"])
            unknown = bool(row["unknown"])
            troops  = int(row["troops_needed"])

            if tribe == "Gaul":
                troop_type = {1: "TT", 2: "TT/hae"}.get(int(row["troop_sum"]), str(int(row["troop_sum"])))
                hae        = int(row["hae_needed"]) if int(row["troop_sum"]) == 2 else 0
                col_btn, col_type, col_team, col_coord, col_dist, col_tt, col_hae = st.columns([1.2, 0.7, 0.9, 0.8, 0.6, 0.7, 0.8])
                col_type.markdown(f'<div class="dist">{troop_type}</div>', unsafe_allow_html=True)
                col_tt.markdown(f'<div class="team">{troops}</div>', unsafe_allow_html=True)
                col_hae.markdown(f'<div class="team-zero">{hae if hae else "—"}</div>', unsafe_allow_html=True)
            else:
                col_btn, col_team, col_coord, col_dist, col_tt = st.columns([1.2, 1.1, 0.8, 0.6, 0.9])
                col_tt.markdown(f'<div class="team">{troops}</div>', unsafe_allow_html=True)

            col_coord.markdown(f'<div class="coord">({x}, {y})</div>', unsafe_allow_html=True)
            col_dist.markdown(f'<div class="dist">{dist}</div>', unsafe_allow_html=True)

            if unknown:
                col_team.markdown('<div class="team-unclearable">unknown</div>', unsafe_allow_html=True)
                col_btn.markdown('<div class="btn-disabled">? Out of range</div>', unsafe_allow_html=True)
            elif has_an and n_teams == 0:
                col_team.markdown('<div class="team-unclearable">unclearable</div>', unsafe_allow_html=True)
                col_btn.markdown('<div class="btn-disabled">✖ N/A</div>', unsafe_allow_html=True)
            elif has_an:
                if tribe == "Gaul":
                    team_str = f"{n_teams} TT"
                    url = gaul_build_url(x, y, village_id, n_teams)
                else:
                    nclub = int(row["n_clubs"])
                    ntk   = int(row["n_tk"])
                    team_str = f"{nclub}C + {ntk}TK"
                    url = teuton_build_url(x, y, village_id, nclub, ntk)
                col_team.markdown(f'<div class="team">{team_str}</div>', unsafe_allow_html=True)
                col_btn.markdown('<div class="btn-red">', unsafe_allow_html=True)
                col_btn.link_button("⚔ Attack", url, use_container_width=True)
                col_btn.markdown('</div>', unsafe_allow_html=True)
            else:
                col_team.markdown('<div class="team-zero">no animals</div>', unsafe_allow_html=True)
                col_btn.markdown('<div class="btn-green">', unsafe_allow_html=True)
                col_btn.link_button("🗺 Map", build_map_url(x, y), use_container_width=True)
                col_btn.markdown('</div>', unsafe_allow_html=True)
