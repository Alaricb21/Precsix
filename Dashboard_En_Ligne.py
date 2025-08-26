# Fichier: Dashboard_En_Ligne.py

import pandas as pd
import json
import requests
import numpy as np
import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc
import plotly.express as px
import base64
import io
import xml.etree.ElementTree as ET

# --- Configuration ---
GITHUB_USER = "Alaricb21"
GITHUB_REPO = "Precsix"
GITHUB_BRANCH = "main"

# Fonction pour obtenir une couleur en fonction de la vitesse
def get_color_from_speed_list(speeds):
    colors = []
    for speed in speeds:
        if speed <= 0.1:
            colors.append('rgba(0, 0, 255, 1)') # Bleu
        elif speed <= 3:
            colors.append('rgba(0, 179, 255, 1)') # Bleu clair
        elif speed <= 8:
            colors.append('rgba(0, 255, 0, 1)') # Vert
        elif speed <= 20:
            colors.append('rgba(255, 255, 0, 1)') # Jaune
        else:
            colors.append('rgba(255, 0, 0, 1)') # Rouge
    return colors

# --- NOUVEAU : Fonction de chargement de données à partir de fichiers uploadés ---
def parse_contents(contents, filename):
    if contents is None:
        return None
    
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)

    try:
        if 'xml' in filename:
            # On assume un format XML simple avec des balises pour chaque donnée
            root = ET.fromstring(decoded)
            data_dict = {}
            for child in root:
                data_dict[child.tag] = [float(c.text) for c in child]
            df = pd.DataFrame(data_dict)

            # On simule les données requises pour le dashboard
            df['TCP_Speed'] = np.random.rand(len(df)) * 50 # Valeurs aléatoires
            
            # TODO: Adapter cette partie pour extraire les vraies données de votre XML
            timeseries = df.to_dict('records')
            tcp_positions = df[['Pos_X', 'Pos_Y', 'Pos_Z']].values.tolist()
            most_solicited_joint = np.zeros(len(df)).tolist()
            total_travel = np.zeros(len(df)).tolist()
            
        elif 'json' in filename:
            json_data = json.loads(decoded)
            
            # On assume le même format JSON que précédemment
            timeseries = json_data.get('timeseries', [])
            tcp_positions = json_data.get('tcp_positions', [])
            most_solicited_joint = json_data.get('most_solicited_joint', [])
            total_travel = json_data.get('total_travel', [])
            
        else:
            return None, "Format de fichier non pris en charge."

    except Exception as e:
        return None, f"Erreur lors du traitement du fichier : {e}"

    num_joints = len(total_travel) if total_travel else 0
    return {
        'timeseries': timeseries,
        'tcp_positions': tcp_positions,
        'most_solicited_joint': most_solicited_joint,
        'total_travel': total_travel,
        'commanded_tcp_speeds': [5, 16.67, 100], # Consignes par défaut
    }, num_joints, None

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Analyseur de Simulations Robot"

app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H1("Analyseur de Simulations Robot"), width=12, className="text-center my-4")),
    dbc.Row([
        dbc.Col([
            html.H4("Télécharger une simulation"),
            dcc.Upload(
                id='upload-data',
                children=html.Div(['Glissez-déposez ou ', html.A('Sélectionnez un fichier')]),
                style={'width': '100%', 'height': '60px', 'lineHeight': '60px', 'borderWidth': '1px', 'borderStyle': 'dashed', 'borderRadius': '5px', 'textAlign': 'center'},
                multiple=False
            ),
        ], md=3, className="bg-light p-4 rounded"),
        dbc.Col([
            html.Div(id='graph-container')
        ], md=9)
    ])
], fluid=True)

@app.callback(
    Output('graph-container', 'children'),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def update_output(contents, filename):
    if contents is None:
        return html.Div("Veuillez télécharger un fichier de simulation (XML ou JSON) pour commencer l'analyse.")

    data, num_joints, error_msg = parse_contents(contents, filename)
    if error_msg:
        return html.Div(f"❌ {error_msg}")
    
    try:
        df = pd.DataFrame(data['timeseries'])
        
        # --- GRAPH A : Tracé 3D coloré par l'axe sollicité ---
        fig_sollicitation = go.Figure()
        # ... (code pour fig_sollicitation, inchangé)
        
        # --- GRAPH B : Tracé 3D coloré par la vitesse ---
        fig_vitesse_3d = go.Figure()
        # ... (code pour fig_vitesse_3d, inchangé)
        
        # --- GRAPH C : Vitesses TCP et des Axes ---
        fig_vitesses_courbes = make_subplots(
            rows=num_joints + 1,
            cols=1,
            shared_xaxes=True,
            subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
        )
        # ... (code pour fig_vitesses_courbes, inchangé)
        
        # --- GRAPH D : Vitesse TCP en fonction de la distance ---
        fig_vitesse_distance = go.Figure()
        # ... (code pour fig_vitesse_distance, inchangé)
        
        # --- GRAPH E : Déplacement angulaire total ---
        fig_cumul = go.Figure()
        # ... (code pour fig_cumul, inchangé)

        return html.Div([
            html.H2(f"Analyse du fichier : {filename}"),
            html.Hr(),
            html.H3("Tracé 3D par axe sollicité"),
            dcc.Graph(figure=fig_sollicitation, style={'height': '600px'}),
            html.Hr(),
            html.H3("Carte des Vitesses 3D"),
            dcc.Graph(figure=fig_vitesse_3d, style={'height': '600px'}),
            html.Hr(),
            html.Div([dcc.Graph(figure=fig_vitesses_courbes)], style={'maxHeight': '65vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
            html.Hr(),
            html.H3("Vitesse TCP en fonction de la distance"),
            dcc.Graph(figure=fig_vitesse_distance),
            html.Hr(),
            dcc.Graph(figure=fig_cumul, style={'height': '450px'})
        ])

    except Exception as e:
        return html.Div(f"❌ Erreur lors du rendu des graphiques : {e}")

if __name__ == '__main__':
    app.run_server(debug=True)
