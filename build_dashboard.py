"""
Пересобирает dashboard.html, вставляя актуальный output/recommended_orders.json.
Запускать после каждого нового прогона main.py:

    python scripts/build_dashboard.py
"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_PATH = os.path.join(ROOT, "output", "recommended_orders.json")
HTML_PATH = os.path.join(ROOT, "dashboard.html")


def main():
    with open(JSON_PATH, encoding="utf-8") as f:
        data_json = f.read()
    with open(HTML_PATH, encoding="utf-8") as f:
        html = f.read()

    html = re.sub(
        r'(<script id="data" type="application/json">).*?(</script>)',
        lambda m: m.group(1) + data_json + m.group(2),
        html,
        flags=re.S,
    )

    with open(HTML_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"dashboard.html обновлён, встроено {len(data_json)} байт данных")


if __name__ == "__main__":
    main()
