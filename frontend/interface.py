import os
from datetime import datetime

import requests
import streamlit as st

API = os.environ.get("LOCADORA_API", "http://127.0.0.1:5000")
MODALIDADES = ["Online", "Presencial", "Híbrido"]

st.set_page_config(page_title="Locadora de Cursos", page_icon="🎓", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f4f8fc; }
    section[data-testid="stSidebar"] { background: #0b2545; }
    section[data-testid="stSidebar"] * { color: #e8f2fc; }
    section[data-testid="stSidebar"] input { color: #0b2545; }
    .hero {
        background: linear-gradient(135deg, #0b2545 0%, #1d4e89 100%);
        color: white; border-radius: 16px; padding: 28px 32px; margin-bottom: 16px;
    }
    .hero h1 { color: white; margin: 0 0 6px 0; font-size: 2rem; }
    .hero p { color: #d6e8fa; margin: 0; }
    .selo {
        display: inline-block; background: #d7ebff; color: #0b2545;
        border-radius: 999px; padding: 2px 10px; font-size: 0.8rem; font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def moeda(valor):
    texto = f"{float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def data_br(valor):
    if not valor:
        return "—"
    try:
        return datetime.strptime(valor, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return valor


def api(method, path, payload=None, auth=True, silent=False):
    headers = {}
    if auth and st.session_state.get("token"):
        headers["Authorization"] = f"Bearer {st.session_state.token}"
    try:
        resposta = requests.request(method, f"{API}{path}", json=payload, headers=headers, timeout=15)
    except requests.RequestException:
        if not silent:
            st.error("Sem conexão com o backend. Inicie o Flask em http://127.0.0.1:5000.")
        return None
    try:
        dados = resposta.json()
    except ValueError:
        if not silent:
            st.error("O backend retornou uma resposta inválida.")
        return None
    if resposta.status_code >= 400:
        if not silent:
            st.error(dados.get("erro", "Não foi possível concluir a operação."))
        if resposta.status_code == 401 and auth:
            st.session_state.token = None
            st.session_state.usuario = None
        return None
    return dados


def ir_para(pagina):
    st.session_state.pagina_pendente = pagina
    st.rerun()


def entrar(dados):
    st.session_state.token = dados["token"]
    st.session_state.usuario = dados["usuario"]
    ir_para("Início")


def usuario():
    return st.session_state.get("usuario")


def pagina_inicio():
    st.markdown(
        """
        <div class="hero">
            <h1>Locadora de Cursos</h1>
            <p>Cursos, quizzes e atendimento em um só lugar. O pagamento é simulado.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    painel = api("GET", "/api/painel", auth=False) or {}
    colunas = st.columns(3)
    colunas[0].metric("Cursos", painel.get("cursos", "—"))
    colunas[1].metric("Gratuitos", painel.get("gratuitos", "—"))
    colunas[2].metric("Quizzes", painel.get("quizzes", "—"))
    if usuario():
        area = api("GET", "/api/minha-area", silent=True) or {}
        extras = st.columns(3)
        extras[0].metric("Inscrições", len(area.get("inscricoes", [])))
        extras[1].metric("Compras", len(area.get("compras", [])))
        extras[2].metric("Quizzes adquiridos", len(area.get("quizzes", [])))
    else:
        st.info("Entre ou crie uma conta para se inscrever, comprar e fazer quizzes.")
    st.subheader("Como funciona")
    um, dois, tres = st.columns(3)
    um.write("**1. Escolha** um curso gratuito ou pago no catálogo.")
    dois.write("**2. Confirme** a inscrição ou a compra simulada no carrinho.")
    tres.write("**3. Estude** com os quizzes e fale com o atendimento quando precisar.")


def acao_curso(curso):
    if not usuario():
        if st.button("Entrar para continuar", key=f"entrar_curso_{curso['id']}"):
            ir_para("Entrar")
        return
    if curso.get("possui"):
        st.success("Já está na sua área")
        return
    if curso["gratuito"]:
        if st.button("Inscrever-se grátis", key=f"ins_{curso['id']}"):
            if api("POST", "/api/inscricoes", {"curso_id": curso["id"]}):
                st.success("Inscrição confirmada.")
                st.rerun()
    elif st.button("Adicionar ao carrinho", key=f"add_curso_{curso['id']}"):
        if api("POST", "/api/carrinho", {"tipo": "curso", "item_id": curso["id"]}):
            st.success("Curso adicionado ao carrinho.")


def pagina_catalogo():
    st.title("Catálogo")
    dados = api("GET", "/api/cursos") or {"cursos": [], "categorias": []}
    busca, categoria = st.columns([2, 1])
    termo = busca.text_input("Pesquisar por nome ou categoria")
    opcoes = ["Todas"] + dados["categorias"]
    escolhida = categoria.selectbox("Categoria", opcoes)
    params = []
    if termo.strip():
        params.append(f"q={requests.utils.quote(termo.strip())}")
    if escolhida != "Todas":
        params.append(f"categoria={requests.utils.quote(escolhida)}")
    if params:
        dados = api("GET", "/api/cursos?" + "&".join(params)) or dados
    cursos = dados["cursos"]
    if not cursos:
        st.info("Nenhum curso encontrado.")
        return
    colunas = st.columns(3)
    for indice, curso in enumerate(cursos):
        with colunas[indice % 3]:
            with st.container(border=True):
                if curso.get("imagem"):
                    st.image(curso["imagem"], use_container_width=True)
                st.markdown(f"**{curso['nome']}**")
                st.caption(f"{curso['categoria']} · {curso['modalidade']}")
                st.write(curso["descricao"])
                if curso["gratuito"]:
                    st.markdown('<span class="selo">Gratuito</span>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span class="selo">{moeda(curso["preco"])}</span>', unsafe_allow_html=True)
                st.write("")
                acao_curso(curso)


def pagina_quizzes():
    st.title("Quizzes")
    st.caption("A correção fica no servidor. Você vê a nota ao finalizar.")
    dados = api("GET", "/api/quizzes") or {"quizzes": [], "categorias": []}
    termo = st.text_input("Pesquisar quiz por nome ou categoria")
    if termo.strip():
        dados = api("GET", f"/api/quizzes?q={requests.utils.quote(termo.strip())}") or dados
    quizzes = dados["quizzes"]
    if not quizzes:
        st.info("Nenhum quiz encontrado.")
        return
    nomes = {f"{item['nome']} — {moeda(item['preco']) if item['preco'] else 'Gratuito'}": item for item in quizzes}
    foco = st.session_state.pop("quiz_foco", None)
    rotulos = list(nomes)
    indice = 0
    if foco:
        for i, item in enumerate(quizzes):
            if item["id"] == foco:
                indice = i
    escolha = st.selectbox("Quiz", rotulos, index=indice)
    quiz = nomes[escolha]
    with st.container(border=True):
        st.markdown(f"**{quiz['nome']}**")
        st.caption(quiz["categoria"])
        st.write(quiz["descricao"])
        if quiz["gratuito"]:
            st.markdown('<span class="selo">Gratuito</span>', unsafe_allow_html=True)
        else:
            st.markdown(f'<span class="selo">{moeda(quiz["preco"])}</span>', unsafe_allow_html=True)
        if not usuario():
            if st.button("Entrar para continuar"):
                ir_para("Entrar")
            return
        if not quiz.get("possui"):
            if st.button("Adicionar ao carrinho"):
                if api("POST", "/api/carrinho", {"tipo": "quiz", "item_id": quiz["id"]}):
                    st.success("Quiz adicionado ao carrinho.")
            return
    detalhe = api("GET", f"/api/quizzes/{quiz['id']}")
    perguntas = (detalhe or {}).get("quiz", {}).get("perguntas") or []
    if not perguntas:
        st.warning("Este quiz ainda não tem perguntas.")
        return
    with st.form(f"quiz_{quiz['id']}"):
        respostas = []
        for pergunta in perguntas:
            opcoes = {alt["texto"]: alt["id"] for alt in pergunta["alternativas"]}
            marcada = st.radio(pergunta["enunciado"], list(opcoes), key=f"p{pergunta['id']}")
            respostas.append({"pergunta_id": pergunta["id"], "alternativa_id": opcoes[marcada]})
        enviar = st.form_submit_button("Finalizar quiz")
    if enviar:
        resultado = api("POST", f"/api/quizzes/{quiz['id']}/resultado", {"respostas": respostas})
        if resultado:
            texto = f"{resultado['pontuacao']} de {resultado['total']} ({resultado['percentual']}%)"
            if resultado["aprovado"]:
                st.success(f"Resultado: {texto}. Aprovado — 70% ou mais.")
            else:
                st.warning(f"Resultado: {texto}. Abaixo de 70%. Você pode tentar de novo.")


def pagina_carrinho():
    st.title("Carrinho")
    st.caption("O pagamento é simulado. Nenhum valor real é cobrado.")
    dados = api("GET", "/api/carrinho") or {"itens": [], "total": 0}
    if not dados["itens"]:
        st.info("Seu carrinho está vazio.")
        return
    for item in dados["itens"]:
        esquerda, direita = st.columns([4, 1])
        tipo = "Curso" if item["tipo"] == "curso" else "Quiz"
        esquerda.write(f"**{item['nome']}** · {tipo} · {moeda(item['preco'])}")
        if direita.button("Remover", key=f"rm_{item['id']}"):
            if api("DELETE", f"/api/carrinho/{item['id']}"):
                st.rerun()
    st.subheader(f"Total: {moeda(dados['total'])}")
    confirmar = st.checkbox("Confirmo esta compra simulada")
    if st.button("Finalizar compra"):
        resultado = api("POST", "/api/carrinho/finalizar", {"confirmar": confirmar})
        if resultado:
            st.success(resultado["mensagem"])
            st.rerun()


def pagina_atendimento():
    st.title("Atendimento")
    st.write("Envie uma mensagem. A resposta aparece aqui quando o atendente registrar.")
    with st.form("nova_mensagem"):
        texto = st.text_area("Mensagem")
        if st.form_submit_button("Enviar") and api("POST", "/api/mensagens", {"texto": texto}):
            st.success("Mensagem registrada.")
            st.rerun()
    mensagens = (api("GET", "/api/mensagens") or {}).get("mensagens", [])
    if not mensagens:
        st.info("Você ainda não enviou mensagens.")
    for mensagem in mensagens:
        with st.container(border=True):
            st.caption(data_br(mensagem["criado_em"]))
            st.write(mensagem["texto"])
            if mensagem.get("resposta"):
                st.info(f"Atendente · {data_br(mensagem.get('respondido_em'))}\n\n{mensagem['resposta']}")
            else:
                st.warning("Aguardando resposta")


def tabela(registros):
    if registros:
        st.dataframe(registros, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhum registro.")


def pagina_minha_area():
    st.title("Minha área")
    area = api("GET", "/api/minha-area")
    if not area:
        return
    pessoa = area["usuario"]
    st.write(f"**{pessoa['nome']}**")
    st.caption(f"{pessoa['email']} · conta desde {data_br(pessoa['criado_em'])}")
    abas = st.tabs(["Cursos", "Compras", "Quizzes", "Atividades"])
    with abas[0]:
        st.subheader("Inscrições gratuitas")
        tabela(
            [
                {"Curso": item["nome"], "Categoria": item["categoria"], "Modalidade": item["modalidade"], "Data": data_br(item["criado_em"])}
                for item in area["inscricoes"]
            ]
        )
        pagos = []
        for compra in area["compras"]:
            for item in compra["itens"]:
                if item["curso_id"]:
                    pagos.append({"Curso": item["nome"], "Pago": moeda(item["preco"]), "Pedido": compra["id"], "Data": data_br(compra["criado_em"])})
        st.subheader("Cursos adquiridos")
        tabela(pagos)
    with abas[1]:
        linhas = []
        for compra in area["compras"]:
            nomes = ", ".join(item["nome"] for item in compra["itens"])
            linhas.append({"Pedido": compra["id"], "Itens": nomes, "Total": moeda(compra["total"]), "Data": data_br(compra["criado_em"])})
        tabela(linhas)
    with abas[2]:
        for item in area["quizzes"]:
            esquerda, direita = st.columns([4, 1])
            esquerda.write(f"**{item['nome']}** · {item['categoria']} · {moeda(item['preco'])}")
            if direita.button("Abrir", key=f"abrir_quiz_{item['id']}_{item['criado_em']}"):
                st.session_state.quiz_foco = item["id"]
                ir_para("Quizzes")
        if not area["quizzes"]:
            st.info("Nenhum quiz adquirido.")
        if area["resultados"]:
            st.subheader("Resultados")
            tabela(
                [
                    {"Quiz": item["nome"], "Nota": f"{item['pontuacao']}/{item['total']}", "Data": data_br(item["criado_em"])}
                    for item in area["resultados"]
                ]
            )
    with abas[3]:
        tabela(
            [
                {
                    "Data": data_br(item["data"]),
                    "Tipo": item["tipo"],
                    "Descrição": item["descricao"],
                    "Valor": moeda(item["valor"]) if "valor" in item else "—",
                }
                for item in area["atividades"]
            ]
        )


def formulario_curso(prefixo, curso=None):
    nome = st.text_input("Nome", value="" if curso is None else curso["nome"], key=f"{prefixo}_nome")
    descricao = st.text_area("Descrição", value="" if curso is None else curso["descricao"], key=f"{prefixo}_desc")
    categoria = st.text_input("Categoria", value="" if curso is None else curso["categoria"], key=f"{prefixo}_cat")
    imagem = st.text_input("Imagem (URL opcional)", value="" if curso is None else (curso.get("imagem") or ""), key=f"{prefixo}_img")
    preco = st.number_input("Preço", min_value=0.0, step=1.0, value=0.0 if curso is None else float(curso["preco"]), key=f"{prefixo}_preco")
    modalidade = st.selectbox(
        "Modalidade",
        MODALIDADES,
        index=0 if curso is None else MODALIDADES.index(curso["modalidade"]),
        key=f"{prefixo}_mod",
    )
    return {
        "nome": nome,
        "descricao": descricao,
        "categoria": categoria,
        "imagem": imagem,
        "preco": preco,
        "modalidade": modalidade,
    }


def pagina_admin():
    st.title("Administração")
    resumo = api("GET", "/api/admin/resumo") or {}
    indicadores = st.columns(5)
    for coluna, rotulo, chave in zip(
        indicadores,
        ["Usuários", "Cursos", "Vendas", "Inscrições", "Pendências"],
        ["usuarios", "cursos", "compras", "inscricoes", "pendentes"],
    ):
        coluna.metric(rotulo, resumo.get(chave, "—"))
    st.caption(
        f"Receita simulada: {moeda(resumo.get('receita_simulada', 0))} · "
        f"Quizzes: {resumo.get('quizzes', 0)} · adquiridos: {resumo.get('quizzes_vendidos', 0)} · "
        f"mensagens: {resumo.get('mensagens', 0)} · respondidas: {resumo.get('atendimentos', 0)}"
    )
    abas = st.tabs(["Usuários", "Cursos", "Vendas", "Inscrições", "Quizzes", "Atendimento"])
    with abas[0]:
        usuarios = (api("GET", "/api/admin/usuarios") or {}).get("usuarios", [])
        tabela(
            [
                {"Nome": item["nome"], "E-mail": item["email"], "Perfil": "Admin" if item["admin"] else "Aluno", "Desde": data_br(item["criado_em"])}
                for item in usuarios
            ]
        )
    with abas[1]:
        st.subheader("Novo curso")
        with st.form("novo_curso"):
            payload = formulario_curso("novo")
            if st.form_submit_button("Cadastrar curso") and api("POST", "/api/cursos", payload):
                st.success("Curso cadastrado.")
                st.rerun()
        cursos = (api("GET", "/api/cursos") or {}).get("cursos", [])
        if cursos:
            st.subheader("Editar curso")
            escolhido = st.selectbox("Curso", cursos, format_func=lambda item: item["nome"])
            with st.form(f"editar_curso_{escolhido['id']}"):
                payload = formulario_curso(f"edit_{escolhido['id']}", escolhido)
                salvar = st.form_submit_button("Salvar alterações")
            if salvar and api("PUT", f"/api/cursos/{escolhido['id']}", payload):
                st.success("Curso atualizado.")
                st.rerun()
            if st.button("Excluir curso", key=f"del_curso_{escolhido['id']}"):
                if api("DELETE", f"/api/cursos/{escolhido['id']}"):
                    st.success("Curso excluído.")
                    st.rerun()
    with abas[2]:
        vendas = (api("GET", "/api/admin/vendas") or {}).get("vendas", [])
        tabela(
            [
                {
                    "Pedido": item["compra_id"],
                    "Aluno": item["aluno"],
                    "E-mail": item["email"],
                    "Item": item["item"],
                    "Tipo": "Curso" if item["curso_id"] else "Quiz",
                    "Preço": moeda(item["preco"]),
                    "Total do pedido": moeda(item["total"]),
                    "Data": data_br(item["criado_em"]),
                }
                for item in vendas
            ]
        )
    with abas[3]:
        inscricoes = (api("GET", "/api/admin/inscricoes") or {}).get("inscricoes", [])
        tabela(
            [
                {"Aluno": item["aluno"], "E-mail": item["email"], "Curso": item["curso"], "Data": data_br(item["criado_em"])}
                for item in inscricoes
            ]
        )
    with abas[4]:
        st.subheader("Novo quiz")
        with st.form("novo_quiz"):
            nome = st.text_input("Nome do quiz")
            descricao = st.text_area("Descrição do quiz")
            categoria = st.text_input("Categoria do quiz")
            preco = st.number_input("Preço do quiz", min_value=0.0, step=1.0)
            perguntas = []
            for numero in (1, 2):
                st.markdown(f"**Pergunta {numero}**")
                enunciado = st.text_input("Enunciado", key=f"enun_{numero}")
                correta = st.radio("Alternativa correta", [1, 2, 3], horizontal=True, key=f"certa_{numero}")
                alternativas = []
                for opcao in (1, 2, 3):
                    alternativas.append(
                        {"texto": st.text_input(f"Alternativa {opcao}", key=f"alt_{numero}_{opcao}"), "correta": opcao == correta}
                    )
                perguntas.append({"enunciado": enunciado, "alternativas": alternativas})
            if st.form_submit_button("Cadastrar quiz"):
                payload = {"nome": nome, "descricao": descricao, "categoria": categoria, "preco": preco, "perguntas": perguntas}
                if api("POST", "/api/quizzes", payload):
                    st.success("Quiz cadastrado.")
                    st.rerun()
        quizzes = (api("GET", "/api/quizzes") or {}).get("quizzes", [])
        if quizzes:
            st.subheader("Editar quiz")
            quiz = st.selectbox("Quiz", quizzes, format_func=lambda item: item["nome"])
            with st.form(f"editar_quiz_{quiz['id']}"):
                nome = st.text_input("Nome", value=quiz["nome"])
                descricao = st.text_area("Descrição", value=quiz["descricao"])
                categoria = st.text_input("Categoria", value=quiz["categoria"])
                preco = st.number_input("Preço", min_value=0.0, step=1.0, value=float(quiz["preco"]))
                salvar = st.form_submit_button("Salvar quiz")
            if salvar and api("PUT", f"/api/quizzes/{quiz['id']}", {"nome": nome, "descricao": descricao, "categoria": categoria, "preco": preco}):
                st.success("Quiz atualizado.")
                st.rerun()
            st.caption("As perguntas são definidas no cadastro. Excluir só é permitido sem vendas nem resultados.")
            if st.button("Excluir quiz"):
                if api("DELETE", f"/api/quizzes/{quiz['id']}"):
                    st.success("Quiz excluído.")
                    st.rerun()
    with abas[5]:
        mensagens = (api("GET", "/api/mensagens") or {}).get("mensagens", [])
        if not mensagens:
            st.info("Nenhuma mensagem recebida.")
        for mensagem in mensagens:
            with st.container(border=True):
                st.write(f"**{mensagem['aluno']}** · {mensagem['email']}")
                st.caption(data_br(mensagem["criado_em"]))
                st.write(mensagem["texto"])
                if mensagem.get("resposta"):
                    st.success(f"Respondida em {data_br(mensagem['respondido_em'])}: {mensagem['resposta']}")
                else:
                    resposta = st.text_input("Resposta", key=f"resp_{mensagem['id']}")
                    if st.button("Responder", key=f"btn_resp_{mensagem['id']}"):
                        if api("POST", f"/api/mensagens/{mensagem['id']}/resposta", {"resposta": resposta}):
                            st.success("Resposta registrada.")
                            st.rerun()


def pagina_entrar():
    st.title("Acesso")
    entrar_col, criar_col = st.columns(2)
    with entrar_col:
        st.subheader("Entrar")
        with st.form("login"):
            email = st.text_input("E-mail")
            senha = st.text_input("Senha", type="password")
            if st.form_submit_button("Entrar"):
                dados = api("POST", "/api/auth/login", {"email": email, "senha": senha}, auth=False)
                if dados:
                    entrar(dados)
    with criar_col:
        st.subheader("Criar conta")
        with st.form("registro"):
            nome = st.text_input("Nome")
            email = st.text_input("E-mail", key="reg_email")
            senha = st.text_input("Senha", type="password", key="reg_senha")
            confirmar = st.text_input("Confirmar senha", type="password")
            if st.form_submit_button("Cadastrar"):
                if senha != confirmar:
                    st.error("As senhas não coincidem.")
                else:
                    dados = api("POST", "/api/auth/registro", {"nome": nome, "email": email, "senha": senha}, auth=False)
                    if dados:
                        entrar(dados)
    st.caption("Conta de demonstração do administrador: admin@locadora.local / admin123")


def main():
    st.session_state.setdefault("token", None)
    st.session_state.setdefault("usuario", None)
    if st.session_state.token and not st.session_state.usuario:
        dados = api("GET", "/api/auth/eu", silent=True)
        if dados:
            st.session_state.usuario = dados["usuario"]
    pessoa = usuario()
    opcoes = ["Início", "Catálogo", "Quizzes"]
    if pessoa:
        opcoes += ["Carrinho", "Atendimento", "Minha área"]
        if pessoa.get("admin"):
            opcoes.append("Administração")
    else:
        opcoes.append("Entrar")
    destino = st.session_state.pop("pagina_pendente", None)
    if destino in opcoes:
        st.session_state.menu_radio = destino
    if st.session_state.get("menu_radio") not in opcoes:
        st.session_state.menu_radio = opcoes[0]
    with st.sidebar:
        st.markdown("### Locadora de Cursos")
        if pessoa:
            st.write(pessoa["nome"])
            st.caption("Administrador" if pessoa.get("admin") else pessoa["email"])
        else:
            st.caption("Você não está conectado")
        menu = st.radio("Navegação", opcoes, key="menu_radio")
        if pessoa and st.button("Sair"):
            api("POST", "/api/auth/logout", silent=True)
            st.session_state.token = None
            st.session_state.usuario = None
            ir_para("Início")
    paginas = {
        "Início": pagina_inicio,
        "Catálogo": pagina_catalogo,
        "Quizzes": pagina_quizzes,
        "Carrinho": pagina_carrinho,
        "Atendimento": pagina_atendimento,
        "Minha área": pagina_minha_area,
        "Administração": pagina_admin,
        "Entrar": pagina_entrar,
    }
    paginas[menu]()


main()
