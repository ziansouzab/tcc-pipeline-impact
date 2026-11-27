import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import yaml


PASTA = Path(__file__).resolve().parent


def ler_json(caminho):
    return json.loads(caminho.read_text(encoding="utf-8"))


def gravar_json(caminho, dados):
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def hash_arquivo(caminho):
    return sha256(caminho.read_bytes()).hexdigest()


def chave(dados):
    return json.dumps(dados, ensure_ascii=False, sort_keys=True)


def diferencas(esperados, observados):
    contagem_esperada = Counter()
    contagem_observada = Counter()
    for registro in esperados:
        contagem_esperada[chave(registro)] += 1
    for registro in observados:
        contagem_observada[chave(registro)] += 1
    ausentes = []
    inesperados = []
    for item in (contagem_esperada - contagem_observada).elements():
        ausentes.append(json.loads(item))
    for item in (contagem_observada - contagem_esperada).elements():
        inesperados.append(json.loads(item))
    return {"ausentes": ausentes, "inesperados": inesperados}


def nome_contexto(contexto, contextos):
    if contexto is None:
        return None
    for nome, valor in contextos.items():
        if contexto == valor:
            return nome
    return contexto


def alerta(registro, contextos):
    return {
        "regra": registro["rule"],
        "local": registro["location"],
        "contexto": nome_contexto(registro["context"], contextos),
    }


def alertas_considerados(snapshot, regras, contextos):
    resultado = []
    for achado in snapshot["findings"]:
        if achado["kind"] == "warning" and achado["rule"] in regras:
            resultado.append(alerta(achado, contextos))
    return resultado


def ler_vinculos(relatorio, contextos):
    registros = []
    referencias_invalidas = []
    diagnosticos = {}
    for achado in relatorio["after"]["findings"]:
        diagnosticos[achado["id"]] = achado
    for item in relatorio["impact_links"]:
        diagnostico = diagnosticos.get(item["finding_id"])
        indice = item["change_index"]
        if diagnostico is None or not 0 <= indice < len(relatorio["changes"]):
            referencias_invalidas.append(item)
            continue
        mudanca = relatorio["changes"][indice]
        evidencia = item["evidence"]
        referencia_valida = diagnostico["location"] == item["location"]
        if item["type"] == "upload_condition_changed":
            posicao = item.get("step_change_index", -1)
            if not 0 <= posicao < len(relatorio["step_changes"]):
                referencias_invalidas.append(item)
                continue
            etapa = relatorio["step_changes"][posicao]
            referencia_valida = (
                referencia_valida
                and etapa["job"] == mudanca["job"]
                and etapa["after_step"] == evidencia["producer_step_after"]
                and "if" in etapa["fields"]
                and item.get("context") == diagnostico["context"]
            )
        else:
            produtor, dependente = evidencia["removed_edge"]
            referencia_valida = (
                referencia_valida
                and mudanca["rule"] == "R01_DEPENDENCY_CHANGE"
                and mudanca["job"] == dependente
                and produtor in mudanca["before"]
                and produtor not in mudanca["after"]
            )
        if not referencia_valida:
            referencias_invalidas.append(item)
        registros.append({
            "tipo": item["type"],
            "alerta": alerta(diagnostico, contextos),
            "mudanca_job": mudanca["job"],
            "evidencia": evidencia,
        })
    return registros, referencias_invalidas


def conferir_cobertura(relatorio, especificacoes):
    resultados = []
    por_analise = {}
    for registro in relatorio["after"]["coverage"]:
        por_analise[registro["analysis"]] = registro
    for criterio in especificacoes:
        registro = por_analise.get(criterio["analise"], {})
        detalhes = []
        for detalhe in registro.get("details", []):
            if detalhe.get("location") == criterio["local"] and detalhe["result"] == criterio["detalhe"]:
                detalhes.append(detalhe)
        resultados.append({
            "criterio": criterio,
            "status_observado": registro.get("status"),
            "detalhes_observados": detalhes,
            "atendeu": registro.get("status") == criterio["status"] and bool(detalhes),
        })
    return resultados


def examinar(caso, manifesto, relatorio):
    regras = manifesto["regras_verificadas"]
    contextos = manifesto["contextos"]
    antes = alertas_considerados(relatorio["before"], regras, contextos)
    depois = alertas_considerados(relatorio["after"], regras, contextos)
    vinculos, referencias_invalidas = ler_vinculos(relatorio, contextos)
    comparacao_antes = diferencas(caso["alertas_antes"], antes)
    comparacao_depois = diferencas(caso["alertas_depois"], depois)
    comparacao_vinculos = diferencas(caso["vinculos"], vinculos)
    cobertura = conferir_cobertura(relatorio, caso["cobertura"])
    cobertura_confere = True
    for item in cobertura:
        if not item["atendeu"]:
            cobertura_confere = False
    conforme = (
        not comparacao_antes["ausentes"] and not comparacao_antes["inesperados"]
        and not comparacao_depois["ausentes"] and not comparacao_depois["inesperados"]
        and not comparacao_vinculos["ausentes"] and not comparacao_vinculos["inesperados"]
        and not referencias_invalidas and cobertura_confere
    )
    return {
        "id": caso["id"], "grupo": caso["grupo"], "alteracao": caso["alteracao"],
        "alertas_antes": antes, "alertas_depois": depois, "vinculos": vinculos,
        "mudancas_reportadas": len(relatorio["changes"]),
        "mudancas_nos_steps": len(relatorio["step_changes"]),
        "diferencas_alertas_antes": comparacao_antes,
        "diferencas_alertas_depois": comparacao_depois,
        "diferencas_vinculos": comparacao_vinculos,
        "referencias_invalidas": referencias_invalidas,
        "cobertura_conferida": cobertura,
        "conforme_protocolo": conforme,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("fonte_zip", type=Path, help="Arquivo fonte gerado por git archive na revisão do protocolo")
    parser.add_argument("destino", type=Path, help="Pasta nova para resultados")
    args = parser.parse_args()
    from zipfile import ZipFile
    from tempfile import TemporaryDirectory

    arquivo_expectativas = PASTA / "expectativas.json"
    arquivo_contextos = PASTA / "contextos.json"
    manifesto = ler_json(arquivo_expectativas)
    if hash_arquivo(arquivo_contextos) != manifesto["contextos_sha256"]:
        raise SystemExit("Os contextos divergem do protocolo.")
    for caso in manifesto["casos"]:
        pasta_caso = PASTA / "casos" / caso["id"]
        for nome, digest in caso["sha256"].items():
            if hash_arquivo(pasta_caso / nome) != digest:
                raise SystemExit(f"Entrada alterada: {caso['id']} / {nome}")

    inicio = datetime.now(timezone.utc).isoformat()
    destino = args.destino.resolve()
    resultados = []
    with ZipFile(args.fonte_zip) as fonte, TemporaryDirectory(prefix="pipeline-impact-avaliacao-") as tmp:
        revisao = fonte.comment.decode("ascii").strip()
        if revisao != manifesto["commit"]:
            raise SystemExit(f"A revisão do arquivo fonte diverge do protocolo: {revisao}")
        fonte.extractall(tmp)
        ambiente = os.environ.copy()
        ambiente["PYTHONPATH"] = str(Path(tmp) / "src")
        ambiente["PYTHONIOENCODING"] = "utf-8"
        ambiente["PYTHONUTF8"] = "1"
        destino.mkdir(parents=True, exist_ok=False)
        for caso in manifesto["casos"]:
            identificador = caso["id"]
            pasta_caso = PASTA / "casos" / identificador
            saida = destino / identificador
            comando = [
                sys.executable, "-B", "-m", "pipeline_impact",
                "--before", str(pasta_caso / "before.yml"),
                "--after", str(pasta_caso / "after.yml"),
                "--contexts", str(arquivo_contextos),
                "--output", str(saida),
            ]
            processo = subprocess.run(comando, cwd=tmp, env=ambiente, capture_output=True, encoding="utf-8", timeout=30)
            saida.mkdir(exist_ok=True)
            gravar_json(saida / "execucao.json", {
                "comando": comando, "codigo_de_saida": processo.returncode,
                "stdout": processo.stdout, "stderr": processo.stderr,
            })
            if processo.returncode != 0:
                raise SystemExit(f"Falha na comparação de {identificador}. Consulte o registro da execução.")
            relatorio = ler_json(saida / "report.json")
            if relatorio["tool_version"] != manifesto["versao"] or relatorio["schema_version"] != manifesto["esquema"]:
                raise SystemExit(f"Versão do resultado diverge do protocolo em {identificador}.")
            resultado = examinar(caso, manifesto, relatorio)
            resultados.append(resultado)
            print(identificador, "confere" if resultado["conforme_protocolo"] else "divergência",
                  len(resultado["alertas_antes"]), len(resultado["alertas_depois"]), len(resultado["vinculos"]))
    resumo = {
        "inicio_utc": inicio, "fim_utc": datetime.now(timezone.utc).isoformat(),
        "commit": revisao, "versao": manifesto["versao"], "esquema": manifesto["esquema"],
        "python": platform.python_version(), "pyyaml": yaml.__version__, "sistema": platform.platform(),
        "sha256_expectativas": hash_arquivo(arquivo_expectativas),
        "sha256_arquivo_fonte": hash_arquivo(args.fonte_zip),
        "casos": resultados,
    }
    gravar_json(destino / "resultado.json", resumo)


if __name__ == "__main__":
    main()
