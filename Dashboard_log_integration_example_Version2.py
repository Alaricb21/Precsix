"""
Exemple d'intégration simple dans votre Dashboard (Dash) existant.

Ce petit exemple montre comment remplacer/reconnecter la lecture des fichiers .log
par le parseur générique ci-dessus. Il expose une fonction `parse_log_file_generic`
qui renvoie :
    - paths : dictionnaire {chemin: [valeurs]}
    - df : DataFrame si possible (déduit par IPOC), sinon None

Vous pouvez intégrer ceci dans Dashboard_En_Ligne.py en important `parse_log_file_generic`
et en l'utilisant dans parse_uploaded_contents(...) pour traiter les .log de façon plus générale.
"""
from kuka_log_parser import parse_log_text, build_dataframe_from_paths, _detect_ipoc_key
import base64

def parse_log_file_generic_from_contents(contents: str, filename: str):
    """
    contents : chaîne 'data:...;base64,xxxxx' provenant d'un Upload Dash
    filename : nom de fichier (pour l'extension)
    retourne (paths_dict, df_or_none, error_message_or_None)
    """
    try:
        content_type, content_string = contents.split(",", 1)
        decoded = base64.b64decode(content_string)
        text = decoded.decode("utf-8", errors="ignore")
    except Exception as e:
        return None, None, f"Erreur de décodage : {e}"

    paths = parse_log_text(text)
    if not paths:
        return None, None, "Aucune trame XML valide trouvée dans le .log."

    ipoc_key = _detect_ipoc_key(paths)
    df = build_dataframe_from_paths(paths, time_key=ipoc_key)
    return paths, df, None


# Exemple minimal d'utilisation :
if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python Dashboard_log_integration_example.py <fichier.log>")
        sys.exit(1)

    with open(sys.argv[1], "rb") as f:
        b = f.read()
    # Simuler le contenu base64 tel que Dash l'envoie
    import base64
    contents = "data:;base64," + base64.b64encode(b).decode("ascii")

    paths, df, err = parse_log_file_generic_from_contents(contents, sys.argv[1])
    if err:
        print("Erreur:", err)
    else:
        print("Nombre de chemins extraits :", len(paths))
        if df is not None:
            print("Aperçu DataFrame:\n", df.head())
        else:
            print("DataFrame non construit automatiquement.")