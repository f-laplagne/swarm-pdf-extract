#!/bin/bash
# ============================================================
# run_pipeline.sh — Pipeline complet d'extraction PDF
# ============================================================
#
# Usage: ./scripts/run_pipeline.sh [dossier_pdfs]
#
# Par défaut utilise le dossier samples/

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

INPUT_DIR="${1:-samples}"
OUTPUT_DIR="output"

echo "============================================================"
echo "🐝 Swarm PDF Extract — Pipeline Complet"
echo "============================================================"
echo "📁 Input:  $INPUT_DIR"
echo "📁 Output: $OUTPUT_DIR"
echo ""

# Vérifier les PDFs
PDF_COUNT=$(find "$INPUT_DIR" -name "*.pdf" -o -name "*.PDF" 2>/dev/null | wc -l)
if [ "$PDF_COUNT" -eq 0 ]; then
    echo "❌ Aucun PDF trouvé dans $INPUT_DIR"
    echo "   Placez vos PDFs dans le dossier $INPUT_DIR/ et relancez."
    exit 1
fi
echo "📄 $PDF_COUNT PDFs trouvés"
echo ""

# Créer les répertoires
mkdir -p "$OUTPUT_DIR/extractions"
mkdir -p "$OUTPUT_DIR/analyses"
mkdir -p "$OUTPUT_DIR/reports"

# Phase 1: Extraction batch (texte + tableaux)
echo "============================================================"
echo "📋 Phase 1: Extraction batch (texte + tableaux)"
echo "============================================================"
python tools/batch_runner.py "$INPUT_DIR" "$OUTPUT_DIR/extractions" > "$OUTPUT_DIR/extractions/_batch_result.json"
echo ""

# Phase 2: Lancer Claude Code pour classification + extraction + analyse
echo "============================================================"
echo "🧠 Phase 2-4: Agents IA (Classification → Extraction → Analyse)"
echo "============================================================"
echo ""
echo "Les données brutes sont extraites. Lancez maintenant Claude Code :"
echo ""
echo "  cd $PROJECT_DIR"
echo "  claude"
echo ""
echo "Puis dans Claude Code, tapez :"
echo "  Lis CLAUDE.md et exécute les phases 2 à 5 sur les données"
echo "  extraites dans output/extractions/"
echo ""
echo "============================================================"
echo "✅ Phase 1 terminée — données brutes prêtes dans $OUTPUT_DIR/extractions/"
echo "============================================================"
