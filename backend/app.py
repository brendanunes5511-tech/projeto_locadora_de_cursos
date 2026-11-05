import re
import secrets
import sqlite3
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from database import get_db, init_db

app = Flask(__name__)
app.json.ensure_ascii = False

MODALIDADES = ("Online", "Presencial", "Híbrido")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def erro(mensagem, codigo):
    return jsonify({"erro": mensagem}), codigo


def linhas(rows):
    return [dict(row) for row in rows]


def usuario_publico(row):
    return {
        "id": row["id"],
        "nome": row["nome"],
        "email": row["email"],
        "admin": bool(row["admin"]),
        "criado_em": row["criado_em"],
    }


def usuario_atual():
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    token = header[7:].strip()
    if not token:
        return None
    conn = get_db()
    row = conn.execute("SELECT * FROM usuarios WHERE token = ?", (token,)).fetchone()
    conn.close()
    return row


def requer_login(admin=False):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = usuario_atual()
            if user is None:
                return erro("Faça login para continuar.", 401)
            if admin and not user["admin"]:
                return erro("Acesso restrito ao administrador.", 403)
            g.usuario = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def texto(data, campo, minimo, maximo):
    valor = data.get(campo)
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    if not (minimo <= len(valor) <= maximo):
        return None
    return valor


def preco_valido(valor):
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    valor = round(float(valor), 2)
    if valor < 0 or valor > 100000:
        return None
    return valor


def validar_usuario(data):
    nome = texto(data, "nome", 2, 80)
    email = texto(data, "email", 5, 120)
    senha = data.get("senha")
    if not nome:
        return "Informe um nome entre 2 e 80 caracteres."
    if not email or not EMAIL_RE.match(email.lower()):
        return "Informe um e-mail válido."
    if not isinstance(senha, str) or not (6 <= len(senha) <= 64):
        return "A senha deve ter de 6 a 64 caracteres."
    return None


def validar_curso(data):
    nome = texto(data, "nome", 3, 120)
    descricao = texto(data, "descricao", 10, 2000)
    categoria = texto(data, "categoria", 2, 60)
    modalidade = data.get("modalidade")
    preco = preco_valido(data.get("preco"))
    imagem = data.get("imagem") or ""
    if isinstance(imagem, str):
        imagem = imagem.strip()
    else:
        imagem = ""
    if not nome or not descricao or not categoria:
        return None, "Preencha nome, descrição e categoria."
    if modalidade not in MODALIDADES:
        return None, "Modalidade inválida."
    if preco is None:
        return None, "Preço inválido."
    if imagem and not (imagem.startswith("http://") or imagem.startswith("https://")):
        return None, "A imagem deve ser um endereço http ou https."
    if len(imagem) > 500:
        return None, "Endereço da imagem muito longo."
    return {
        "nome": nome,
        "descricao": descricao,
        "categoria": categoria,
        "modalidade": modalidade,
        "preco": preco,
        "imagem": imagem or None,
    }, None


def validar_perguntas(perguntas):
    if not isinstance(perguntas, list) or not (1 <= len(perguntas) <= 20):
        return "Informe de 1 a 20 perguntas."
    limpas = []
    for pergunta in perguntas:
        if not isinstance(pergunta, dict):
            return "Pergunta inválida."
        enunciado = texto(pergunta, "enunciado", 5, 500)
        alternativas = pergunta.get("alternativas")
        if not enunciado:
            return "Cada enunciado precisa ter de 5 a 500 caracteres."
        if not isinstance(alternativas, list) or not (2 <= len(alternativas) <= 6):
            return "Cada pergunta precisa de 2 a 6 alternativas."
        opcoes = []
        corretas = 0
        for alternativa in alternativas:
            if not isinstance(alternativa, dict):
                return "Alternativa inválida."
            rotulo = texto(alternativa, "texto", 1, 300)
            if not rotulo:
                return "Preencha todas as alternativas."
            correta = bool(alternativa.get("correta"))
            corretas += int(correta)
            opcoes.append({"texto": rotulo, "correta": correta})
        if corretas != 1:
            return "Marque exatamente uma alternativa correta por pergunta."
        limpas.append({"enunciado": enunciado, "alternativas": opcoes})
    return limpas


def salvar_perguntas(conn, quiz_id, perguntas):
    for ordem, pergunta in enumerate(perguntas):
        cur = conn.execute(
            "INSERT INTO perguntas (quiz_id, enunciado, ordem) VALUES (?, ?, ?)",
            (quiz_id, pergunta["enunciado"], ordem),
        )
        conn.executemany(
            "INSERT INTO alternativas (pergunta_id, texto, correta) VALUES (?, ?, ?)",
            [(cur.lastrowid, alt["texto"], int(alt["correta"])) for alt in pergunta["alternativas"]],
        )


def ja_possui(conn, usuario_id, curso_id=None, quiz_id=None):
    if curso_id:
        curso = conn.execute("SELECT preco FROM cursos WHERE id = ?", (curso_id,)).fetchone()
        if curso is None:
            return False
        if curso["preco"] == 0:
            sql = "SELECT 1 FROM inscricoes WHERE usuario_id = ? AND curso_id = ?"
            return conn.execute(sql, (usuario_id, curso_id)).fetchone() is not None
        sql = """
            SELECT 1 FROM itens_compra ic
            JOIN compras c ON c.id = ic.compra_id
            WHERE c.usuario_id = ? AND ic.curso_id = ?
        """
        return conn.execute(sql, (usuario_id, curso_id)).fetchone() is not None
    sql = """
        SELECT 1 FROM itens_compra ic
        JOIN compras c ON c.id = ic.compra_id
        WHERE c.usuario_id = ? AND ic.quiz_id = ?
    """
    return conn.execute(sql, (usuario_id, quiz_id)).fetchone() is not None


def curso_json(row, usuario_id=None, conn=None):
    item = dict(row)
    item["gratuito"] = item["preco"] == 0
    if usuario_id and conn:
        item["possui"] = ja_possui(conn, usuario_id, curso_id=item["id"])
    return item


def quiz_json(row, usuario_id=None, conn=None):
    item = dict(row)
    item["gratuito"] = item["preco"] == 0
    if usuario_id and conn:
        item["possui"] = ja_possui(conn, usuario_id, quiz_id=item["id"])
    return item


@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/api/auth/registro")
def registro():
    data = request.get_json(silent=True) or {}
    mensagem = validar_usuario(data)
    if mensagem:
        return erro(mensagem, 400)
    token = secrets.token_urlsafe(32)
    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO usuarios (nome, email, senha_hash, token) VALUES (?, ?, ?, ?)",
            (data["nome"].strip(), data["email"].strip().lower(), generate_password_hash(data["senha"]), token),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return erro("Este e-mail já está cadastrado.", 409)
    row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"token": token, "usuario": usuario_publico(row)}), 201


@app.post("/api/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    senha = data.get("senha") or ""
    conn = get_db()
    row = conn.execute("SELECT * FROM usuarios WHERE email = ?", (email,)).fetchone()
    if row is None or not check_password_hash(row["senha_hash"], senha):
        conn.close()
        return erro("E-mail ou senha inválidos.", 401)
    token = secrets.token_urlsafe(32)
    conn.execute("UPDATE usuarios SET token = ? WHERE id = ?", (token, row["id"]))
    conn.commit()
    row = conn.execute("SELECT * FROM usuarios WHERE id = ?", (row["id"],)).fetchone()
    conn.close()
    return jsonify({"token": token, "usuario": usuario_publico(row)})


@app.post("/api/auth/logout")
@requer_login()
def logout():
    conn = get_db()
    conn.execute("UPDATE usuarios SET token = NULL WHERE id = ?", (g.usuario["id"],))
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.get("/api/auth/eu")
@requer_login()
def eu():
    return jsonify({"usuario": usuario_publico(g.usuario)})


@app.get("/api/cursos")
def listar_cursos():
    q = (request.args.get("q") or "").strip()
    categoria = (request.args.get("categoria") or "").strip()
    sql = "SELECT * FROM cursos WHERE 1 = 1"
    params = []
    if q:
        sql += " AND (nome LIKE ? OR categoria LIKE ?)"
        termo = f"%{q}%"
        params.extend([termo, termo])
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)
    sql += " ORDER BY nome"
    user = usuario_atual()
    conn = get_db()
    cursos = [curso_json(row, user["id"] if user else None, conn) for row in conn.execute(sql, params)]
    categorias = [row["categoria"] for row in conn.execute("SELECT DISTINCT categoria FROM cursos ORDER BY categoria")]
    conn.close()
    return jsonify({"cursos": cursos, "categorias": categorias})


@app.post("/api/cursos")
@requer_login(admin=True)
def criar_curso():
    campos, mensagem = validar_curso(request.get_json(silent=True) or {})
    if mensagem:
        return erro(mensagem, 400)
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO cursos (nome, descricao, categoria, imagem, preco, modalidade)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (campos["nome"], campos["descricao"], campos["categoria"], campos["imagem"], campos["preco"], campos["modalidade"]),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM cursos WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"curso": curso_json(row)}), 201


@app.put("/api/cursos/<int:curso_id>")
@requer_login(admin=True)
def editar_curso(curso_id):
    campos, mensagem = validar_curso(request.get_json(silent=True) or {})
    if mensagem:
        return erro(mensagem, 400)
    conn = get_db()
    if conn.execute("SELECT 1 FROM cursos WHERE id = ?", (curso_id,)).fetchone() is None:
        conn.close()
        return erro("Curso não encontrado.", 404)
    conn.execute(
        """UPDATE cursos
           SET nome = ?, descricao = ?, categoria = ?, imagem = ?, preco = ?, modalidade = ?
           WHERE id = ?""",
        (campos["nome"], campos["descricao"], campos["categoria"], campos["imagem"], campos["preco"], campos["modalidade"], curso_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM cursos WHERE id = ?", (curso_id,)).fetchone()
    conn.close()
    return jsonify({"curso": curso_json(row)})


@app.delete("/api/cursos/<int:curso_id>")
@requer_login(admin=True)
def excluir_curso(curso_id):
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM cursos WHERE id = ?", (curso_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return erro("Não é possível excluir: há inscrições ou vendas deste curso.", 409)
    conn.close()
    if cur.rowcount == 0:
        return erro("Curso não encontrado.", 404)
    return jsonify({"ok": True})


@app.get("/api/quizzes")
def listar_quizzes():
    q = (request.args.get("q") or "").strip()
    categoria = (request.args.get("categoria") or "").strip()
    sql = "SELECT * FROM quizzes WHERE 1 = 1"
    params = []
    if q:
        sql += " AND (nome LIKE ? OR categoria LIKE ?)"
        termo = f"%{q}%"
        params.extend([termo, termo])
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)
    sql += " ORDER BY nome"
    user = usuario_atual()
    conn = get_db()
    quizzes = [quiz_json(row, user["id"] if user else None, conn) for row in conn.execute(sql, params)]
    categorias = [row["categoria"] for row in conn.execute("SELECT DISTINCT categoria FROM quizzes ORDER BY categoria")]
    conn.close()
    return jsonify({"quizzes": quizzes, "categorias": categorias})


@app.get("/api/quizzes/<int:quiz_id>")
def detalhe_quiz(quiz_id):
    user = usuario_atual()
    conn = get_db()
    row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    if row is None:
        conn.close()
        return erro("Quiz não encontrado.", 404)
    quiz = quiz_json(row, user["id"] if user else None, conn)
    if quiz.get("possui"):
        perguntas = []
        for pergunta in conn.execute(
            "SELECT id, enunciado FROM perguntas WHERE quiz_id = ? ORDER BY ordem, id", (quiz_id,)
        ):
            alternativas = linhas(
                conn.execute(
                    "SELECT id, texto FROM alternativas WHERE pergunta_id = ? ORDER BY id",
                    (pergunta["id"],),
                )
            )
            perguntas.append({"id": pergunta["id"], "enunciado": pergunta["enunciado"], "alternativas": alternativas})
        quiz["perguntas"] = perguntas
    conn.close()
    return jsonify({"quiz": quiz})


@app.post("/api/quizzes")
@requer_login(admin=True)
def criar_quiz():
    data = request.get_json(silent=True) or {}
    nome = texto(data, "nome", 3, 120)
    descricao = texto(data, "descricao", 10, 2000)
    categoria = texto(data, "categoria", 2, 60)
    preco = preco_valido(data.get("preco"))
    perguntas = validar_perguntas(data.get("perguntas"))
    if not nome or not descricao or not categoria or preco is None:
        return erro("Preencha nome, descrição, categoria e preço.", 400)
    if isinstance(perguntas, str):
        return erro(perguntas, 400)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO quizzes (nome, descricao, categoria, preco) VALUES (?, ?, ?, ?)",
        (nome, descricao, categoria, preco),
    )
    salvar_perguntas(conn, cur.lastrowid, perguntas)
    conn.commit()
    row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return jsonify({"quiz": quiz_json(row)}), 201


@app.put("/api/quizzes/<int:quiz_id>")
@requer_login(admin=True)
def editar_quiz(quiz_id):
    data = request.get_json(silent=True) or {}
    nome = texto(data, "nome", 3, 120)
    descricao = texto(data, "descricao", 10, 2000)
    categoria = texto(data, "categoria", 2, 60)
    preco = preco_valido(data.get("preco"))
    if not nome or not descricao or not categoria or preco is None:
        return erro("Preencha nome, descrição, categoria e preço.", 400)
    conn = get_db()
    if conn.execute("SELECT 1 FROM quizzes WHERE id = ?", (quiz_id,)).fetchone() is None:
        conn.close()
        return erro("Quiz não encontrado.", 404)
    conn.execute(
        "UPDATE quizzes SET nome = ?, descricao = ?, categoria = ?, preco = ? WHERE id = ?",
        (nome, descricao, categoria, preco, quiz_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM quizzes WHERE id = ?", (quiz_id,)).fetchone()
    conn.close()
    return jsonify({"quiz": quiz_json(row)})


@app.delete("/api/quizzes/<int:quiz_id>")
@requer_login(admin=True)
def excluir_quiz(quiz_id):
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM quizzes WHERE id = ?", (quiz_id,))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return erro("Não é possível excluir: há compras ou resultados deste quiz.", 409)
    conn.close()
    if cur.rowcount == 0:
        return erro("Quiz não encontrado.", 404)
    return jsonify({"ok": True})


@app.post("/api/quizzes/<int:quiz_id>/resultado")
@requer_login()
def responder_quiz(quiz_id):
    data = request.get_json(silent=True) or {}
    respostas = data.get("respostas")
    if not isinstance(respostas, list):
        return erro("Envie as respostas do quiz.", 400)
    conn = get_db()
    if conn.execute("SELECT 1 FROM quizzes WHERE id = ?", (quiz_id,)).fetchone() is None:
        conn.close()
        return erro("Quiz não encontrado.", 404)
    if not ja_possui(conn, g.usuario["id"], quiz_id=quiz_id):
        conn.close()
        return erro("Adquira o quiz antes de respondê-lo.", 403)
    perguntas = conn.execute("SELECT id FROM perguntas WHERE quiz_id = ? ORDER BY ordem, id", (quiz_id,)).fetchall()
    mapa = {}
    for item in respostas:
        if not isinstance(item, dict):
            conn.close()
            return erro("Resposta inválida.", 400)
        try:
            mapa[int(item["pergunta_id"])] = int(item["alternativa_id"])
        except (KeyError, TypeError, ValueError):
            conn.close()
            return erro("Resposta inválida.", 400)
    if set(mapa) != {row["id"] for row in perguntas}:
        conn.close()
        return erro("Responda todas as perguntas.", 400)
    acertos = 0
    for pergunta in perguntas:
        alternativa = conn.execute(
            "SELECT correta FROM alternativas WHERE id = ? AND pergunta_id = ?",
            (mapa[pergunta["id"]], pergunta["id"]),
        ).fetchone()
        if alternativa is None:
            conn.close()
            return erro("Alternativa inválida.", 400)
        acertos += int(alternativa["correta"])
    total = len(perguntas)
    conn.execute(
        "INSERT INTO resultados_quiz (usuario_id, quiz_id, pontuacao, total) VALUES (?, ?, ?, ?)",
        (g.usuario["id"], quiz_id, acertos, total),
    )
    conn.commit()
    conn.close()
    percentual = round(100 * acertos / total) if total else 0
    return jsonify(
        {
            "pontuacao": acertos,
            "total": total,
            "percentual": percentual,
            "aprovado": percentual >= 70,
        }
    )


def montar_carrinho(conn, usuario_id):
    itens = []
    rows = conn.execute(
        "SELECT * FROM carrinho WHERE usuario_id = ? ORDER BY id", (usuario_id,)
    ).fetchall()
    for row in rows:
        if row["curso_id"]:
            item = conn.execute("SELECT id, nome, preco FROM cursos WHERE id = ?", (row["curso_id"],)).fetchone()
            tipo = "curso"
        else:
            item = conn.execute("SELECT id, nome, preco FROM quizzes WHERE id = ?", (row["quiz_id"],)).fetchone()
            tipo = "quiz"
        if item is None:
            continue
        itens.append(
            {
                "id": row["id"],
                "tipo": tipo,
                "item_id": item["id"],
                "nome": item["nome"],
                "preco": item["preco"],
            }
        )
    return itens


@app.get("/api/carrinho")
@requer_login()
def ver_carrinho():
    conn = get_db()
    itens = montar_carrinho(conn, g.usuario["id"])
    conn.close()
    return jsonify({"itens": itens, "total": round(sum(item["preco"] for item in itens), 2)})


@app.post("/api/carrinho")
@requer_login()
def adicionar_carrinho():
    data = request.get_json(silent=True) or {}
    tipo = data.get("tipo")
    try:
        item_id = int(data.get("item_id"))
    except (TypeError, ValueError):
        return erro("Item inválido.", 400)
    if tipo not in ("curso", "quiz"):
        return erro("Tipo inválido.", 400)
    conn = get_db()
    if tipo == "curso":
        item = conn.execute("SELECT * FROM cursos WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            conn.close()
            return erro("Curso não encontrado.", 404)
        if item["preco"] == 0:
            conn.close()
            return erro("Curso gratuito: faça a inscrição, sem usar o carrinho.", 400)
        if ja_possui(conn, g.usuario["id"], curso_id=item_id):
            conn.close()
            return erro("Você já possui este curso.", 409)
        curso_id, quiz_id = item_id, None
    else:
        item = conn.execute("SELECT * FROM quizzes WHERE id = ?", (item_id,)).fetchone()
        if item is None:
            conn.close()
            return erro("Quiz não encontrado.", 404)
        if ja_possui(conn, g.usuario["id"], quiz_id=item_id):
            conn.close()
            return erro("Você já possui este quiz.", 409)
        curso_id, quiz_id = None, item_id
    try:
        conn.execute(
            "INSERT INTO carrinho (usuario_id, curso_id, quiz_id) VALUES (?, ?, ?)",
            (g.usuario["id"], curso_id, quiz_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return erro("Este item já está no carrinho.", 409)
    itens = montar_carrinho(conn, g.usuario["id"])
    conn.close()
    return jsonify({"itens": itens, "total": round(sum(i["preco"] for i in itens), 2)}), 201


@app.delete("/api/carrinho/<int:item_id>")
@requer_login()
def remover_carrinho(item_id):
    conn = get_db()
    cur = conn.execute(
        "DELETE FROM carrinho WHERE id = ? AND usuario_id = ?", (item_id, g.usuario["id"])
    )
    conn.commit()
    itens = montar_carrinho(conn, g.usuario["id"])
    conn.close()
    if cur.rowcount == 0:
        return erro("Item não encontrado no carrinho.", 404)
    return jsonify({"itens": itens, "total": round(sum(i["preco"] for i in itens), 2)})


@app.post("/api/carrinho/finalizar")
@requer_login()
def finalizar_compra():
    data = request.get_json(silent=True) or {}
    if data.get("confirmar") is not True:
        return erro("Confirme a compra simulada para finalizar.", 400)
    conn = get_db()
    itens = montar_carrinho(conn, g.usuario["id"])
    if not itens:
        conn.close()
        return erro("O carrinho está vazio.", 400)
    for item in itens:
        if item["tipo"] == "curso" and item["preco"] == 0:
            conn.close()
            return erro(f"'{item['nome']}' é gratuito. Remova do carrinho e faça a inscrição.", 400)
        possui = ja_possui(
            conn,
            g.usuario["id"],
            curso_id=item["item_id"] if item["tipo"] == "curso" else None,
            quiz_id=item["item_id"] if item["tipo"] == "quiz" else None,
        )
        if possui:
            conn.close()
            return erro(f"Você já possui '{item['nome']}'. Remova do carrinho.", 409)
    total = round(sum(item["preco"] for item in itens), 2)
    cur = conn.execute(
        "INSERT INTO compras (usuario_id, total) VALUES (?, ?)", (g.usuario["id"], total)
    )
    for item in itens:
        conn.execute(
            """INSERT INTO itens_compra (compra_id, curso_id, quiz_id, nome, preco)
               VALUES (?, ?, ?, ?, ?)""",
            (
                cur.lastrowid,
                item["item_id"] if item["tipo"] == "curso" else None,
                item["item_id"] if item["tipo"] == "quiz" else None,
                item["nome"],
                item["preco"],
            ),
        )
    conn.execute("DELETE FROM carrinho WHERE usuario_id = ?", (g.usuario["id"],))
    conn.commit()
    conn.close()
    return jsonify(
        {
            "compra_id": cur.lastrowid,
            "total": total,
            "mensagem": "Pagamento simulado concluído. Nenhum valor real foi cobrado.",
        }
    )


@app.post("/api/inscricoes")
@requer_login()
def inscrever():
    data = request.get_json(silent=True) or {}
    try:
        curso_id = int(data.get("curso_id"))
    except (TypeError, ValueError):
        return erro("Curso inválido.", 400)
    conn = get_db()
    curso = conn.execute("SELECT * FROM cursos WHERE id = ?", (curso_id,)).fetchone()
    if curso is None:
        conn.close()
        return erro("Curso não encontrado.", 404)
    if curso["preco"] != 0:
        conn.close()
        return erro("Este curso é pago. Adicione ao carrinho.", 400)
    try:
        conn.execute(
            "INSERT INTO inscricoes (usuario_id, curso_id) VALUES (?, ?)",
            (g.usuario["id"], curso_id),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        return erro("Você já está inscrito neste curso.", 409)
    conn.close()
    return jsonify({"ok": True, "mensagem": "Inscrição gratuita confirmada."}), 201


@app.get("/api/minha-area")
@requer_login()
def minha_area():
    uid = g.usuario["id"]
    conn = get_db()
    inscricoes = linhas(
        conn.execute(
            """SELECT i.id, i.criado_em, c.nome, c.categoria, c.modalidade
               FROM inscricoes i JOIN cursos c ON c.id = i.curso_id
               WHERE i.usuario_id = ? ORDER BY i.id DESC""",
            (uid,),
        )
    )
    compras = linhas(
        conn.execute(
            "SELECT id, total, criado_em FROM compras WHERE usuario_id = ? ORDER BY id DESC",
            (uid,),
        )
    )
    for compra in compras:
        compra["itens"] = linhas(
            conn.execute(
                """SELECT nome, preco, curso_id, quiz_id FROM itens_compra
                   WHERE compra_id = ? ORDER BY id""",
                (compra["id"],),
            )
        )
    quizzes = linhas(
        conn.execute(
            """SELECT q.id, q.nome, q.categoria, ic.preco, co.criado_em
               FROM itens_compra ic
               JOIN compras co ON co.id = ic.compra_id
               JOIN quizzes q ON q.id = ic.quiz_id
               WHERE co.usuario_id = ? AND ic.quiz_id IS NOT NULL
               ORDER BY co.id DESC""",
            (uid,),
        )
    )
    resultados = linhas(
        conn.execute(
            """SELECT r.pontuacao, r.total, r.criado_em, q.nome
               FROM resultados_quiz r JOIN quizzes q ON q.id = r.quiz_id
               WHERE r.usuario_id = ? ORDER BY r.id DESC""",
            (uid,),
        )
    )
    mensagens = linhas(
        conn.execute(
            "SELECT id, texto, resposta, criado_em, respondido_em FROM mensagens WHERE usuario_id = ? ORDER BY id DESC",
            (uid,),
        )
    )
    atividades = []
    for item in inscricoes:
        atividades.append({"data": item["criado_em"], "tipo": "Inscrição", "descricao": item["nome"]})
    for compra in compras:
        atividades.append({"data": compra["criado_em"], "tipo": "Compra", "descricao": f"Pedido {compra['id']}", "valor": compra["total"]})
    for item in resultados:
        atividades.append(
            {
                "data": item["criado_em"],
                "tipo": "Quiz",
                "descricao": f"{item['nome']} ({item['pontuacao']}/{item['total']})",
            }
        )
    for item in mensagens:
        atividades.append({"data": item["criado_em"], "tipo": "Atendimento", "descricao": "Mensagem enviada"})
    atividades.sort(key=lambda item: item["data"], reverse=True)
    conn.close()
    return jsonify(
        {
            "usuario": usuario_publico(g.usuario),
            "inscricoes": inscricoes,
            "compras": compras,
            "quizzes": quizzes,
            "resultados": resultados,
            "mensagens": mensagens,
            "atividades": atividades[:30],
        }
    )


@app.get("/api/mensagens")
@requer_login()
def listar_mensagens():
    conn = get_db()
    if g.usuario["admin"]:
        rows = conn.execute(
            """SELECT m.*, u.nome AS aluno, u.email
               FROM mensagens m JOIN usuarios u ON u.id = m.usuario_id
               ORDER BY m.id DESC"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT m.*, u.nome AS aluno, u.email
               FROM mensagens m JOIN usuarios u ON u.id = m.usuario_id
               WHERE m.usuario_id = ? ORDER BY m.id DESC""",
            (g.usuario["id"],),
        ).fetchall()
    conn.close()
    return jsonify({"mensagens": linhas(rows)})


@app.post("/api/mensagens")
@requer_login()
def enviar_mensagem():
    data = request.get_json(silent=True) or {}
    mensagem = texto(data, "texto", 5, 2000)
    if not mensagem:
        return erro("Escreva uma mensagem entre 5 e 2000 caracteres.", 400)
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO mensagens (usuario_id, texto) VALUES (?, ?)", (g.usuario["id"], mensagem)
    )
    conn.commit()
    conn.close()
    return jsonify({"id": cur.lastrowid}), 201


@app.post("/api/mensagens/<int:mensagem_id>/resposta")
@requer_login(admin=True)
def responder_mensagem(mensagem_id):
    data = request.get_json(silent=True) or {}
    resposta = texto(data, "resposta", 2, 2000)
    if not resposta:
        return erro("Escreva uma resposta entre 2 e 2000 caracteres.", 400)
    conn = get_db()
    cur = conn.execute(
        """UPDATE mensagens
           SET resposta = ?, respondido_em = datetime('now', 'localtime')
           WHERE id = ?""",
        (resposta, mensagem_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return erro("Mensagem não encontrada.", 404)
    return jsonify({"ok": True})


@app.get("/api/admin/resumo")
@requer_login(admin=True)
def resumo_admin():
    conn = get_db()
    dados = {
        "usuarios": conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0],
        "cursos": conn.execute("SELECT COUNT(*) FROM cursos").fetchone()[0],
        "quizzes": conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0],
        "compras": conn.execute("SELECT COUNT(*) FROM compras").fetchone()[0],
        "receita_simulada": conn.execute("SELECT COALESCE(SUM(total), 0) FROM compras").fetchone()[0],
        "inscricoes": conn.execute("SELECT COUNT(*) FROM inscricoes").fetchone()[0],
        "quizzes_vendidos": conn.execute("SELECT COUNT(*) FROM itens_compra WHERE quiz_id IS NOT NULL").fetchone()[0],
        "mensagens": conn.execute("SELECT COUNT(*) FROM mensagens").fetchone()[0],
        "atendimentos": conn.execute("SELECT COUNT(*) FROM mensagens WHERE resposta IS NOT NULL").fetchone()[0],
        "pendentes": conn.execute("SELECT COUNT(*) FROM mensagens WHERE resposta IS NULL").fetchone()[0],
    }
    conn.close()
    return jsonify(dados)


@app.get("/api/admin/usuarios")
@requer_login(admin=True)
def admin_usuarios():
    conn = get_db()
    rows = conn.execute(
        "SELECT id, nome, email, admin, criado_em FROM usuarios ORDER BY id"
    ).fetchall()
    conn.close()
    return jsonify({"usuarios": linhas(rows)})


@app.get("/api/admin/vendas")
@requer_login(admin=True)
def admin_vendas():
    conn = get_db()
    rows = conn.execute(
        """SELECT co.id AS compra_id, co.total, co.criado_em, u.nome AS aluno, u.email,
                  ic.nome AS item, ic.preco, ic.curso_id, ic.quiz_id
           FROM itens_compra ic
           JOIN compras co ON co.id = ic.compra_id
           JOIN usuarios u ON u.id = co.usuario_id
           ORDER BY co.id DESC, ic.id"""
    ).fetchall()
    conn.close()
    return jsonify({"vendas": linhas(rows)})


@app.get("/api/admin/inscricoes")
@requer_login(admin=True)
def admin_inscricoes():
    conn = get_db()
    rows = conn.execute(
        """SELECT i.id, i.criado_em, u.nome AS aluno, u.email, c.nome AS curso
           FROM inscricoes i
           JOIN usuarios u ON u.id = i.usuario_id
           JOIN cursos c ON c.id = i.curso_id
           ORDER BY i.id DESC"""
    ).fetchall()
    conn.close()
    return jsonify({"inscricoes": linhas(rows)})


@app.get("/api/painel")
def painel():
    conn = get_db()
    dados = {
        "cursos": conn.execute("SELECT COUNT(*) FROM cursos").fetchone()[0],
        "gratuitos": conn.execute("SELECT COUNT(*) FROM cursos WHERE preco = 0").fetchone()[0],
        "quizzes": conn.execute("SELECT COUNT(*) FROM quizzes").fetchone()[0],
    }
    conn.close()
    return jsonify(dados)


init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
