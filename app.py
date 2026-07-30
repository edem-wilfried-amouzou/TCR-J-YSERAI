"""
J'Y SERAI - Générateur d'affiche personnalisée pour Togo Code Run #TCR
------------------------------------------------------------------------
Un participant uploade sa photo, saisit son nom et son titre, et télécharge
une affiche "J'y serai" personnalisée générée à partir du template media/fond.png.

Lancer avec :  python main.py
Puis ouvrir :  http://127.0.0.1:5000
"""

import io
import os
import unicodedata

from flask import Flask, render_template, request, send_file, flash, redirect, url_for
from PIL import Image, ImageDraw, ImageFont, ImageOps

app = Flask(__name__)
app.secret_key = "jyserai-tcr-secret"  # utilisé seulement pour les flash messages

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_IMG = os.path.join(BASE_DIR, "media", "fond.png")
FONT_FILE = os.path.join(BASE_DIR, "fonts", "Inter.ttf")  # police variable (Regular -> Black)
FONT_BOLD = "Bold"      # instance nommée utilisée pour le nom
FONT_MEDIUM = "Medium"  # instance nommée utilisée pour le titre

# --- Coordonnées mesurées directement sur media/fond.png (1142x1255 px) ---
# Cercle où va la photo de la personne
CIRCLE_CX, CIRCLE_CY, CIRCLE_R = 572, 586, 172

# Boîte noire "Nom Prenom"
NAME_BOX = (371, 777, 776, 853)   # (x1, y1, x2, y2)

# Boîte blanche à bordure orange "Titre"
TITLE_BOX = (371, 856, 776, 905)  # (x1, y1, x2, y2)

ORANGE = (255, 92, 1)
WHITE = (255, 255, 255)

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def safe_filename_part(text: str) -> str:
    """Nettoie une chaine pour l'utiliser dans le nom du fichier téléchargé."""
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = nfkd.encode("ascii", "ignore").decode("ascii")
    ascii_text = "".join(c if c.isalnum() else "_" for c in ascii_text)
    return ascii_text.strip("_") or "participant"


def load_font(size, variation):
    """Charge Inter.ttf à la taille demandée et sélectionne la graisse (variation) voulue."""
    font = ImageFont.truetype(FONT_FILE, size)
    font.set_variation_by_name(variation)
    return font


def fit_font(draw, text, variation, max_width, max_height, start_size=60, min_size=14):
    """Renvoie la plus grande police (jusqu'à start_size) qui tient dans la boîte donnée."""
    size = start_size
    while size > min_size:
        font = load_font(size, variation)
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if w <= max_width and h <= max_height:
            return font, w, h
        size -= 2
    font = load_font(min_size, variation)
    bbox = draw.textbbox((0, 0), text, font=font)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1]


def draw_centered_text(draw, box, text, variation, color, start_size, padding=20):
    x1, y1, x2, y2 = box
    max_w = (x2 - x1) - padding * 2
    max_h = (y2 - y1) - padding
    font, w, h = fit_font(draw, text, variation, max_w, max_h, start_size=start_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    cx = x1 + (x2 - x1) / 2
    cy = y1 + (y2 - y1) / 2
    tx = cx - w / 2 - bbox[0]
    ty = cy - h / 2 - bbox[1]
    draw.text((tx, ty), text, font=font, fill=color)


def generate_poster(photo_stream, nom: str, titre: str) -> Image.Image:
    base = Image.open(TEMPLATE_IMG).convert("RGBA")

    # --- 1. Traiter la photo uploadée : recadrage "cover" + redimensionnement pour remplir le cercle ---
    photo = Image.open(photo_stream)
    photo = ImageOps.exif_transpose(photo)  # corrige l'orientation (photos prises au téléphone)
    photo = photo.convert("RGB")

    diameter = CIRCLE_R * 2
    # ImageOps.fit recadre en mode "cover" (comme background-size: cover en CSS)
    # centering=(0.5, 0.35) cadre un peu plus haut pour bien garder les visages dans le cercle
    photo_fit = ImageOps.fit(photo, (diameter, diameter), method=Image.LANCZOS, centering=(0.5, 0.35))

    # Masque circulaire (supersamplé pour un bord bien lisse, sans crénelage)
    scale = 4
    mask_big = Image.new("L", (diameter * scale, diameter * scale), 0)
    ImageDraw.Draw(mask_big).ellipse((0, 0, diameter * scale, diameter * scale), fill=255)
    mask = mask_big.resize((diameter, diameter), Image.LANCZOS)

    photo_rgba = photo_fit.convert("RGBA")
    photo_rgba.putalpha(mask)

    # Petit cerclage orange autour de la photo pour rester dans la charte TCR
    ring_pad = 6
    ring_size = diameter + ring_pad * 2
    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse((0, 0, ring_size, ring_size), fill=ORANGE + (255,))
    ring.paste(photo_rgba, (ring_pad, ring_pad), photo_rgba)

    top_left = (CIRCLE_CX - CIRCLE_R - ring_pad, CIRCLE_CY - CIRCLE_R - ring_pad)
    base.alpha_composite(ring, top_left)

    # --- 2. Nom (texte blanc, dans la boîte noire) ---
    draw = ImageDraw.Draw(base)
    nom_affiche = nom.strip() or "Participant"
    draw_centered_text(draw, NAME_BOX, nom_affiche, FONT_BOLD, WHITE, start_size=48)

    # --- 3. Titre (texte orange, dans la boîte blanche) ---
    titre_affiche = titre.strip() or "Participant TCR"
    draw_centered_text(draw, TITLE_BOX, titre_affiche, FONT_MEDIUM, ORANGE, start_size=28)
    # (FONT_BOLD / FONT_MEDIUM sont maintenant des noms d'instance de la police variable Inter.ttf)

    return base.convert("RGB")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/generate", methods=["POST"])
def generate():
    photo = request.files.get("photo")
    nom = request.form.get("nom", "").strip()
    titre = request.form.get("titre", "").strip()

    if not photo:
        flash("Merci d'ajouter une photo.")
        return redirect(url_for("index"))

    if not allowed_file(photo.filename):
        flash("Format d'image non supporté (utilise JPG, PNG ou WEBP).")
        return redirect(url_for("index"))

    if not nom:
        flash("Merci d'indiquer ton nom.")
        return redirect(url_for("index"))

    try:
        poster = generate_poster(photo.stream, nom, titre)
    except Exception as exc:  # image corrompue, format inattendu, etc.
        flash(f"Impossible de générer l'affiche : {exc}")
        return redirect(url_for("index"))

    buffer = io.BytesIO()
    poster.save(buffer, format="PNG", optimize=True)
    buffer.seek(0)

    filename = f"jy_serai_{safe_filename_part(nom)}.png"
    return send_file(buffer, mimetype="image/png", as_attachment=True, download_name=filename)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=8000)
