"""Build HTML de acompanhamento de experimentos MIQA.

Dashboard interativo que mostra todos os experimentos de modelos lightweight.
"""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent
EXP_DIR = ROOT / "ml_models" / "checkpoints"
OUT = ROOT.parent / "apresentacao_executivo" / "miqa-experiments.html"


def collect_experiments() -> list[dict]:
    """Coleta todos os experimentos do diretório de checkpoints."""
    experiments = []
    
    if not EXP_DIR.exists():
        return experiments
    
    for modality_dir in EXP_DIR.iterdir():
        if not modality_dir.is_dir():
            continue
        modality = modality_dir.name
        
        for body_part_dir in modality_dir.iterdir():
            if not body_part_dir.is_dir():
                continue
            body_part = body_part_dir.name
            
            # Procura metadados
            for meta_file in body_part_dir.glob("*_metadata.json"):
                model_type = meta_file.stem.replace("_metadata", "")
                meta = json.loads(meta_file.read_text())
                
                experiments.append({
                    "modality": modality,
                    "body_part": body_part,
                    "model_name": model_type,
                    "val_mae": meta.get("val_mae", "N/A"),
                    "val_r2": meta.get("val_r2", "N/A"),
                    "train_mae": meta.get("train_mae", "N/A"),
                    "train_r2": meta.get("train_r2", "N/A"),
                    "n_samples": meta.get("n_samples", "N/A"),
                    "n_features": meta.get("n_features", "N/A"),
                    "model_type": meta.get("model_type", "N/A"),
                })
    
    return experiments


def generate_html(experiments: list[dict]) -> str:
    """Gera HTML do dashboard de experimentos."""
    
    # Contagens
    n_mods = len(set(e["modality"] for e in experiments))
    n_contexts = len(set(f"{e['modality']}/{e['body_part']}" for e in experiments))
    n_models = len(experiments)
    
    # Cards de experimentos
    exp_cards = []
    for exp in experiments:
        mod = exp["modality"].upper()
        bp = exp["body_part"]
        name = exp["model_name"]
        
        val_mae = exp.get("val_mae", "N/A")
        val_r2 = exp.get("val_r2", "N/A")
        n_samples = exp.get("n_samples", "N/A")
        n_features = exp.get("n_features", "N/A")
        model_type = exp.get("model_type", "N/A")
        
        # Formata valores
        val_mae_str = f"{val_mae:.2f}" if isinstance(val_mae, (int, float)) else str(val_mae)
        val_r2_str = f"{val_r2:.3f}" if isinstance(val_r2, (int, float)) else str(val_r2)
        
        card = f"""
        <div class="exp-card" data-modality="{exp['modality']}" data-body-part="{bp}">
            <div class="exp-header">
                <span class="modality-badge mod-{exp['modality']}">{mod}</span>
                <span class="body-part">{bp}</span>
                <span class="model-name">{name}</span>
            </div>
            <div class="exp-metrics">
                <div class="metric">
                    <span class="metric-label">Val MAE</span>
                    <span class="metric-value"{' style="color:var(--success)"' if isinstance(val_mae, (int, float)) and val_mae < 10 else ''}>{val_mae_str}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Val R²</span>
                    <span class="metric-value">{val_r2_str}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Amostras</span>
                    <span class="metric-value">{n_samples}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Features</span>
                    <span class="metric-value">{n_features}</span>
                </div>
            </div>
            <div class="exp-details">
                <div class="detail-row">
                    <span class="detail-label">Tipo:</span>
                    <span class="detail-value">{model_type}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Modo:</span>
                    <span class="detail-value">CPU Lightweight</span>
                </div>
            </div>
        </div>"""
        exp_cards.append(card)
    
    exp_cards_html = "\n".join(exp_cards) if exp_cards else "<p class='no-data'>Nenhum experimento encontrado. Execute o treinamento primeiro.</p>"
    
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MIQA — Acompanhamento de Experimentos</title>
<link href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{
  --navy: #0a1628;
  --navy-mid: #1a2f52;
  --gold: #b8972a;
  --gold-light: #d4b04a;
  --cream: #faf8f4;
  --white: #ffffff;
  --gray-100: #f4f2ee;
  --gray-200: #e8e4dc;
  --gray-400: #9a9488;
  --gray-600: #5a5650;
  --text: #1a1814;
  --success: #1a5c2e;
  --danger: #8b1a1a;
  --warn: #b8972a;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
  background: var(--cream);
  font-family: 'Source Sans 3', sans-serif;
  color: var(--text);
  line-height: 1.6;
}}
.container {{
  max-width: 1400px;
  margin: 0 auto;
  padding: 40px 20px;
}}

/* Header */
.header {{
  background: var(--navy);
  color: var(--white);
  padding: 40px;
  border-radius: 8px;
  margin-bottom: 40px;
}}
.header h1 {{
  font-size: 36px;
  font-weight: 700;
  margin-bottom: 8px;
}}
.header h1 span {{ color: var(--gold); }}
.header p {{
  color: var(--gray-400);
  font-size: 16px;
}}

/* Stats Grid */
.stats-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 40px;
}}
.stat-card {{
  background: var(--white);
  border-left: 4px solid var(--gold);
  padding: 24px;
  border-radius: 4px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}}
.stat-card .number {{
  font-size: 36px;
  font-weight: 700;
  color: var(--navy);
  line-height: 1;
}}
.stat-card .label {{
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 1.5px;
  color: var(--gray-600);
  margin-top: 8px;
}}

/* Filters */
.filters {{
  display: flex;
  gap: 12px;
  margin-bottom: 32px;
  flex-wrap: wrap;
}}
.filter-btn {{
  padding: 8px 16px;
  border: 2px solid var(--gray-200);
  background: var(--white);
  color: var(--gray-600);
  border-radius: 4px;
  cursor: pointer;
  font-family: inherit;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.2s;
}}
.filter-btn:hover, .filter-btn.active {{
  border-color: var(--gold);
  color: var(--gold);
  background: var(--cream);
}}

/* Experiment Cards */
.exp-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
  gap: 24px;
}}
.exp-card {{
  background: var(--white);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px rgba(0,0,0,0.08);
  transition: transform 0.2s, box-shadow 0.2s;
}}
.exp-card:hover {{
  transform: translateY(-2px);
  box-shadow: 0 8px 24px rgba(0,0,0,0.12);
}}
.exp-header {{
  background: var(--navy);
  color: var(--white);
  padding: 16px 20px;
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}}
.modality-badge {{
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1px;
  text-transform: uppercase;
  padding: 4px 10px;
  border-radius: 3px;
}}
.mod-rx {{ background: var(--danger); }}
.mod-us {{ background: var(--warn); }}
.mod-ct {{ background: var(--success); }}
.mod-mri {{ background: var(--navy-mid); border: 1px solid var(--gold); }}
.body-part {{
  font-size: 14px;
  color: var(--gray-400);
  text-transform: capitalize;
}}
.model-name {{
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: var(--gold-light);
  margin-left: auto;
}}
.exp-metrics {{
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  padding: 20px;
  gap: 16px;
  border-bottom: 1px solid var(--gray-100);
}}
.metric {{
  text-align: center;
}}
.metric-label {{
  display: block;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--gray-400);
  margin-bottom: 4px;
}}
.metric-value {{
  display: block;
  font-size: 20px;
  font-weight: 700;
  color: var(--navy);
}}
.exp-details {{
  padding: 16px 20px;
  background: var(--gray-100);
}}
.detail-row {{
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
  border-bottom: 1px solid var(--gray-200);
  font-size: 13px;
}}
.detail-row:last-child {{ border-bottom: none; }}
.detail-label {{ color: var(--gray-600); }}
.detail-value {{ color: var(--navy); font-weight: 600; }}

.no-data {{
  text-align: center;
  padding: 60px 20px;
  color: var(--gray-400);
  font-size: 18px;
  grid-column: 1 / -1;
}}

.info-box {{
  background: var(--white);
  border-left: 4px solid var(--success);
  padding: 20px;
  margin-bottom: 40px;
  border-radius: 4px;
}}
.info-box h3 {{
  color: var(--navy);
  margin-bottom: 8px;
}}
.info-box p {{
  color: var(--gray-600);
  font-size: 14px;
}}

.footer {{
  margin-top: 60px;
  padding-top: 30px;
  border-top: 2px solid var(--navy);
  text-align: center;
  color: var(--gray-400);
  font-size: 13px;
}}
@media (max-width: 768px) {{
  .exp-metrics {{ grid-template-columns: repeat(2, 1fr); }}
  .exp-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="container">

<div class="header">
  <h1>MIQA <span>·</span> Experimentos</h1>
  <p>Dashboard de acompanhamento de modelos ML lightweight para Quality Assessment</p>
</div>

<div class="info-box">
  <h3>🚀 CPU-Only Lightweight Models</h3>
  <p>Nenhuma rede neural. Modelos baseados em features físicas + Random Forest/XGBoost.
     Tempo de inferência < 50ms por imagem em CPU. Sem dependência de GPU.</p>
</div>

<div class="stats-grid">
  <div class="stat-card"><div class="number">{n_mods}</div><div class="label">Modalidades</div></div>
  <div class="stat-card"><div class="number">{n_contexts}</div><div class="label">Contextos Anatômicos</div></div>
  <div class="stat-card"><div class="number">{n_models}</div><div class="label">Modelos Treinados</div></div>
  <div class="stat-card"><div class="number">21</div><div class="label">Métricas Físicas</div></div>
</div>

<div class="filters">
  <button class="filter-btn active" onclick="filterExp('all')">Todos</button>
  <button class="filter-btn" onclick="filterExp('rx')">RX</button>
  <button class="filter-btn" onclick="filterExp('us')">US</button>
  <button class="filter-btn" onclick="filterExp('ct')">CT</button>
  <button class="filter-btn" onclick="filterExp('mri')">MRI</button>
</div>

<div class="exp-grid" id="expGrid">
  {exp_cards_html}
</div>

<div class="footer">
  MIQA Backend Local · WingsAI · {datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
  CPU-Only · Random Forest · XGBoost · Ridge Regression
</div>

<script>
function filterExp(modality) {{
  const cards = document.querySelectorAll('.exp-card');
  const buttons = document.querySelectorAll('.filter-btn');
  
  buttons.forEach(btn => btn.classList.remove('active'));
  event.target.classList.add('active');
  
  cards.forEach(card => {{
    if (modality === 'all' || card.dataset.modality === modality) {{
      card.style.display = '';
    }} else {{
      card.style.display = 'none';
    }}
  }});
}}
</script>

</body>
</html>"""
    
    return html


def main():
    experiments = collect_experiments()
    html = generate_html(experiments)
    OUT.write_text(html)
    print(f"OK — {OUT} ({len(html)/1024:.0f} KB)")
    print(f"  {len(experiments)} experimentos encontrados")


if __name__ == "__main__":
    main()
