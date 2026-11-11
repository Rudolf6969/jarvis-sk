# -*- coding: utf-8 -*-
"""Prekladac medzi hey-claude a Microsoft Edge TTS.

Instaluje sa ako edge-piper.exe, takze hey-claude ho vola presne
rovnako ako piper.exe - bez obalok a bez problemov s uvodzovkami.

hey-claude vola Piper takto:
    piper.exe --model <cesta> --output_raw     (text na vstupe, PCM na vystupe)

Tento skript sa tvari presne tak, ale namiesto Pipera pouzije
Edge TTS (slovensky muzsky hlas Lukas). Ked net nejde alebo sa
cokolvek pokazi, prepne sa na lokalny Piper s hlasom lili, aby
Jarvis nikdy neonemel.

Do kodu projektu sa nesiaha, takze to prezije aj git pull.
"""
import io
import json
import os
import subprocess
import sys
import time

# Na Windows musi byt stdout v binarnom rezime, inak by sa \n menilo
# na \r\n a zvuk by sa pokazil.
try:
    import msvcrt
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "edge-tts-log.txt")


def log(msg):
    """Loguje do suboru. Na stdout nesmie ist nic okrem zvuku."""
    try:
        line = "%s  %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
        # drz log maly
        if os.path.exists(LOG) and os.path.getsize(LOG) > 512 * 1024:
            with open(LOG, "w", encoding="utf-8") as f:
                f.write(line)
        else:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
    print(msg, file=sys.stderr)


def parse_args(argv):
    """Z argumentov nas zaujima len --model."""
    model = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("--model", "-m") and i + 1 < len(argv):
            model = argv[i + 1]
            i += 2
            continue
        i += 1
    return model


def load_cfg(model_path):
    meta = (model_path or "") + ".json"
    if not os.path.isfile(meta):
        raise RuntimeError("chyba konfiguracny subor %s" % meta)
    with open(meta, encoding="utf-8") as f:
        return json.load(f)


def mp3_to_pcm16(mp3_bytes, want_rate):
    """MP3 -> mono PCM int16 na pozadovanej frekvencii. Pouziva pyav."""
    import av
    import numpy as np

    container = av.open(io.BytesIO(mp3_bytes))
    resampler = av.AudioResampler(format="s16", layout="mono", rate=want_rate)
    chunks = []
    for frame in container.decode(audio=0):
        for out in resampler.resample(frame):
            chunks.append(out.to_ndarray().reshape(-1))
    # dopln zvysok z resampleru
    for out in resampler.resample(None):
        chunks.append(out.to_ndarray().reshape(-1))
    container.close()
    if not chunks:
        return b""
    return np.concatenate(chunks).astype(np.int16).tobytes()


def synth_edge(text, edge_cfg, want_rate):
    """Hlavna cesta: Microsoft Edge TTS."""
    import asyncio
    import edge_tts

    voice = edge_cfg.get("voice", "sk-SK-LukasNeural")
    rate = edge_cfg.get("rate", "+0%")
    volume = edge_cfg.get("volume", "+0%")
    pitch = edge_cfg.get("pitch", "+0Hz")
    timeout = float(edge_cfg.get("timeout_s", 15))

    async def go():
        comm = edge_tts.Communicate(text, voice, rate=rate, volume=volume, pitch=pitch)
        buf = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                buf.extend(chunk["data"])
        return bytes(buf)

    # wait_for musi bezat vnutri event loopu, preto obalka
    async def go_with_timeout():
        return await asyncio.wait_for(go(), timeout)

    mp3 = asyncio.run(go_with_timeout())
    if not mp3:
        raise RuntimeError("Edge TTS nevratil zvuk")
    return mp3_to_pcm16(mp3, want_rate)


def synth_piper(text, fb_cfg, want_rate):
    """Zaloha: lokalny Piper (hlas lili). Bezi aj bez internetu."""
    import numpy as np

    exe = fb_cfg.get("piper_exe")
    model = fb_cfg.get("piper_model")
    src_rate = int(fb_cfg.get("sample_rate", 22050))
    if not exe or not os.path.isfile(exe):
        raise RuntimeError("zalozny piper.exe nenajdeny: %s" % exe)
    if not model or not os.path.isfile(model):
        raise RuntimeError("zalozny model nenajdeny: %s" % model)

    r = subprocess.run(
        [exe, "--model", model, "--output_raw"],
        input=text.encode("utf-8"),
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if not r.stdout:
        raise RuntimeError("zalozny piper nevratil zvuk: %s" % (r.stderr[:200] if r.stderr else "bez chyby"))

    pcm = np.frombuffer(r.stdout, dtype=np.int16)
    if src_rate != want_rate and len(pcm) > 1:
        # jednoducha linearna interpolacia - na zalozny hlas staci
        n_out = int(round(len(pcm) * want_rate / float(src_rate)))
        x_old = np.arange(len(pcm), dtype=np.float64)
        x_new = np.linspace(0, len(pcm) - 1, n_out)
        pcm = np.interp(x_new, x_old, pcm.astype(np.float64)).astype(np.int16)
    return pcm.astype(np.int16).tobytes()


def main():
    t0 = time.time()
    model = parse_args(sys.argv[1:])

    raw = sys.stdin.buffer.read()
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return 0

    try:
        cfg = load_cfg(model)
    except Exception as e:
        log("CHYBA configu: %s" % e)
        return 1

    want_rate = int(cfg.get("audio", {}).get("sample_rate", 24000))
    edge_cfg = cfg.get("edge", {})
    fb_cfg = cfg.get("fallback", {})
    prefer = cfg.get("prefer", "edge")

    pcm = b""
    used = "?"

    if prefer == "edge":
        try:
            pcm = synth_edge(text, edge_cfg, want_rate)
            used = "edge"
        except Exception as e:
            log("Edge TTS zlyhal (%s) -> prepinam na lokalny hlas" % str(e)[:160])

    if not pcm:
        try:
            pcm = synth_piper(text, fb_cfg, want_rate)
            used = "piper-zaloha"
        except Exception as e:
            log("aj zaloha zlyhala: %s" % str(e)[:200])
            return 1

    sys.stdout.buffer.write(pcm)
    sys.stdout.buffer.flush()

    ms = int((time.time() - t0) * 1000)
    secs = len(pcm) / 2.0 / want_rate
    log("ok [%s] %d ms, %.1fs zvuku, %d znakov" % (used, ms, secs, len(text)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
