import base64
import io
import json
import re
import xml.etree.ElementTree as ET

import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import pandas as pd
import numpy as np
import plotly.graph_objs as go
import requests

# ----------------------------
# Fonction utilitaire
# ----------------------------

def moving_average(data, window_size=5):
    if len(data) < window_size:
        return data
    return np.convolve(data, np.ones(window_size)/window_size, mode="same")

# ----------------------------
# Parsing des fichiers
# ----------------------------

def parse_log_file(text):
    """
    Parse un fichier .log RSI où chaque ligne DBG contient un bloc XML <Rob>...</Rob>.
    """
    parsed_data_list = []

    for line in text.splitlines():
        # On isole la partie XML entre guillemets si c’est un <Rob>
        match = re.search(r'DBG\s+"(<Rob.*</Rob>)', line)
        if not match:
            continue
        xml_str = match.group(1)
        try:
            root = ET.fromstring(xml_str)
            ipoc = float(root.find("IPOC").text) / 1000.0
            pos = root.find("RIst")
            joints = root.find("AIPos")
            data_row = {
                "Time": ipoc,
                "Pos_X": float(pos.get("X")),
                "Pos_Y": float(pos.get("Y")),
                "Pos_Z": float(pos.get("Z")),
                "J1": float(joints.get("A1")),
                "J2": float(joints.get("A2")),
                "J3": float(joints.get("A3")),
                "J4": float(joints.get("A4")),
                "J5": float(joints.get("A5")),
                "J6": float(joints.get("A6")),
            }
            parsed_data_list.append(data_row)
        except Exception:
            continue

    if not parsed_data_list:
        return None

    return pd.DataFrame(parsed_data_list)


def parse_json_file(content):
    try:
        return json.loads(content)
    except Exception:
        return None


def parse_uploaded_contents(contents, filename):
    """
    Gère à la fois les fichiers .json et .log
    """
    content_type, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)

    if filename.endswith(".json"):
        return parse_json_file(decoded.decode("utf-8")), None
    elif filename.endswith(".log"):
        log_text = decoded.decode("utf-8", errors="ignore")
        df = parse_log_file(log_text)
        if df is None:
            return None, "Impossible de parser le .log : aucun bloc <Rob> valide trouvé."
        return compute_metrics(df, smooth=True), None
    else:
        return None, "Format non supporté (utiliser .json ou .log)."

# ----------------------------
# Calcul des métriques
# ----------------------------

def compute_metrics(df, smooth=False):
    times = df["Time"].values
    positions_np = df[["Pos_X", "Pos_Y", "Pos_Z"]].values
    joints_np = df[["J1", "J2", "J3", "J4", "J5", "J6"]].values

    delta_time = np.diff(times)
    delta_time[delta_time <= 0] = 1e-4

    delta_dist = np.linalg.norm(np.diff(positions_np, axis=0), axis=1)
    tcp_speeds = np.divide(delta_dist, delta_time)

    delta_joints = np.diff(joints_np, axis=0)
    joint_speeds = np.divide(delta_joints, delta_time[:, np.newaxis])

    # --- option lissage ---
    if smooth and len(tcp_speeds) > 5:
        tcp_speeds = moving_average(tcp_speeds, 5)
        joint_speeds = np.array(
            [moving_average(joint_speeds[:, i], 5) for i in range(joint_speeds.shape[1])]
        ).T

    most_solicited_joint = np.argmax(np.abs(joint_speeds), axis=1).tolist()
    total_travel = np.sum(np.abs(delta_joints), axis=0).tolist()

    timeseries = pd.DataFrame({
        "Time": times[1:],
        "TCP_Speed": tcp_speeds,
        **{f"J{i+1}_Speed": joint_speeds[:, i] for i in range(joints_np.shape[1])}
    }).to_dict("records")

    tcp_positions = positions_np.tolist()

    return {
        "timeseries": timeseries,
        "tcp_positions": tcp_positions,
        "most_solicited_joint": most_solicited_joint,
        "total_travel": total_travel,
        "commanded_tcp_speeds": [5, 16.67, 100],
    }

# ----------------------------
# Dash app
# ----------------------------

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server

app.layout = dbc.Container([
    html.H1("Tableau de bord Robot KUKA"),
    html.Hr(),

    dbc.Row([
        dbc.Col([
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
            html.Div(id="output-upload")
        ], md=3),

        dbc.Col(
            dcc.Loading(
                id="loading-graphs",
                type="circle",
                children=html.Div(id="graph-container")
            ),
            md=9
        )
    ])
], fluid=True)

# ----------------------------
# Callbacks
# ----------------------------

@app.callback(
    [Output("graph-container", "children"),
     Output("output-upload", "children")],
    [Input("upload-data", "contents")],
    [State("upload-data", "filename")]
)
def update_output(contents, filename):
    if contents is not None:
        data, error = parse_uploaded_contents(contents, filename)
        if error:
            return None, html.Div(error, style={"color": "red"})
        if data is None:
            return None, html.Div("❌ Impossible de parser le fichier", style={"color": "red"})

        # Graphes
        times = [d["Time"] for d in data["timeseries"]]
        tcp_speed = [d["TCP_Speed"] for d in data["timeseries"]]

        graphs = [
            dcc.Graph(
                figure=go.Figure(
                    data=[go.Scatter(x=times, y=tcp_speed, mode="lines", name="Vitesse TCP")]
                ).update_layout(title="Vitesse TCP en fonction du temps")
            )
        ]

        return graphs, html.Div(f"✅ Fichier {filename} chargé avec succès")

    return None, None

# ----------------------------
# Main
# ----------------------------

if __name__ == "__main__":
    app.run_server(debug=True)
