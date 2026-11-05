import os
import sqlite3

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "banco.db")

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    senha_hash TEXT NOT NULL,
    admin INTEGER NOT NULL DEFAULT 0,
    token TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS cursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    imagem TEXT,
    preco REAL NOT NULL DEFAULT 0,
    modalidade TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS quizzes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    preco REAL NOT NULL DEFAULT 0,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS perguntas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    enunciado TEXT NOT NULL,
    ordem INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS alternativas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pergunta_id INTEGER NOT NULL REFERENCES perguntas(id) ON DELETE CASCADE,
    texto TEXT NOT NULL,
    correta INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS carrinho (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    curso_id INTEGER REFERENCES cursos(id) ON DELETE CASCADE,
    quiz_id INTEGER REFERENCES quizzes(id) ON DELETE CASCADE,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    CHECK ((curso_id IS NULL) + (quiz_id IS NULL) = 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_carrinho_curso
    ON carrinho(usuario_id, curso_id) WHERE curso_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_carrinho_quiz
    ON carrinho(usuario_id, quiz_id) WHERE quiz_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS compras (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    total REAL NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS itens_compra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    compra_id INTEGER NOT NULL REFERENCES compras(id) ON DELETE CASCADE,
    curso_id INTEGER REFERENCES cursos(id) ON DELETE RESTRICT,
    quiz_id INTEGER REFERENCES quizzes(id) ON DELETE RESTRICT,
    nome TEXT NOT NULL,
    preco REAL NOT NULL,
    CHECK ((curso_id IS NULL) + (quiz_id IS NULL) = 1)
);

CREATE TABLE IF NOT EXISTS inscricoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    curso_id INTEGER NOT NULL REFERENCES cursos(id) ON DELETE RESTRICT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    UNIQUE (usuario_id, curso_id)
);

CREATE TABLE IF NOT EXISTS resultados_quiz (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    quiz_id INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE RESTRICT,
    pontuacao INTEGER NOT NULL,
    total INTEGER NOT NULL,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS mensagens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    texto TEXT NOT NULL,
    resposta TEXT,
    respondido_em TEXT,
    criado_em TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
"""

CURSOS_DEMO = [
    ("Introdução ao Python", "Primeiros passos: variáveis, condições e repetição.", "Programação", 0, "Online"),
    ("Planilhas com Excel", "Fórmulas, tabelas e gráficos para o dia a dia.", "Produtividade", 0, "Online"),
    ("API com Flask", "Como criar uma API REST simples com Flask e SQLite.", "Programação", 99.9, "Online"),
    ("Comunicação escrita", "Textos claros para e-mail, relatórios e atendimento.", "Carreira", 69.9, "Online"),
    ("Gestão financeira pessoal", "Orçamento, reserva de emergência e controle de gastos.", "Finanças", 119.9, "Híbrido"),
    ("Atendimento ao cliente", "Escuta, postura e resolução de problemas.", "Negócios", 149.9, "Presencial"),
]

QUIZZES_DEMO = [
    {
        "nome": "Python básico",
        "descricao": "Três perguntas rápidas para revisar a sintaxe inicial.",
        "categoria": "Programação",
        "preco": 0,
        "perguntas": [
            ("Qual função imprime texto na tela no Python 3?", [("print()", 1), ("echo()", 0), ("console.log()", 0)]),
            ("Qual tipo representa um texto?", [("int", 0), ("str", 1), ("bool", 0)]),
            ("Como começa um comentário de uma linha?", [("//", 0), ("#", 1), ("<!--", 0)]),
        ],
    },
    {
        "nome": "Lógica de programação",
        "descricao": "Conceitos de algoritmo, condição e valores booleanos.",
        "categoria": "Programação",
        "preco": 25,
        "perguntas": [
            ("O que é um algoritmo?", [("Uma sequência finita de passos", 1), ("Um tipo de computador", 0), ("Um erro de programa", 0)]),
            ("Para que serve a condição no SE/SENÃO?", [("Escolher um caminho", 1), ("Repetir para sempre", 0), ("Apagar variáveis", 0)]),
            ("Qual valor é booleano?", [('Texto "abc"', 0), ("10", 0), ("True", 1)]),
        ],
    },
    {
        "nome": "Atendimento ao cliente",
        "descricao": "Situações curtas de atendimento presencial e digital.",
        "categoria": "Negócios",
        "preco": 20,
        "perguntas": [
            ("Qual é a primeira atitude no atendimento?", [("Ouvir o cliente", 1), ("Interromper para ganhar tempo", 0), ("Encerrar a conversa", 0)]),
            ("Se você não souber a resposta, o indicado é:", [("Inventar uma solução", 0), ("Dizer que vai verificar e retornar", 1), ("Culpar outro setor", 0)]),
            ("Uma mensagem clara deve:", [("Ser objetiva e educada", 1), ("Usar o máximo de jargão", 0), ("Evitar dizer o próximo passo", 0)]),
        ],
    },
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _seed(conn):
    if conn.execute("SELECT 1 FROM usuarios WHERE admin = 1").fetchone() is None:
        conn.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, admin) VALUES (?, ?, ?, 1)",
            ("Administrador", "admin@locadora.local", generate_password_hash("admin123")),
        )
    if conn.execute("SELECT COUNT(*) FROM cursos").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO cursos (nome, descricao, categoria, preco, modalidade) VALUES (?, ?, ?, ?, ?)",
            CURSOS_DEMO,
        )
    if conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0] == 0:
        for quiz in QUIZZES_DEMO:
            cur = conn.execute(
                "INSERT INTO quizzes (nome, descricao, categoria, preco) VALUES (?, ?, ?, ?)",
                (quiz["nome"], quiz["descricao"], quiz["categoria"], quiz["preco"]),
            )
            for ordem, (enunciado, alternativas) in enumerate(quiz["perguntas"]):
                pergunta = conn.execute(
                    "INSERT INTO perguntas (quiz_id, enunciado, ordem) VALUES (?, ?, ?)",
                    (cur.lastrowid, enunciado, ordem),
                )
                conn.executemany(
                    "INSERT INTO alternativas (pergunta_id, texto, correta) VALUES (?, ?, ?)",
                    [(pergunta.lastrowid, texto, correta) for texto, correta in alternativas],
                )


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    _seed(conn)
    conn.commit()
    conn.close()
