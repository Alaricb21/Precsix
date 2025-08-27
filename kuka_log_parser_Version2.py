"""
kuka_log_parser.py

Module simple pour extraire des trames XML contenues dans des logs RSI (KUKA)
et exposer un dictionnaire {chemin_xml: [valeurs]} ainsi qu'une fonction
de construction de DataFrame si une clé IPOC (temps) est détectée.
"""
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from typing import DefaultDict, Dict, List, Optional
import pandas as pd
import math

_XML_QUOTED_PATTERN = re.compile(r'"(<.*?>.*)"')

def _is_number(s: str) -> bool:
    try:
        float(s)
        return True
    except Exception:
        return False

def _extract_paths_from_element(
    element: ET.Element,
    out: DefaultDict[str, List[float]],
    path: str = ""
) -> None:
    current_path = f"{path}/{element.tag}" if path else element.tag

    # Texte de l'élément
    if element.text:
        txt = element.text.strip()
        if txt != "" and _is_number(txt):
            out[current_path].append(float(txt))

    # Attributs
    for attr, val in element.attrib.items():
        if val is None:
            continue
        val_str = val.strip()
        if val_str != "" and _is_number(val_str):
            key = f"{current_path}@{attr}"
            out[key].append(float(val_str))

    # Enfants récursifs
    for child in element:
        _extract_paths_from_element(child, out, current_path)

def parse_log_text(log_text: str) -> DefaultDict[str, List[float]]:
    """
    Parse le texte complet d'un fichier .log RSI et retourne defaultdict(list)
    contenant toutes les valeurs numériques extraites par chemin.
    """
    out: DefaultDict[str, List[float]] = defaultdict(list)

    for line in log_text.splitlines():
        m = _XML_QUOTED_PATTERN.search(line)
        if not m:
            continue
        xml_str = m.group(1)
        xml_str = xml_str.replace('\\"', '"').replace('\\n', '')
        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError:
            continue
        _extract_paths_from_element(root, out)

    return out

def parse_log_file(path: str, encoding: str = "utf-8") -> DefaultDict[str, List[float]]:
    with open(path, "r", encoding=encoding, errors="ignore") as f:
        text = f.read()
    return parse_log_text(text)

def _detect_ipoc_key(paths: Dict[str, List[float]]) -> Optional[str]:
    lowered = {k.lower(): k for k in paths.keys()}
    for k in lowered:
        if "ipoc" in k:
            return lowered[k]
    return None

def build_dataframe_from_paths(
    paths: Dict[str, List[float]],
    time_key: Optional[str] = None,
    convert_ipoc_to_seconds: bool = True
) -> Optional[pd.DataFrame]:
    """
    Construit un DataFrame Pandas à partir du dictionnaire paths.
    Si time_key est None, tente de détecter IPOC automatiquement.
    Tronque les séries pour la longueur minimale commune.
    """
    if not paths:
        return None

    numeric_keys = [k for k, v in paths.items() if v and any((not math.isnan(x)) for x in v)]
    if not numeric_keys:
        return None

    if time_key is None:
        time_key = _detect_ipoc_key(paths)

    lengths = [len(paths[k]) for k in numeric_keys]
    min_len = min(lengths) if lengths else 0
    if min_len == 0:
        return None

    data = {}
    if time_key and time_key in paths:
        tvals = paths[time_key][:min_len]
        if convert_ipoc_to_seconds:
            avg = sum(abs(x) for x in tvals) / max(1, len(tvals))
            if avg > 1e6:
                tvals = [x / 1e6 for x in tvals]
            elif avg > 1e3:
                tvals = [x / 1e3 for x in tvals]
        data["Time"] = tvals

    for k in numeric_keys:
        if k == time_key:
            continue
        data[k] = paths[k][:min_len]

    df = pd.DataFrame(data)
    if "Time" not in df.columns:
        df.insert(0, "Time", list(range(len(df))))
    return df

def save_paths_to_json(paths: Dict[str, List[float]], dest_path: str) -> None:
    import json
    with open(dest_path, "w", encoding="utf-8") as f:
        json.dump(paths, f, indent=2, ensure_ascii=False)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python kuka_log_parser.py <fichier_log>")
        sys.exit(1)
    paths = parse_log_file(sys.argv[1])
    print(f"Chemins extraits: {len(paths)}")
    ipoc = _detect_ipoc_key(paths)
    print("IPOC key détectée :", ipoc)
    df = build_dataframe_from_paths(paths, time_key=ipoc)
    if df is not None:
        print("Aperçu DataFrame:")
        print(df.head())
    else:
        print("Impossible de construire un DataFrame (données manquantes).")