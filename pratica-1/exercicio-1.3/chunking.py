"""
chunking.py
===========
Estrategia de chunking ESTRUTURAL (header-aware) para documentos Markdown.

Justificativa (responde ao criterio de avaliacao do exercicio):
- Documentos .md tem estrutura semantica EXPLICITA: headers (#, ##), tabelas,
  listas e paragrafos. Essa estrutura ja marca, de graca, as unidades de
  significado do texto.
- Dividir por SECAO produz chunks que sao unidades coerentes e auto-contidas,
  o que melhora a precisao da recuperacao quando comparado a um corte cego por
  "N tokens fixos" (que separa cabecalho do conteudo e parte tabelas no meio).
- TABELAS sao tratadas como blocos ATOMICOS: nunca cortadas. Isso resolve por
  construcao o problema classico de "tabela cortada no meio".
- Secoes muito longas sao subdivididas respeitando limites de paragrafo, com
  OVERLAP, para nao perder contexto nas bordas entre dois chunks.
- O titulo da secao e PREFIXADO ao texto do chunk ([Secao: ...]). Isso enriquece
  o embedding com o topico da secao e melhora a recuperacao, alem de servir de
  fonte para citacao.

Em uma frase: recuperacao por relevancia funciona melhor quando cada chunk e uma
unidade de significado auto-suficiente, e o Markdown ja marca essas unidades.
"""
import re
from dataclasses import dataclass, field


@dataclass
class Chunk:
    text: str
    metadata: dict = field(default_factory=dict)


def _split_long_text(text: str, max_chars: int = 1200, overlap: int = 150) -> list[str]:
    """Subdivide um texto longo respeitando limites de paragrafo, com overlap."""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks, current = [], ""
    for p in paragraphs:
        if len(current) + len(p) + 2 <= max_chars:
            current += (p + "\n\n")
        else:
            if current:
                chunks.append(current.strip())
            # inicia novo chunk com overlap do final do anterior
            tail = current[-overlap:] if current else ""
            current = (tail + p + "\n\n")
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _is_table_line(line: str) -> bool:
    """Uma linha de tabela Markdown contem ao menos um pipe."""
    return "|" in line


def _segment_section_body(body: str) -> list[tuple[str, str]]:
    """
    Quebra o corpo de uma secao em blocos do tipo ('table', txt) ou ('text', txt),
    agrupando linhas CONSECUTIVAS de tabela num unico bloco atomico.
    Isso garante que a tabela NUNCA seja cortada no meio, mesmo quando comeca
    imediatamente apos o titulo (sem linha em branco antes).
    """
    lines = body.splitlines()
    blocks: list[tuple[str, list[str]]] = []
    mode = None  # "table" ou "text"

    for line in lines:
        kind = "table" if _is_table_line(line) else "text"
        # linhas em branco nao quebram a tabela em si, mas encerram um bloco de texto
        if kind != mode:
            blocks.append((kind, [line]))
            mode = kind
        else:
            blocks[-1][1].append(line)

    result = []
    for kind, ls in blocks:
        txt = "\n".join(ls).strip()
        if txt:
            result.append((kind, txt))
    return result


def chunk_markdown(text: str, source: str, max_chars: int = 1200) -> list[Chunk]:
    """
    Divide um documento Markdown em chunks por secao (header-aware),
    mantendo tabelas inteiras e anexando metadados de origem/secao.
    """
    # divide o doc em segmentos sempre que aparece um header (# ate ######)
    pattern = r"(?m)^(#{1,6}\s.*)$"
    parts = re.split(pattern, text)

    chunks: list[Chunk] = []

    # parts alterna entre [texto_antes, header, texto, header, texto, ...]
    segments = []
    if parts[0].strip():
        segments.append(("inicio do documento", parts[0]))
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        body = parts[i + 1] if i + 1 < len(parts) else ""
        segments.append((header.lstrip("# ").strip(), body))

    for header, body in segments:
        body = body.strip()
        if not body:
            continue

        for kind, block in _segment_section_body(body):
            if kind == "table":
                # tabela inteira vira um chunk atomico, com o header como contexto
                chunks.append(Chunk(
                    text=f"[Secao: {header}]\n{block}",
                    metadata={"source": source, "section": header, "type": "table"},
                ))
            else:
                for piece in _split_long_text(block, max_chars=max_chars):
                    chunks.append(Chunk(
                        text=f"[Secao: {header}]\n{piece}",
                        metadata={"source": source, "section": header, "type": "text"},
                    ))
    return chunks
