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

        # --- GRAPH A : Tracé 3D coloré par l'axe sollicité (avec survol) ---
        fig_sollicitation = go.Figure()
        if 'tcp_positions' in data and data['tcp_positions'] and 'most_solicited_joint' in data and data['most_solicited_joint']:
            path_data = np.array(data['tcp_positions'])
            most_solicited = np.array(data['most_solicited_joint'])
            colors = px.colors.qualitative.Plotly
            color_map = {i: colors[i % len(colors)] for i in range(num_joints)}
            
            change_indices = np.where(np.diff(most_solicited) != 0)[0] + 1
            segment_indices = np.insert(change_indices, [0, len(change_indices)], [0, len(most_solicited)-1])

            legend_shown = set()
            for i in range(len(segment_indices) - 1):
                start_idx = segment_indices[i]
                end_idx = segment_indices[i+1]
                joint_idx = most_solicited[start_idx]
                end_idx = end_idx + 1 if end_idx < len(most_solicited) - 1 else end_idx
                segment_x = path_data[start_idx:end_idx, 0]
                segment_y = path_data[start_idx:end_idx, 1]
                segment_z = path_data[start_idx:end_idx, 2]
                show_legend = joint_idx not in legend_shown
                legend_shown.add(joint_idx)

                # NOUVEAU : Création des informations de survol
                hover_texts = [
                    f"X: {x:.2f} mm<br>Y: {y:.2f} mm<br>Z: {z:.2f} mm<br>Vitesse: {vitesse:.2f} mm/s"
                    for x, y, z, vitesse in zip(segment_x, segment_y, segment_z, df['TCP_Speed'][start_idx:end_idx])
                ]
                
                fig_sollicitation.add_trace(go.Scatter3d(
                    x=segment_x, y=segment_y, z=segment_z,
                    mode='lines',
                    line=dict(color=color_map.get(joint_idx, 'black'), width=4),
                    name=f"Axe {joint_idx + 1}",
                    showlegend=show_legend,
                    hoverinfo="text",
                    hovertext=hover_texts
                ))
            
            fig_sollicitation.update_layout(
                title_text="Tracé 3D par axe sollicité",
                scene=dict(
                    xaxis_title='Axe X (mm)', 
                    yaxis_title='Axe Y (mm)', 
                    zaxis_title='Axe Z (mm)',
                    aspectmode='data'
                )
            )
        else:
            fig_sollicitation.add_annotation(text="Pas de données de sollicitation d'axe pour cette simulation.", showarrow=False)
            fig_sollicitation.update_layout(title_text="Tracé 3D par axe sollicité", height=600)

        # --- GRAPH B : Tracé 3D coloré par la vitesse (avec survol et légende) ---
        fig_vitesse_3d = go.Figure()
        if 'tcp_positions' in data and data['tcp_positions'] and 'timeseries' in data and data['timeseries']:
            path_data = np.array(data['tcp_positions'])
            tcp_speeds = df['TCP_Speed']
            colors = get_color_from_speed_list(tcp_speeds)
            
            # NOUVEAU : Création des informations de survol
            hover_texts = [
                f"X: {x:.2f} mm<br>Y: {y:.2f} mm<br>Z: {z:.2f} mm<br>Vitesse: {vitesse:.2f} mm/s"
                for x, y, z, vitesse in zip(path_data[:, 0], path_data[:, 1], path_data[:, 2], tcp_speeds)
            ]

            fig_vitesse_3d.add_trace(go.Scatter3d(
                x=path_data[:, 0],
                y=path_data[:, 1],
                z=path_data[:, 2],
                mode='lines',
                line=dict(
                    color=colors,
                    width=4
                ),
                hoverinfo="text",
                hovertext=hover_texts
            ))
            
            # NOUVEAU : Ajout de traces "fantômes" pour la légende
            legend_items = [
                (0.1, 'Bleu', '0 - 0.1 mm/s'),
                (3, 'Bleu clair', '0.1 - 3 mm/s'),
                (8, 'Vert', '3 - 8 mm/s'),
                (20, 'Jaune', '8 - 20 mm/s'),
                (100, 'Rouge', '> 20 mm/s')
            ]
            
            for speed, color, name in legend_items:
                fig_vitesse_3d.add_trace(go.Scatter3d(
                    x=[None], y=[None], z=[None],
                    mode='lines',
                    line=dict(color=color, width=4),
                    name=name
                ))

            fig_vitesse_3d.update_layout(
                title_text="Carte des Vitesses 3D",
                scene=dict(
                    xaxis_title='Axe X (mm)', 
                    yaxis_title='Axe Y (mm)', 
                    zaxis_title='Axe Z (mm)',
                    aspectmode='data'
                )
            )
        else:
            fig_vitesse_3d.add_annotation(text="Pas de données de vitesse ou de tracé pour cette simulation.", showarrow=False)
            fig_vitesse_3d.update_layout(title_text="Carte des Vitesses 3D", height=600)
        
        # --- GRAPH C : Vitesses TCP et des Axes ---
        fig_vitesses_courbes = make_subplots(
            rows=num_joints + 1,
            cols=1,
            shared_xaxes=True,
            subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
        )
        if 'timeseries' in data and data['timeseries']:
            fig_vitesses_courbes.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)

            if 'commanded_tcp_speeds' in data and data['commanded_tcp_speeds']:
                for consigne in data['commanded_tcp_speeds']:
                    fig_vitesses_courbes.add_hline(
                        y=consigne,
                        line_dash="dot",
                        annotation_text=f"Consigne: {consigne} mm/s",
                        annotation_position="top right",
                        row=1, col=1
                    )
            
            for i in range(num_joints):
                if f'J{i+1}_Speed' in df.columns:
                    fig_vitesses_courbes.add_trace(go.Scatter(x=df['Time'], y=df[f'J{i+1}_Speed'], name=f"Axe {i+1}"), row=i+2, col=1)
        fig_vitesses_courbes.update_layout(showlegend=False, height=400 + num_joints * 200)

        # --- GRAPH D : Déplacement angulaire total ---
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
            html.H3("Tracé 3D par axe sollicité"),
            dcc.Graph(figure=fig_sollicitation, style={'height': '600px'}),
            html.Hr(),
            html.H3("Carte des Vitesses 3D"),
            dcc.Graph(figure=fig_vitesse_3d, style={'height': '600px'}),
            html.Hr(),
            html.Div([dcc.Graph(figure=fig_vitesses_courbes)], style={'maxHeight': '65vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
            html.Hr(),
            dcc.Graph(figure=fig_cumul, style={'height': '450px'})
        ])
    except Exception as e:
        return html.Div(f"❌ Erreur lors du rendu des graphiques. Erreur : {e}")

if __name__ == '__main__':
    app.run_server(debug=True)
