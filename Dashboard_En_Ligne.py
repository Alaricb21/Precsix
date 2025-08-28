import pandas as pd
import json
import requests
import numpy as np
import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc
import plotly.express as px
import base64
import io

# --- Configuration ---
GITHUB_USER = "Alaricb21"
GITHUB_REPO = "Precsix"
GITHUB_BRANCH = "main"

# --- Fonctions de chargement de données ---
def get_simulation_list():
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/"
        response = requests.get(api_url)
        response.raise_for_status()
        files = [{'label': item['name'], 'value': item['path']} for item in response.json() if item['name'].endswith('.json') and item['type'] == 'file']
        return files
    except Exception as e:
        print(f"Erreur en récupérant la liste des fichiers depuis GitHub: {e}")
        return []

def load_simulation_data_from_github(filename):
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
        response = requests.get(raw_url)
        response.raise_for_status()
        json_data = json.loads(response.text)
        json_data['filename'] = filename
        return json_data
    except Exception as e:
        return None

# NOUVEAU : Fonction pour analyser le contenu du fichier uploadé
def parse_uploaded_contents(contents, filename):
    if contents is None:
        return None
    
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    
    try:
        if 'json' in filename:
            data = json.loads(decoded)
        else:
            return None
    except Exception as e:
        return None
    
    if data:
        data['filename'] = filename
    return data

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Analyseur de Simulations Robot"

app.layout = dbc.Container([
    dcc.Store(id='data-store'), # NOUVEAU : Composant pour stocker les données
    dbc.Row(dbc.Col(html.H1("Analyseur de Simulations Robot"), width=12, className="text-center my-4")),
    dbc.Row([
        dbc.Col([
            html.H4("Sélectionner depuis GitHub"),
            dcc.Dropdown(
                id='dropdown-simulation',
                options=get_simulation_list(),
                placeholder="Choisissez un fichier GitHub...",
            ),
            html.Br(),
            dbc.Button("Rafraîchir la liste", id='btn-refresh', color="info", className="w-100"),
            html.Hr(),
            html.H4("Télécharger un fichier local"),
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

# Callback pour mettre à jour la liste des fichiers GitHub
@app.callback(
    Output('dropdown-simulation', 'options'),
    Input('btn-refresh', 'n_clicks')
)
def update_dropdown_list(n_clicks):
    return get_simulation_list()

# NOUVEAU : Callback pour charger des données depuis GitHub et les stocker
@app.callback(
    Output('data-store', 'data'),
    Input('dropdown-simulation', 'value')
)
def load_data_from_dropdown(simulation_filename):
    if simulation_filename:
        data = load_simulation_data_from_github(simulation_filename)
        return data if data else {}
    return {}

# NOUVEAU : Callback pour charger des données depuis l'upload local et les stocker
@app.callback(
    Output('data-store', 'data', allow_duplicate=True),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename')
)
def load_data_from_upload(contents, filename):
    data = parse_uploaded_contents(contents, filename)
    return data if data else {}

# NOUVEAU : Callback pour générer les graphiques à partir des données stockées
@app.callback(
    Output('graph-container', 'children'),
    Input('data-store', 'data')
)
def update_graphs(data):
    if not data:
        return html.Div("Veuillez sélectionner un fichier ou en télécharger un pour commencer l'analyse.")
    
    try:
        df = pd.DataFrame(data['timeseries'])
        num_joints = len(data.get('total_travel', []))
        simulation_filename = data.get('filename', 'Fichier téléchargé')

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
            fig_path.add_annotation(text="Pas de données de tracé 3D pour cette simulation.", showarrow=False)
            fig_path.update_layout(title_text="Tracé 3D du robot", height=600)
        
        fig_vitesse = make_subplots(
            rows=num_joints + 1,
            cols=1,
            shared_xaxes=True,
            subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
        )
        if 'timeseries' in data and data['timeseries']:
            fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)

            if 'commanded_tcp_speeds' in data and data['commanded_tcp_speeds']:
                for consigne in data['commanded_tcp_speeds']:
                    fig_vitesse.add_hline(
                        y=consigne,
                        line_dash="dot",
                        annotation_text=f"Consigne: {consigne} mm/s",
                        annotation_position="top right",
                        row=1, col=1
                    )
            
            for i in range(num_joints):
                if f'J{i+1}_Speed' in df.columns:
                    fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df[f'J{i+1}_Speed'], name=f"Axe {i+1}"), row=i+2, col=1)
        fig_vitesse.update_layout(showlegend=False, height=400 + num_joints * 200)

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
        return html.Div(f"❌ Erreur lors du rendu des graphiques. Erreur : {e}")

if __name__ == '__main__':
    app.run_server(debug=True)
