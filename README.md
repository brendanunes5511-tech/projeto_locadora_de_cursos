# Locadora de Cursos

MVP local de uma plataforma de cursos. O aluno consulta o catálogo, inscreve-se em cursos gratuitos, compra cursos e quizzes com pagamento simulado, responde quizzes e envia mensagens ao atendimento. O administrador gerencia cadastros, vendas e respostas.

Nenhum valor real é cobrado e não há integração com serviços de pagamento.

## Tecnologias

- Python
- Flask (API REST)
- SQLite
- Streamlit
- Requests (o frontend chama a API)

## Estrutura

```
locadora_cursos/
├── backend/
│   ├── app.py         # rotas da API
│   ├── database.py    # tabelas, relações e dados de demonstração
│   └── banco.db       # criado na primeira execução
├── frontend/
│   └── interface.py   # interface Streamlit
├── requirements.txt
└── README.md
```

O banco cria as tabelas `usuarios`, `cursos`, `carrinho`, `compras`, `itens_compra`, `inscricoes`, `quizzes`, `perguntas`, `alternativas`, `resultados_quiz` e `mensagens`, com chaves estrangeiras. Senhas ficam apenas como hash. As consultas usam parâmetros.

Cursos e quizzes de demonstração são inseridos somente se as tabelas estiverem vazias. Compras não são inventadas.

## Instalação

No diretório do projeto:

```bash
python -m pip install -r requirements.txt
```

## Execução

Use dois terminais.

Terminal 1, backend:

```bash
python backend/app.py
```

A API fica em http://127.0.0.1:5000.

Terminal 2, frontend:

```bash
streamlit run frontend/interface.py
```

Abra o endereço mostrado pelo Streamlit, em geral http://localhost:8501.

## Acesso

- Crie uma conta pela tela Entrar, ou use um usuário já cadastrado.
- Administrador de demonstração: `admin@locadora.local` / `admin123`.

Troque essa senha se o computador for compartilhado. Ela existe só para abrir o painel local.
