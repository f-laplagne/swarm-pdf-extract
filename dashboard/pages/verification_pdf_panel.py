"""Pure rendering functions for the verification PDF panel.

Extracted from 11_verification_pdf.py for testability.
No Streamlit or HTTP imports allowed here.
"""

from __future__ import annotations

# ── Confidence helpers ────────────────────────────────────────────────────────

def conf_tier(score) -> tuple[str, str]:
    if score is None or score == 0: return "absent",  "0%"
    if score < 0.5:                  return "faible",  f"{score:.0%}"
    if score < 0.7:                  return "moyen",   f"{score:.0%}"
    if score < 0.9:                  return "bon",     f"{score:.0%}"
    return                                  "parfait", f"{score:.0%}"


def conf_badge(score, cc: dict) -> str:
    tier, pct = conf_tier(score)
    fg, bg = cc[tier]
    return (
        f'<span style="background:{bg};color:{fg};border:1px solid {fg}55;'
        f'font-family:JetBrains Mono,monospace;font-size:9px;font-weight:600;'
        f'padding:1px 7px;border-radius:3px;white-space:nowrap">⬤ {pct}</span>'
    )


def val_cell(val, P: dict) -> str:
    if val is None:
        return f'<span style="color:{P["txt_dim"]};font-style:italic">—</span>'
    if isinstance(val, float):
        return (f'<span style="font-family:JetBrains Mono,monospace;'
                f'color:{P["txt_num"]}">{val:,.2f}</span>')
    return str(val)


# ── Main panel builder ────────────────────────────────────────────────────────

CONF_SEUIL_EDITABLE = 0.5  # Fields below this threshold are editable
FLOAT_FIELDS = {"prix_unitaire", "quantite", "prix_total"}

CONF_FIELDS_MAP = [
    ("type_matiere", "Matière"), ("unite", "Unité"), ("quantite", "Qté"),
    ("prix_unitaire", "PU"), ("prix_total", "Total"), ("date_depart", "D.dép"),
    ("date_arrivee", "D.arr"), ("lieu_depart", "Départ"), ("lieu_arrivee", "Arrivée"),
]


def build_extraction_panel(
    ext: dict | None,
    P: dict,
    cc: dict,
    ligne_ids: dict[int, int] | None = None,
) -> str:
    """Build the HTML for the extraction data panel.

    Args:
        ext: Parsed extraction JSON dict, or None if extraction not found.
        P: Color palette dict.
        cc: Confidence colors dict.
        ligne_ids: Optional {ligne_numero: db_ligne_id}. When provided, cells
                   with conf < CONF_SEUIL_EDITABLE get editable attributes.
                   If None or empty, all cells are read-only.

    Returns:
        HTML string for the right panel.
    """
    if ligne_ids is None:
        ligne_ids = {}

    if not ext:
        return (f"<p style='color:{P['txt_dim']};padding:40px;"
                f"font-family:Manrope,sans-serif'>Extraction introuvable.</p>")

    meta   = ext.get("metadonnees", {})
    fourn  = meta.get("fournisseur", {}) or {}
    client = meta.get("client", {}) or {}
    refs   = meta.get("references", {}) or {}
    lignes = ext.get("lignes", [])
    warns  = ext.get("warnings", [])
    champs = ext.get("champs_manquants", [])
    conf_g = ext.get("confiance_globale", 0)

    tier_g, pct_g = conf_tier(conf_g)
    fg_g, bg_g    = cc[tier_g]

    strat_labels = {
        "pdfplumber_tables":       "PDF natif — tableaux",
        "auto_pdfplumber":         "PDF natif",
        "ocr_tesseract":           "OCR Tesseract",
        "auto_fallback_paddleocr": "OCR PaddleOCR",
    }

    def mrow(label, value):
        if not value: return ""
        return (
            f'<tr>'
            f'<td style="font-family:Manrope,sans-serif;font-size:10px;font-weight:600;'
            f'letter-spacing:.07em;text-transform:uppercase;color:{P["txt_s"]};'
            f'padding:5px 14px 5px 0;white-space:nowrap;vertical-align:top">{label}</td>'
            f'<td style="font-family:Manrope,sans-serif;font-size:12px;color:{P["txt_p"]};'
            f'padding:5px 0;line-height:1.5">{value}</td>'
            f'</tr>'
        )

    meta_card = f"""
<div style="background:{P['card_bg']};border:1px solid {P['border']};border-radius:6px;
            padding:16px 20px;margin-bottom:14px">
  <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px">
    <div>
      <div style="font-family:'DM Serif Display',serif;font-size:22px;
                  color:{P['txt_p']};letter-spacing:.01em">
        {meta.get('numero_document','—')}
      </div>
      <div style="font-family:Manrope,sans-serif;font-size:10px;color:{P['txt_s']};
                  letter-spacing:.1em;text-transform:uppercase;margin-top:2px">
        {meta.get('date_document','—')}
        &nbsp;·&nbsp; {strat_labels.get(ext.get('strategie_utilisee',''), ext.get('strategie_utilisee',''))}
      </div>
    </div>
    <div style="background:{bg_g};border:1px solid {fg_g}55;border-radius:5px;
                padding:8px 14px;text-align:center;flex-shrink:0;margin-left:16px">
      <div style="font-family:'JetBrains Mono',monospace;font-size:22px;
                  font-weight:700;color:{fg_g};line-height:1">{pct_g}</div>
      <div style="font-family:Manrope,sans-serif;font-size:8px;color:{fg_g};
                  letter-spacing:.1em;text-transform:uppercase;margin-top:3px;opacity:.7">confiance</div>
    </div>
  </div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:0 32px">
    <table style="border-collapse:collapse">
      {mrow("Fournisseur", fourn.get("nom"))}
      {mrow("TVA fourn.", fourn.get("tva_intra"))}
      {mrow("Client", client.get("nom"))}
      {mrow("Commande", refs.get("commande"))}
    </table>
    <table style="border-collapse:collapse">
      {mrow("HT",  f"{meta.get('montant_ht'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ht') else None)}
      {mrow("TTC", f"{meta.get('montant_ttc'):,.2f} {meta.get('devise','EUR')}" if meta.get('montant_ttc') else None)}
      {mrow("Paiement", meta.get("conditions_paiement"))}
      {mrow("Champs ∅", ", ".join(champs) if champs else None)}
    </table>
  </div>
</div>"""

    col_defs = [
        ("#","36px","center"), ("Matière / Pièce","auto","left"),
        ("Unité","52px","center"), ("Quantité","76px","right"),
        ("Prix unit.","80px","right"), ("Total €","80px","right"),
        ("Date dép.","88px","center"), ("Date arr.","88px","center"),
        ("Départ","110px","left"), ("Arrivée","110px","left"),
    ]

    th = (f"font-family:Manrope,sans-serif;font-size:9px;font-weight:700;"
          f"letter-spacing:.1em;text-transform:uppercase;color:{P['txt_m']};"
          f"padding:8px 10px;border-bottom:2px solid {P['border']};white-space:nowrap;")
    headers = "".join(
        f'<th style="{th}text-align:{a};width:{w}">{n}</th>'
        for n, w, a in col_defs
    )

    rows = ""
    for i, ligne in enumerate(lignes):
        conf       = ligne.get("confiance", {})
        bg_r       = P["row_even"] if i % 2 == 0 else P["row_odd"]
        pu, qt, pt = ligne.get("prix_unitaire"), ligne.get("quantite"), ligne.get("prix_total")
        total_c    = "#ff6b6b" if (pu and qt and pt and abs(round(pu*qt,2)-pt) > 0.02) else P["txt_p"]
        td         = (f'style="padding:7px 10px;border-bottom:1px solid {P["border_light"]};'
                      f'vertical-align:middle;background:{bg_r};')

        ligne_num = ligne.get("ligne_numero")
        db_id     = ligne_ids.get(ligne_num)  # None if not in DB

        def _cell(field: str, value, align: str, extra_style: str = "") -> str:
            """Render a data cell, editable if conf < threshold and db_id available."""
            score = conf.get(field)
            is_editable = (
                db_id is not None
                and score is not None
                and score < CONF_SEUIL_EDITABLE
            )
            display_val = ""
            if value is None:
                display_val = f'<span style="color:{P["txt_dim"]};font-style:italic">—</span>'
            elif isinstance(value, float):
                display_val = f'{value:,.4f}' if field in FLOAT_FIELDS else f'{value:,.2f}'
            else:
                display_val = str(value)

            if not is_editable:
                return (f'<td {td}text-align:{align};{extra_style}">'
                        f'{display_val}</td>')

            # Editable cell: span (display) + input (hidden)
            input_type = "number" if field in FLOAT_FIELDS else "text"
            input_step = ' step="0.0001"' if field in FLOAT_FIELDS else ""
            raw_val    = str(value) if value is not None else ""
            orig_escaped = raw_val.replace('"', '&quot;')
            return (
                f'<td class="cell-editable" {td}text-align:{align};{extra_style}"'
                f' data-ligne-id="{db_id}"'
                f' data-champ="{field}"'
                f' data-original="{orig_escaped}"'
                f' data-conf="{score}">'
                f'<span class="cell-display">{display_val}</span>'
                f'<input class="cell-input" type="{input_type}"{input_step}'
                f' value="{orig_escaped}" style="display:none">'
                f'</td>'
            )

        rows += f"""
<tr>
  <td {td}text-align:center;color:{P['txt_dim']};font-family:'JetBrains Mono',monospace;font-size:11px">{ligne_num or ''}</td>
  {_cell("type_matiere", ligne.get("type_matiere"), "left", f"color:{P['txt_p']};font-family:Manrope,sans-serif;font-size:12px")}
  {_cell("unite",        ligne.get("unite"),        "center", f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_s']}")}
  {_cell("quantite",     ligne.get("quantite"),     "right",  f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_p']}")}
  {_cell("prix_unitaire",ligne.get("prix_unitaire"),"right",  f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{P['txt_p']}")}
  {_cell("prix_total",   ligne.get("prix_total"),   "right",  f"font-family:'JetBrains Mono',monospace;font-size:11px;color:{total_c}")}
  {_cell("date_depart",  ligne.get("date_depart"),  "center", f"font-family:'JetBrains Mono',monospace;font-size:10px;color:{P['txt_dim']}")}
  {_cell("date_arrivee", ligne.get("date_arrivee"), "center", f"font-family:'JetBrains Mono',monospace;font-size:10px;color:{P['txt_dim']}")}
  {_cell("lieu_depart",  ligne.get("lieu_depart"),  "left",   f"color:{P['txt_s']};font-family:Manrope,sans-serif;font-size:11px")}
  {_cell("lieu_arrivee", ligne.get("lieu_arrivee"), "left",   f"color:{P['txt_s']};font-family:Manrope,sans-serif;font-size:11px")}
</tr>
<tr>
  <td colspan="10" style="padding:3px 10px 9px;background:{bg_r};border-bottom:1px solid {P['border_light']}">
    <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
      <span style="font-family:Manrope,sans-serif;font-size:9px;color:{P['txt_m']};
                   font-weight:600;letter-spacing:.07em;text-transform:uppercase;
                   margin-right:3px">conf.</span>
      {"".join(
          f'<span class="conf-badge-container" style="display:inline-flex;align-items:center;gap:3px"'
          f' data-ligne-id="{db_id or ""}" data-champ="{key}">'
          f'<span style="font-family:Manrope,sans-serif;font-size:9px;color:{P["txt_m"]}">{label}</span>'
          f'{conf_badge(conf.get(key), cc)}</span>'
          for key, label in CONF_FIELDS_MAP
      )}
    </div>
  </td>
</tr>"""

    table = (
        f'<div style="overflow-x:auto;border:1px solid {P["border"]};'
        f'border-radius:6px;margin-bottom:14px">'
        f'<table style="border-collapse:collapse;width:100%;min-width:880px">'
        f'<thead><tr style="background:{P["hdr_bg"]}">{headers}</tr></thead>'
        f'<tbody>{rows}</tbody>'
        f'</table></div>'
    )

    alerts_html = ""
    if warns or champs:
        champ_li = "".join(
            f'<li style="font-family:JetBrains Mono,monospace;font-size:10px;'
            f'color:#ff4d4d;margin-bottom:3px">{c}</li>' for c in champs)
        warn_li = "".join(
            f'<li style="font-family:Manrope,sans-serif;font-size:11px;color:#ff8c42;'
            f'margin-bottom:5px;line-height:1.5">{w}</li>' for w in warns)
        ul_champs = f'<ul style="margin:0;padding-left:14px;margin-bottom:8px">{champ_li}</ul>' if champs else ""
        ul_warns  = f'<ul style="margin:0;padding-left:14px">{warn_li}</ul>' if warns else ""
        alerts_html = (
            f'<div style="border:1px solid {P["alert_border"]};border-left:3px solid {P["alert_border"]};'
            f'border-radius:4px;padding:12px 16px;margin-bottom:12px;background:{P["alert_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["alert_border"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:8px">'
            f'⚠ Alertes & Champs manquants</div>'
            f'{ul_champs}{ul_warns}</div>'
        )

    notes = ext.get("extraction_notes", "")
    notes_html = ""
    if notes:
        notes_html = (
            f'<div style="border:1px solid {P["notes_border"]};border-radius:4px;'
            f'padding:12px 16px;background:{P["notes_bg"]}">'
            f'<div style="font-family:Manrope,sans-serif;font-size:9px;font-weight:700;'
            f'color:{P["txt_m"]};letter-spacing:.12em;text-transform:uppercase;margin-bottom:7px">'
            f'Notes d\'extraction</div>'
            f'<p style="font-family:Manrope,sans-serif;font-size:11px;color:{P["txt_s"]};'
            f'line-height:1.7;margin:0">{notes}</p>'
            f'</div>'
        )

    return meta_card + table + alerts_html + notes_html
