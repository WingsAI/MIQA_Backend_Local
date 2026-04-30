#!/bin/bash
# deploy-railway.sh — Script para facilitar deploy no Railway

set -e

echo "🚀 MIQA Backend — Deploy para Railway"
echo "======================================"
echo ""

# Verifica se railway CLI está instalado
if ! command -v railway &> /dev/null; then
    echo "❌ Railway CLI não encontrado."
    echo "   Instale com: npm install -g @railway/cli"
    echo "   Ou acesse: https://railway.app"
    exit 1
fi

# Login (se necessário)
echo "🔐 Verificando login no Railway..."
railway whoami || railway login

echo ""
echo "📦 Preparando deploy..."

# Commita mudanças pendentes
if [ -n "$(git status --porcelain)" ]; then
    echo "📝 Commitando mudanças pendentes..."
    git add -A
    git commit -m "deploy: preparando para Railway $(date +%Y-%m-%d-%H:%M)"
    git push origin main
fi

# Linka com projeto Railway (se ainda não linkado)
echo ""
echo "🔗 Linkando com projeto Railway..."
railway link || true

# Deploy
echo ""
echo "🚀 Iniciando deploy..."
railway up

echo ""
echo "✅ Deploy iniciado!"
echo ""
echo "📊 Verifique o status em: https://railway.app/dashboard"
echo "🌐 URL da API será gerada automaticamente"
echo ""
echo "⚠️  IMPORTANTE: Lembre-se de fazer upload dos modelos .pkl"
echo "   Veja RAILWAY_DEPLOY.md para instruções detalhadas"

# Health check (aguarda alguns segundos)
echo ""
echo "⏳ Aguardando 10 segundos para health check..."
sleep 10

# Tenta fazer health check (pode falhar se ainda não propagou)
API_URL=$(railway variables get RAILWAY_STATIC_URL 2>/dev/null || echo "")
if [ -n "$API_URL" ]; then
    echo ""
    echo "🏥 Health Check:"
    curl -s "$API_URL/health" || echo "   (ainda iniciando...)"
fi

echo ""
echo "✨ Deploy completo!"