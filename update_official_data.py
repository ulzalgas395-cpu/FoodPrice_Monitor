from pathlib import Path
import subprocess
import sys

BASE_DIR = Path(__file__).resolve().parent


def run_script(filename):
    script_path = BASE_DIR / filename

    print("\n" + "=" * 55)
    print("Орындалып жатыр:", filename)
    print("=" * 55)

    result = subprocess.run([sys.executable, str(script_path)], cwd=BASE_DIR)

    if result.returncode != 0:
        print("\n❌ Қате пайда болды:", filename)
        return False

    return True


def main():
    print("FOODPRICE MONITOR")
    print("Ресми деректерді жаңарту басталды...\n")

    # 1. Деректерді сайттан жүктеу скрипті
    if not run_script("fetch_official_data.py"):
        return

    # 2. Дерекқорға импорттау скрипті
    # (Ескерту: файлыңыздың атауы 'import_official_data.py' немесе 'import_official.py' екенін тексеріңіз)
    if not run_script("import_official_data.py"):
        return

    print("\n" + "=" * 55)
    print("🎉 РЕСМИ ДЕРЕКТЕР СӘТТІ ЖАҢАРТЫЛДЫ!")
    print("=" * 55)


if __name__ == "__main__":
    main()