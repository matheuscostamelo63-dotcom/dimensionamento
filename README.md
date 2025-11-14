# 🔧 Sistema de Dimensionamento de Bombas Centrífugas

API REST para cálculo hidráulico completo de sistemas de bombeamento.

## 🚀 Tecnologias

- **Backend**: Flask (Python)
- **Cálculos**: NumPy
- **Gráficos**: Matplotlib
- **PDFs**: Pillow
- **Storage**: Supabase
- **Deploy**: Render

## 📊 Recursos

- ✅ Cálculo de Hmt (Altura Manométrica Total)
- ✅ Análise de NPSH (cavitação)
- ✅ Validação de velocidades
- ✅ Geração de gráficos (curva do sistema)
- ✅ Relatório PDF profissional
- ✅ Base de dados com 17 materiais

## 🔗 Endpoints

- `GET /api/materiais` - Lista materiais disponíveis
- `POST /api/calcular` - Executa cálculo completo

## 🛠️ Deploy

render