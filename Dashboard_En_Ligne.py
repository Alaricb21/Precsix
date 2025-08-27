"""
Dashboard_En_Ligne.py

Dashboard Dash qui propose :
- upload de fichiers .log (analyse via kuka_log_parser)
- sélection de fichiers de simulation .json directement depuis le repo GitHub
  (tracé 3D, vitesses, déplacement angulaire total)

Remplacez ce fichier dans votre repo pour avoir l'intégration.
"""
import base64
import json
import re
import requests
from collections import defaultdict

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc

import pandas as pd
import numpy as np
import plotly.graph_objs as go
from plotly.subplots import make_subplots

# Importer le parseur de logs que nous avons précédemment ajouté
from kuka_log_parser import parse_log_text, build_dataframe_from_paths, _detect_ipoc_key

# --- Configuration GitHub pour les simulations ---
GITHUB_USER = "Alaricb21"
GITHUB_REPO = "Precsix"
GITHUB_BRANCH = "main"

def get_simulation_list():
    """Récupère la liste des fichiers .json à la racine du repo via l'API GitHub."""
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/"
        response = requests.get(api_url, timeout=10)
        response.raise_for_status()
        files = [
            {'label': item['name'], 'value': item['path']}
            for item in response.json()
            if item['name'].endswith('.json') and item['type'] == 'file'
        ]
        return files
    except Exception as e:
        print(f"Erreur en récupérant la liste des fichiers depuis GitHub: {e}")
        return []

def load_simulation_data_from_github(filename):
    """Charge le JSON brut depuis raw.githubusercontent.com."""
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
        response = requests.get(raw_url, timeout=10)
        response.raise_for_status()
        json_data = json.loads(response.text)
        json_data['filename'] = filename
        return json_data
    except Exception as e:
        print(f"Erreur en téléchargeant {filename} depuis GitHub: {e}")
        return None

# --- Parsing des uploads (comme précédemment) ---
def parse_uploaded_contents(contents, filename):
    """
    Gère .json et .log envoyés via Upload.
    Retourne (paths_dict_or_None, df_or_none, error_or_None)
    """
    if contents is None:
        return None, None, "No content"

    try:
        content_type, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
    except Exception as e:
        return None, None, f"Erreur de décodage : {e}"

    # JSON : renvoyer le JSON décodé sous forme de dict (compatibilité)
    if filename.endswith(".json"):
        try:
            data = json.loads(decoded.decode("utf-8"))
            return data, None, None
        except Exception as e:
            return None, None, f"Impossible de parser le JSON : {e}"

    # LOG : utiliser le parseur XML que nous avons fourni
    if filename.endswith(".log"):
        text = decoded.decode("utf-8", errors="ignore")
        paths = parse_log_text(text)
        if not paths:
            return None, None, "Aucune trame XML valide trouvée dans le .log."
        ipoc = _detect_ipoc_key(paths)
        df = build_dataframe_from_paths(paths, time_key=ipoc)
        # plainify paths pour stockage JSON-compatible
        paths_plain = {k: [float(x) for x in v] for k, v in paths.items()}
        return paths_plain, df, None

    return None, None, "Format non supporté (utiliser .json ou .log)."

# --- App Dash ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Tableau de bord Robot KUKA"

app.layout = dbc.Container([
    html.H1("Tableau de bord Robot KUKA", className="text-center my-4"),

    dbc.Row([
        dbc.Col([
            html.H5("1) Charger un fichier .log (local)"),
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
            html.Div(id="output-upload", style={"marginTop": "8px"}),
            html.Hr(),

            html.H5("2) Sélectionner une simulation depuis GitHub"),
            dcc.Dropdown(
                id='dropdown-simulation',
                options=get_simulation_list(),
                placeholder="Choisissez un fichier GitHub...",
            ),
            html.Br(),
            dbc.Button("Rafraîchir la liste", id='btn-refresh', color="info", className="w-100"),
            html.Hr(),

            html.H5("3) Sélectionner un tag extrait du log (après upload)"),
            dcc.Dropdown(id="tag-dropdown", placeholder="Sélectionnez un tag", style={"marginTop": "10px"}),
            html.Div(id="info-parsed", style={"marginTop": "6px", "fontSize": "0.9em", "color": "#555"}),

            # STORE : stocke soit {"paths": {...}} pour un log, soit {"simulation_json": {...}} pour JSON uploadé
            dcc.Store(id="parsed-paths", storage_type="memory")
        ], md=3, className="bg-light p-3 rounded"),

        dbc.Col([
            dcc.Loading(id="loading-graphs", type="circle", children=html.Div(id="graph-container"))
        ], md=9)
    ])
], fluid=True)

# --- Callbacks ---

@app.callback(
    Output('dropdown-simulation', 'options'),
    Input('btn-refresh', 'n_clicks')
)
def update_dropdown_list(n_clicks):
    return get_simulation_list()

# Réel callback d'upload (met à jour parsed-paths store et le dropdown des tags)
@app.callback(
    Output("parsed-paths", "data"),
    Output("tag-dropdown", "options"),
    Output("tag-dropdown", "value"),
    Output("info-parsed", "children"),
    Input("upload-data", "contents"),
    State("upload-data", "filename")
)
def handle_upload(contents, filename):
    if contents is None:
        return dash.no_update, [], None, ""

    paths, df, err = parse_uploaded_contents(contents, filename)
    if err:
        return None, [], None, html.Div(err, style={"color": "red"})
    # Si c'était un JSON de simulation uploadé, on ne transforme pas ici, on informe
    if isinstance(paths, dict) and 'timeseries' in paths:
        # c'était un JSON de simulation uploadé
        options = []
        default = None
        store = {"simulation_json": paths}
        info = html.Div(f"JSON de simulation chargé depuis l'upload : {filename}", style={"color": "green"})
        return store, options, default, info

    # sinon c'est un dictionnaire paths issu d'un .log
    options = [{"label": k, "value": k} for k in sorted(paths.keys())]
    default_value = options[0]["value"] if options else None
    store = {"paths": paths}
    info = html.Div(f"{len(paths)} tags extraits depuis le .log '{filename}'", style={"color": "green"})
    return store, options, default_value, info

# Callback principal d'affichage : priorise la simulation GitHub si sélectionnée,
# sinon affiche la simulation uploadée (si présente), sinon affiche tag du log (si présent).
@app.callback(
    Output("graph-container", "children"),
    Input("dropdown-simulation", "value"),
    Input("tag-dropdown", "value"),
    State("parsed-paths", "data")
)
def update_graph_container(simulation_filename, selected_tag, store):
    # 1) Si un fichier simulation GitHub est choisi -> afficher les graphiques de simulation
    if simulation_filename:
        data = load_simulation_data_from_github(simulation_filename)
        if data is None:
            return html.Div("❌ Erreur : Impossible de charger le fichier de simulation depuis GitHub.")
        try:
            df = pd.DataFrame(data.get('timeseries', []))
            num_joints = len(data.get('total_travel', []))
            simulation_filename = data.get('filename', 'Fichier téléchargé')

            # Tracé 3D
            fig_path = go.Figure()
            if 'tcp_positions' in data and data['tcp_positions']:
                path_data = np.array(data['tcp_positions'])
                fig_path.add_trace(go.Scatter3d(
                    x=path_data[:, 0],
                    y=path_data[:, 1],
                    z=path_data[:, 2],
                    mode='lines',
                    line=dict(color='blue', width=4),
                    name="Trajectoire de l'outil"
                ))
                fig_path.update_layout(
                    title_text="Tracé 3D du robot",
                    scene=dict(
                        xaxis_title='Axe X (mm)',
                        yaxis_title='Axe Y (mm)',
                        zaxis_title='Axe Z (mm)',
                        aspectmode='data'
                    )
                )
            else:
                fig_path = go.Figure()
                fig_path.add_annotation(text="Pas de données de tracé 3D pour cette simulation.", showarrow=False)
                fig_path.update_layout(title_text="Tracé 3D du robot", height=600)

            # Vitesse TCP et joints
            fig_vitesse = make_subplots(
                rows=max(1, num_joints + 1),
                cols=1,
                shared_xaxes=True,
                subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
            )
            if not df.empty and 'Time' in df.columns:
                fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)

                for consigne in data.get('commanded_tcp_speeds', []) or []:
                    fig_vitesse.add_hline(
                        y=consigne,
                        line_dash="dot",
                        annotation_text=f"Consigne: {consigne} mm/s",
                        annotation_position="top right",
                        row=1, col=1
                    )

                for i in range(num_joints):
                    col_name = f"J{i+1}_Speed"
                    if col_name in df.columns:
                        fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df[col_name], name=f"Axe {i+1}"), row=i+2, col=1)
            fig_vitesse.update_layout(showlegend=False, height=400 + num_joints * 200)

            # Déplacement angulaire total
            fig_cumul = go.Figure()
            if 'total_travel' in data and data['total_travel']:
                total_travel_data = data['total_travel']
                axis_labels = [f'Axe {i+1}' for i in range(len(total_travel_data))]
                fig_cumul.add_trace(go.Bar(
                    x=axis_labels,
                    y=total_travel_data,
                    text=[f'{val:.1f}°' for val in total_travel_data],
                    textposition='auto'
                ))
                fig_cumul.update_layout(title_text="Déplacement Angulaire Total")
            else:
                fig_cumul.add_annotation(text="Pas de données de déplacement d'axe pour cette simulation.", showarrow=False)
                fig_cumul.update_layout(title_text="Déplacement Angulaire Total", height=450)

            return html.Div([
                html.H2(f"Analyse de : {simulation_filename}"),
                html.Hr(),
                dcc.Graph(figure=fig_path, style={'height': '600px'}),
                html.Hr(),
                html.Div([dcc.Graph(figure=fig_vitesse)], style={'maxHeight': '65vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
                html.Hr(),
                dcc.Graph(figure=fig_cumul, style={'height': '450px'})
            ])
        except Exception as e:
            return html.Div(f"❌ Erreur lors du rendu des graphiques de simulation. Erreur : {e}")

    # 2) Si aucune simulation GitHub sélectionnée, regarder si l'utilisateur a uploadé un JSON de simulation
    if store and isinstance(store, dict) and "simulation_json" in store:
        data = store["simulation_json"]
        try:
            df = pd.DataFrame(data.get('timeseries', []))
            # réutiliser même logique d'affichage que pour GitHub
            num_joints = len(data.get('total_travel', []))
            # Tracé 3D
            fig_path = go.Figure()
            if 'tcp_positions' in data and data['tcp_positions']:
                path_data = np.array(data['tcp_positions'])
                fig_path.add_trace(go.Scatter3d(
                    x=path_data[:, 0],
                    y=path_data[:, 1],
                    z=path_data[:, 2],
                    mode='lines',
                    line=dict(color='blue', width=4),
                    name="Trajectoire de l'outil"
                ))
                fig_path.update_layout(title_text="Tracé 3D du robot", scene=dict(aspectmode='data'))
            else:
                fig_path.add_annotation(text="Pas de données de tracé 3D pour cette simulation.", showarrow=False)
                fig_path.update_layout(title_text="Tracé 3D du robot", height=600)

            fig_vitesse = make_subplots(rows=max(1, num_joints + 1), cols=1, shared_xaxes=True,
                                       subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)]))
            if not df.empty and 'Time' in df.columns:
                fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)
                for consigne in data.get('commanded_tcp_speeds', []) or []:
                    fig_vitesse.add_hline(y=consigne, line_dash="dot", annotation_text=f"Consigne: {consigne} mm/s",
                                          annotation_position="top right", row=1, col=1)
                for i in range(num_joints):
                    col_name = f"J{i+1}_Speed"
                    if col_name in df.columns:
                        fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df[col_name], name=f"Axe {i+1}"), row=i+2, col=1)
            fig_vitesse.update_layout(showlegend=False, height=400 + num_joints * 200)

            fig_cumul = go.Figure()
            if 'total_travel' in data and data['total_travel']:
                total_travel_data = data['total_travel']
                axis_labels = [f'Axe {i+1}' for i in range(len(total_travel_data))]
                fig_cumul.add_trace(go.Bar(x=axis_labels, y=total_travel_data,
                                          text=[f'{val:.1f}°' for val in total_travel_data], textposition='auto'))
                fig_cumul.update_layout(title_text="Déplacement Angulaire Total")
            else:
                fig_cumul.add_annotation(text="Pas de données de déplacement d'axe pour cette simulation.", showarrow=False)
                fig_cumul.update_layout(title_text="Déplacement Angulaire Total", height=450)

            return html.Div([
                html.H2("Analyse de la simulation uploadée"),
                html.Hr(),
                dcc.Graph(figure=fig_path, style={'height': '600px'}),
                html.Hr(),
                html.Div([dcc.Graph(figure=fig_vitesse)], style={'maxHeight': '65vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
                html.Hr(),
                dcc.Graph(figure=fig_cumul, style={'height': '450px'})
            ])
        except Exception as e:
            return html.Div(f"❌ Erreur lors du rendu des graphiques de la simulation uploadée. Erreur : {e}")

    # 3) Enfin, si on a un tag issu d'un .log uploadé -> afficher le graphe associé (comme précédemment)
    if store and isinstance(store, dict) and "paths" in store and selected_tag:
        paths = store.get("paths", {})
        if selected_tag not in paths:
            return html.Div("Tag introuvable dans les données.")
        values = paths[selected_tag]
        if not values:
            return html.Div("Le tag sélectionné ne contient pas de valeurs numériques.")

        # récupérer Time s'il existe
        ipoc_key = None
        for k in paths:
            if "ipoc" in k.lower():
                ipoc_key = k
                break
        if ipoc_key:
            time = paths[ipoc_key][:len(values)]
            avg = sum(abs(x) for x in time) / max(1, len(time))
            if avg > 1e6:
                time = [x / 1e6 for x in time]
            elif avg > 1e3:
                time = [x / 1e3 for x in time]
        else:
            time = list(range(len(values)))

        # figure
        fig_line = go.Figure()
        fig_line.add_trace(go.Scatter(x=time, y=values, mode="lines+markers", name=selected_tag))
        fig_line.update_layout(title=f"{selected_tag} - Série temporelle", xaxis_title="Time (s)" if ipoc_key else "Index", height=420)

        fig_hist = go.Figure()
        fig_hist.add_trace(go.Histogram(x=values, marker=dict(line=dict(width=1, color="white"), color="#1f77b4")))
        fig_hist.update_layout(title=f"{selected_tag} - Histogramme", height=420, margin=dict(t=40))

        return html.Div([
            html.H2(f"Analyse du tag : {selected_tag}"),
            html.Hr(),
            dcc.Graph(figure=fig_line),
            dcc.Graph(figure=fig_hist)
        ])

    # Si rien de sélectionné
    return html.Div("Aucune simulation GitHub sélectionnée, aucun fichier uploadé ou aucun tag choisi. Déposez un .log ou choisissez une simulation depuis GitHub.")

if __name__ == "__main__":
    app.run_server(debug=True)
