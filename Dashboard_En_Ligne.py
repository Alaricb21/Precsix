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

# --- Configuration ---
GITHUB_USER = "Alaricb21"
GITHUB_REPO = "Precsix"
GITHUB_BRANCH = "main"

# --- Fonctions pour récupérer les données depuis GitHub ---
def get_simulation_list():
    """Récupère la liste des fichiers .json du dépôt GitHub."""
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/"
        response = requests.get(api_url)
        response.raise_for_status()
        return [file['name'] for file in response.json() if file['name'].endswith('.json')]
    except Exception as e:
        print(f"Erreur en récupérant la liste des fichiers depuis GitHub: {e}")
        return []

def load_simulation_data(filename):
    """Charge les données d'un fichier .json spécifique depuis GitHub."""
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
        response = requests.get(raw_url)
        response.raise_for_status()
        return json.loads(response.text)
    except Exception as e:
        print(f"Erreur en chargeant le fichier {filename}: {e}")
        return None

# --- Création de l'application Dash ---
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Base de Données des Simulations Robot"

app.layout = dbc.Container([
    dbc.Row(dbc.Col(html.H1("Analyseur de Simulations Robot"), width=12, className="text-center my-4")),
    dbc.Row([
        dbc.Col([
            html.H4("Sélection de la Simulation"),
            dcc.Dropdown(
                id='dropdown-simulation', 
                options=get_simulation_list(),
                placeholder="Choisissez une simulation..."
            ),
            html.Br(),
            dbc.Button("Rafraîchir la liste", id='btn-refresh', color="info", className="w-100"),
        ], md=3, className="bg-light p-4 rounded"),
        dbc.Col([
            html.Div(id='graph-container')
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

@app.callback(
    Output('graph-container', 'children'),
    Input('dropdown-simulation', 'value')
)
def update_graphs(simulation_filename):
    if not simulation_filename:
        return html.Div("Veuillez sélectionner une simulation à afficher.")

    data = load_simulation_data(simulation_filename)
    if data is None:
        return html.Div("❌ Erreur : Impossible de charger le fichier de simulation. Le fichier est peut-être absent ou corrompu.")
    
    try:
        df = pd.DataFrame(data['timeseries'])
        
        fig_path = None
        if 'tcp_positions' in data and data['tcp_positions'] and 'most_solicited_joint' in data:
            path_data = np.array(data['tcp_positions'])
            most_solicited = np.array(data['most_solicited_joint'])

            fig_path = go.Figure()

            # --- DÉBUT DE LA NOUVELLE MÉTHODE POUR LA COULEUR ---
            
            # Définition des couleurs pour chaque axe
            colors_map = {
                0: 'blue',
                1: 'red',
                2: 'green',
                3: 'orange',
                4: 'purple',
                5: 'brown'
            }
            
            # On trouve les points où l'axe le plus sollicité change
            change_indices = np.where(np.diff(most_solicited) != 0)[0] + 1
            split_indices = np.insert(change_indices, [0, len(change_indices)], [0, len(most_solicited)])
            
            for i in range(len(split_indices) - 1):
                start_index = split_indices[i]
                end_index = split_indices[i+1]
                
                # On s'assure d'inclure les points de transition
                if i < len(split_indices) - 2:
                    end_index += 1
                
                segment_data = path_data[start_index:end_index]
                joint_index = most_solicited[start_index]
                
                # On ajoute un trace pour chaque segment
                fig_path.add_trace(go.Scatter3d(
                    x=segment_data[:, 0],
                    y=segment_data[:, 1],
                    z=segment_data[:, 2],
                    mode='lines',
                    line=dict(color=colors_map.get(joint_index, 'black'), width=4),
                    name=f"Axe {joint_index + 1}",
                    showlegend=True
                ))

            # --- FIN DE LA NOUVELLE MÉTHODE ---

            fig_path.update_layout(
                title_text="Trajectoire 3D du robot",
                scene=dict(xaxis_title='Axe X (mm)', yaxis_title='Axe Y (mm)', zaxis_title='Axe Z (mm)')
            )
        else:
            fig_path = go.Figure().add_annotation(text="Pas de données de tracé 3D pour cette simulation.", showarrow=False)
            fig_path.update_layout(title_text="Trajectoire 3D du robot", height=600)
        
        fig_vitesse = make_subplots(rows=len(data['total_travel']) + 1, cols=1, shared_xaxes=True, subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(len(data['total_travel']))]))
        fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)
        for i in range(len(data['total_travel'])):
            fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df[f'J{i+1}_Speed'], name=f"Axe {i+1}"), row=i+2, col=1)
        fig_vitesse.update_layout(showlegend=False, height=800)
        
        total_travel_data = data['total_travel']
        axis_labels = [f'Axe {i+1}' for i in range(len(total_travel_data))]
        fig_cumul = go.Figure(data=[go.Bar(x=axis_labels, y=total_travel_data, text=[f'{val:.1f}°' for val in total_travel_data], textposition='auto')])
        fig_cumul.update_layout(title_text="Déplacement Angulaire Total")
        
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
        return html.Div(f"❌ Erreur lors du rendu des graphiques. Le fichier est probablement dans un format invalide. Erreur : {e} ")

if __name__ == '__main__':
    app.run_server(debug=True)
