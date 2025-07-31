# Fichier: Dashboard_En_Ligne.py

import pandas as pd
import json
import requests
from io import BytesIO

import dash
from dash import dcc, html, Input, Output, State
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import dash_bootstrap_components as dbc

# --- Configuration ---
GITHUB_USER = "Alaricb21"
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
    dcc.Download(id="download-excel"),
    
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
            dbc.Button("Rafraîchir la liste", id='btn-refresh', color="info", className="w-100 mb-3"),
            dbc.Button("Exporter en Excel", id='btn-export', color="success", className="w-100"),
            
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

    # ---- Graphique des vitesses (inchangé) ----
    df_vitesse = pd.DataFrame(data['timeseries'])
    num_axes = len(data['total_travel'])
    fig_vitesse = make_subplots(
        rows=num_axes + 1, 
        cols=1, 
        shared_xaxes=True, 
        subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_axes)])
    )
    fig_vitesse.add_trace(go.Scatter(x=df_vitesse['Time'], y=df_vitesse['TCP_Speed'], name="TCP", mode='lines'), row=1, col=1)
    for i in range(num_axes):
        col_name = f'J{i+1}_Speed'
        if col_name in df_vitesse.columns:
            fig_vitesse.add_trace(go.Scatter(x=df_vitesse['Time'], y=df_vitesse[col_name], name=f"Axe {i+1}", mode='lines'), row=i+2, col=1)
    fig_vitesse.update_layout(showlegend=False, margin=dict(t=40, b=20), height=250 * (num_axes + 1))
    
    # ---- NOUVEAU : Graphique des couples ----
    # On vérifie si les données de couple existent dans le fichier
    if 'torqueseries' in data:
        df_torque = pd.DataFrame(data['torqueseries'])
        fig_torque = make_subplots(
            rows=num_axes, 
            cols=1, 
            shared_xaxes=True, 
            subplot_titles=[f"Couple Axe {i+1} (Nm)" for i in range(num_axes)]
        )
        for i in range(num_axes):
            col_name = f'J{i+1}_Torque'
            if col_name in df_torque.columns:
                fig_torque.add_trace(go.Scatter(x=df_torque['Time'], y=df_torque[col_name], name=f"Couple {i+1}", mode='lines'), row=i+1, col=1)
        fig_torque.update_layout(showlegend=False, margin=dict(t=40, b=20), height=200 * num_axes)
        
        # On crée un conteneur pour le graphique de couple
        torque_graph_div = html.Div([
            html.Hr(),
            html.H2("Analyse des Couples", className="text-center"),
            html.Div([dcc.Graph(figure=fig_torque)], style={'maxHeight': '80vh', 'overflowY': 'auto', 'border': '1px solid #ddd'})
        ])
    else:
        # Si pas de données de couple, on n'affiche rien pour cette section
        torque_graph_div = html.Div()

    # ---- Graphique des cumuls (inchangé) ----
    total_travel_data = data['total_travel']
    axis_labels = [f'Axe {i+1}' for i in range(num_axes)]
    fig_cumul = go.Figure(data=[go.Bar(x=axis_labels, y=total_travel_data, text=[f'{val:.1f}°' for val in total_travel_data], textposition='auto')])
    fig_cumul.update_layout(title_text="Déplacement Angulaire Total")
    
    # MODIFIÉ : On retourne la mise en page complète avec les trois graphiques
    return html.Div([
        html.H2(f"Analyse de : {simulation_filename}", className="text-center"),
        html.Hr(),
        html.H2("Analyse des Vitesses", className="text-center"),
        html.Div([dcc.Graph(figure=fig_vitesse)], style={'maxHeight': '80vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
        
        # Ajout du graphique de couple
        torque_graph_div,
        
        html.Hr(),
        dcc.Graph(figure=fig_cumul, style={'height': '450px'})
    ])

@app.callback(
    Output("download-excel", "data"),
    Input("btn-export", "n_clicks"),
    State("dropdown-simulation", "value"),
    prevent_initial_call=True,
)
def export_to_excel(n_clicks, simulation_filename):
    if not simulation_filename:
        return dash.no_update

    data = load_simulation_data(simulation_filename)
    if not data:
        return dash.no_update

    # Préparation du fichier Excel en mémoire
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Feuille 1 : Vitesses
        df_vitesse = pd.DataFrame(data['timeseries'])
        df_vitesse.to_excel(writer, sheet_name='Données de Vitesse', index=False)
        
        # Feuille 2 : Cumuls
        df_cumul = pd.DataFrame({
            'Axe': [f'Axe {i+1}' for i in range(len(data['total_travel']))],
            'Déplacement Total (degrés)': data['total_travel']
        })
        df_cumul.to_excel(writer, sheet_name='Cumul par Axe', index=False)
        
        # MODIFIÉ : Ajout de la feuille 3 pour les couples, si elle existe
        if 'torqueseries' in data:
            df_torque = pd.DataFrame(data['torqueseries'])
            df_torque.to_excel(writer, sheet_name='Données de Couple', index=False)
    
    excel_data = output.getvalue()
    
    clean_filename = simulation_filename.replace(".json", "")
    return dcc.send_bytes(excel_data, f"analyse_{clean_filename}.xlsx")


if __name__ == '__main__':
    app.run_server(debug=True)
