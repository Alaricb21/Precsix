# Fichier: Dashboard_En_Ligne.py

import pandas as pd
import json
import requests # Pour lire les fichiers depuis GitHub

import dash
from dash import dcc, html, Input, Output
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc

# --- Configuration ---
# Remplacez avec votre nom d'utilisateur et nom de dépôt GitHub
GITHUB_USER = "Alarich21"
GITHUB_REPO = "Precsix"

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
    if not data:
        return html.Div("Impossible de charger les données de cette simulation.")

    df = pd.DataFrame(data['timeseries'])
    
    num_axes = len(data['total_travel'])
    
    # Graphique des vitesses
    fig_vitesse = make_subplots(
        rows=num_axes + 1, 
        cols=1, 
        shared_xaxes=True, 
        subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_axes)])
    )
    
    # Trace de la vitesse TCP
    fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP", mode='lines'), row=1, col=1)
    
    # Traces des vitesses des axes
    for i in range(num_axes):
        col_name = f'J{i+1}_Speed'
        if col_name in df.columns:
            fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df[col_name], name=f"Axe {i+1}", mode='lines'), row=i+2, col=1)
    
    # MODIFIÉ : Le paramètre 'height' fixe qui causait le bug a été retiré
    fig_vitesse.update_layout(showlegend=False, margin=dict(t=30, b=10))
    
    # Graphique des cumuls
    total_travel_data = data['total_travel']
    axis_labels = [f'Axe {i+1}' for i in range(num_axes)]
    fig_cumul = go.Figure(data=[go.Bar(x=axis_labels, y=total_travel_data, text=[f'{val:.1f}°' for val in total_travel_data], textposition='auto')])
    fig_cumul.update_layout(title_text="Déplacement Angulaire Total")
    
    # On retourne la mise en page des graphiques
    return html.Div([
        html.H2(f"Analyse de : {simulation_filename}", className="text-center"),
        html.Hr(),
        # MODIFIÉ : La hauteur maximale a été augmentée pour plus de confort
        html.Div([dcc.Graph(figure=fig_vitesse)], style={'maxHeight': '80vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
        html.Hr(),
        dcc.Graph(figure=fig_cumul, style={'height': '450px'})
    ])

if __name__ == '__main__':
    app.run_server(debug=True)
