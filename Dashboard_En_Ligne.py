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

# --- Configuration ---
GITHUB_USER = "Alaricb21"
GITHUB_REPO = "Precsix"
GITHUB_BRANCH = "main"

def get_simulation_list():
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/"
        response = requests.get(api_url)
        response.raise_for_status()
        return [file['name'] for file in response.json() if file['name'].endswith('.json')]
    except Exception as e:
        return []

def load_simulation_data(filename):
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
        response = requests.get(raw_url)
        response.raise_for_status()
        return json.loads(response.text)
    except Exception as e:
        return None

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Analyseur de Simulations Robot"

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
        return html.Div("❌ Erreur : Impossible de charger le fichier de simulation. Le fichier est peut-être absent, corrompu ou l'URL est invalide.")
    
    try:
        df = pd.DataFrame(data['timeseries'])
        num_joints = len(data.get('total_travel', []))

        # --- GRAPH A : Tracé 3D du robot (avec couleurs et proportions fixes) ---
        fig_path = go.Figure()
        if 'tcp_positions' in data and data['tcp_positions']:
            path_data = np.array(data['tcp_positions'])
            
            # --- CORRECTION FINALE DU TRACÉ ET DE LA LÉGENDE ---
            if 'most_solicited_joint' in data and data['most_solicited_joint']:
                most_solicited = np.array(data['most_solicited_joint'])
                colors = px.colors.qualitative.Plotly
                color_map = {i: colors[i % len(colors)] for i in range(num_joints)}
                
                # On trouve les points où l'axe le plus sollicité change
                change_indices = np.where(np.diff(most_solicited) != 0)[0] + 1
                segment_indices = np.insert(change_indices, [0, len(change_indices)], [0, len(most_solicited)-1])

                # On garde une trace des légendes déjà affichées
                legend_shown = set()

                # On crée une trace pour chaque segment de couleur
                for i in range(len(segment_indices) - 1):
                    start_idx = segment_indices[i]
                    end_idx = segment_indices[i+1]
                    joint_idx = most_solicited[start_idx]
                    
                    # On s'assure d'inclure le point de fin du segment
                    end_idx = end_idx + 1 if end_idx < len(most_solicited) - 1 else end_idx
                    
                    segment_x = path_data[start_idx:end_idx, 0]
                    segment_y = path_data[start_idx:end_idx, 1]
                    segment_z = path_data[start_idx:end_idx, 2]
                    
                    # On vérifie si la légende pour cet axe a déjà été affichée
                    show_legend = joint_idx not in legend_shown
                    legend_shown.add(joint_idx)
                    
                    fig_path.add_trace(go.Scatter3d(
                        x=segment_x, y=segment_y, z=segment_z,
                        mode='lines',
                        line=dict(color=color_map.get(joint_idx, 'black'), width=4),
                        name=f"Axe {joint_idx + 1}",
                        showlegend=show_legend # Cette ligne a été modifiée
                    ))
            else:
                # Si pas de données de sollicitation, le tracé est en une seule couleur
                path_data = np.array(data['tcp_positions'])
                fig_path.add_trace(go.Scatter3d(
                    x=path_data[:, 0],
                    y=path_data[:, 1],
                    z=path_data[:, 2],
                    mode='lines',
                    line=dict(color='blue', width=4),
                    name="Trajectoire de l'outil"
                ))
            
            # Correction pour le format "ratatiné"
            fig_path.update_layout(
                title_text="Trajectoire 3D du robot",
                scene=dict(
                    xaxis_title='Axe X (mm)', 
                    yaxis_title='Axe Y (mm)', 
                    zaxis_title='Axe Z (mm)',
                    aspectmode='data'
                )
            )
        else:
            fig_path.add_annotation(text="Pas de données de tracé 3D pour cette simulation.", showarrow=False)
            fig_path.update_layout(title_text="Trajectoire 3D du robot", height=600)
        
        # --- GRAPH B : Vitesses TCP et des Axes ---
        fig_vitesse = make_subplots(
            rows=num_joints + 1,
            cols=1,
            shared_xaxes=True,
            subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
        )
        if 'timeseries' in data and data['timeseries']:
            fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)
            for i in range(num_joints):
                if f'J{i+1}_Speed' in df.columns:
                    fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df[f'J{i+1}_Speed'], name=f"Axe {i+1}"), row=i+2, col=1)
        fig_vitesse.update_layout(showlegend=False, height=400 + num_joints * 200)

        # --- GRAPH C : Déplacement angulaire total ---
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
"""
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

# --- Configuration ---
GITHUB_USER = "Alaricb21"
GITHUB_REPO = "Precsix"
GITHUB_BRANCH = "main"

def get_simulation_list():
    try:
        api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/"
        response = requests.get(api_url)
        response.raise_for_status()
        return [file['name'] for file in response.json() if file['name'].endswith('.json')]
    except Exception as e:
        return []

def load_simulation_data(filename):
    try:
        raw_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}/{filename}"
        response = requests.get(raw_url)
        response.raise_for_status()
        return json.loads(response.text)
    except Exception as e:
        return None

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Analyseur de Simulations Robot"

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
        return html.Div("❌ Erreur : Impossible de charger le fichier de simulation. Le fichier est peut-être absent, corrompu ou l'URL est invalide.")
    
    try:
        df = pd.DataFrame(data['timeseries'])
        num_joints = len(data.get('total_travel', []))
        
        # --- GRAPH A : Tracé 3D du robot (couleur unie) ---
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
                title_text="Trajectoire 3D du robot",
                scene=dict(
                    xaxis_title='Axe X (mm)', 
                    yaxis_title='Axe Y (mm)', 
                    zaxis_title='Axe Z (mm)',
                    aspectmode='data'
                )
            )
        else:
            fig_path.add_annotation(text="Pas de données de tracé 3D pour cette simulation.", showarrow=False)
            fig_path.update_layout(title_text="Trajectoire 3D du robot", height=600)
        
        # --- GRAPH B : Vitesses TCP et des Axes ---
        fig_vitesse = make_subplots(
            rows=num_joints + 1,
            cols=1,
            shared_xaxes=True,
            subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
        )
        if 'timeseries' in data and data['timeseries']:
            fig_vitesse.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)

            # NOUVEAU : Affichage des consignes
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

        # --- GRAPH C : Déplacement angulaire total ---
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
"""
