# Fichier: Dashboard_En_Ligne.py

import pandas as pd
import json
import requests
import numpy as np
import dash
from dash import dcc, html, Input, Output, State, no_update
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

def get_color_from_speed_list(speeds):
    colors = []
    for speed in speeds:
        if speed <= 0.1:
            colors.append('rgba(0, 0, 255, 1)')
        elif speed <= 3:
            colors.append('rgba(0, 179, 255, 1)')
        elif speed <= 8:
            colors.append('rgba(0, 255, 0, 1)')
        elif speed <= 20:
            colors.append('rgba(255, 255, 0, 1)')
        else:
            colors.append('rgba(255, 0, 0, 1)')
    return colors

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
        json_data['filename'] = filename # On ajoute le nom du fichier au dictionnaire
        return json_data
    except Exception as e:
        return None

def parse_uploaded_contents(contents, filename):
    if contents is None:
        return None, "Veuillez télécharger un fichier de simulation (XML, JSON ou LOG)."
    
    content_type, content_string = contents.split(',')
    decoded = base64.b64decode(content_string)
    data = None
    error_message = None

    try:
        if 'log' in filename:
            df = pd.read_csv(io.StringIO(decoded.decode('utf-8')), sep='\s+', header=None)
            
            if len(df.columns) < 7:
                error_message = "Format du fichier .log invalide. Nombre de colonnes insuffisant."
                return None, error_message
            
            times = df.iloc[:, 0].values
            positions_np = df.iloc[:, 1:4].values
            joints_np = df.iloc[:, 4:10].values
            
            delta_time = np.diff(times)
            delta_time[delta_time <= 0] = 0.0001
            
            delta_dist = np.linalg.norm(np.diff(positions_np, axis=0), axis=1)
            tcp_speeds = np.divide(delta_dist, delta_time)
            
            delta_joints = np.diff(joints_np, axis=0)
            joint_speeds = np.divide(delta_joints, delta_time[:, np.newaxis])
            
            most_solicited_joint = np.argmax(np.abs(joint_speeds), axis=1).tolist()
            total_travel = np.sum(np.abs(delta_joints), axis=0).tolist()
            
            timeseries = pd.DataFrame({
                'Time': times[1:],
                'TCP_Speed': tcp_speeds,
                **{f'J{i+1}_Speed': joint_speeds[:, i] for i in range(joints_np.shape[1])}
            }).to_dict('records')
            
            tcp_positions = positions_np.tolist()
            num_joints = joints_np.shape[1]
            
            data = {
                'timeseries': timeseries,
                'tcp_positions': tcp_positions,
                'most_solicited_joint': most_solicited_joint,
                'total_travel': total_travel,
                'commanded_tcp_speeds': [5, 16.67, 100],
            }

        elif 'xml' in filename:
            root = ET.fromstring(decoded)
            data_dict = {}
            for child in root:
                data_dict[child.tag] = [float(c.text) for c in child]
            df = pd.DataFrame(data_dict)
            
            df['TCP_Speed'] = np.random.rand(len(df)) * 50
            
            timeseries = df.to_dict('records')
            tcp_positions = df[['Pos_X', 'Pos_Y', 'Pos_Z']].values.tolist()
            most_solicited_joint = np.zeros(len(df)).tolist()
            total_travel = np.zeros(len(df)).tolist()
            num_joints = 6

            data = {
                'timeseries': timeseries,
                'tcp_positions': tcp_positions,
                'most_solicited_joint': most_solicited_joint,
                'total_travel': total_travel,
                'commanded_tcp_speeds': [5, 16.67, 100],
            }

        elif 'json' in filename:
            data = json.loads(decoded)
            
        else:
            error_message = "Format de fichier non pris en charge."
            return None, error_message

    except Exception as e:
        error_message = f"Erreur lors du traitement du fichier : {e}"
        return None, error_message
    
    if data:
        data['filename'] = filename
        
    return data, error_message

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Analyseur de Simulations Robot"

app.layout = dbc.Container([
    dcc.Store(id='data-store'),
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

@app.callback(
    Output('dropdown-simulation', 'options'),
    Input('btn-refresh', 'n_clicks')
)
def update_dropdown_list(n_clicks):
    return get_simulation_list()

@app.callback(
    Output('data-store', 'data'),
    Input('dropdown-simulation', 'value'),
    prevent_initial_call=True
)
def load_data_from_dropdown(simulation_filename):
    if simulation_filename:
        data = load_simulation_data_from_github(simulation_filename)
        return data if data else {}
    return {}

@app.callback(
    Output('data-store', 'data', allow_duplicate=True),
    Input('upload-data', 'contents'),
    State('upload-data', 'filename'),
    prevent_initial_call=True
)
def load_data_from_upload(contents, filename):
    if contents is None:
        return no_update
    data, error_msg = parse_uploaded_contents(contents, filename)
    if error_msg:
        # Affiche l'erreur si le parsing échoue
        return {'error': error_msg}
    return data

@app.callback(
    Output('graph-container', 'children'),
    Input('data-store', 'data')
)
def update_graphs(data):
    if not data or 'error' in data:
        return html.Div(f"❌ {data.get('error', 'Veuillez sélectionner un fichier ou en télécharger un pour commencer l\'analyse.')}")
    
    try:
        df = pd.DataFrame(data['timeseries'])
        num_joints = len(data.get('total_travel', []))
        simulation_filename = data.get('filename', 'Fichier téléchargé')

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

        # --- GRAPH B : Tracé 3D coloré par la vitesse ---
        fig_vitesse_3d = go.Figure()
        if 'tcp_positions' in data and data['tcp_positions'] and 'timeseries' in data and data['timeseries']:
            path_data = np.array(data['tcp_positions'])
            tcp_speeds = df['TCP_Speed']
            colors = get_color_from_speed_list(tcp_speeds)
            
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
            
            legend_items = [
                (0.1, 'rgba(0, 0, 255, 1)', '0 - 0.1 mm/s'),
                (3, 'rgba(0, 179, 255, 1)', '0.1 - 3 mm/s'),
                (8, 'rgba(0, 255, 0, 1)', '3 - 8 mm/s'),
                (20, 'rgba(255, 255, 0, 1)', '8 - 20 mm/s'),
                (100, 'rgba(255, 0, 0, 1)', '> 20 mm/s')
            ]
            
            for _, color, name in legend_items:
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
        
        # --- GRAPH C : Vitesse TCP en fonction du temps ---
        fig_vitesse_temps = make_subplots(
            rows=num_joints + 1,
            cols=1,
            shared_xaxes=True,
            subplot_titles=(["Vitesse TCP"] + [f"Vitesse Axe {i+1}" for i in range(num_joints)])
        )
        if 'timeseries' in data and data['timeseries']:
            fig_vitesse_temps.add_trace(go.Scatter(x=df['Time'], y=df['TCP_Speed'], name="TCP"), row=1, col=1)

            if 'commanded_tcp_speeds' in data and data['commanded_tcp_speeds']:
                for consigne in data['commanded_tcp_speeds']:
                    fig_vitesse_temps.add_hline(
                        y=consigne,
                        line_dash="dot",
                        annotation_text=f"Consigne: {consigne} mm/s",
                        annotation_position="top right",
                        row=1, col=1
                    )
            
            for i in range(num_joints):
                if f'J{i+1}_Speed' in df.columns:
                    fig_vitesse_temps.add_trace(go.Scatter(x=df['Time'], y=df[f'J{i+1}_Speed'], name=f"Axe {i+1}"), row=i+2, col=1)
        fig_vitesse_temps.update_layout(showlegend=False, height=400 + num_joints * 200)

        # --- NOUVEAU GRAPH D : Vitesse TCP en fonction de la distance ---
        fig_vitesse_distance = go.Figure()
        if 'tcp_positions' in data and data['tcp_positions'] and 'timeseries' in data and data['timeseries']:
            path_data = np.array(data['tcp_positions'])
            tcp_speeds = df['TCP_Speed']
            
            distances = np.linalg.norm(np.diff(path_data, axis=0), axis=1)
            cumulative_distance = np.insert(np.cumsum(distances), 0, 0)
            
            fig_vitesse_distance.add_trace(go.Scatter(
                x=cumulative_distance[1:],
                y=tcp_speeds,
                mode='lines',
                name="Vitesse TCP"
            ))

            if 'commanded_tcp_speeds' in data and data['commanded_tcp_speeds']:
                for consigne in data['commanded_tcp_speeds']:
                    fig_vitesse_distance.add_hline(
                        y=consigne,
                        line_dash="dot",
                        annotation_text=f"Consigne: {consigne} mm/s",
                        annotation_position="top right"
                    )

            fig_vitesse_distance.update_layout(
                title_text="Vitesse TCP en fonction de la distance",
                xaxis_title="Distance parcourue (mm)",
                yaxis_title="Vitesse TCP (mm/s)"
            )
        else:
            fig_vitesse_distance.add_annotation(text="Pas de données de vitesse ou de distance pour cette simulation.", showarrow=False)
            fig_vitesse_distance.update_layout(title_text="Vitesse TCP en fonction de la distance")

        # --- GRAPH E : Déplacement angulaire total ---
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
            html.H3("Tracé 3D par axe sollicité"),
            dcc.Graph(figure=fig_sollicitation, style={'height': '600px'}),
            html.Hr(),
            html.H3("Carte des Vitesses 3D"),
            dcc.Graph(figure=fig_vitesse_3d, style={'height': '600px'}),
            html.Hr(),
            html.Div([dcc.Graph(figure=fig_vitesse_temps)], style={'maxHeight': '65vh', 'overflowY': 'auto', 'border': '1px solid #ddd'}),
            html.Hr(),
            html.H3("Vitesse TCP en fonction de la distance"),
            dcc.Graph(figure=fig_vitesse_distance),
            html.Hr(),
            dcc.Graph(figure=fig_cumul, style={'height': '450px'})
        ])
    except Exception as e:
        return html.Div(f"❌ Erreur lors du rendu des graphiques. Erreur : {e}")

if __name__ == '__main__':
    app.run_server(debug=True)
