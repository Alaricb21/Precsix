# Fichier: Dashboard_En_Ligne.py (Version de débogage)

import pandas as pd
import json
import requests

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc

# --- Configuration ---
GITHUB_USER = "Alarich21"
GITHUB_REPO = "Precsix"

# --- Fonctions pour récupérer les données depuis GitHub ---
def get_simulation_list():
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/"
        response = requests.get(api_url)
        response.raise_for_status()
        return [file['name'] for file in response.json() if file['name'].endswith('.json')]
    except Exception as e:
        print(f"Erreur en récupérant la liste des fichiers depuis GitHub: {e}")
        return []

def load_simulation_data(filename):
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{filename}"
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
            dcc.Dropdown(id='dropdown-simulation', options=get_simulation_list(), placeholder="Choisissez une simulation..."),
            html.Br(),
            dbc.Button("Rafraîchir la liste", id='btn-refresh', color="info", className="w-100"),
        ], md=3, className="bg-light p-4 rounded"),
        dbc.Col([html.Div(id='graph-container')], md=9)
    ])
], fluid=True)

# --- Callbacks ---
@app.callback(
    Output('dropdown-simulation', 'options'),
    Input('btn-refresh', 'n_clicks')
)
def update_dropdown_list(n_clicks):
    return get_simulation_list()

# MODIFIÉ : Cette fonction est simplifiée pour le débogage
@app.callback(
    Output('graph-container', 'children'),
    Input('dropdown-simulation', 'value')
)
def update_graphs_debug(simulation_filename):
    if not simulation_filename:
        return html.Div("Veuillez sélectionner une simulation à afficher.")

    data = load_simulation_data(simulation_filename)
    if not data:
        return html.Div("Impossible de charger les données de cette simulation.")

    df = pd.DataFrame(data['timeseries'])

    # --- TEST : Création d'un graphique unique et simple ---
    # On ne crée qu'une seule figure pour la vitesse du TCP.
    fig_test = go.Figure()
    
    # On ajoute la trace de la vitesse TCP
    fig_test.add_trace(go.Scatter(
        x=df['Time'], 
        y=df['TCP_Speed'], 
        name="Vitesse TCP", 
        mode='lines'
    ))
    
    fig_test.update_layout(
        title="Graphique de Test : Vitesse TCP uniquement"
    )

    # On retourne uniquement ce graphique de test.
    return html.Div([
        html.H2(f"Analyse de : {simulation_filename}", className="text-center"),
        html.Hr(),
        html.H4("Mode de débogage :"),
        dcc.Graph(figure=fig_test)
    ])

if __name__ == '__main__':
    app.run_server(debug=True)
