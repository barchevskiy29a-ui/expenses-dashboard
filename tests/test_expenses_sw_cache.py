"""Service worker обязан обновлять закэшированную оболочку при изменениях.

Инцидент 06.10.2026: кнопки +/− «не работали» ни на мобилке, ни на ПК —
код был исправен (доказано воспроизведением в браузере: 640→800→1000→800),
но на устройствах лежал старый app.js из SW-кэша expenses-shell-v1 рядом
со свежим index.html. Версионирование имени кэша + чистка старых кэшей
в activate гарантирует: новая версия SW = свежие файлы оболочки.
"""

import re
from pathlib import Path

SW = Path("mobile-expenses/sw.js")


def _sw():
    return SW.read_text(encoding="utf-8")


def test_sw_cache_name_is_versioned():
    """Имя кэша содержит версию: иначе клиенты никогда не обновят оболочку."""
    js = _sw()
    m = re.search(r"const CACHE='([^']+)'", js)
    assert m, "CACHE constant not found"
    assert re.fullmatch(r"[a-z-]+-shell-v\d+", m.group(1)), m.group(1)


def test_sw_activate_purges_old_caches():
    """activate удаляет чужие кэши, иначе старые app.js копятся и всплывают."""
    js = _sw()
    body_start = js.find("addEventListener('activate'")
    assert body_start != -1
    body = js[body_start:]
    assert "caches.keys()" in body
    assert "caches.delete" in body


def test_sw_precaches_app_shell():
    """Оболочка (включая app.js) предзагружается целиком — без рассинхрона версий."""
    js = _sw()
    for name in ("./index.html", "./styles.css", "./app.js"):
        assert f"'{name}'" in js, name


def test_sw_js_parses():
    """sw.js обязан быть валидным JS после правок."""
    import shutil
    import subprocess

    if shutil.which("node") is None:
        raise RuntimeError("NEEDS_CONTEXT: node not found in PATH")
    proc = subprocess.run(
        ["node", "--check", str(SW)], capture_output=True, text=True, encoding="utf-8", timeout=30
    )
    assert proc.returncode == 0, proc.stderr
