import streamlit as st
import json
import requests
import folium
from streamlit_folium import st_folium
from groq import Groq
from datetime import datetime

# ─────────────────────────────────────────────
# CONFIG — keys loaded from Streamlit Secrets
# Set in: App Settings → Advanced → Secrets
# ─────────────────────────────────────────────
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
AGRO_API_KEY = st.secrets.get("AGRO_API_KEY", "")   # optional
MODEL        = "llama-3.3-70b-versatile"

client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are Agri-Guru, a world-class Agricultural Consultant AI specialising
in biological crop pairing, companion planting, and smart farming systems.
Answer ONLY agriculture-related questions. For anything else, say:
"I'm Agri-Guru — I can only assist with agriculture-related questions. 🌾"
Keep answers practical and concise. Use metric units. Suggest eco-friendly practices.
When weather data is provided in the question, use it to give smarter crop recommendations.
"""

# ── Bio zone definitions ──
BIO_ZONES = [
    {
        "id": "Z1", "name": "Nitrogen Fixer Zone",
        "main_crop": "Groundnut", "companion": "Sorghum",
        "pair_type": "Nitrogen-Fixer + Cereal",
        "reason": "Groundnut fixes atmospheric nitrogen. Sorghum absorbs it as a heavy feeder. Deep + shallow roots avoid competition.",
        "soil": "Red Sandy Loam", "irrigation": "Drip",
        "color": "#4ecb61", "icon": "🌿",
    },
    {
        "id": "Z2", "name": "Three Sisters Zone",
        "main_crop": "Maize + Beans", "companion": "Pumpkin",
        "pair_type": "Three Sisters",
        "reason": "Ancient trio: Maize provides pole for beans. Beans fix nitrogen. Pumpkin shades soil to retain moisture & suppress weeds.",
        "soil": "Alluvial Loam", "irrigation": "Canal Fed",
        "color": "#e0b84a", "icon": "🌽",
    },
    {
        "id": "Z3", "name": "Pest Repellent Border",
        "main_crop": "Tomato + Chilli", "companion": "Marigold (border)",
        "pair_type": "Pest-Repellent + Nightshade",
        "reason": "Marigold border repels nematodes and whiteflies naturally. Chilli acts as secondary pest deterrent for tomato.",
        "soil": "Black Cotton Soil", "irrigation": "Sprinkler",
        "color": "#e07a4a", "icon": "🍅",
    },
    {
        "id": "Z4", "name": "Pollinator Corridor",
        "main_crop": "Sunflower", "companion": "Lavender + Mustard",
        "pair_type": "Pollinator-Attractor",
        "reason": "Sunflower and lavender attract bees. This corridor boosts pollination across the entire farm by ~40%.",
        "soil": "Sandy Loam", "irrigation": "Rainfed",
        "color": "#f0d060", "icon": "🌻",
    },
    {
        "id": "Z5", "name": "Orchard Understory",
        "main_crop": "Mango + Coconut", "companion": "Turmeric + Ginger",
        "pair_type": "Canopy + Shade-Tolerant Understory",
        "reason": "Turmeric & ginger thrive in partial shade under mango/coconut canopy. Their root secretions repel soil pests.",
        "soil": "Laterite", "irrigation": "Sprinkler",
        "color": "#c47fe0", "icon": "🥭",
    },
    {
        "id": "Z6", "name": "Soil Recovery Block",
        "main_crop": "Green Manure (Dhaincha)", "companion": "Sesbania",
        "pair_type": "Soil-Restoration",
        "reason": "Dhaincha fixes 80-100 kg nitrogen/ha. Ploughed before flowering to restore degraded land within one season.",
        "soil": "Degraded Sandy", "irrigation": "Rainfed",
        "color": "#e05a5a", "icon": "🌱",
    },
]

# ─────────────────────────────────────────────
# WEATHER FETCH FUNCTION
# ─────────────────────────────────────────────
def fetch_agro_weather(lat, lon, api_key):
    """
    Fetches current weather + agro data from Agromonitoring API.
    Returns a dict with all weather params or error info.
    """
    try:
        # ── Current weather ──
        weather_url = "http://api.agromonitoring.com/agro/1.0/weather"
        params = {"lat": lat, "lon": lon, "appid": api_key, "units": "metric"}
        r = requests.get(weather_url, params=params, timeout=8)
        r.raise_for_status()
        w = r.json()

        result = {
            "success":      True,
            "temperature":  round(w.get("main", {}).get("temp", 0), 1),
            "feels_like":   round(w.get("main", {}).get("feels_like", 0), 1),
            "temp_min":     round(w.get("main", {}).get("temp_min", 0), 1),
            "temp_max":     round(w.get("main", {}).get("temp_max", 0), 1),
            "humidity":     w.get("main", {}).get("humidity", "N/A"),
            "pressure":     w.get("main", {}).get("pressure", "N/A"),
            "wind_speed":   round(w.get("wind", {}).get("speed", 0), 1),
            "wind_deg":     w.get("wind", {}).get("deg", 0),
            "clouds":       w.get("clouds", {}).get("all", 0),
            "visibility":   w.get("visibility", "N/A"),
            "description":  w.get("weather", [{}])[0].get("description", "N/A").title(),
            "weather_icon": w.get("weather", [{}])[0].get("icon", "01d"),
            "rain_1h":      w.get("rain", {}).get("1h", 0),
            "soil_moisture": w.get("soil_moisture", "N/A"),   # agro-specific
            "soil_temp":     w.get("soil_temp", "N/A"),        # agro-specific
            "location_name": w.get("name", f"{lat:.4f}, {lon:.4f}"),
            "sunrise":      datetime.fromtimestamp(w.get("sys", {}).get("sunrise", 0)).strftime("%H:%M"),
            "sunset":       datetime.fromtimestamp(w.get("sys", {}).get("sunset", 0)).strftime("%H:%M"),
            "timestamp":    datetime.now().strftime("%d %b %Y, %H:%M"),
        }
        return result

    except requests.exceptions.ConnectionError:
        return {"success": False, "error": "Network error. Check your internet connection."}
    except requests.exceptions.Timeout:
        return {"success": False, "error": "Request timed out. Try again."}
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response else "?"
        if code == 401:
            return {"success": False, "error": "Invalid Agromonitoring API key. Get a free key at agromonitoring.com"}
        elif code == 429:
            return {"success": False, "error": "Rate limit hit. Wait a minute and refresh."}
        else:
            return {"success": False, "error": f"API error {code}: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def wind_direction(deg):
    dirs = ["N","NE","E","SE","S","SW","W","NW"]
    return dirs[round(deg / 45) % 8]

def temp_color(temp):
    if temp < 15:   return "#5ab4e0"
    elif temp < 25: return "#4ecb61"
    elif temp < 32: return "#e0b84a"
    else:           return "#e05a5a"

def humidity_color(h):
    if h < 30:   return "#e05a5a"
    elif h < 60: return "#4ecb61"
    else:        return "#5ab4e0"


# ─────────────────────────────────────────────
# POLYGON SPLITTER
# ─────────────────────────────────────────────
def split_polygon_into_zones(coords, n_zones=6):
    lons = [pt[0] for pt in coords]
    lats = [pt[1] for pt in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    cols, rows = 2, 3
    lon_step = (max_lon - min_lon) / cols
    lat_step = (max_lat - min_lat) / rows
    zones, idx = [], 0
    for r in range(rows):
        for c in range(cols):
            if idx >= n_zones: break
            x0 = min_lon + c * lon_step
            x1 = x0 + lon_step
            y1 = max_lat - r * lat_step
            y0 = y1 - lat_step
            zones.append([[x0,y0],[x1,y0],[x1,y1],[x0,y1],[x0,y0]])
            idx += 1
    return zones


# ─────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────
st.set_page_config(page_title="Agri-Guru Pro", page_icon="🌾", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@600;700&family=Inter:wght@300;400;500;600&display=swap');

:root {
    --bg:       #060d07;
    --surface:  #0c1a0e;
    --card:     #111f13;
    --card2:    #162b19;
    --accent:   #3ddc6e;
    --accent2:  #27a84e;
    --glow:     rgba(61,220,110,0.18);
    --gold:     #d4a843;
    --blue:     #4ab8e8;
    --text:     #dff0e2;
    --muted:    #5a8a62;
    --border:   #1e3d22;
    --user-msg: #0e2712;
    --bot-msg:  #0a150c;
}

/* ── Global ── */
.stApp, [data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    font-family: 'Inter', sans-serif;
    color: var(--text);
}
.block-container { padding-top: 1rem !important; max-width: 1560px; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(160deg, #060e07 0%, #091410 100%) !important;
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] * { color: var(--text) !important; }

/* ── Typography ── */
h1, h2, h3 { font-family: 'Cormorant Garamond', serif !important; letter-spacing: 0.3px; }
h1 { color: var(--accent) !important; }
h2, h3 { color: #7dd99a !important; }

/* ══════════════════════════════════
   CHAT UI — Complete Redesign
══════════════════════════════════ */

/* Chat container scrollbox */
[data-testid="stVerticalBlockBorderWrapper"] {
    border: none !important;
    background: transparent !important;
}

/* Every chat message bubble */
[data-testid="stChatMessage"] {
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    margin-bottom: 2px !important;
    padding: 4px 0 !important;
    box-shadow: none !important;
}

/* Avatar icons */
[data-testid="stChatMessageAvatarUser"],
[data-testid="stChatMessageAvatarAssistant"] {
    border-radius: 50% !important;
    border: 2px solid var(--border) !important;
    background: var(--card2) !important;
    box-shadow: 0 0 12px var(--glow) !important;
}

/* Message content wrapper — custom bubble look */
[data-testid="stChatMessageContent"] {
    background: var(--bot-msg) !important;
    border: 1px solid var(--border) !important;
    border-radius: 0 16px 16px 16px !important;
    padding: 12px 16px !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(61,220,110,0.05) !important;
    position: relative !important;
}

/* User message bubble — right-rounded */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {
    background: linear-gradient(135deg, #0e2712 0%, #122916 100%) !important;
    border-color: #2a5c30 !important;
    border-radius: 16px 0 16px 16px !important;
    box-shadow: 0 2px 16px rgba(0,0,0,0.4), inset 0 1px 0 rgba(61,220,110,0.1) !important;
}

/* Message text */
[data-testid="stChatMessageContent"] p,
[data-testid="stChatMessageContent"] li,
[data-testid="stChatMessageContent"] span,
[data-testid="stChatMessageContent"] {
    color: var(--text) !important;
    font-size: 0.94rem !important;
    line-height: 1.75 !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="stChatMessageContent"] strong { color: var(--accent) !important; }
[data-testid="stChatMessageContent"] code {
    background: #0d200f !important;
    color: #7dd99a !important;
    border-radius: 4px !important;
    padding: 1px 6px !important;
    font-size: 0.85rem !important;
}

/* ── Chat input box ── */
[data-testid="stChatInput"] {
    background: var(--card2) !important;
    border: 1.5px solid var(--border) !important;
    border-radius: 20px !important;
    box-shadow: 0 0 0 0 var(--glow) !important;
    transition: box-shadow 0.3s, border-color 0.3s !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--accent) !important;
    box-shadow: 0 0 24px var(--glow) !important;
}
[data-testid="stChatInput"] textarea {
    color: var(--text) !important;
    background: transparent !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 0.93rem !important;
    caret-color: var(--accent) !important;
}
[data-testid="stChatInput"] textarea::placeholder { color: var(--muted) !important; }

/* Send button glow */
[data-testid="stChatInput"] button {
    background: var(--accent) !important;
    border-radius: 50% !important;
    color: #060d07 !important;
    box-shadow: 0 0 12px var(--glow) !important;
}

/* ── Buttons ── */
.stButton > button {
    background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%) !important;
    color: #060d07 !important;
    font-weight: 600 !important;
    font-family: 'Inter', sans-serif !important;
    border: none !important;
    border-radius: 12px !important;
    padding: 0.5rem 1.4rem !important;
    letter-spacing: 0.3px !important;
    transition: all 0.2s !important;
    box-shadow: 0 4px 16px rgba(61,220,110,0.2) !important;
}
.stButton > button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 8px 28px rgba(61,220,110,0.45) !important;
}

/* ── File uploader ── */
[data-testid="stFileUploader"] {
    background: var(--card) !important;
    border: 2px dashed #2a5c30 !important;
    border-radius: 14px !important;
    padding: 1rem !important;
    transition: border-color 0.2s !important;
}
[data-testid="stFileUploader"]:hover { border-color: var(--accent) !important; }
[data-testid="stFileUploader"] * { color: var(--text) !important; }

/* ── Metrics ── */
[data-testid="stMetricValue"] { color: var(--accent) !important; font-size: 1.4rem !important; font-weight: 600 !important; }
[data-testid="stMetricLabel"] { color: var(--muted) !important; font-size: 0.74rem !important; text-transform: uppercase; letter-spacing: 0.5px; }
[data-testid="metric-container"] {
    background: var(--card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 12px !important;
    padding: 0.7rem 1rem !important;
    box-shadow: inset 0 1px 0 rgba(61,220,110,0.06) !important;
}

/* ── Alerts ── */
.stAlert {
    background: var(--card) !important;
    border-left: 3px solid var(--gold) !important;
    border-radius: 10px !important;
    color: var(--text) !important;
}

/* ── Select / Dropdown ── */
[data-baseweb="select"] { background: var(--card) !important; border-color: var(--border) !important; border-radius: 10px !important; }
[data-baseweb="select"] * { color: var(--text) !important; background: var(--card) !important; }

/* ── Divider ── */
hr { border-color: var(--border) !important; margin: 0.7rem 0 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }

/* ── Caption ── */
.stCaption, small { color: var(--muted) !important; font-size: 0.78rem !important; }

/* ── Zone & Weather cards ── */
.zone-card {
    background: var(--card);
    border-radius: 12px;
    padding: 0.75rem 1rem;
    margin-bottom: 0.5rem;
    border-left: 3px solid var(--accent);
    transition: transform 0.15s;
}
.zone-card:hover { transform: translateX(3px); }
.weather-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 1rem 1.2rem;
    margin-bottom: 0.6rem;
}
.weather-tile {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 0.6rem 0.8rem;
    text-align: center;
}
.weather-tile .val { font-size: 1.2rem; font-weight: 600; }
.weather-tile .lbl { font-size: 0.68rem; color: var(--muted); margin-top: 2px; text-transform: uppercase; letter-spacing: 0.4px; }

/* ── Glowing section headers ── */
.chat-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    background: linear-gradient(90deg, rgba(61,220,110,0.08) 0%, transparent 100%);
    border-left: 3px solid var(--accent);
    border-radius: 0 10px 10px 0;
    margin-bottom: 10px;
}
.chat-header .title {
    font-family: 'Cormorant Garamond', serif;
    font-size: 1.15rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.3px;
}
.chat-header .subtitle {
    font-size: 0.72rem;
    color: var(--muted);
    margin-top: 1px;
}

/* ── Typing dots animation ── */
@keyframes blink { 0%,80%,100%{opacity:0.2} 40%{opacity:1} }
.typing-dot { display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--accent); animation:blink 1.4s infinite; margin:0 2px; }
.typing-dot:nth-child(2){animation-delay:0.2s}
.typing-dot:nth-child(3){animation-delay:0.4s}

/* ── Glow pulse on new message ── */
@keyframes msgIn { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }
[data-testid="stChatMessage"] { animation: msgIn 0.25s ease-out; }

/* ── Input area shimmer border ── */
@keyframes shimmer {
    0%   { border-color: var(--border); }
    50%  { border-color: var(--accent); box-shadow: 0 0 20px var(--glow); }
    100% { border-color: var(--border); }
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:0.8rem 0 0.4rem 0'>
      <div style='font-size:2rem;filter:drop-shadow(0 0 10px rgba(61,220,110,0.5))'>🌾</div>
      <div style='font-family:Cormorant Garamond,serif;font-size:1.25rem;font-weight:700;color:#3ddc6e'>
        Agri-Guru Pro
      </div>
      <div style='font-size:0.7rem;color:#5a8a62;margin-top:2px'>AI Smart Agriculture System</div>
    </div>
    <div style='height:1px;background:linear-gradient(90deg,transparent,#2a5c30,transparent);margin:0.5rem 0 0.8rem 0'></div>
    """, unsafe_allow_html=True)

    st.markdown("### 📂 Land Data")
    uploaded_file = st.file_uploader("Upload GeoJSON Plot File", type=["geojson"])

    st.markdown("---")
    st.markdown("### 🌦️ Weather API")
    agro_key_input = st.text_input(
        "Agromonitoring API Key (optional override)",
        value="",
        type="password",
        help="Leave blank to use key from Streamlit Secrets. Or paste a different key here.",
        placeholder="Uses secret by default — paste to override"
    )
    manual_lat = st.number_input("Override Latitude",  value=0.0, format="%.4f", help="Leave 0 to auto-detect from GeoJSON")
    manual_lon = st.number_input("Override Longitude", value=0.0, format="%.4f", help="Leave 0 to auto-detect from GeoJSON")

    st.markdown("---")
    st.markdown("### ⚙️ Map Settings")
    zoom_level  = st.slider("Zoom Level", 10, 20, 17)
    map_tile    = st.selectbox("Map Style", ["OpenStreetMap", "CartoDB positron", "CartoDB dark_matter"], index=0)
    n_zones     = st.slider("Number of Zones", 2, 6, 6)
    show_labels = st.toggle("Show Crop Labels on Map", value=True)

    st.markdown("---")
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

    st.markdown("---")
    st.markdown("""
    <div style='font-size:0.78rem;color:#4ecb61;line-height:1.9'>
      🔒 Role-Locked: Agriculture only<br>
      ⚡ Groq + LLaMA 3.3 70B — Free<br>
      🌦️ Agro-Weather API integrated<br>
      🌿 Auto Land Splitting + Bio Zones<br>
      🗺️ Crop Suggestions on Live Map
    </div>""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "messages"     not in st.session_state: st.session_state.messages     = []
if "weather_data" not in st.session_state: st.session_state.weather_data = None
if "last_coords"  not in st.session_state: st.session_state.last_coords  = (None, None)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown("""
<div style='padding:0.6rem 0 1rem 0;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:1rem'>
  <div>
    <div style='display:flex;align-items:center;gap:12px'>
      <div style='font-size:2.4rem;filter:drop-shadow(0 0 12px rgba(61,220,110,0.5))'>🌾</div>
      <div>
        <h1 style='margin:0;font-size:2rem;font-family:Cormorant Garamond,serif;
                   background:linear-gradient(135deg,#3ddc6e,#27a84e);
                   -webkit-background-clip:text;-webkit-text-fill-color:transparent'>
          Agri-Guru Pro
        </h1>
        <div style='font-size:0.82rem;color:#5a8a62;margin-top:1px;letter-spacing:0.3px'>
          AI-Driven Smart Agriculture &nbsp;·&nbsp; Agro-Weather &nbsp;·&nbsp; Biological Crop Pairing &nbsp;·&nbsp; Smart Plot Analysis
        </div>
      </div>
    </div>
  </div>
  <div style='display:flex;gap:10px;flex-wrap:wrap'>
    <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:20px;
                padding:5px 14px;font-size:0.74rem;color:#3ddc6e'>
      🔒 Role-Locked AI
    </div>
    <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:20px;
                padding:5px 14px;font-size:0.74rem;color:#4ab8e8'>
      ⚡ Groq LLaMA 3.3
    </div>
    <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:20px;
                padding:5px 14px;font-size:0.74rem;color:#d4a843'>
      🌦️ Live Agro-Weather
    </div>
  </div>
</div>
<div style='height:1px;background:linear-gradient(90deg,#3ddc6e33,#3ddc6e88,#3ddc6e33);margin-bottom:1rem'></div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# THREE COLUMNS: Chat | Map | Weather
# ─────────────────────────────────────────────
col1, col2, col3 = st.columns([1, 1.2, 0.85], gap="medium")

# ══════════════════════════════════════════════
# COL 1 — AI CHAT
# ══════════════════════════════════════════════
with col1:
    # ── Glowing chat header ──
    st.markdown("""
    <div class='chat-header'>
      <div style='font-size:1.4rem;filter:drop-shadow(0 0 8px rgba(61,220,110,0.6))'>🤖</div>
      <div>
        <div class='title'>AI Agri-Consultant</div>
        <div class='subtitle'>Groq · LLaMA 3.3 70B · Role-locked to Agriculture</div>
      </div>
      <div style='margin-left:auto;display:flex;align-items:center;gap:6px'>
        <div style='width:7px;height:7px;border-radius:50%;background:#3ddc6e;
                    box-shadow:0 0 8px #3ddc6e;animation:blink 2s infinite'></div>
        <span style='font-size:0.7rem;color:#3ddc6e'>ONLINE</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    chat_box = st.container(height=420)
    with chat_box:
        if not st.session_state.messages:
            st.markdown("""
            <div style='text-align:center;padding:2.5rem 1rem;'>
              <div style='font-size:3.5rem;filter:drop-shadow(0 0 20px rgba(61,220,110,0.4));
                          animation:blink 3s infinite'>🌾</div>
              <div style='font-family:Cormorant Garamond,serif;font-size:1.3rem;
                          font-weight:700;color:#3ddc6e;margin-top:0.8rem;letter-spacing:0.3px'>
                Agri-Guru is ready
              </div>
              <div style='font-size:0.85rem;margin-top:0.4rem;color:#7dd99a;line-height:1.6'>
                Ask about crop pairing, soil health,<br>irrigation, pest control & more
              </div>
              <div style='margin-top:1.2rem;display:flex;flex-wrap:wrap;gap:6px;justify-content:center'>
                <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:16px;
                            padding:4px 12px;font-size:0.72rem;color:#5a8a62'>
                  🌱 Crop suggestions
                </div>
                <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:16px;
                            padding:4px 12px;font-size:0.72rem;color:#5a8a62'>
                  🪸 Soil advice
                </div>
                <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:16px;
                            padding:4px 12px;font-size:0.72rem;color:#5a8a62'>
                  💧 Irrigation tips
                </div>
                <div style='background:#0c1a0e;border:1px solid #1e3d22;border-radius:16px;
                            padding:4px 12px;font-size:0.72rem;color:#5a8a62'>
                  🌿 Bio pairing
                </div>
              </div>
              <div style='margin-top:1rem;font-size:0.7rem;color:#3a5a3d;font-style:italic'>
                ⚡ Live weather context auto-included in every response
              </div>
            </div>""", unsafe_allow_html=True)
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

    if prompt := st.chat_input("💬  Ask Agri-Guru anything about farming…"):
        # Auto-append live weather context to prompt
        weather_context = ""
        if st.session_state.weather_data and st.session_state.weather_data.get("success"):
            wd = st.session_state.weather_data
            weather_context = (
                f"\n\n[LIVE FARM WEATHER DATA: Temp={wd['temperature']}°C, "
                f"Humidity={wd['humidity']}%, Wind={wd['wind_speed']}m/s {wind_direction(wd['wind_deg'])}, "
                f"Conditions={wd['description']}, Rain(1h)={wd['rain_1h']}mm, "
                f"Clouds={wd['clouds']}%, Pressure={wd['pressure']}hPa. "
                f"Use this data to give smarter, location-specific advice.]"
            )
        enriched_prompt = prompt + weather_context

        st.session_state.messages.append({"role": "user", "content": prompt})  # show clean version
        history = [{"role": "system", "content": SYSTEM_PROMPT}]
        for m in st.session_state.messages[-10:]:
            role    = m["role"]
            content = enriched_prompt if (role == "user" and m == st.session_state.messages[-1]) else m["content"]
            history.append({"role": role, "content": content})

        try:
            response = client.chat.completions.create(model=MODEL, messages=history, max_tokens=1024, temperature=0.65)
            reply    = response.choices[0].message.content
        except Exception as e:
            err   = str(e)
            reply = (
                "⚠️ **Invalid Groq Key** — get one free at [console.groq.com](https://console.groq.com)" if "401" in err
                else "⚠️ **Rate limit** — wait a few seconds and retry." if "429" in err
                else f"⚠️ **Error:** {err}"
            )

        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

# ══════════════════════════════════════════════
# COL 2 — MAP
# ══════════════════════════════════════════════
with col2:
    st.markdown("""
    <div class='chat-header' style='border-left-color:#4ab8e8;background:linear-gradient(90deg,rgba(74,184,232,0.07),transparent)'>
      <div style='font-size:1.4rem'>🗺️</div>
      <div>
        <div class='title' style='color:#4ab8e8'>Smart Bio-Zone Map</div>
        <div class='subtitle'>Land auto-split into biological crop pairing zones</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if uploaded_file:
        try:
            data       = json.load(uploaded_file)
            features   = data.get("features", [])
            if not features:
                st.error("No features found in GeoJSON.")
            else:
                first_geom = features[0]["geometry"]
                geom_type  = first_geom["type"]
                raw_coords = first_geom["coordinates"]

                if geom_type == "Polygon":
                    ring = raw_coords[0]
                elif geom_type == "MultiPolygon":
                    ring = raw_coords[0][0]
                elif geom_type == "Point":
                    lon, lat = raw_coords[0], raw_coords[1]; d = 0.001
                    ring = [[lon-d,lat-d],[lon+d,lat-d],[lon+d,lat+d],[lon-d,lat+d],[lon-d,lat-d]]
                elif geom_type == "LineString":
                    # flat list of [lon,lat] pairs — use directly as ring
                    ring = raw_coords
                elif geom_type == "MultiLineString":
                    ring = raw_coords[0]
                else:
                    # fallback: detect nesting level
                    if raw_coords and isinstance(raw_coords[0], (int, float)):
                        lon, lat = raw_coords[0], raw_coords[1]; d = 0.001
                        ring = [[lon-d,lat-d],[lon+d,lat-d],[lon+d,lat+d],[lon-d,lat+d],[lon-d,lat-d]]
                    elif raw_coords and isinstance(raw_coords[0][0], (int, float)):
                        ring = raw_coords
                    else:
                        ring = raw_coords[0]

                lons       = [pt[0] for pt in ring]
                lats_list  = [pt[1] for pt in ring]
                center_lat = (min(lats_list) + max(lats_list)) / 2
                center_lon = (min(lons) + max(lons)) / 2

                # ── Auto-fetch weather when coords change ──
                fetch_lat = manual_lat if manual_lat != 0.0 else center_lat
                fetch_lon = manual_lon if manual_lon != 0.0 else center_lon

                if (fetch_lat, fetch_lon) != st.session_state.last_coords:
                    st.session_state.last_coords  = (fetch_lat, fetch_lon)
                    # Use sidebar input first, fall back to secret
                    _sidebar_key = agro_key_input.strip() if agro_key_input.strip() not in ["", "YOUR_AGROMONITORING_API_KEY_HERE"] else ""
                    active_key   = _sidebar_key if _sidebar_key else (AGRO_API_KEY.strip() if AGRO_API_KEY.strip() else None)
                    if active_key:
                        with st.spinner("🌦️ Fetching live agro-weather..."):
                            st.session_state.weather_data = fetch_agro_weather(fetch_lat, fetch_lon, active_key)
                    else:
                        st.session_state.weather_data = None

                # ── Build map ──
                m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_level, tiles=map_tile)

                # Draw original boundary — works for Polygon, LineString, etc.
                if geom_type in ("Polygon", "MultiPolygon"):
                    folium.GeoJson(
                        {"type": "Feature", "geometry": first_geom},
                        style_function=lambda x: {"fillColor": "transparent", "color": "#ffffff", "weight": 3, "dashArray": "8 4", "fillOpacity": 0},
                        tooltip=folium.Tooltip("📍 Original Land Boundary"),
                    ).add_to(m)
                else:
                    # LineString / MultiLineString — draw as polyline
                    folium.PolyLine(
                        locations=[[pt[1], pt[0]] for pt in ring],
                        color="#ffffff", weight=3, dash_array="8 4",
                        tooltip="📍 Original Land Boundary (LineString)"
                    ).add_to(m)
                    # Also draw closing line to complete the shape visually
                    if ring[0] != ring[-1]:
                        folium.PolyLine(
                            locations=[[ring[-1][1], ring[-1][0]], [ring[0][1], ring[0][0]]],
                            color="#ffffff", weight=2, dash_array="4 4", opacity=0.5
                        ).add_to(m)

                zone_coords_list = split_polygon_into_zones(ring, n_zones=n_zones)
                zones_to_draw    = BIO_ZONES[:n_zones]

                for zone, zcoords in zip(zones_to_draw, zone_coords_list):
                    z_lats = [pt[1] for pt in zcoords]
                    z_lons = [pt[0] for pt in zcoords]
                    z_clat = (min(z_lats) + max(z_lats)) / 2
                    z_clon = (min(z_lons) + max(z_lons)) / 2

                    # Weather hint for tooltip
                    wd = st.session_state.weather_data
                    weather_hint = ""
                    if wd and wd.get("success"):
                        weather_hint = f"""
                        <div style="margin-top:6px;padding:5px 7px;background:#0a1c0c;
                                    border-radius:6px;font-size:0.74rem;color:#96dba0">
                          🌡️ {wd['temperature']}°C &nbsp; 💧 {wd['humidity']}% humidity
                          &nbsp; 🌬️ {wd['wind_speed']}m/s &nbsp; ☁️ {wd['description']}
                        </div>"""

                    tooltip_html = f"""
                    <div style="font-family:'DM Sans',sans-serif;min-width:240px;max-width:300px;
                                background:#172d1b;border:1px solid {zone['color']};
                                border-radius:10px;padding:10px 13px;color:#e2f5e5">
                      <div style="font-size:1.3rem;text-align:center">{zone['icon']}</div>
                      <b style="color:{zone['color']};font-size:0.95rem">{zone['name']}</b>
                      <div style="font-size:0.72rem;color:#6a9e72;margin-bottom:5px">{zone['id']} · {zone['pair_type']}</div>
                      <div style="margin:3px 0">🌱 <b>Main:</b> {zone['main_crop']}</div>
                      <div style="margin:3px 0">🤝 <b>Companion:</b> {zone['companion']}</div>
                      <div style="margin:3px 0">🪸 <b>Soil:</b> {zone['soil']}</div>
                      <div style="margin:3px 0">💧 <b>Irrigation:</b> {zone['irrigation']}</div>
                      {weather_hint}
                      <div style="margin-top:6px;padding:6px;background:#0f1f11;
                                  border-radius:6px;font-size:0.76rem;color:#c8e8cc;line-height:1.5">
                        💡 {zone['reason']}
                      </div>
                    </div>"""

                    folium.Polygon(
                        locations=[[pt[1], pt[0]] for pt in zcoords],
                        color="#071408", weight=2, fill=True,
                        fill_color=zone["color"], fill_opacity=0.55,
                        tooltip=folium.Tooltip(tooltip_html, sticky=True),
                    ).add_to(m)

                    if show_labels:
                        folium.Marker(
                            [z_clat, z_clon],
                            icon=folium.DivIcon(html=f"""
                            <div style="font-family:'DM Sans',sans-serif;text-align:center;pointer-events:none;white-space:nowrap;">
                              <div style="font-size:15px">{zone['icon']}</div>
                              <div style="font-size:9px;font-weight:700;color:#fff;text-shadow:0 1px 4px #000;
                                          background:rgba(0,0,0,0.5);border-radius:4px;padding:1px 5px;">
                                {zone['main_crop'][:15]}</div>
                              <div style="font-size:8px;color:#c8e8cc;text-shadow:0 1px 3px #000;
                                          background:rgba(0,0,0,0.35);border-radius:3px;padding:0 4px;">
                                +{zone['companion'][:13]}</div>
                            </div>""", icon_size=(130, 48), icon_anchor=(65, 24))
                        ).add_to(m)

                folium.FitBounds([[min(lats_list), min(lons)], [max(lats_list), max(lons)]]).add_to(m)
                st_folium(m, width="100%", height=430, returned_objects=[], use_container_width=True)

                # Stats
                st.markdown("---")
                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("📍 Zones", n_zones)
                mc2.metric("🌐 Lat",   f"{center_lat:.4f}°")
                mc3.metric("🌐 Lon",   f"{center_lon:.4f}°")
                mc4.metric("🌿 Pairs", n_zones)

                # Zone cards
                st.markdown("---")
                st.markdown("**🌿 Biological Zone Breakdown**")
                card_cols = st.columns(2)
                for i, zone in enumerate(zones_to_draw):
                    with card_cols[i % 2]:
                        st.markdown(f"""
                        <div class='zone-card' style='border-left-color:{zone["color"]}'>
                          <div style='display:flex;align-items:center;gap:7px;margin-bottom:3px'>
                            <span style='font-size:1.1rem'>{zone['icon']}</span>
                            <b style='color:{zone["color"]};font-size:0.85rem'>{zone['name']}</b>
                          </div>
                          <div style='font-size:0.8rem'>🌱 <b>{zone['main_crop']}</b> + {zone['companion']}</div>
                          <div style='font-size:0.74rem;color:#96dba0'>⚗️ {zone['pair_type']}</div>
                          <div style='font-size:0.72rem;color:#7aab80;font-style:italic;margin-top:3px'>
                            💡 {zone['reason'][:90]}…</div>
                        </div>""", unsafe_allow_html=True)

        except json.JSONDecodeError:
            st.error("❌ Invalid GeoJSON file. Please upload a valid .geojson file.")
        except (KeyError, IndexError, TypeError) as e:
            st.error(f"❌ Geometry error: {e}")
            st.info("💡 Try uploading the sample GeoJSON file provided, or check your file has valid coordinates.")
        except Exception as e:
            st.error(f"❌ Unexpected error: {e}")
            import traceback
            st.code(traceback.format_exc(), language="python")
    else:
        st.markdown("""
        <div style='background:#112214;border:2px dashed #234a28;border-radius:18px;
                    padding:3rem 2rem;text-align:center;'>
          <div style='font-size:3rem'>🗺️</div>
          <div style='font-size:1rem;margin-top:0.8rem;color:#96dba0;font-weight:500'>No Land Data Loaded</div>
          <div style='font-size:0.82rem;color:#6a9e72;margin-top:0.5rem;line-height:1.7'>
            Upload a <code style="background:#172d1b;padding:1px 5px;border-radius:4px;color:#4ecb61">.geojson</code>
            file to auto-split land into bio zones
          </div>
        </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════
# COL 3 — WEATHER DASHBOARD
# ══════════════════════════════════════════════
with col3:
    st.markdown("""
    <div class='chat-header' style='border-left-color:#d4a843;background:linear-gradient(90deg,rgba(212,168,67,0.07),transparent)'>
      <div style='font-size:1.4rem'>🌦️</div>
      <div>
        <div class='title' style='color:#d4a843'>Agro-Weather</div>
        <div class='subtitle'>Live data · Agromonitoring API</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    wd = st.session_state.weather_data

    if wd is None:
        st.markdown("""
        <div style='background:#112214;border:2px dashed #234a28;border-radius:14px;
                    padding:2rem 1rem;text-align:center;'>
          <div style='font-size:2.5rem'>🌦️</div>
          <div style='font-size:0.95rem;color:#96dba0;margin-top:0.7rem;font-weight:500'>
            No Weather Data
          </div>
          <div style='font-size:0.78rem;color:#6a9e72;margin-top:0.4rem;line-height:1.6'>
            1. Upload your GeoJSON<br>
            2. Paste Agromonitoring API key in sidebar<br>
            3. Weather auto-loads from land coordinates<br><br>
            <b style='color:#4ecb61'>Free key:</b> agromonitoring.com
          </div>
        </div>""", unsafe_allow_html=True)

    elif not wd.get("success"):
        st.error(f"⚠️ Weather fetch failed:\n{wd.get('error','Unknown error')}")
        st.markdown("""
        <div style='font-size:0.8rem;color:#6a9e72;padding:0.5rem;'>
          Get a free key at <a href='https://agromonitoring.com' style='color:#4ecb61'>agromonitoring.com</a><br>
          → Sign up → Dashboard → API Keys
        </div>""", unsafe_allow_html=True)

    else:
        tc = temp_color(wd["temperature"])
        hc = humidity_color(wd["humidity"])

        # Location header
        st.markdown(f"""
        <div class='weather-card' style='text-align:center;border-color:#4ecb61'>
          <div style='font-size:0.75rem;color:#6a9e72'>{wd['timestamp']}</div>
          <div style='font-size:1.1rem;font-weight:700;color:#4ecb61;margin:3px 0'>
            📍 {wd['location_name']}
          </div>
          <div style='font-size:1.8rem;margin:4px 0'>{wd['description']}</div>
        </div>""", unsafe_allow_html=True)

        # Main temp + humidity
        st.markdown(f"""
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:0.6rem;margin-bottom:0.6rem'>
          <div class='weather-tile'>
            <div class='val' style='color:{tc}'>{wd['temperature']}°C</div>
            <div class='lbl'>🌡️ Temperature</div>
            <div style='font-size:0.68rem;color:#4a6a50'>Feels {wd['feels_like']}°C</div>
          </div>
          <div class='weather-tile'>
            <div class='val' style='color:{hc}'>{wd['humidity']}%</div>
            <div class='lbl'>💧 Humidity</div>
            <div style='font-size:0.68rem;color:#4a6a50'>{
              'Dry — irrigate' if wd['humidity'] < 35
              else 'Optimal' if wd['humidity'] < 65
              else 'High — watch fungal'
            }</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # Grid of agro params
        st.markdown(f"""
        <div style='display:grid;grid-template-columns:1fr 1fr;gap:0.5rem;margin-bottom:0.6rem'>
          <div class='weather-tile'>
            <div class='val' style='color:#5ab4e0'>{wd['wind_speed']} m/s</div>
            <div class='lbl'>🌬️ Wind · {wind_direction(wd['wind_deg'])}</div>
          </div>
          <div class='weather-tile'>
            <div class='val' style='color:#e0b84a'>{wd['clouds']}%</div>
            <div class='lbl'>☁️ Cloud Cover</div>
          </div>
          <div class='weather-tile'>
            <div class='val' style='color:#5ab4e0'>{wd['rain_1h']} mm</div>
            <div class='lbl'>🌧️ Rain (1h)</div>
          </div>
          <div class='weather-tile'>
            <div class='val' style='color:#96dba0'>{wd['pressure']}</div>
            <div class='lbl'>📊 Pressure hPa</div>
          </div>
          <div class='weather-tile'>
            <div class='val' style='color:#f0d060'>{wd['sunrise']}</div>
            <div class='lbl'>🌅 Sunrise</div>
          </div>
          <div class='weather-tile'>
            <div class='val' style='color:#e07a4a'>{wd['sunset']}</div>
            <div class='lbl'>🌇 Sunset</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # Agro-specific params
        st.markdown(f"""
        <div class='weather-card' style='margin-bottom:0.6rem'>
          <div style='font-size:0.8rem;font-weight:700;color:#4ecb61;margin-bottom:6px'>
            🌾 Agro-Specific Parameters
          </div>
          <div style='display:grid;grid-template-columns:1fr 1fr;gap:0.5rem'>
            <div class='weather-tile'>
              <div class='val' style='color:#c47fe0'>{wd['soil_moisture']}</div>
              <div class='lbl'>💧 Soil Moisture</div>
            </div>
            <div class='weather-tile'>
              <div class='val' style='color:#e07a4a'>{wd['soil_temp']}</div>
              <div class='lbl'>🌡️ Soil Temp</div>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)

        # Temp range bar
        t_min, t_max = wd['temp_min'], wd['temp_max']
        t_range = max(t_max - t_min, 0.1)
        t_pos   = ((wd['temperature'] - t_min) / t_range) * 100
        st.markdown(f"""
        <div class='weather-card'>
          <div style='font-size:0.78rem;color:#6a9e72;margin-bottom:5px'>
            🌡️ Today's Range: {t_min}°C — {t_max}°C
          </div>
          <div style='background:#0f1f11;border-radius:6px;height:8px;position:relative;overflow:hidden'>
            <div style='position:absolute;left:0;top:0;height:100%;
                        background:linear-gradient(90deg,#5ab4e0,#4ecb61,#e0b84a,#e05a5a);
                        width:100%;border-radius:6px'></div>
            <div style='position:absolute;top:-3px;left:{t_pos:.0f}%;
                        transform:translateX(-50%);width:14px;height:14px;
                        background:#fff;border-radius:50%;border:2px solid #0a1c0c;'></div>
          </div>
          <div style='display:flex;justify-content:space-between;font-size:0.7rem;color:#6a9e72;margin-top:3px'>
            <span>{t_min}°C</span><span style='color:{tc};font-weight:700'>{wd['temperature']}°C</span><span>{t_max}°C</span>
          </div>
        </div>""", unsafe_allow_html=True)

        # AI agro advice chip
        st.markdown(f"""
        <div style='background:#0f1f11;border:1px solid #4ecb61;border-radius:10px;
                    padding:0.7rem 0.9rem;font-size:0.78rem;color:#c8e8cc;line-height:1.6'>
          <b style='color:#4ecb61'>🤖 AI Agro Tip:</b><br>
          {
            f"Temp {wd['temperature']}°C is ideal for tropical crops like rice, maize & sugarcane." if 25 <= wd['temperature'] <= 35
            else f"Cool temp ({wd['temperature']}°C) — good for wheat, mustard & leafy vegetables." if wd['temperature'] < 25
            else f"High temp ({wd['temperature']}°C) — ensure extra irrigation and mulching."
          }
          {' High humidity — watch for fungal diseases.' if wd['humidity'] > 70 else ''}
          {' Dry conditions — activate drip irrigation.' if wd['humidity'] < 35 else ''}
          <br><span style='color:#6a9e72;font-size:0.7rem'>Ask the AI chat for detailed advice →</span>
        </div>""", unsafe_allow_html=True)