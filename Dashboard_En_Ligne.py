"""
Dashboard_En_Ligne.py (modifié pour utiliser kuka_log_parser)

Intégration :
- lorsqu'un .log est uploadé, on parse avec kuka_log_parser.parse_log_text
- les chemins extraits sont stockés dans dcc.Store('parsed-paths')
- un dropdown 'tag-dropdown' est rempli avec les clés trouvées
- un callback trace Time vs valeurs sélectionnées + histogramme
"""
import base64
import re
import json
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
import plotly.graph_objs as go

from kuka_log_parser import parse_log_text, build_dataframe_from_paths, _detect_ipoc_key

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.layout = dbc.Container([
    html.H1("Tableau de bord Robot KUKA"),
    html.Hr(),

    dbc.Row([
        dbc.Col([
            dcc.Upload(
                id="upload-data",
                children=html.Div(["Glissez un fichier ou ", html.A("cliquez pour sélectionner")]),
                style={
                    "width": "100%", "height": "60px", "lineHeight": "60px",
                    "borderWidth": "1px", "borderStyle": "dashed",
                    "borderRadius": "5px", "textAlign": "center",
                },
                multiple=False
            ),
            html.Br(),
            html.Div(id="output-upload"),
            # Stocker les chemins extraits (JSON sérialisable)
            dcc.Store(id="parsed-paths", storage_type="memory"),
            # Dropdown pour sélectionner un tag à tracer
            dcc.Dropdown(id="tag-dropdown", placeholder="Sélectionnez un tag", style={"marginTop": "10px"})
        ], md=3),

        dbc.Col(
            dcc.Loading(
                id="loading-graphs",
                type="circle",
                children=html.Div(id="graph-container")
            ),
            md=9
        )
    ])
], fluid=True)

def parse_uploaded_contents_generic(contents: str, filename: str):
    """
    Prend le contenu base64 d'un upload et tente de parser .json ou .log.
    Retourne (paths_dict_or_None, df_or_None, error_or_None)
    """
    if contents is None:
        return None, None, "No content"

    try:
        content_type, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
    except Exception as e:
        return None, None, f"Erreur de décodage : {e}"

    if filename.endswith(".json"):
        try:
            data = json.loads(decoded.decode("utf-8"))
            return data, None, None
        except Exception as e:
            return None, None, f"Impossible de parser le JSON : {e}"

    if filename.endswith(".log"):
        text = decoded.decode("utf-8", errors="ignore")
        paths = parse_log_text(text)
        if not paths:
            return None, None, "Aucune trame XML valide trouvée dans le .log."
        ipoc = _detect_ipoc_key(paths)
        df = build_dataframe_from_paths(paths, time_key=ipoc)
        # Convertir paths en plain dict pour JSON (listes simples)
        paths_plain = {k: [float(x) for x in v] for k, v in paths.items()}
        return paths_plain, df, None

    return None, None, "Format non supporté (utiliser .json ou .log)."

@app.callback(
    Output("parsed-paths", "data"),
    Output("tag-dropdown", "options"),
    Output("tag-dropdown", "value"),
    Output("output-upload", "children"),
    Input("upload-data", "contents"),
    State("upload-data", "filename")
)
def handle_upload(contents, filename):
    if contents is None:
        return dash.no_update, dash.no_update, dash.no_update, ""
    paths, df, err = parse_uploaded_contents_generic(contents, filename)
    if err:
        return None, [], None, html.Div(err, style={"color": "red"})
    # Préparer options dropdown
    options = [{"label": k, "value": k} for k in sorted(paths.keys())]
    # Par défaut -> sélectionner une clé représentative (p.ex. IPOC si présent ou première clé)
    default_value = None
    # essayer de détecter une clé comportant 'RIst' ou 'J1' etc. sinon laisser None
    for preferred in ["RIst", "AIPos", "J1", "ipoc"]:
        for k in paths.keys():
            if preferred.lower() in k.lower():
                default_value = k
                break
        if default_value:
            break
    if not default_value and options:
        default_value = options[0]["value"]
    # Stocker paths et dataframe (df serializable ? on stocke pas df complet pour éviter pb : juste indicateur)
    store = {"paths": paths}
    return store, options, default_value, html.Div(f"✅ Fichier {filename} chargé avec succès ({len(paths)} tags trouvés)")

@app.callback(
    Output("graph-container", "children"),
    Input("tag-dropdown", "value"),
    State("parsed-paths", "data")
)
def update_graph(selected_tag, store):
    if not store or not selected_tag:
        return html.Div("Aucun tag sélectionné.")
    paths = store.get("paths", {})
    if selected_tag not in paths:
        return html.Div("Tag introuvable dans les données.")

    values = paths[selected_tag]
    if not values:
        return html.Div("Le tag sélectionné ne contient pas de valeurs numériques.")

    # Tenter de récupérer Time si présence d'une clé IPOC
    ipoc_key = None
    for k in paths:
        if "ipoc" in k.lower():
            ipoc_key = k
            break

    if ipoc_key:
        time = paths[ipoc_key][:len(values)]
        # tenter conversion automatique selon ordre de grandeur
        avg = sum(abs(x) for x in time) / max(1, len(time))
        if avg > 1e6:
            time = [x / 1e6 for x in time]
        elif avg > 1e3:
            time = [x / 1e3 for x in time]
    else:
        time = list(range(len(values)))

    # Figure composée : ligne + histogramme
    fig_line = go.Figure()
    fig_line.add_trace(go.Scatter(x=time, y=values, mode="lines+markers", name=selected_tag))
    fig_line.update_layout(title=f"{selected_tag} - Série temporelle", xaxis_title="Time (s)" if ipoc_key else "Index", height=420)

    fig_hist = go.Figure()
    fig_hist.add_trace(go.Histogram(x=values, marker=dict(line=dict(width=1, color="white"), color="#1f77b4")))
    fig_hist.update_layout(title=f"{selected_tag} - Histogramme", height=420, margin=dict(t=40))

    # Retourner deux graphes empilés
    return html.Div([
        dcc.Graph(figure=fig_line),
        dcc.Graph(figure=fig_hist)
    ])

if __name__ == "__main__":
    app.run_server(debug=True)
