import streamlit as st
import folium
from streamlit_folium import st_folium

from dashboard.data.db import get_session, get_engine, init_db
from dashboard.analytics.transport import liste_expeditions
from dashboard.data.routing import geocode_location, get_osrm_route
from dashboard.components.kpi_card import kpi_row

st.set_page_config(page_title="Transport", page_icon="\U0001F6E3\uFE0F", layout="wide")
from dashboard.styles.theme import inject_theme
inject_theme()

st.title("\U0001F6E3\uFE0F Visualisation Transport")

engine = st.session_state.get("engine")
if not engine:
    engine = get_engine()
    init_db(engine)

session = get_session(engine)

# --- Load data ---
df = liste_expeditions(session)

if df.empty:
    st.info("Aucune expedition avec lieux de depart et d'arrivee renseignes.")
    session.close()
    st.stop()

# --- KPIs ---
routes_distinctes = df["route"].nunique()
origines = df["resolved_lieu_depart"].nunique()
destinations = df["resolved_lieu_arrivee"].nunique()

kpi_row([
    {"label": "Expeditions", "value": str(len(df))},
    {"label": "Routes distinctes", "value": str(routes_distinctes)},
    {"label": "Origines", "value": str(origines)},
    {"label": "Destinations", "value": str(destinations)},
])

st.markdown("---")

# --- Route selection ---
col_route, col_expedition = st.columns(2)

with col_route:
    routes = sorted(df["route"].unique())
    selected_route = st.selectbox("Selectionner une route", routes)

df_route = df[df["route"] == selected_route].copy()

with col_expedition:
    # Build expedition labels
    labels = []
    for _, row in df_route.iterrows():
        parts = [f"#{row['id']}"]
        if row.get("type_matiere"):
            parts.append(str(row["type_matiere"]))
        if row.get("date_depart"):
            parts.append(str(row["date_depart"]))
        labels.append(" - ".join(parts))
    df_route["label"] = labels
    selected_label = st.selectbox("Selectionner une expedition", df_route["label"].tolist())

expedition = df_route[df_route["label"] == selected_label].iloc[0]

# --- Metadata panel ---
st.markdown("---")
st.subheader("Details de l'expedition")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"**Matiere :** {expedition.get('type_matiere', '-')}")
    st.markdown(f"**Fournisseur :** {expedition.get('fournisseur', '-') or '-'}")
with col2:
    st.markdown(f"**Depart :** {expedition['resolved_lieu_depart']} ({expedition.get('date_depart', '-')})")
    st.markdown(f"**Arrivee :** {expedition['resolved_lieu_arrivee']} ({expedition.get('date_arrivee', '-') or '-'})")
with col3:
    prix = expedition.get("prix_total")
    st.markdown(f"**Montant :** {f'{prix:.2f} EUR' if prix else '-'}")
    delai = expedition.get("delai_jours")
    st.markdown(f"**Delai :** {f'{int(delai)} jours' if delai is not None else '-'}")

# --- Map ---
st.markdown("---")
st.subheader("Carte du trajet")

origin_name = expedition["resolved_lieu_depart"]
dest_name = expedition["resolved_lieu_arrivee"]

origin_coords = geocode_location(origin_name)
dest_coords = geocode_location(dest_name)

if not origin_coords:
    st.error(f"Impossible de geocoder le lieu de depart : {origin_name}")
    session.close()
    st.stop()

if not dest_coords:
    st.error(f"Impossible de geocoder le lieu d'arrivee : {dest_name}")
    session.close()
    st.stop()

# Center map between origin and destination
center_lat = (origin_coords[0] + dest_coords[0]) / 2
center_lon = (origin_coords[1] + dest_coords[1]) / 2

m = folium.Map(location=[center_lat, center_lon], zoom_start=6)

# Markers
folium.Marker(
    location=origin_coords,
    popup=f"Depart: {origin_name}",
    icon=folium.Icon(color="green", icon="play", prefix="fa"),
).add_to(m)

folium.Marker(
    location=dest_coords,
    popup=f"Arrivee: {dest_name}",
    icon=folium.Icon(color="red", icon="stop", prefix="fa"),
).add_to(m)

# OSRM route
route_data = get_osrm_route(origin_coords, dest_coords)

if route_data:
    folium.PolyLine(
        locations=route_data["geometry"],
        color="blue",
        weight=4,
        opacity=0.8,
    ).add_to(m)

    col_dist, col_dur = st.columns(2)
    with col_dist:
        st.metric("Distance routiere", f"{route_data['distance_km']} km")
    with col_dur:
        heures = int(route_data["duration_min"] // 60)
        minutes = int(route_data["duration_min"] % 60)
        st.metric("Duree estimee", f"{heures}h {minutes:02d}min")
else:
    st.warning("Route OSRM indisponible — affichage du trajet en ligne droite.")
    folium.PolyLine(
        locations=[origin_coords, dest_coords],
        color="gray",
        weight=3,
        dash_array="10",
        opacity=0.6,
    ).add_to(m)

# Fit map bounds
m.fit_bounds([origin_coords, dest_coords], padding=(50, 50))

st_folium(m, use_container_width=True, height=500)

session.close()
