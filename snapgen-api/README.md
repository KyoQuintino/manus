# snapgen.ai API

API REST assíncrona para geração de imagens, vídeos a partir de texto e vídeos a partir de uma imagem de referência. O primeiro corte foi implementado em FastAPI e usa um provedor local determinístico para que o projeto possa ser executado e testado sem chaves externas.

## O que está implementado

| Recurso | Endpoint | Comportamento |
|---|---|---|
| Saúde da API | `GET /health` | Retorna versão e provedor ativo |
| Modelos disponíveis | `GET /v1/models` | Lista modalidades suportadas pelo provedor |
| Criar geração | `POST /v1/generations` | Retorna `202 Accepted` e inicia uma tarefa em segundo plano |
| Listar gerações | `GET /v1/generations` | Retorna tarefas paginadas |
| Consultar geração | `GET /v1/generations/{task_id}` | Retorna status e progresso |
| Cancelar geração | `POST /v1/generations/{task_id}/cancel` | Cancela tarefas ainda não finalizadas |
| Baixar ativo | `GET /v1/assets/{asset_id}` | Entrega o arquivo gerado |

> **Estados da tarefa:** `QUEUED`, `PROCESSING`, `COMPLETED`, `FAILED` e `CANCELED`.

## Execução local

```bash
cd snapgen-api
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # opcional; carregue as variáveis no shell ou via seu processo
uvicorn app.main:app --reload
```

A documentação interativa fica disponível em `http://localhost:8000/docs`.

O modo padrão é `SNAPGEN_PROVIDER=mock`. Ele cria um SVG para imagens e um MP4 curto para vídeos, permitindo testar o contrato ponta a ponta. Esses arquivos são apenas artefatos de desenvolvimento, não resultados de um modelo generativo.

## Exemplos de uso

### Texto para imagem

```bash
curl -X POST http://localhost:8000/v1/generations \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "TEXT_TO_IMAGE",
    "prompt": "uma cidade futurista ao amanhecer",
    "width": 1024,
    "height": 1024
  }'
```

### Texto para vídeo

```bash
curl -X POST http://localhost:8000/v1/generations \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "TEXT_TO_VIDEO",
    "prompt": "ondas suaves quebrando em uma praia cinematográfica",
    "duration_seconds": 5
  }'
```

### Imagem para vídeo

```bash
curl -X POST http://localhost:8000/v1/generations \
  -H 'Content-Type: application/json' \
  -d '{
    "mode": "IMAGE_TO_VIDEO",
    "prompt": "movimento de câmera lento para frente",
    "image_url": "https://example.com/referencia.png",
    "duration_seconds": 5
  }'
```

As três chamadas retornam uma tarefa. O cliente deve consultar o `task_id` até que o status seja `COMPLETED` ou `FAILED`. Para evitar polling, informe `webhook_url`; a API enviará o evento `generation.completed` ou `generation.failed` com o cabeçalho `X-Snapgen-Signature`.

### Autenticação

Defina `SNAPGEN_API_KEY` no ambiente. Quando configurada, todas as rotas `/v1` exigem:

```bash
-H 'X-API-Key: sua-chave'
```

O endpoint `/health` permanece público. Em produção, use um segredo forte gerenciado pelo ambiente de implantação e nunca o coloque no repositório.

## Contrato do provedor externo

Para conectar um provedor de IA real, defina `SNAPGEN_PROVIDER=http`, `SNAPGEN_PROVIDER_BASE_URL` e, se necessário, `SNAPGEN_PROVIDER_API_KEY`. O adaptador envia `POST {base_url}/generations` com o mesmo JSON recebido pela API. O provedor pode responder imediatamente com:

```json
{
  "id": "provider-job-id",
  "asset_url": "https://cdn.example.com/result.mp4"
}
```

Ou pode iniciar um job assíncrono e responder com `status_url`:

```json
{
  "id": "provider-job-id",
  "status_url": "https://provider.example.com/generations/provider-job-id"
}
```

Nesse segundo caso, o adaptador consulta a URL até o status ser `COMPLETED`, `SUCCEEDED` ou `SUCCESS` e espera `asset_url` ou `url`. Respostas e conteúdos recebidos do provedor são tratados como não confiáveis e validados antes do armazenamento.

## Arquitetura do MVP

A camada pública está em `app/main.py`, as regras de tarefa em `app/service.py`, os contratos em `app/schemas.py`, o armazenamento em `app/store.py` e os adaptadores em `app/providers/`. A implementação atual mantém o índice de tarefas em memória e os arquivos em disco local. Antes de escalar para múltiplos processos, substitua o índice por PostgreSQL/Redis e o disco por armazenamento de objetos, como S3 compatível. O worker também deve ser separado da API quando o volume de vídeo crescer.

## Próximas etapas de produção

O MVP ainda precisa de filas duráveis, cobrança/contabilização por créditos, limites por usuário, retenção e remoção automática de arquivos, verificação de SSRF para `image_url` e `webhook_url`, observabilidade, idempotência por chave de requisição e integração com um provedor de vídeo real. Essas decisões dependem do provedor escolhido, do modelo de cobrança e do ambiente de deploy.
