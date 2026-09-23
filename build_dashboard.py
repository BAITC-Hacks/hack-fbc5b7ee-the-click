"""
Пересобирает dashboard.html, вставляя актуальный recommended_orders.json.
Запускать из корня репозитория после обновления данных:

    python build_dashboard.py
"""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
JSON_PATH = ROOT / "recommended_orders.json"
HTML_PATH = ROOT / "dashboard.html"


def main():
    with JSON_PATH.open(encoding="utf-8") as f:
        data_json = f.read()
    with HTML_PATH.open(encoding="utf-8") as f:
        html = f.read()

    html = re.sub(
        r'(<script id="data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + data_json + m.group(2),
        html,
        flags=re.S,
    )

    with HTML_PATH.open("w", encoding="utf-8") as f:
        f.write(html)
    print(f"dashboard.html обновлён, встроено {len(data_json)} байт данных")


if __name__ == "__main__":
    main()
