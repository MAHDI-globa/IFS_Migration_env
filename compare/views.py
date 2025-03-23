import os
import json
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponseBadRequest
from django.core.cache import cache

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, 'data')

def scan_files():
    """
    Parcourt data/fic/ et met les résultats en cache pour 5min.
    """
    cache_key = "scan_files_result"
    result = cache.get(cache_key)
    if result:
        return result

    data_root = os.path.join(DATA_PATH, 'fic')
    result = {}
    all_envs = []

    if not os.path.exists(data_root):
        return {"__all_envs__": []}

    with os.scandir(data_root) as env_entries:
        for env_entry in env_entries:
            if env_entry.is_dir():
                env = env_entry.name
                all_envs.append(env)
                env_path = env_entry.path
                with os.scandir(env_path) as file_entries:
                    for file_entry in file_entries:
                        if file_entry.is_file() and file_entry.name.endswith('.json'):
                            file_path = file_entry.path
                            try:
                                with open(file_path, 'r', encoding='utf-8') as f:
                                    content = json.load(f)
                                    table_name = content.get("@odata.context", "").split("#")[-1]
                                    if table_name:
                                        result.setdefault(table_name, set()).add(env)
                            except Exception as e:
                                print(f"[Erreur JSON] {file_path} : {e}")

    result["__all_envs__"] = all_envs
    result = {k: list(v) if isinstance(v, set) else v for k, v in result.items()}
    cache.set(cache_key, result, 300)
    return result

def load_table_data(env, table_name):
    env_path = os.path.join(DATA_PATH, 'fic', env)
    if not os.path.exists(env_path):
        return []
    for file in os.listdir(env_path):
        if file.endswith('.json'):
            file_path = os.path.join(env_path, file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = json.load(f)
                    if content.get("@odata.context", "").endswith(f"#{table_name}"):
                        return content.get("value", [])
            except Exception as e:
                print(f"[Erreur lecture fichier] {file_path} : {e}")
    return []

def compare_rows(data1, data2):
    """
    Compare deux listes de dicts ligne par ligne.
    Retourne pour chaque ligne la liste des clés où val1 != val2.
    """
    differences_env1 = []
    differences_env2 = []
    max_len = max(len(data1), len(data2))
    for i in range(max_len):
        row1 = data1[i] if i < len(data1) else {}
        row2 = data2[i] if i < len(data2) else {}
        keys = set(row1.keys()) | set(row2.keys())
        diff_keys = []
        for key in keys:
            val1 = row1.get(key)
            val2 = row2.get(key)
            if isinstance(val1, list) and isinstance(val2, list):
                try:
                    if sorted(val1) != sorted(val2):
                        diff_keys.append(key)
                except:
                    if val1 != val2:
                        diff_keys.append(key)
            else:
                if val1 != val2:
                    diff_keys.append(key)
        differences_env1.append(diff_keys)
        differences_env2.append(diff_keys)
    return differences_env1, differences_env2

def index(request):
    tables = scan_files()
    selected_table = request.GET.get('table')
    env1 = request.GET.get('env1')
    env2 = request.GET.get('env2')

    data_env1 = []
    data_env2 = []
    diffs_env1 = []
    diffs_env2 = []

    environments = tables.get("__all_envs__", [])

    if selected_table in tables:
        valid_envs = tables[selected_table]
    else:
        valid_envs = []

    if env1 and env2 and env1 != env2 and selected_table:
        if env1 in valid_envs:
            data_env1 = load_table_data(env1, selected_table) or []
        if env2 in valid_envs or env2 in environments:
            data_env2 = load_table_data(env2, selected_table) or []
        diffs_env1, diffs_env2 = compare_rows(data_env1, data_env2)

    context = {
        'tables': tables,
        'selected_table': selected_table,
        'environments': environments,
        'env1': env1,
        'env2': env2,
        'data_env1': data_env1,
        'data_env2': data_env2,
        'diffs_env1': diffs_env1,
        'diffs_env2': diffs_env2,
    }
    return render(request, 'compare/index.html', context)

@csrf_exempt
def promote(request):
    """
    Promotion : récupère 'selected_data', parse en dict,
    ajoute '__migrated__' et écrase la table dans l'env cible.
    """
    if request.method != "POST":
        return HttpResponseBadRequest("Méthode non autorisée")

    table = request.POST.get("table")
    source_env = request.POST.get("source_env")
    target_env = request.POST.get("target_env")
    selected_data_str = request.POST.get("selected_data", "[]")

    if not table or not source_env or not target_env:
        return HttpResponseBadRequest("Champs manquants")

    print(f"📤 Promotion de données de {source_env} vers {target_env} pour la table {table}")

    try:
        raw_list = json.loads(selected_data_str)
        data_to_write = []
        for item in raw_list:
            if isinstance(item, str):
                item = json.loads(item)
            item["__migrated__"] = True
            data_to_write.append(item)
    except Exception as e:
        print(f"❌ Erreur parsing JSON : {e}")
        return HttpResponseBadRequest("Erreur de format JSON")

    target_path = os.path.join(DATA_PATH, "fic", target_env)
    os.makedirs(target_path, exist_ok=True)
    output_file = os.path.join(target_path, f"{table}.json")

    payload = {
        "@odata.context": f"https://example.com/odata/$metadata#{table}",
        "value": data_to_write
    }

    try:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"✅ Données écrasées dans {output_file}")
    except Exception as e:
        print(f"❌ Erreur lors de la promotion : {e}")
        return HttpResponseBadRequest("Erreur lors de l’écriture du fichier")

    return redirect(f"/?table={table}&env1={source_env}&env2={target_env}")
