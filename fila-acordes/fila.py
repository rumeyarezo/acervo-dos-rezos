"""
Acervo dos Rezos — programa da fila de acordes.

Roda no computador do Caio. A cada poucos segundos:
  1. avisa o Supabase que está ligado (o app mostra "computador ligado");
  2. pega o pedido mais antigo da fila;
  3. baixa o áudio da pasta privada, converte com o ffmpeg e analisa com o
     chordotomy (lv-chordia + Beat This!);
  4. grava a progressão no pedido e APAGA o áudio do Supabase e do computador.

Configuração: arquivo config.env nesta mesma pasta (veja config.exemplo.env).
Usa só a biblioteca padrão do Python, além do chordotomy instalado pelo instalar.bat.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSAO = "1.0.0"
PASTA = Path(__file__).resolve().parent
BUCKET = "chord-audio"
DURACAO_MAXIMA_S = 12 * 60          # músicas de até 12 minutos
TEMPO_LIMITE_ANALISE_S = 20 * 60    # desiste de uma análise travada depois de 20 min
INTERVALO_SINAL_S = 30              # de quanto em quanto tempo avisa que está ligado


# ---------------------------------------------------------------- utilidades
def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    linha = f"[{datetime.now().strftime('%d/%m %H:%M:%S')}] {msg}"
    print(linha, flush=True)
    try:
        with open(PASTA / "fila.log", "a", encoding="utf-8") as f:
            f.write(linha + "\n")
    except OSError:
        pass


def ler_config() -> dict:
    caminho = Path(os.environ.get("FILA_CONFIG", PASTA / "config.env"))
    if not caminho.exists():
        raise SystemExit(
            f"Não achei {caminho}. Copie config.exemplo.env para config.env e preencha."
        )
    cfg = {}
    for linha in caminho.read_text(encoding="utf-8-sig").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        k, v = linha.split("=", 1)
        cfg[k.strip()] = v.strip().strip('"').strip("'")
    url = cfg.get("SUPABASE_URL", "").rstrip("/")
    chave = cfg.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not chave or "COLE_AQUI" in chave:
        raise SystemExit("Preencha SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY no config.env.")
    return {
        "url": url,
        "chave": chave,
        "intervalo": max(3, int(cfg.get("INTERVALO_SEGUNDOS", "10") or 10)),
        "motor": cfg.get("MOTOR", "auto") or "auto",
        "nome": cfg.get("NOME_COMPUTADOR", "principal") or "principal",
    }


def manter_acordado() -> None:
    """No Windows, pede para o computador não dormir enquanto a fila roda."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        log("Pedi ao Windows para não suspender o computador enquanto a fila estiver aberta.")
    except Exception as e:  # noqa: BLE001
        log(f"Não consegui impedir a suspensão do Windows: {e}")


# ---------------------------------------------------------------- Supabase
class Supabase:
    def __init__(self, url: str, chave: str):
        self.url = url
        self.chave = chave

    def _req(self, metodo, caminho, corpo=None, cabecalhos=None, bruto=False, timeout=60):
        h = {"apikey": self.chave}
        # A chave antiga (service_role) é um JWT e vai também no Authorization.
        # As chaves novas ("sb_secret_...") não são JWT: só no apikey.
        if not self.chave.startswith("sb_"):
            h["Authorization"] = f"Bearer {self.chave}"
        dados = None
        if corpo is not None:
            if isinstance(corpo, (bytes, bytearray)):
                dados = bytes(corpo)
            else:
                dados = json.dumps(corpo).encode("utf-8")
                h["Content-Type"] = "application/json"
        h.update(cabecalhos or {})
        req = urllib.request.Request(self.url + caminho, data=dados, method=metodo, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            conteudo = resp.read()
        if bruto:
            return conteudo
        return json.loads(conteudo) if conteudo else None

    # tabela de pedidos
    def sinal_de_vida(self, nome: str, extra: dict) -> None:
        self._req(
            "POST",
            "/rest/v1/cifrario_worker_status?on_conflict=id",
            [{"id": nome, "last_seen": agora_iso(), "info": extra}],
            {"Prefer": "resolution=merge-duplicates,return=minimal"},
        )

    def devolver_travados(self) -> int:
        """Pedidos que ficaram 'processing' (ex.: computador desligou no meio) voltam pra fila."""
        r = self._req(
            "PATCH",
            "/rest/v1/cifrario_chord_jobs?status=eq.processing",
            {"status": "pending", "started_at": None},
            {"Prefer": "return=representation"},
        )
        return len(r or [])

    def proximo_pedido(self):
        r = self._req(
            "GET",
            "/rest/v1/cifrario_chord_jobs?status=eq.pending&order=created_at.asc&limit=1"
            "&select=id,user_id,file_name,audio_path,created_at",
        )
        return r[0] if r else None

    def reservar(self, job_id: str) -> bool:
        r = self._req(
            "PATCH",
            f"/rest/v1/cifrario_chord_jobs?id=eq.{job_id}&status=eq.pending",
            {"status": "processing", "started_at": agora_iso()},
            {"Prefer": "return=representation"},
        )
        return bool(r)

    def concluir(self, job_id: str, resultado: dict) -> None:
        self._req(
            "PATCH",
            f"/rest/v1/cifrario_chord_jobs?id=eq.{job_id}",
            {"status": "done", "result": resultado, "error": None,
             "finished_at": agora_iso(), "audio_path": None},
            {"Prefer": "return=minimal"},
        )

    def falhar(self, job_id: str, mensagem: str) -> None:
        self._req(
            "PATCH",
            f"/rest/v1/cifrario_chord_jobs?id=eq.{job_id}",
            {"status": "error", "error": mensagem[:500], "finished_at": agora_iso(),
             "audio_path": None},
            {"Prefer": "return=minimal"},
        )

    # pasta privada de áudios
    def baixar_audio(self, caminho: str) -> bytes:
        alvo = urllib.parse.quote(caminho, safe="/")
        ultimo = None
        for prefixo in ("/storage/v1/object/authenticated/", "/storage/v1/object/"):
            try:
                return self._req("GET", f"{prefixo}{BUCKET}/{alvo}", bruto=True, timeout=180)
            except urllib.error.HTTPError as e:
                ultimo = e
                if e.code not in (400, 404):
                    raise
        raise ultimo  # type: ignore[misc]

    def apagar_audio(self, caminho: str) -> None:
        self._req("DELETE", f"/storage/v1/object/{BUCKET}", {"prefixes": [caminho]})


# ---------------------------------------------------------------- análise
def achar_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SystemExit("ffmpeg não encontrado. Rode o instalar.bat de novo ou instale o ffmpeg.")
    return exe


def duracao_em_segundos(ffmpeg: str, arquivo: Path) -> float | None:
    ffprobe = shutil.which("ffprobe") or str(Path(ffmpeg).with_name(
        "ffprobe.exe" if os.name == "nt" else "ffprobe"))
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(arquivo)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except Exception:  # noqa: BLE001
        return None


class ErroAmigavel(Exception):
    """Erro com mensagem que pode ser mostrada para quem enviou o áudio."""


def converter(ffmpeg: str, entrada: Path, saida: Path) -> None:
    r = subprocess.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
         "-i", str(entrada), "-vn", "-ac", "2", "-ar", "44100", str(saida)],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0 or not saida.exists() or saida.stat().st_size < 1000:
        raise ErroAmigavel("Não consegui ler esse arquivo de áudio. Tente enviar em MP3 ou WAV.")


def rodar_chordotomy(wav: Path, saida: Path, motor: str) -> None:
    cmd = [sys.executable, "-c", "from chordotomy.cli import app; app()",
           "analyze", str(wav), "-o", str(saida), "--force"]
    if motor in ("model", "dsp"):
        cmd += ["--engine", motor]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=TEMPO_LIMITE_ANALISE_S)
    if r.returncode != 0 or not saida.exists():
        detalhe = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["sem detalhes"]
        log(f"chordotomy falhou: {detalhe[0]}")
        raise ErroAmigavel("A análise falhou neste áudio. Tente outro arquivo ou um trecho menor.")


def bpm_das_batidas(batidas: list) -> float | None:
    if not batidas or len(batidas) < 8:
        return None
    intervalos = sorted(b - a for a, b in zip(batidas, batidas[1:]) if b > a)
    if not intervalos:
        return None
    meio = intervalos[len(intervalos) // 2]
    return round(60.0 / meio, 1) if meio > 0 else None


def resumir(tl: dict, nome_arquivo: str) -> dict:
    """Guarda só o que o app usa (o JSON completo do chordotomy é bem maior)."""
    tom = tl.get("global_key") or {}
    segs = []
    for s in tl.get("segments", []):
        if not s.get("chord") or s["chord"] in ("N", "X"):
            continue
        segs.append({
            "start": round(float(s.get("start_time", 0)), 3),
            "end": round(float(s.get("end_time", 0)), 3),
            "chord": s["chord"],
            "candidates": (s.get("candidates") or [])[:3],
            "bass": s.get("bass"),
            "inversion": s.get("inversion"),
        })
    gerador = tl.get("generator") or {}
    motor = gerador.get("engine") or {}
    nome_motor = (f"{motor.get('name', '')} {motor.get('version', '')}".strip()
                  if isinstance(motor, dict) else str(motor))
    return {
        "format": "acervo-progressao-1",
        "engine": f"chordotomy {gerador.get('version', '')} / {nome_motor}".strip(" /"),
        "file_name": nome_arquivo,
        "duration": (tl.get("source") or {}).get("duration"),
        "key": tom.get("label"),
        "key_candidates": tom.get("candidates") or [],
        "bpm": bpm_das_batidas(tl.get("beats") or []),
        "segments": segs,
    }


def analisar_pedido(sb: Supabase, ffmpeg: str, motor: str, pedido: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="acervo-fila-") as tmp:
        tmp = Path(tmp)
        ext = Path(pedido["file_name"]).suffix.lower()[:6] or ".audio"
        original = tmp / f"original{ext}"
        wav = tmp / "audio.wav"
        saida = tmp / "audio.chords.json"
        try:
            original.write_bytes(sb.baixar_audio(pedido["audio_path"]))
        except urllib.error.HTTPError as e:
            if e.code in (400, 404):
                raise ErroAmigavel("O áudio não chegou ao servidor. Envie de novo.") from e
            raise
        converter(ffmpeg, original, wav)
        dur = duracao_em_segundos(ffmpeg, wav)
        if dur is not None and dur > DURACAO_MAXIMA_S:
            raise ErroAmigavel("Áudio muito longo: envie músicas de até 12 minutos.")
        inicio = time.time()
        rodar_chordotomy(wav, saida, motor)
        tl = json.loads(saida.read_text(encoding="utf-8"))
        res = resumir(tl, pedido["file_name"])
        res["seconds"] = round(time.time() - inicio, 1)
        if not res["segments"]:
            raise ErroAmigavel("Não encontrei acordes nesse áudio.")
        return res
    # a pasta temporária (com o áudio) é apagada ao sair do "with"


# ---------------------------------------------------------------- laço principal
def processar_um(sb: Supabase, ffmpeg: str, motor: str) -> bool:
    pedido = sb.proximo_pedido()
    if not pedido:
        return False
    if not sb.reservar(pedido["id"]):
        return True  # outro computador pegou; tenta o próximo
    log(f"Analisando '{pedido['file_name']}' (pedido {pedido['id'][:8]})...")
    try:
        res = analisar_pedido(sb, ffmpeg, motor, pedido)
        sb.concluir(pedido["id"], res)
        log(f"Pronto: {len(res['segments'])} acordes, tom {res.get('key')}, {res['seconds']} s.")
    except ErroAmigavel as e:
        sb.falhar(pedido["id"], str(e))
        log(f"Não deu: {e}")
    except Exception as e:  # noqa: BLE001
        log("Erro inesperado:\n" + traceback.format_exc())
        sb.falhar(pedido["id"], "Erro inesperado no computador da fila. Tente de novo mais tarde.")
    finally:
        if pedido.get("audio_path"):
            try:
                sb.apagar_audio(pedido["audio_path"])
            except Exception as e:  # noqa: BLE001
                log(f"Aviso: não consegui apagar o áudio do Supabase ({e}).")
    return True


def main() -> None:
    cfg = ler_config()
    sb = Supabase(cfg["url"], cfg["chave"])
    ffmpeg = achar_ffmpeg()
    manter_acordado()
    log(f"Fila de acordes do Acervo dos Rezos v{VERSAO} — motor: {cfg['motor']}")
    log("Deixe esta janela aberta. Para parar, feche a janela ou aperte Ctrl+C.")
    uma_vez = "--uma-vez" in sys.argv
    ultimo_sinal = 0.0
    devolvidos_iniciais = False
    while True:
        try:
            if time.time() - ultimo_sinal > INTERVALO_SINAL_S:
                sb.sinal_de_vida(cfg["nome"], {"versao": VERSAO, "motor": cfg["motor"]})
                ultimo_sinal = time.time()
            if not devolvidos_iniciais:
                n = sb.devolver_travados()
                if n:
                    log(f"{n} pedido(s) que ficaram pela metade voltaram para a fila.")
                devolvidos_iniciais = True
            trabalhou = processar_um(sb, ffmpeg, cfg["motor"])
            if uma_vez and not trabalhou:
                log("Fila vazia. Encerrando (--uma-vez).")
                return
            if not trabalhou:
                time.sleep(cfg["intervalo"])
        except KeyboardInterrupt:
            log("Fila encerrada.")
            return
        except urllib.error.URLError as e:
            log(f"Sem conexão com o Supabase ({getattr(e, 'reason', e)}). Tentando de novo em 30 s.")
            time.sleep(30)
        except Exception:  # noqa: BLE001
            log("Erro no laço da fila:\n" + traceback.format_exc())
            time.sleep(30)


if __name__ == "__main__":
    main()
